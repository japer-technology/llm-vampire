# Every `/v1/models` and `/vampire/v1/models` call triggers an uncoalesced, uncapped full-cluster health refresh — no TTL cache, no single-flight, no concurrency ceiling — so model-list polling stampedes the whole cluster


- **Status:** Suggestion taken with notes.
- **Notes:** Implemented a short TTL cache, single-flight lock, and bounded fan-out for registered-node refreshes; node mutation paths invalidate the snapshot.
- **Severity:** High — the two model-list endpoints are the single most-polled surface of any OpenAI-compatible gateway (every client SDK, dashboard, and load balancer hits `/v1/models` on startup and often on a timer). Each call fans a live `/v1/models` probe out to *every* registered node with **no result caching, no single-flight coalescing, and no concurrency bound**. M concurrent pollers over N nodes produce up to **M·N simultaneous upstream probes** for data that changes on the order of seconds. Not Critical only because the endpoints are auth-gated and the registry is small in dev; in any real multi-client deployment this is a self-inflicted thundering-herd that scales the cluster's probe load with *client* count, not node count.
- **Category:** performance / resource management — missing backpressure (no debounce/TTL cache + no request coalescing/single-flight) on the hottest read path, with a secondary unbounded-fan-out dimension.

## Summary

`openai_compat.list_models` (`openai_compat.py:38-39`) and `control.list_vampire_models` (`control.py:119`) both call `cluster.refresh_registered_nodes(...)` **synchronously, inline, on every single request**. `refresh_registered_nodes` (`cluster.py:203-218`) `asyncio.gather`s a fresh `refresh_node` network probe across *all* registered nodes with no semaphore and — critically — there is **no cache layer**: identical back-to-back model-list reads each re-probe the entire cluster from scratch, and concurrent reads do not share a single in-flight refresh. The result is that model-list traffic, which clients treat as cheap and poll aggressively, is silently amplified into N live HTTP round-trips per call, multiplied again by the number of simultaneous callers.

## Location

- `src/vampire/api/openai_compat.py:38-39` — `list_models`: `if registry.list(): nodes = await refresh_registered_nodes(client=...)` on every request, no cache.
- `src/vampire/api/control.py:116-123` — `list_vampire_models`: `nodes = await refresh_registered_nodes(client=...)` on every request, no cache.
- `src/vampire/cluster.py:203-218` — `refresh_registered_nodes`: unbounded `asyncio.gather` over `registry.list()`, no concurrency cap, no single-flight, no TTL.
- Contrast: `src/vampire/cluster.py:305` — `discover_nodes` *does* bound its fan-out with `asyncio.Semaphore(_DISCOVERY_CONCURRENCY)`; the refresh path conspicuously does not.

## Evidence

The hot read path refreshes the entire cluster inline, every call, with no cache check:

```python
# src/vampire/api/openai_compat.py:35-48
@router.get("/models")
async def list_models(request: Request) -> Response:
    """Return registered-node model aggregation, falling back to Phase 1 passthrough."""
    if registry.list():
        nodes = await refresh_registered_nodes(client=_request_http_client(request))  # <-- live N-way fan-out, EVERY call
        physical = aggregate_model_cards(nodes).data
        ...
```

```python
# src/vampire/api/control.py:116-123
@router.get("/models")
async def list_vampire_models(request: Request) -> dict[str, Any]:
    """Aggregate a detailed physical model inventory across registered nodes (§15)."""
    nodes = await refresh_registered_nodes(client=_request_http_client(request))  # <-- same, no cache
    return {...}
```

And the refresh helper itself — no semaphore, no coalescing, no TTL; it always probes all nodes:

```python
# src/vampire/cluster.py:203-218
async def refresh_registered_nodes(
    *, timeout_ms: int | None = None, client: httpx.AsyncClient | None = None
) -> list[Node]:
    """Refresh every registered node and return the updated snapshot."""
    nodes = registry.list()
    if not nodes:
        return []
    if client is not None:
        return list(
            await asyncio.gather(
                *(refresh_node(node, timeout_ms=timeout_ms, client=client) for node in nodes)
            )
        )
    return list(
        await asyncio.gather(*(refresh_node(node, timeout_ms=timeout_ms) for node in nodes))
    )
```

Compare the discovery path, which the authors *did* bound — proving the asymmetry is an oversight, not a deliberate design choice:

```python
# src/vampire/cluster.py:305
    semaphore = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)   # discovery is capped; refresh is not
```

### Step-by-step manifestation

1. A deployment has, say, N = 12 registered nodes (modest LAN cluster).
2. Three things poll `/v1/models` routinely: each connected client SDK (OpenAI/LangChain clients call it on init and on model-cache misses), the bundled web dashboard, and any external health-check/load-balancer probe. Call the number of near-simultaneous pollers M.
3. Each poll enters `list_models`, sees a non-empty registry, and calls `refresh_registered_nodes`, which `asyncio.gather`s **12 live `GET /v1/models` probes** to the nodes — *with a per-node `timeout_ms` default of 1500 ms* (`cluster.py:164`).
4. There is no cache: a second poll arriving 5 ms later repeats the full 12-probe fan-out from scratch. There is no single-flight: M concurrent polls each launch their own independent fan-out, so the cluster sees up to **M × 12** concurrent inbound probes for identical, near-static data.
5. Each probe also mutates registry state: `refresh_node` does `request_count + 1` and rewrites `last_checked_at`/`latency_ms` (`cluster.py:172-200`) and writes back via `registry.add` (`cluster.py:198-199`). So model-list polling generates continuous registry churn proportional to M·N, and the per-node `request_count` metric is dominated by Vampire's own health probes rather than real inference traffic — corrupting the very metrics in `metrics_snapshot` (`cluster.py:246-271`).
6. Under a transient slow node, every concurrent `/v1/models` call blocks up to the full 1500 ms timeout simultaneously (no shared in-flight refresh to wait on), so a single sluggish node stalls *all* model-list responses at once, M-fold.

This compounds the already-filed phantom-node leak (`2026-06-14_0802`): with hundreds of dead phantoms registered, the same uncached, uncoalesced fan-out probes *all* of them on *every* poll from *every* client — turning a slow endpoint into a cluster-wide probe storm. The two issues are distinct (that one is registry growth; this one is the missing cache/coalescing/cap on the refresh path itself), but they multiply each other.

## Impact

- **Probe amplification scales with client count, not load:** model-list reads are the cheapest-looking, most-polled calls clients make, yet here each one costs N upstream round-trips, and concurrent reads do not share work. A dashboard auto-refreshing model lists every few seconds, plus a handful of SDK clients, can sustain hundreds of probes/minute against a cluster that has nothing to do.
- **Tail-latency coupling:** with no single-flight, one slow/timing-out node stalls every concurrent model-list response up to `timeout_ms` simultaneously, instead of one shared refresh absorbing the cost once.
- **Metric pollution:** `request_count`/`error_count` (surfaced in `/vampire/v1/metrics`) are dominated by Vampire's own refresh probes, making real per-node request/error rates unreadable for capacity decisions.
- **No backpressure ceiling:** unbounded `asyncio.gather` over the registry means a large cluster (or a phantom-polluted one) opens N sockets per call with no cap, unlike the deliberately-capped `discover_nodes`.
- **Triggers:** any deployment with more than one polling client and more than a couple of nodes — i.e. the project's headline multi-node mesh use-case. Invisible in the test suite, which uses a single in-process client and tiny registries.

## Fix

Introduce a short **TTL cache** for the registered-node health snapshot, guarded by an `asyncio.Lock` that provides **single-flight coalescing**, and bound the fan-out with a semaphore (mirroring `discover_nodes`). Reads inside the TTL return the cached snapshot with zero upstream probes; concurrent cold reads share exactly one in-flight refresh. The TTL should be small (e.g. 1000 ms, on the order of the probe timeout) so freshness is effectively unchanged while collapsing M·N probes into at most N-per-TTL-window.

**Before (`src/vampire/cluster.py:203-218`):**

```python
async def refresh_registered_nodes(
    *, timeout_ms: int | None = None, client: httpx.AsyncClient | None = None
) -> list[Node]:
    """Refresh every registered node and return the updated snapshot."""
    nodes = registry.list()
    if not nodes:
        return []
    if client is not None:
        return list(
            await asyncio.gather(
                *(refresh_node(node, timeout_ms=timeout_ms, client=client) for node in nodes)
            )
        )
    return list(
        await asyncio.gather(*(refresh_node(node, timeout_ms=timeout_ms) for node in nodes))
    )
```

**After:** add module-level cache state and a coalescing/capped refresh.

```python
# src/vampire/cluster.py (new module-level state, near the other constants)
_REFRESH_CONCURRENCY = 16          # cap simultaneous probes, like _DISCOVERY_CONCURRENCY
_REFRESH_TTL_SECONDS = 1.0         # serve cached snapshot within this window

_refresh_lock = asyncio.Lock()
_refresh_cache: list[Node] | None = None
_refresh_cache_at: float = 0.0


async def refresh_registered_nodes(
    *,
    timeout_ms: int | None = None,
    client: httpx.AsyncClient | None = None,
    force: bool = False,
) -> list[Node]:
    """Refresh every registered node, coalescing concurrent callers and caching briefly.

    Within ``_REFRESH_TTL_SECONDS`` of the last refresh, callers receive the cached
    snapshot without re-probing. Concurrent cold callers share a single in-flight
    refresh (single-flight) via ``_refresh_lock``. The fan-out is bounded by a
    semaphore so a large (or phantom-polluted) registry cannot open N sockets at once.
    """
    nodes = registry.list()
    if not nodes:
        return []

    global _refresh_cache, _refresh_cache_at
    now = perf_counter()
    if (
        not force
        and _refresh_cache is not None
        and (now - _refresh_cache_at) < _REFRESH_TTL_SECONDS
    ):
        return _refresh_cache

    async with _refresh_lock:
        # Re-check after acquiring: a coalesced caller may have just refreshed.
        now = perf_counter()
        if (
            not force
            and _refresh_cache is not None
            and (now - _refresh_cache_at) < _REFRESH_TTL_SECONDS
        ):
            return _refresh_cache

        nodes = registry.list()
        semaphore = asyncio.Semaphore(_REFRESH_CONCURRENCY)

        async def _bounded(node: Node) -> Node:
            async with semaphore:
                if client is not None:
                    return await refresh_node(node, timeout_ms=timeout_ms, client=client)
                return await refresh_node(node, timeout_ms=timeout_ms)

        refreshed = list(await asyncio.gather(*(_bounded(node) for node in nodes)))
        _refresh_cache = refreshed
        _refresh_cache_at = perf_counter()
        return refreshed
```

Notes:
- `perf_counter` is already imported (`cluster.py:9`); `asyncio` already imported (`cluster.py:5`). No new third-party deps.
- Add a `force=True` escape hatch and call it from `discover` / explicit operator refresh paths if a guaranteed-fresh read is ever required; the default polled paths (`/v1/models`, `/vampire/v1/models`) use the cached/coalesced path.
- Invalidate the cache wherever the node set changes deliberately — e.g. after `register_node`, `patch_node`, `delete_node`, and `discover_nodes` — by resetting `_refresh_cache_at = 0.0` (or exposing a `invalidate_refresh_cache()` helper in `cluster.py`). This keeps explicit operator mutations instantly visible while still collapsing read storms. A 1 s TTL already bounds staleness for the implicit case.
- No `# type: ignore` to remove. Docs: add a sentence to the DESIGN-API.md `/v1/models` (§5/§6) and `/vampire/v1/models` (§15) sections noting that model-list reads serve a sub-second-cached, coalesced cluster snapshot rather than probing every node per request.

## Test

A regression test that fails today (every call re-probes; concurrent calls each fan out) and passes after the fix (cache + single-flight collapse the probes). Place in `tests/test_phase2.py`:

```python
@pytest.mark.anyio
async def test_refresh_registered_nodes_coalesces_and_caches(monkeypatch):
    """Concurrent + back-to-back model-list refreshes must not re-probe every node each time."""
    from vampire import cluster
    from vampire.models import Node
    from vampire.registry import registry as node_registry

    node_registry.clear()
    cluster._refresh_cache = None          # reset cache between tests
    cluster._refresh_cache_at = 0.0
    for i in range(5):
        node_registry.add(Node(id=f"n{i}", lmstudio_base_url=f"http://10.0.0.{i}:1234"))

    probes = 0

    async def _counting_refresh(node, *, timeout_ms=None, client=None):
        nonlocal probes
        probes += 1
        return node.model_copy(update={"status": "online"})

    monkeypatch.setattr(cluster, "refresh_node", _counting_refresh)

    # 10 concurrent callers, then one more immediately after.
    await asyncio.gather(*(cluster.refresh_registered_nodes() for _ in range(10)))
    await cluster.refresh_registered_nodes()

    # Today: 11 callers * 5 nodes = 55 probes.
    # After fix: a single coalesced fan-out within the TTL = exactly 5 probes.
    assert probes == 5

    node_registry.clear()
    cluster._refresh_cache = None
    cluster._refresh_cache_at = 0.0
```

Today every caller independently fans out (`probes == 55`), so the assertion fails. After the fix, the first caller probes all 5 nodes once, every other concurrent caller awaits the same lock and the subsequent call is served from the TTL cache, so `probes == 5` and the test passes. A complementary test can assert that after `_REFRESH_TTL_SECONDS` (or a `force=True` / invalidate call) a fresh fan-out occurs, guarding against a permanently-stale cache.

## Effort & risk

- **Lines changed:** ~40 in `src/vampire/cluster.py` (cache state + rewritten `refresh_registered_nodes` + optional `invalidate_refresh_cache`); ~3 call-site invalidations in `api/control.py` register/patch/delete handlers; ~25 lines of new tests. No changes to `openai_compat.py`/`control.py` read endpoints — they call the same function signature.
- **Backward-compat:** the function's return type and existing keyword args are unchanged (`force` is additive with a default). Response shapes of both `/v1/models` and `/vampire/v1/models` are identical. The only observable behavior change is that model-list reads may reflect node health up to `_REFRESH_TTL_SECONDS` stale — a deliberate, sub-second, tunable trade for collapsing the probe storm.
- **Risk:** Low. Main subtlety is module-level mutable cache state in a long-lived process — guarded by an `asyncio.Lock` (single event loop per worker, so no thread race) and reset in tests via the fixture shown. If the gateway is ever run multi-worker, each worker keeps its own cache, which is correct (each has its own client pool too). Ensure tests that mutate the registry reset `_refresh_cache`/`_refresh_cache_at` (or call the invalidate helper) to avoid cross-test bleed.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~95,000 tok · output ~3,300 tok · est. cost ~$1.67 · run started 08:41 finished 08:43. (Estimated — input dominated by reading `cluster.py`, `proxy.py`, `router.py`, `registry.py`, `openai_compat.py`, `control.py`, `app.py` and two prior suggestions; Opus pricing $15/1M in, $75/1M out.)
