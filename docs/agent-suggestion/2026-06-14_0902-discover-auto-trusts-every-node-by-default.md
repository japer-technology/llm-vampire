# Discovery silently elevates every reachable LM Studio endpoint to `trusted=True` by default — `trusted = not request.trusted_only` inverts and auto-grants the project's only security/trust boundary, and the same expression makes `trusted_only=True` discovery unable to ever find a new node

- **Severity:** High — discovery is the *bulk* node-onboarding path, and on the default request (`trusted_only=False`) it marks **every** node it can reach as `trusted=True` with no owner approval and no fingerprint, even though manual registration (`POST /vampire/v1/nodes`) and the `Node` model both default trust to `False`. The `trusted_only` routing strategy and the `trusted_only` route constraint then treat these auto-trusted, unverified hosts as owner-vetted, so a request that explicitly asked to be confined to trusted nodes is routed to whatever answered a `/v1/models` probe on the LAN. Not Critical only because it requires the discovery endpoint to be reachable (authenticated once `VAMPIRE_AUTH_TOKEN` is set, suggestion `0548`, taken), but on the still-supported unauthenticated default it is a one-call trust bypass.
- **Category:** security (trust-boundary bypass / privilege auto-grant) — with a secondary api-correctness dimension: the same expression makes `trusted_only=True` discovery logically dead (it can never return a freshly discovered node).

## Summary

In `discover_nodes`, a newly discovered node is constructed with `trusted=not request.trusted_only` (`cluster.py:313`). The default `DiscoveryRequest.trusted_only` is `False` (`models.py:118`), so `not False == True`: **every** node discovered by the default request — every static target, every `base_urls` entry, every LAN-scan hit — is registered as `trusted=True`. This contradicts the `Node.trusted` default of `False` (`models.py:81`) and the manual-registration path, which never auto-trusts. The `trusted_only` router strategy (`router.py:50-51`) and the `trusted_only` route constraint documented in DESIGN-API.md §16/§24 then select these auto-trusted hosts as if they were owner-verified. The inverse case is also broken: with `trusted_only=True` the new node is built `trusted=False` and then immediately discarded by the post-filter (`refreshed.trusted or not request.trusted_only` → `False or False`), so `trusted_only=True` discovery can *never* surface a node it didn't already know.

## Location

- `src/vampire/cluster.py:307-324` — `_probe`: node construction and the trust-gated return filter.
- `src/vampire/cluster.py:313` — `trusted=not request.trusted_only` (the inverted auto-grant).
- `src/vampire/cluster.py:322` — `if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):` (the filter that makes `trusted_only=True` discovery dead).
- `src/vampire/models.py:81` — `trusted: bool = False` (the honored default that discovery violates).
- `src/vampire/models.py:118` — `trusted_only: bool = False` (so the default request hits the auto-trust branch).
- `src/vampire/router.py:50-51` — `if strategy == "trusted_only": candidates = [t for t in candidates if self._node(t).trusted]` (the consumer that trusts the flag).
- `src/vampire/api/control.py:60-70` — `register_node`: contrasting manual path that does **not** auto-trust (stores the posted `Node`, whose `trusted` defaults to `False`).

## Evidence

The offending construction and filter:

```python
# src/vampire/cluster.py:307-324
async def _probe(base_url: str) -> Node | None:
    current = registry.get(_node_id_for_url(base_url))
    node = current or Node(
        id=_node_id_for_url(base_url),
        host=urlparse(base_url).hostname,
        lmstudio_base_url=base_url,
        trusted=not request.trusted_only,          # <-- line 313: inverted auto-grant
    )
    if current is None:
        registry.add(node)
    async with semaphore:
        if client is not None:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
        else:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
    if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
        return refreshed                            # <-- line 322-323: trust filter
    return None
```

Step-by-step, default request (`trusted_only=False`, the value the CLI and the `POST /vampire/v1/discover` body default to — `models.py:114-119`, `cli.py:275` `--trusted-only` is `store_true` so omitted ⇒ `False`):

1. `current` is `None` for a never-seen host, so a fresh `Node` is built.
2. `trusted = not request.trusted_only = not False = True`. The node is **trusted** before a single byte of verification.
3. `registry.add(node)` persists it process-wide.
4. After a successful `/v1/models` probe `refreshed.status == "online"`, and `refreshed.trusted or not request.trusted_only = True or True` ⇒ returned and now a permanent trusted member of the registry.

Contrast the manual path, which honors the model default:

```python
# src/vampire/api/control.py:60-70
@router.post("/nodes")
async def register_node(node: Node, request: Request) -> dict[str, Any]:
    registry.add(node)                              # node.trusted defaults to False (models.py:81)
    refreshed = await refresh_node(node, client=_request_http_client(request))
    return {"id": refreshed.id, "status": "registered", "trusted": refreshed.trusted}
```

And the consumer that relies on the flag actually meaning "owner-verified":

```python
# src/vampire/router.py:50-51
if strategy == "trusted_only":
    candidates = [target for target in candidates if self._node(target).trusted]
```

The contract being violated is **"`trusted` is an owner-granted property, default-deny."** It is honored by `Node` (`models.py:81`, default `False`), by `register_node` (`control.py:68`, no elevation), and is the explicit semantics of DESIGN-API.md §13 where trust is established via a `trust` object (`"mode": "manual"`, `"fingerprint": "sha256:..."`, DESIGN-API.md:822-825). Discovery is the one place that breaks it, and it breaks it for the *default* request.

The inverse failure (dead `trusted_only=True` discovery): with `trusted_only=True`, step 2 yields `trusted=False`; step 4's filter is `False or not True = False or False = False`, so the freshly discovered online node is dropped. `trusted_only=True` can therefore only ever return a node that was *already* in the registry as trusted — it cannot discover one. So neither value of the flag does anything sensible: `False` over-trusts everything, `True` discovers nothing new.

## Impact

- **Trust bypass / blast radius:** Any operator (or, on the unauthenticated default deployment, any LAN client able to POST `/vampire/v1/discover`) can promote arbitrary reachable LM Studio endpoints to `trusted=True` in one call. Those nodes are then eligible under the `trusted_only` routing strategy and the `trusted_only` route constraint, which exist precisely to confine sensitive traffic to vetted hardware. A user who configures `vampire:secure → trusted_only` believing only their fingerprinted office box qualifies will silently have prompts routed to any machine that answered a discovery probe (including, combined with the still-open `base_urls`/SSRF gap in suggestion `0828`, a caller-chosen URL).
- **Observable symptom:** After `vampire discover` (no flags), `GET /vampire/v1/nodes` shows every freshly found node with `"trusted": true`. The `register_node` API for the *same* host shows `"trusted": false`. Two onboarding paths, opposite trust outcomes — a confusing and dangerous inconsistency.
- **Functional dead-end:** `vampire discover --trusted-only` returns an empty `nodes` list even when trusted nodes are reachable but not yet registered, so operators cannot use the flag for its apparent purpose ("only bring in already-trusted nodes").
- **When it triggers:** Every discovery call. The default path over-trusts; the opt-in path under-returns.

## Fix

Discovery must never *grant* trust. A freshly discovered node should default to **untrusted** (`trusted=False`), matching `Node`'s default and the manual path. The `trusted_only` request flag should mean "only *return* nodes that are already trusted" — a read/filter predicate, never a writer of the trust bit. Preserve the trust state of a node that already exists in the registry (don't downgrade an owner-trusted node on re-probe).

```python
# BEFORE (src/vampire/cluster.py:307-324)
async def _probe(base_url: str) -> Node | None:
    current = registry.get(_node_id_for_url(base_url))
    node = current or Node(
        id=_node_id_for_url(base_url),
        host=urlparse(base_url).hostname,
        lmstudio_base_url=base_url,
        trusted=not request.trusted_only,
    )
    if current is None:
        registry.add(node)
    async with semaphore:
        if client is not None:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
        else:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
    if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
        return refreshed
    return None

# AFTER
async def _probe(base_url: str) -> Node | None:
    current = registry.get(_node_id_for_url(base_url))
    # Newly discovered nodes are UNTRUSTED by default, matching Node.trusted=False
    # and POST /vampire/v1/nodes. Trust is owner-granted (DESIGN-API.md §13), never
    # auto-assigned by reachability. An existing node keeps its established trust.
    node = current or Node(
        id=_node_id_for_url(base_url),
        host=urlparse(base_url).hostname,
        lmstudio_base_url=base_url,
        trusted=False,
    )
    if current is None:
        registry.add(node)
    async with semaphore:
        if client is not None:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
        else:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
    if refreshed.status != "online":
        return None
    # trusted_only is a *filter* over results, not a grant of trust.
    if request.trusted_only and not refreshed.trusted:
        return None
    return refreshed
```

Notes:
- Removes the `not request.trusted_only` auto-grant entirely; trust now flows only from explicit owner action (manual registration / future `PATCH … {"trusted": true}` / fingerprint verification).
- `trusted_only=True` now does the sensible thing: it discovers reachable nodes but only *returns* (and the caller only acts on) those already trusted, while still recording newly seen untrusted nodes for later owner approval.
- Preserves the invariant "re-probing a node never changes its trust bit" because `current` (with its existing `trusted`) is reused and `refresh_node` does not touch `trusted`.
- **Docs:** DESIGN-API.md §12 shows a discovery example with `"trusted_only": false`; add one sentence clarifying that discovery never sets `trusted` and that the flag filters results. No `# type: ignore` involved.

## Test

This regression test fails today (the discovered node comes back `trusted=True`) and passes after the fix. It uses a mock transport so no sockets are opened.

```python
# tests/test_phase2.py
import httpx
import pytest

from vampire.cluster import discover_nodes
from vampire.models import DiscoveryRequest
from vampire.registry import registry


@pytest.mark.anyio
async def test_discovery_does_not_auto_trust_nodes(monkeypatch):
    registry.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        # Any probed node answers /v1/models successfully.
        return httpx.Response(200, json={"object": "list", "data": [{"id": "m"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        nodes = await discover_nodes(
            DiscoveryRequest(methods=["static"], base_urls=["http://10.0.0.9:1234"]),
            client=client,
        )

    # Default request (trusted_only=False) must NOT mark the node trusted.
    assert nodes, "an online node should be discovered"
    assert all(node.trusted is False for node in nodes), (
        "discovery must never auto-grant trust; default is owner-deny"
    )
    # And the registry copy must agree (no auto-trust persisted).
    assert registry.get("node-10-0-0-9-1234").trusted is False


@pytest.mark.anyio
async def test_trusted_only_discovery_returns_already_trusted_nodes(monkeypatch):
    registry.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list", "data": [{"id": "m"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # First pass: discover an untrusted node (recorded, not returned under trusted_only).
        await discover_nodes(
            DiscoveryRequest(methods=["static"], base_urls=["http://10.0.0.9:1234"]),
            client=client,
        )
        # Owner grants trust out of band.
        node = registry.get("node-10-0-0-9-1234")
        registry.add(node.model_copy(update={"trusted": True}))
        # trusted_only discovery now returns the already-trusted node (today: dead, returns []).
        nodes = await discover_nodes(
            DiscoveryRequest(
                methods=["static"], base_urls=["http://10.0.0.9:1234"], trusted_only=True
            ),
            client=client,
        )

    assert [n.id for n in nodes] == ["node-10-0-0-9-1234"]
    assert nodes[0].trusted is True
```

The first test asserts `node.trusted is False` — today it is `True`, so it fails on the current code and passes after removing the auto-grant. The second documents that `trusted_only=True` becomes useful (today it returns `[]` because the auto-grant + filter interaction discards everything).

## Effort & risk

- **Lines changed:** ~8 in `src/vampire/cluster.py` (one field, restructured filter) plus ~1-2 doc sentences in DESIGN-API.md §12.
- **Files touched:** `src/vampire/cluster.py`, optionally `DESIGN-API.md`, and `tests/test_phase2.py` for the regression tests.
- **Backward-compat:** Behavior change is the point — nodes discovered by the default request will now be `trusted=False` instead of `True`. Any deployment relying (knowingly or not) on discovery to populate trusted nodes for the `trusted_only` strategy will see those routes return `no_route_target` until an owner explicitly grants trust. That is the correct, safe direction (fail-closed), but it should be called out in the changelog. No API shape changes; the `DiscoveryRequest`/`Node` schemas are untouched.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~436,531 tok · output ~14,022 tok · est. cost ~$7.60 (input 436531/1e6×$15 = $6.55 + output 14022/1e6×$75 = $1.05) · run started 09:00 finished 09:05. Estimated; input is the honest sum of per-call `in=` (cumulative context across 12 calls, low cache hit this run).

> APPLIED 2026-06-14T09:28:11Z on branch vampire-fix/discover-auto-trusts-every-node-by-default: tests green (1 failed, 100 passed — the single failure is the known environmental flake test_openai_route_proxies_upstream_error_when_node_unreachable when LM Studio is live on :1234). Discovery no longer auto-grants trust (`trusted=False` default); `trusted_only` is now a result filter. Two regression tests added to tests/test_phase2.py. Awaiting review.
