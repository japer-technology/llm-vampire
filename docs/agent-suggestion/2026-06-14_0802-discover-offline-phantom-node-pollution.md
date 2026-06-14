# `discover_nodes` permanently registers every scanned candidate IP — including the hundreds that never answer — flooding the registry with un-reapable offline "phantom" nodes that then sabotage `/v1/models`

- **Severity:** High — a single `lan_scan` over a real `/24` permanently injects up to ~256 dead, never-reachable "offline" nodes into the process-wide registry. They are never removed, they show up in `/vampire/v1/nodes` and `/vampire/v1/metrics`, and — worst of all — every subsequent `GET /v1/models` call fan-out-refreshes *all of them*, turning the single most-polled OpenAI-compat endpoint into a multi-hundred-connect-timeout operation. Not rated Critical only because `lan_scan` is opt-in (default `methods=["static"]`) and the endpoint is auth-gated/loopback-bound by default.
- **Category:** concurrency / resource-leak (unbounded registry growth) — with a co-equal performance dimension (phantom nodes amplify `/v1/models` cost) and a regression dimension (it is a direct side-effect of the earlier "refresh resurrects deleted nodes" hardening).

## Summary

`discover_nodes._probe` **pre-registers a `Node` for every candidate URL before it is probed** (`registry.add(node)` at `cluster.py:316`). The pre-registration was added so the `refresh_node` persistence guard (`cluster.py:198`) would accept the refreshed result. But `_probe` only *returns* online nodes — it never *de-registers* the candidates that came back `offline`. Since a LAN scan expands to up to 1024 candidate URLs of which typically only a handful answer, the registry is permanently polluted with hundreds of dead phantom nodes that no operator created, that survive the request, and that are only removable one-at-a-time via `DELETE /vampire/v1/nodes/{id}`.

## Location

- `src/vampire/cluster.py:301-327` — `discover_nodes` / the inner `_probe` (the `registry.add(node)` at line 316 with no compensating removal).
- Amplifier: `src/vampire/cluster.py:198-200` — `refresh_node` persistence guard (now passes for every phantom because `_probe` pre-registered it).
- Blast-radius amplifier: `src/vampire/api/openai_compat.py:38-39` — `/v1/models` calls `refresh_registered_nodes` over **all** registered nodes whenever the registry is non-empty.
- `src/vampire/cluster.py:203-218` — `refresh_registered_nodes` `asyncio.gather`s a refresh per registered node (phantoms included).

## Evidence

The offending pre-registration with no cleanup path:

```python
# src/vampire/cluster.py:307-324
async def _probe(base_url: str) -> Node | None:
    current = registry.get(_node_id_for_url(base_url))
    node = current or Node(
        id=_node_id_for_url(base_url),
        host=urlparse(base_url).hostname,
        lmstudio_base_url=base_url,
        trusted=not request.trusted_only,
    )
    if current is None:
        registry.add(node)          # <-- (1) phantom registered BEFORE probing
    async with semaphore:
        if client is not None:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
        else:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
    if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
        return refreshed
    return None                     # <-- (2) offline candidates are dropped from the
                                    #         RESULT, but never removed from the REGISTRY
```

And `refresh_node` *persists* the offline result precisely because line (1) put it in the registry:

```python
# src/vampire/cluster.py:182-200
    except (httpx.HTTPError, ValueError) as exc:
        ...
        updated = node.model_copy(
            update={
                "status": "offline",
                ...
                "last_error": str(exc),
            }
        )
    finally:
        if client is None:
            await http_client.aclose()

    if registry.get(updated.id) is not None:   # <-- TRUE, because _probe pre-registered it
        registry.add(updated)                  # <-- offline phantom written back, persisted
    return updated
```

The candidate-expansion shows the scale of the leak. With the default `ports=[1234]` (`models.py:116`) a single `/24` enumerates up to `_MAX_SCAN_HOSTS_PER_SUBNET = 256` hosts, and the function caps at `_MAX_SCAN_CANDIDATES = 1024`:

```python
# src/vampire/cluster.py:282-298
    if "lan_scan" in methods:
        for subnet in request.subnets[:_MAX_SCAN_SUBNETS]:
            ...
            for index, host in enumerate(network.hosts()):
                if index >= _MAX_SCAN_HOSTS_PER_SUBNET or len(urls) >= _MAX_SCAN_CANDIDATES:
                    break
                for port in request.ports[:_MAX_SCAN_PORTS]:
                    if len(urls) >= _MAX_SCAN_CANDIDATES:
                        break
                    urls.append(f"http://{host}:{port}")
    return _dedupe_local_access_urls(list(dict.fromkeys(urls)))[:_MAX_SCAN_CANDIDATES]
```

### Step-by-step manifestation

1. Operator (or an automated agent) issues `POST /vampire/v1/discover` with `{"methods":["lan_scan"],"subnets":["192.168.1.0/24"]}`.
2. `_candidate_urls` expands to ~254 `http://192.168.1.N:1234` URLs (the private subnet passes the `is_private` check at `cluster.py:288`).
3. For **each** candidate, `_probe` runs line (1): `registry.add(node)` — the registry now holds ~254 brand-new nodes, all `status` defaulting to whatever `Node` defaults to, about to be probed.
4. Each probe times out (no LM Studio at `192.168.1.7:1234`), `refresh_node` builds an `offline` copy and — because the phantom is registered — line `registry.add(updated)` persists it as `status="offline"`.
5. `_probe` returns `None` for all of them (line 2), so the **discovery response** correctly shows `nodes: []`… but the **registry** now permanently contains ~254 offline phantoms.
6. The request ends. Nothing reaps them. `GET /vampire/v1/nodes` now returns 254 dead entries; `GET /vampire/v1/metrics` reports `nodes_offline: 254`.
7. The next `GET /v1/models` hits `openai_compat.py:38` (`if registry.list():` → true), calls `refresh_registered_nodes`, which `asyncio.gather`s a `/v1/models` probe against **all 254 phantoms** plus any real node — each phantom incurring a full `timeout_ms` (default 1500 ms) connect-timeout. Every model-list poll is now permanently degraded, even after the scan is long over.

This is a **regression introduced by the earlier hardening**. Before `2026-06-14_0602-refresh-node-resurrects-deleted-nodes.md`, `refresh_node` unconditionally persisted, and discovery did not pre-register; the fix added pre-registration to discovery + a persistence guard to `refresh_node`. That correctly stopped deleted nodes from being resurrected, but it also made *every offline scan candidate* persist, because discovery's pre-registration trips the very guard that was meant to suppress writes for non-registered nodes.

## Impact

- **Unbounded registry growth / resource leak:** up to 1024 phantom nodes per scan, persisting in process memory indefinitely with no bulk-removal path. Repeated scans across different subnets accumulate without bound (each distinct IP yields a distinct `node-<host>-<port>` id, so they do not collapse).
- **`/v1/models` self-DoS:** the hottest OpenAI-compat endpoint fan-out-refreshes all phantoms on every call. With 254 phantoms at the default 1500 ms timeout and `_DISCOVERY_CONCURRENCY` not applied on this path (`refresh_registered_nodes` gathers *all at once*), each `/v1/models` poll pays ~1.5 s wall-clock (bounded by httpx pool limits) plus 254 wasted connect attempts — observed by every client as a slow, flaky model list.
- **Polluted observability:** `nodes_total` / `nodes_offline` in `/vampire/v1/status` and `/vampire/v1/metrics` become dominated by phantoms, making the metrics useless for capacity decisions.
- **Routing noise:** `Router._candidates` filters on `status == "online"` so phantoms don't get traffic, but `default_policy` and every registry scan still iterate them.
- **Triggers:** any single `lan_scan` discovery. An operator following the project's headline "zero-config LAN discovery" use-case permanently degrades their gateway with one call.

## Fix

**Do not register a candidate until it is confirmed online.** Newly-created candidates should only enter the registry when `refresh_node` reports `online`; already-registered nodes are persisted by `refresh_node`'s existing guard, so no pre-registration is needed at all. This both removes the phantom leak and *preserves* the resurrect-deleted invariant from the earlier fix (a node deleted mid-scan that is genuinely still live and answering will be re-added — which is the *intended* meaning of an explicit operator "discover", unlike a silent background health refresh).

```python
# BEFORE  (src/vampire/cluster.py:307-324)
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
```

```python
# AFTER
async def _probe(base_url: str) -> Node | None:
    node_id = _node_id_for_url(base_url)
    current = registry.get(node_id)
    node = current or Node(
        id=node_id,
        host=urlparse(base_url).hostname,
        lmstudio_base_url=base_url,
        trusted=not request.trusted_only,
    )
    # NOTE: do NOT pre-register here. Pre-registration causes every offline
    # scan candidate to be persisted as a phantom node (refresh_node's guard
    # then accepts the offline write). Persistence is deferred to a confirmed
    # online result below; existing nodes are still persisted in-place by
    # refresh_node's own guard.
    async with semaphore:
        if client is not None:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
        else:
            refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
    if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
        # Register only candidates that actually answered. For a brand-new
        # discovery this adds the node; for an already-registered node
        # refresh_node already persisted the online copy, so this is a no-op
        # overwrite with identical data.
        registry.add(refreshed)
        return refreshed
    return None
```

Notes / invariants:
- **Preserves the resurrect-deleted invariant** for *background* refreshes: `refresh_node`'s guard (`cluster.py:198`) is unchanged, so a node deleted during a health-refresh cycle still will not be resurrected. The only re-add is in `_probe`, gated on an explicit operator discovery + a confirmed-online probe — the correct semantics for "discover".
- No `# type: ignore` to remove here.
- No doc change strictly required; optionally add a sentence to `docs/` (the discovery section) clarifying that discovery registers only reachable nodes, so operators don't expect offline candidates to appear in `/vampire/v1/nodes`.
- Optional belt-and-suspenders: cap total registry size or expose a bulk-reap, but the minimal fix above already stops the leak.

## Test

A regression test that fails today (registry is polluted with the offline candidate) and passes after the fix. Place in `tests/test_phase2.py`:

```python
def test_discover_does_not_register_offline_candidates(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """An offline scan candidate must NOT be left behind in the registry."""
    from vampire.registry import registry as node_registry

    node_registry.clear()

    async def _all_offline(node: Node, *, timeout_ms: int | None = None, client=None) -> Node:
        # Simulate refresh_node's offline path INCLUDING its persistence guard,
        # so the test exercises the real registry-write contract.
        updated = node.model_copy(update={"status": "offline"})
        if node_registry.get(updated.id) is not None:
            node_registry.add(updated)
        return updated

    monkeypatch.setattr(cluster, "refresh_node", _all_offline)

    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"], "base_urls": ["http://dead-node:1234"]},
    )
    assert resp.status_code == 200
    assert resp.json()["nodes"] == []  # nothing answered

    # The bug: the candidate is still registered as an offline phantom.
    assert node_registry.get("node-dead-node-1234") is None
    assert node_registry.list() == []
```

Today, `_probe` pre-registers `node-dead-node-1234`, the stubbed `refresh_node` persists the offline copy, and the final two assertions fail (`registry.list()` contains one phantom). After the fix, no pre-registration occurs, the offline result is never persisted, and both assertions pass.

A complementary positive test (online candidate IS registered) guards against over-correction:

```python
def test_discover_registers_online_candidates(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    from vampire.registry import registry as node_registry

    node_registry.clear()

    async def _online(node: Node, *, timeout_ms: int | None = None, client=None) -> Node:
        return node.model_copy(update={"status": "online"})

    monkeypatch.setattr(cluster, "refresh_node", _online)

    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"], "base_urls": ["http://live-node:1234"]},
    )
    assert resp.status_code == 200
    assert node_registry.get("node-live-node-1234") is not None
```

## Effort & risk

- **Lines changed:** ~6 in `src/vampire/cluster.py` (remove the `if current is None: registry.add(node)` pre-registration; add `registry.add(refreshed)` inside the online branch). ~30 lines of new tests.
- **Files touched:** `src/vampire/cluster.py`; `tests/test_phase2.py` (new tests); optional one-line doc clarification.
- **Backward-compat:** Behavior change is strictly a *reduction* in spurious registry entries. The discovery **response** (`{"nodes": [...]}`) is unchanged — it already only contained online nodes. Anyone relying on the side-effect of offline candidates appearing in `/vampire/v1/nodes` (no documented contract does) would see them disappear, which is the intended fix. The existing `test_discover_caps_candidates_and_skips_public_subnets` and `test_discover_probes_concurrently` tests assert on `seen`/timing, not on registry pollution, so they remain green.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~205,000 tok · output ~7,000 tok · est. cost ~$3.60 · run started 08:00 finished 08:02. (Estimated — summed from `~/.hermes/logs/agent.log` `in=`/`out=` for this cron run; Opus pricing $15/1M in, $75/1M out.)
