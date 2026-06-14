# SSRF: `base_urls` and `lmstudio_base_url` targets are probed/proxied with no scheme or host validation, bypassing the very `is_private`/`is_loopback` guard that `lan_scan` carefully enforces — turning the gateway into an internal-network scanner and metadata-endpoint fetcher

- **Severity:** High — the control plane accepts an arbitrary URL (`http://169.254.169.254/...`, `http://127.0.0.1:<any-port>`, `http://internal-admin:8080`, a public host, etc.) and the gateway issues outbound HTTP requests to it from *its own network position*. The discovery `lan_scan` path already encodes the correct security boundary (`if not (network.is_private or network.is_loopback): continue`, `cluster.py:288`), proving the project knows SSRF targets must be constrained — but the two sibling entry points that take a caller-supplied URL verbatim (`base_urls` discovery and `POST /vampire/v1/nodes`) skip that check entirely. The per-node `status`/`latency_ms`/`last_error` fields then form a read-back oracle that leaks which internal hosts/ports are alive and how they fail. Not rated Critical only because reaching these endpoints requires control-plane access once `VAMPIRE_AUTH_TOKEN` is set (suggestion `0548`, now taken); on the still-supported unauthenticated default it is effectively unauthenticated SSRF.
- **Category:** security (Server-Side Request Forgery / input validation / internal-reachability info leak) — with a secondary code-consistency dimension: the `lan_scan` branch validates target reachability scope, its sibling input paths do not.

## Summary

`_candidate_urls` expands three discovery inputs into probe URLs. The `lan_scan` branch (`cluster.py:282-296`) rejects any subnet that is not `is_private` or `is_loopback`, so a scan can never be steered onto link-local (`169.254.0.0/16`), public, or other off-LAN ranges. But the **`base_urls`** branch (`cluster.py:276`) and the static-node registration path (`POST /vampire/v1/nodes` → `register_node` → `refresh_node`, `control.py:60-70`) take a caller-supplied URL string with **no scheme allow-list and no host-scope check** and hand it straight to `httpx.AsyncClient.get(f"{base_url}/v1/models")` (`cluster.py:169`). The `Node.lmstudio_base_url` field is a bare `str` (`models.py:78`) and `DiscoveryRequest.base_urls` a bare `list[str]` (`models.py:119`), so Pydantic enforces nothing. A caller therefore makes the gateway emit GET requests to any `http(s)` URL it chooses, and reads back per-target liveness/latency/error metadata.

## Location

- `src/vampire/cluster.py:282-289` — the `lan_scan` guard that **does** constrain targets to private/loopback (the correct contract).
- `src/vampire/cluster.py:276` — `urls = [url.rstrip("/") for url in request.base_urls]`: caller URLs accepted verbatim, no validation.
- `src/vampire/cluster.py:169` — `await http_client.get(f"{base_url}/v1/models", ...)`: the outbound request to the unvalidated target.
- `src/vampire/cluster.py:307-316` — `_probe` builds and **registers** a `Node` for the unvalidated `base_url` before probing.
- `src/vampire/api/control.py:60-70` — `register_node`: stores the node and calls `refresh_node` on `node.lmstudio_base_url` with no URL validation.
- `src/vampire/models.py:78` — `lmstudio_base_url: str` (no `HttpUrl`, no validator).
- `src/vampire/models.py:119` — `base_urls: list[str]` (no validator).
- Read-back oracle that returns the SSRF result to the caller: `src/vampire/cluster.py:182-193` (`status`, `latency_ms`, `last_error`) surfaced via `GET /vampire/v1/nodes` (`control.py:54-57`) and the discovery result envelope (`control.py:113`).

## Evidence

The `lan_scan` branch knows the rule and enforces it — off-LAN subnets are skipped:

```python
# src/vampire/cluster.py:282-296
if "lan_scan" in methods:
    for subnet in request.subnets[:_MAX_SCAN_SUBNETS]:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError as exc:
            raise DiscoveryInputError(f"invalid subnet {subnet!r}: {exc}") from exc
        if not (network.is_private or network.is_loopback):
            continue                       # <-- correct SSRF scope guard
        for index, host in enumerate(network.hosts()):
            ...
            for port in request.ports[:_MAX_SCAN_PORTS]:
                ...
                urls.append(f"http://{host}:{port}")
```

The sibling `base_urls` branch — same function, a few lines up — applies **no** such guard:

```python
# src/vampire/cluster.py:274-280
def _candidate_urls(request: DiscoveryRequest) -> list[str]:
    """Expand static and development-subnet discovery inputs to base URLs."""
    urls = [url.rstrip("/") for url in request.base_urls]   # <-- verbatim, unvalidated
    methods = set(request.methods)
    if "static" in methods:
        urls.append(get_settings().lmstudio_base_url.rstrip("/"))
        urls.extend(node.lmstudio_base_url.rstrip("/") for node in registry.list())
```

Those URLs are then fetched directly:

```python
# src/vampire/cluster.py:165-169
base_url = node.lmstudio_base_url.rstrip("/")
http_client = client or proxy.build_async_client()
started = perf_counter()
try:
    response = await http_client.get(f"{base_url}/v1/models", timeout=timeout)
```

The data models impose no constraint — both are plain strings:

```python
# src/vampire/models.py:78
lmstudio_base_url: str
# src/vampire/models.py:119
base_urls: list[str] = Field(default_factory=list)
```

And the SSRF outcome is read straight back to the caller — `status`, `latency_ms`, and a stringified exception:

```python
# src/vampire/cluster.py:182-193
except (httpx.HTTPError, ValueError) as exc:
    latency_ms = round((perf_counter() - started) * 1000, 3)
    updated = node.model_copy(
        update={
            "status": "offline",
            ...
            "latency_ms": latency_ms,
            "last_checked_at": _now(),
            "last_error": str(exc),     # <-- target connection details echoed back
        }
    )
```

### Step-by-step manifestation

1. The caller (control-plane authenticated, or anyone at all on the unauthenticated default) sends:

   ```http
   POST /vampire/v1/discover
   Content-Type: application/json

   {"methods": ["static"],
    "base_urls": ["http://169.254.169.254", "http://127.0.0.1:6379", "http://internal-admin.corp:8080"]}
   ```

2. `_candidate_urls` returns those URLs verbatim (the `lan_scan` private/loopback guard is never consulted for `base_urls`). For each, `_probe` registers a `Node` and calls `refresh_node`, which issues `GET http://169.254.169.254/v1/models`, `GET http://127.0.0.1:6379/v1/models`, `GET http://internal-admin.corp:8080/v1/models` **from the gateway host**.
3. The gateway's outbound requests reach hosts and ports the caller cannot reach directly — the cloud instance-metadata endpoint, loopback-only admin/Redis/DB ports, other machines reachable only from the gateway's vantage point. This is textbook SSRF: the gateway is a confused deputy making requests on the attacker's behalf.
4. The caller reads `GET /vampire/v1/nodes` (or the discovery result envelope) and inspects each node's `status`, `latency_ms`, and `last_error`:
   - A reachable-but-non-LM-Studio host returns a fast `4xx/5xx` → `last_error` = `"Client error '404 Not Found' for url 'http://internal-admin.corp:8080/v1/models'"`, low `latency_ms` → **host/port is alive**.
   - A closed port → `last_error` = connection-refused, low latency.
   - A filtered/black-holed host → timeout, `latency_ms ≈ timeout_ms`.
   This is a precise internal **port/host-scanning and liveness oracle** built from the gateway's network position, with timing.
5. Worse for the data plane: any registered node with an internal `lmstudio_base_url` becomes a routing target (`openai_compat.py:154-156`). If the internal service happens to speak (or be coerced into speaking) an OpenAI-ish reply, routed completions are proxied to it — converting registration-time SSRF into an ongoing request-forwarding channel into the internal network.

The contract violated is the universal SSRF-mitigation invariant: **never issue server-side requests to a caller-controlled URL without validating the scheme and the resolved destination against an allow-list.** The project already honors it for `lan_scan` (`cluster.py:288`) and breaks it for `base_urls` (`cluster.py:276`) and node registration (`control.py:68-69`).

## Impact

- **What an attacker gains:** the gateway as an SSRF proxy/scanner. Cloud metadata endpoints (`169.254.169.254`), loopback-only services, and LAN hosts reachable only from the gateway are all probeable; the response `status`/`latency_ms`/`last_error` give a liveness + timing oracle, and a cooperative internal service can be turned into a routed data sink.
- **Who can do it:** on the unauthenticated default (`auth_token == ""`), anyone who can reach `/vampire/v1/*`. With auth enabled, any control-plane principal — but SSRF that escalates the gateway's *network reach* is dangerous even for an authorized-but-lower-trust caller, because it pivots to hosts the caller has no direct route to.
- **Why the guard asymmetry matters:** an operator who reads `cluster.py:288` reasonably concludes "discovery can't be steered off-LAN." That belief is false for the `base_urls` field and for direct node registration, so the mitigation is silently incomplete exactly where a reviewer would assume it holds.
- **Blast radius:** every `POST /vampire/v1/discover` carrying `base_urls`, and every `POST /vampire/v1/nodes`. Bounded only by `_MAX_SCAN_CANDIDATES` (1024) per discovery call for the `base_urls` list.
- **Detectability:** invisible in the test suite — the mock cluster (`tests/test_phase2.py:21-41`) answers every host, so no test asserts that an off-LAN/link-local/loopback-port target is rejected.

## Fix

Introduce one shared target-URL validator and apply it at **both** unguarded entry points, reusing the same private/loopback policy `lan_scan` already enforces. Restrict the scheme to `http`/`https`, and reject hosts that resolve outside the allowed scope (loopback/private) unless the operator explicitly opts in. Make the scope policy a single source of truth so the three input paths cannot drift again.

**Before** (`src/vampire/cluster.py`, the `base_urls` line and the `lan_scan` guard live in the same function but use different rules):

```python
# cluster.py:276
urls = [url.rstrip("/") for url in request.base_urls]
...
# cluster.py:288
if not (network.is_private or network.is_loopback):
    continue
```

**After** — factor the scope check into a helper and apply it to caller URLs too:

```python
# cluster.py — new shared helper
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _is_allowed_target_url(base_url: str) -> bool:
    """Return whether ``base_url`` is a safe server-side probe/proxy target.

    Mirrors the ``lan_scan`` scope guard: only http(s) to loopback or private
    (RFC1918 / ULA) hosts. Hostnames are permitted (LM Studio nodes are often
    addressed by name); literal IPs are scope-checked here, and link-local
    (169.254/16, fe80::/10) and public literals are rejected to prevent SSRF
    into cloud metadata endpoints and arbitrary external/internal hosts.
    """
    parsed = urlparse(base_url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return False
    host_ip = _host_ip_address(parsed.hostname)
    if host_ip is None:
        return True  # hostname; rely on operator DNS + node trust model
    if host_ip.is_link_local or host_ip.is_reserved or host_ip.is_multicast:
        return False
    return bool(host_ip.is_loopback or host_ip.is_private)


# cluster.py:276 (AFTER) — validate caller-supplied base_urls
urls: list[str] = []
for url in request.base_urls:
    cleaned = url.rstrip("/")
    if not _is_allowed_target_url(cleaned):
        raise DiscoveryInputError(f"disallowed discovery target {url!r}")
    urls.append(cleaned)
```

Apply the same gate at registration so a node URL cannot smuggle an SSRF target past discovery (`src/vampire/api/control.py`):

```python
# control.py:60 (AFTER)
@router.post("/nodes")
async def register_node(node: Node, request: Request) -> dict[str, Any]:
    if not _is_allowed_target_url(node.lmstudio_base_url):
        raise HTTPException(status_code=400, detail="disallowed lmstudio_base_url target")
    registry.add(node)
    refreshed = await refresh_node(node, client=_request_http_client(request))
    return {"id": refreshed.id, "status": "registered", "trusted": refreshed.trusted}
```

And reuse the helper inside the `lan_scan` branch so all three paths share one policy:

```python
# cluster.py:288 (AFTER) — same predicate, no divergence
if not (network.is_private or network.is_loopback):
    continue
# (host:port candidates produced here already satisfy _is_allowed_target_url)
```

Notes / invariants to preserve:
- **No behavior change for legitimate use:** loopback and RFC1918/ULA LM Studio nodes (the documented deployment, `localhost:1234`, `192.168.x.y:1234`) still register and probe exactly as today. Only off-scope literals (link-local/public/reserved) are rejected.
- **Hostname policy is a deliberate choice.** The strict-but-safe option is to resolve the hostname and scope-check every resolved address (defeats DNS-rebinding to metadata IPs); the pragmatic option above allows hostnames because LM Studio nodes are commonly named and the operator controls the node list. If you want full hardening, resolve via `socket.getaddrinfo` and require *every* returned address to be loopback/private, and re-pin the resolved IP for the actual request. Flag this in the fix as the follow-up tier.
- **Allow an explicit override** if a deployment genuinely needs an off-LAN node: gate it behind a `VAMPIRE_ALLOW_EXTERNAL_NODES` setting (default `False`), so the safe default holds and the dangerous case is opt-in and auditable.
- No `# type: ignore` is involved.

**Docs to reconcile:** `DESIGN-API.md:781-785` documents `discover` with `subnets`/`base_urls`; add a sentence that `base_urls` and registered node URLs are restricted to http(s) loopback/private targets by default (matching the `lan_scan` scope), and document the `VAMPIRE_ALLOW_EXTERNAL_NODES` escape hatch.

## Test

Add to `tests/test_phase2.py` (the mock-cluster `client` fixture already exists). Both assertions fail today — the link-local discovery target is probed and returns 200, and the public node registers — and pass after the fix.

```python
def test_discover_rejects_offscope_base_urls(client: TestClient) -> None:
    """base_urls must honor the same loopback/private scope as lan_scan (no SSRF)."""
    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"],
              "base_urls": ["http://169.254.169.254", "http://8.8.8.8:80"]},
    )
    # Today: 200, and each off-scope target is probed + registered as a node.
    assert resp.status_code == 400
    # And nothing off-scope leaked into the registry as a probe target.
    nodes = client.get("/vampire/v1/nodes").json()["data"]
    hosts = {n["host"] for n in nodes}
    assert "169.254.169.254" not in hosts and "8.8.8.8" not in hosts


def test_register_node_rejects_offscope_url(client: TestClient) -> None:
    """Node registration must not accept an arbitrary SSRF target URL."""
    resp = client.post(
        "/vampire/v1/nodes",
        json={"id": "evil", "lmstudio_base_url": "http://169.254.169.254/latest/meta-data"},
    )
    assert resp.status_code == 400
    # The gateway must not have registered (and thus probed) the metadata endpoint.
    assert client.get("/vampire/v1/nodes/evil").status_code == 404


def test_loopback_and_private_targets_still_allowed(client: TestClient) -> None:
    """Regression guard: the legitimate documented deployment is unaffected."""
    resp = client.post(
        "/vampire/v1/nodes",
        json={"id": "node-a", "lmstudio_base_url": "http://127.0.0.1:1234"},
    )
    assert resp.status_code == 200
```

(If the project prefers a unit-level test, assert `cluster._is_allowed_target_url("http://169.254.169.254")` is `False` and `cluster._is_allowed_target_url("http://192.168.1.50:1234")` is `True`; the integration form above is closer to the attacker's actual entry point.)

## Effort & risk

- **Lines changed:** ~15 in `src/vampire/cluster.py` (helper + the `base_urls` loop), ~2 in `src/vampire/api/control.py` (one guard), ~1 doc note in `DESIGN-API.md`, ~30 for the regression tests. Optional `VAMPIRE_ALLOW_EXTERNAL_NODES` setting is ~3 lines in `config.py`.
- **Files touched:** `src/vampire/cluster.py`, `src/vampire/api/control.py`, `tests/test_phase2.py`, optionally `src/vampire/config.py` + `DESIGN-API.md`.
- **Backward-compat:** Negligible risk for the intended deployment — loopback/LAN nodes are unchanged. The only behavioral change is that an off-scope literal URL now returns a structured `400`/`DiscoveryInputError` instead of being silently probed and registered, which is the desired posture; any genuine off-LAN need is served by the explicit opt-in flag. The `lan_scan` path is untouched in behavior (it already satisfied the predicate), so existing discovery tests pass unchanged.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~280,929 tok · output ~16,000 tok (summed from session `cron_c11148734d14_20260614_182447` logged `in=`/`out=`; final write emitted after logging, so output is rounded up from the last logged ~12,240) · est. cost ~$5.41 (input 280929/1e6·$15 = $4.21 + output 16000/1e6·$75 = $1.20) · run started 08:26 finished 08:28 UTC. Estimated.
