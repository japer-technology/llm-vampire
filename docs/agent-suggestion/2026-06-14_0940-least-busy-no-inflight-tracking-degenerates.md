# `least_busy` routing is a no-op in production: the proxy never tracks in-flight requests, so `queue_depth`/`active_requests` stay 0 and every request is pinned to the lowest-id node

- **Severity:** High — `least_busy` is one of the five advertised MVP routing strategies (DESIGN-API.md §24 / §9) and the most operationally important one for a LAN load-balancer, yet on a live cluster it can never balance anything: the gateway proxies real traffic through `_route_or_proxy` without ever incrementing `active_requests`/`queue_depth` on the chosen node, so the load signal the strategy minimizes is frozen at its `0` default for every node. The strategy silently collapses to "always pick the alphabetically-smallest node id," creating a permanent hotspot on one node while the rest idle. Not Critical because it degrades load distribution rather than corrupting responses or leaking data, and an operator *can* drive the counters manually via `PATCH /vampire/v1/nodes/{id}` — but no code path does so automatically, so the documented behavior never occurs in normal use.
- **Category:** api-correctness (routing-strategy semantics) — with a secondary correctness/observability dimension: `/vampire/v1/metrics` `cluster.active_requests` and `cluster.queue_depth` (DESIGN-API.md §18) are likewise always reported as 0.

## Summary
The router's `least_busy` strategy ranks candidate nodes by `(node.queue_depth, node.active_requests, node.id)` (`router.py:124`), but nothing in the request path ever mutates `queue_depth` or `active_requests`. The proxy seam (`proxy.proxy_request_with_body`) and the routing dispatcher (`openai_compat._route_or_proxy`) forward the request to the selected node and stream the reply back without touching the registry's per-node counters. Because both fields default to `0` (`models.py:87-88`) and are only ever set by a manual control-plane `PATCH`, every online node ties on the load key in production and `min(...)` falls through to the `node.id` tie-breaker — so `least_busy` deterministically routes 100% of traffic to one node. The same un-incremented counters make the cluster-level `active_requests`/`queue_depth` metrics permanently read `0`.

## Location
- `src/vampire/router.py:122-124` — `_busy_score` (the load key that is never fed real data).
- `src/vampire/api/openai_compat.py:90-164` — `_route_or_proxy`: selects a target and proxies, but never marks the node busy/idle around the upstream call.
- `src/vampire/proxy.py:125-178` — `proxy_request_with_body`: the single place every routed/passthrough request flows through; the natural place to bracket in-flight accounting, but it never touches the registry.
- `src/vampire/cluster.py:256-257` — `metrics_snapshot`: sums `node.active_requests` / `node.queue_depth`, which are structurally always 0.
- Counters' only writers today: `models.py:106-108` (`NodeUpdate`) + `registry.update` (`registry.py:29-37`), reachable solely from `PATCH /vampire/v1/nodes/{id}`.

## Evidence
The load key the strategy minimizes:

```python
# src/vampire/router.py:121-124
@staticmethod
def _busy_score(node: Node) -> tuple[int, int, str]:
    """Sort least-busy candidates by queue depth, active requests, then id."""
    return (node.queue_depth, node.active_requests, node.id)
```

The full request path that should — but does not — update those fields:

```python
# src/vampire/api/openai_compat.py:137-164  (inside _route_or_proxy)
target = selection.target
node = registry.get(target.node)
...
routed_payload = dict(payload)
routed_payload["model"] = target.model
routed_payload.pop("vampire", None)
return await proxy_request_with_body(
    request,
    downstream_base_url=node.lmstudio_base_url,
    body=json.dumps(routed_payload).encode("utf-8"),
    response_headers={ ... },
)
```

`proxy_request_with_body` then streams the upstream reply and closes the connection (`proxy.py:160-178`) — again with no registry interaction. Grep confirms the **only** assignments to these fields in the whole package are the model defaults and the `NodeUpdate` patch surface:

```
src/vampire/models.py:87:    active_requests: int = 0
src/vampire/models.py:88:    queue_depth: int = 0
src/vampire/models.py:106:    active_requests: int | None = None   # NodeUpdate (manual PATCH only)
src/vampire/models.py:107:    queue_depth: int | None = None       # NodeUpdate (manual PATCH only)
src/vampire/cluster.py:256:            "active_requests": sum(node.active_requests for node in nodes),  # always 0
src/vampire/cluster.py:257:            "queue_depth": sum(node.queue_depth for node in nodes),        # always 0
src/vampire/router.py:124:        return (node.queue_depth, node.active_requests, node.id)        # reads 0, 0, id
```

**Why it manifests, step by step (production interleaving):**
1. Operator registers three online nodes `node-a`, `node-b`, `node-c` (all with `active_requests=0`, `queue_depth=0` — the defaults; `refresh_node` in `cluster.py:172-193` does not set them either).
2. A client sends a routed request (`model="vampire:auto"`, or `X-Vampire-Strategy: least_busy`). `_route_or_proxy` builds a policy and calls `_router.select(policy)`.
3. In `Router.select`, `strategy == "least_busy"` takes the branch `target = min(candidates, key=lambda t: self._busy_score(self._node(t)))` (`router.py:57-59`).
4. Every candidate yields the key `(0, 0, "node-a")`, `(0, 0, "node-b")`, `(0, 0, "node-c")`. Tuple comparison resolves the tie on the third element, so `min` returns `node-a` — **every time**, regardless of how many requests `node-a` is already serving.
5. The request is proxied to `node-a`; **no counter is incremented**, so even a burst of 50 concurrent requests leaves `node-a.active_requests == 0`. Steps 2-5 repeat and `node-a` absorbs the entire load while `node-b`/`node-c` stay idle.
6. The operator opens the dashboard / hits `/vampire/v1/metrics` and sees `cluster.active_requests: 0`, `cluster.queue_depth: 0` despite a saturated `node-a` — the metric is structurally incapable of being non-zero.

The existing test `tests/test_phase3.py:126-158` only ever proves `least_busy` works by *manually* constructing nodes with non-zero `queue_depth` (`_online_node(..., queue_depth=1)`), so it green-lights a strategy that is never actually fed live load. The gap between "works in the unit test with hand-set fields" and "is dead on real traffic" is exactly the missing instrumentation.

## Impact
- **What an operator observes:** after enabling `least_busy` (or relying on `vampire:auto` defaulting to it via a route policy), one node is pegged at high utilization/latency while peers sit idle; throughput is capped at a single node's capacity. The dashboard's load numbers read `0`, masking the imbalance and making the misbehavior hard to diagnose.
- **Blast radius:** all routed traffic using `least_busy`, plus the `least_busy` tie-break path inside `model_affinity`/fallback chains that resolve to it; plus the cluster `active_requests`/`queue_depth` metrics consumed by §18 and the Phase 4 UI.
- **When it triggers:** immediately and permanently on any multi-node cluster — no race or rare condition required. It is the *default* behavior, which is why it is easy to miss in review (the unit test pre-seeds the counters).

## Fix
Track in-flight work around the upstream call so the load signal reflects reality. The cleanest seam is the proxy, because **every** routed request passes through `proxy_request_with_body`; bracket the upstream send/stream with increment/decrement on the selected node. Because `Node` is a frozen-ish Pydantic snapshot stored by value in the registry, add small atomic helpers to `NodeRegistry` rather than mutating snapshots in place, and guard them so a node removed mid-request cannot resurrect.

**1) Add counter helpers to the registry (`registry.py`):**

```python
# src/vampire/registry.py  (add to NodeRegistry)
def mark_busy(self, node_id: str) -> None:
    """Atomically record a new in-flight request against a node."""
    node = self._nodes.get(node_id)
    if node is not None:
        self._nodes[node_id] = node.model_copy(
            update={"active_requests": node.active_requests + 1}
        )

def mark_idle(self, node_id: str) -> None:
    """Atomically release an in-flight request, never dropping below zero."""
    node = self._nodes.get(node_id)
    if node is not None:
        self._nodes[node_id] = node.model_copy(
            update={"active_requests": max(0, node.active_requests - 1)}
        )
```

(Registry access is single-threaded under the asyncio event loop; the get-then-set is not preempted by other coroutines because it contains no `await`, so it is atomic with respect to other registry mutations. Preserve that invariant — do **not** add an `await` between the read and the write.)

**2) Bracket the upstream call in the router dispatcher (`openai_compat._route_or_proxy`)** — the dispatcher knows the selected node id and owns the routed lifetime, whereas the proxy is also used for un-routed passthrough where there is no "selected node":

```python
# src/vampire/api/openai_compat.py  — before/after around the routed proxy call
# BEFORE
    routed_payload = dict(payload)
    routed_payload["model"] = target.model
    routed_payload.pop("vampire", None)
    return await proxy_request_with_body(
        request,
        downstream_base_url=node.lmstudio_base_url,
        body=json.dumps(routed_payload).encode("utf-8"),
        response_headers={...},
    )

# AFTER
    routed_payload = dict(payload)
    routed_payload["model"] = target.model
    routed_payload.pop("vampire", None)
    registry.mark_busy(target.node)
    try:
        response = await proxy_request_with_body(
            request,
            downstream_base_url=node.lmstudio_base_url,
            body=json.dumps(routed_payload).encode("utf-8"),
            response_headers={...},
        )
    except BaseException:
        registry.mark_idle(target.node)
        raise
    # The body streams lazily; release the slot when the stream is exhausted.
    response.background = _release_on_finish(target.node, response.background)
    return response
```

Because the reply is a `StreamingResponse`, the request is *not* finished when `proxy_request_with_body` returns — it is finished when `body_stream()` (`proxy.py:160-168`) is fully consumed. Use Starlette's `BackgroundTask` to decrement after the stream closes:

```python
# src/vampire/api/openai_compat.py
from starlette.background import BackgroundTask, BackgroundTasks

def _release_on_finish(node_id: str, existing: BackgroundTask | None) -> BackgroundTask:
    release = BackgroundTask(registry.mark_idle, node_id)
    if existing is None:
        return release
    tasks = BackgroundTasks()
    tasks.add_task(existing)
    tasks.add_task(release)
    return tasks
```

(If wiring the streaming-completion hook is deemed too large for one change, an acceptable first cut is to also fold `queue_depth` into `_busy_score` is unnecessary — but at minimum increment on dispatch and decrement in a `finally`/background task; never leave both counters permanently 0.)

**3) Update docs:** none of DESIGN-API.md changes, but it is worth a one-line note in the routing section that `least_busy` reflects gateway-observed in-flight requests (not LM Studio's internal queue), so operators understand the signal source.

**Invariant to preserve:** counters must be symmetric (every `mark_busy` is paired with exactly one `mark_idle`, including on client disconnect and upstream error) and must never go negative (`max(0, ...)`). Keep the get-then-set in the registry free of `await`.

## Test
A regression test that fails today (because the second request still scores `node-a` as `(0,0,'node-a')` and routes there) and passes once dispatch increments `active_requests`:

```python
# tests/test_phase3.py
def test_least_busy_reflects_inflight_requests(client: TestClient) -> None:
    """least_busy must move traffic off a node once it has an in-flight request.

    Today both nodes report active_requests=0 forever, so least_busy pins every
    request to the lowest-id node. After instrumenting the proxy path, the node
    serving an open stream is scored busier and the next pick flips.
    """
    from vampire.registry import registry

    registry.clear()
    registry.add(_online_node("node-a", "shared"))
    registry.add(_online_node("node-b", "shared"))

    # Simulate one in-flight request on node-a via the same helper the proxy uses.
    registry.mark_busy("node-a")  # NEW helper introduced by the fix

    from vampire.router import Router
    from vampire.models import RoutePolicy, RouteTarget

    router = Router(registry)
    policy = RoutePolicy(
        id="busy",
        virtual_model="vampire:auto",
        targets=[RouteTarget(node="node-a", model="shared"),
                 RouteTarget(node="node-b", model="shared")],
        strategy="least_busy",
    )
    selection = router.select(policy)
    assert selection is not None
    # FAILS today: with both counters frozen at 0, min() tie-breaks to "node-a".
    assert selection.target.node == "node-b"

    registry.mark_idle("node-a")
    assert registry.get("node-a").active_requests == 0
```

A second, end-to-end test asserts the counter actually moves through the HTTP surface (drive a routed request against the Phase-3 mock cluster and assert `metrics["cluster"]["active_requests"]` is observed `> 0` while a stream is open, or that two sequential routed `least_busy` requests alternate `X-Vampire-Node`). The unit test above is the minimal failing case.

## Effort & risk
- **Lines changed:** ~35-50. New: two registry helpers (~12 lines), the `_release_on_finish` helper (~8 lines), the try/background wiring in `_route_or_proxy` (~8 lines), plus the regression test (~30 lines).
- **Files touched:** `src/vampire/registry.py`, `src/vampire/api/openai_compat.py`, `tests/test_phase3.py` (and optionally a one-line doc note).
- **Backward-compat:** additive and safe. `mark_busy`/`mark_idle` are new methods; `active_requests` already exists in the public `Node` shape and is already summed by metrics, so non-zero values are within spec (DESIGN-API.md §14/§18 show non-zero examples). No API contract changes. Main risk is leak symmetry under client disconnect — covered by the `except BaseException: mark_idle` guard plus the streaming background task; add a disconnect test if paranoid. `queue_depth` can remain operator-set for now (no LM Studio queue introspection in MVP); only `active_requests` needs gateway instrumentation to make `least_busy` functional.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~440000 tok (cumulative, cache-heavy) · output ~12000 tok · est. cost ~$7.50 · run started 09:40 finished 09:45. Marked estimated; derived from `~/.hermes/logs/agent.log` `in=`/`out=` sums for this cron run.
