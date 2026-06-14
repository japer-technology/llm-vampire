# `Router._cursors` is an unbounded `defaultdict` keyed by client-controlled model strings: any client can grow gateway memory without limit via distinct `vampire:<anything>` model names

- **Severity:** High — the process-wide singleton `Router` permanently retains one `dict` entry per *distinct virtual-model string it has ever round-robined*, and that string is fully attacker-controlled (the request body's `model` field). A single unauthenticated-or-authenticated client can issue `vampire:aaaa`, `vampire:aaab`, … indefinitely and force unbounded heap growth in the long-lived gateway process — a slow-burn memory-exhaustion DoS that no current test or metric would catch. Not rated Critical only because it requires ≥1 online node registered (so a candidate list exists to round-robin over) and the per-entry cost is small (~120 bytes), so exhaustion is gradual rather than instantaneous.
- **Category:** concurrency / resource-leak (unbounded process-lifetime state keyed by untrusted input) — with a secondary api-correctness dimension (the same map is the round-robin state machine, so the leak is welded to a load-balancing invariant that the fix must preserve).

## Summary
`Router._round_robin` records its rotation cursor in `self._cursors[route_id]`, where `self._cursors` is a `defaultdict(int)` that is **never pruned**. For the common "no configured route" path the `route_id` is the *ephemeral* default-policy id `f"default:{virtual_model}"`, and `virtual_model` is the client-supplied `model` value (any string beginning with `vampire:`, or any model when `X-Vampire-Mode: route` is set). Because `_router` is a module-level singleton bound to the process for its entire lifetime, every unique virtual-model string a client has ever sent leaves a permanent entry in the map. Memory grows monotonically with request-name cardinality, bounded only by the attacker's patience.

## Location
- `src/vampire/router.py:39` — `self._cursors: defaultdict[str, int] = defaultdict(int)` (unbounded map declaration).
- `src/vampire/router.py:110-114` — `_round_robin`, which writes a new key per `route_id` and never evicts.
- `src/vampire/router.py:67-69` — `model_affinity` fallback also routes through `_round_robin(candidates, policy.id)`, so it leaks too.
- `src/vampire/router.py:88-93` — `default_policy` mints the ephemeral, client-derived id `f"default:{virtual_model}"`.
- `src/vampire/api/openai_compat.py:114-115, 137` — the hot path: `_route_policy(...)` → `default_policy(model, …)` → `_router.select(policy, …)` with `policy.id == "default:" + client_model`.

## Evidence

The map is created with no bound and no eviction:

```python
# src/vampire/router.py:36-39
def __init__(self, registry: NodeRegistry) -> None:
    """Bind the router to the registry that supplies candidate nodes."""
    self._registry = registry
    self._cursors: defaultdict[str, int] = defaultdict(int)
```

Every round-robin selection writes a (possibly brand-new) key and only ever *grows* it:

```python
# src/vampire/router.py:110-114
def _round_robin(self, candidates: list[RouteTarget], route_id: str) -> RouteTarget:
    """Select the next candidate for ``route_id`` and advance its cursor."""
    index = self._cursors[route_id] % len(candidates)   # defaultdict insert on first touch
    self._cursors[route_id] += 1                         # mutation; key persists forever
    return candidates[index]
```

The `route_id` for the default (un-configured) path is derived directly from the client's `model` string:

```python
# src/vampire/router.py:88-93
return RoutePolicy(
    id=f"default:{virtual_model}",   # virtual_model == client-supplied model
    virtual_model=virtual_model,
    targets=targets,
    strategy=strategy,
)
```

And the OpenAI-compat handler feeds the raw client model into exactly that path:

```python
# src/vampire/api/openai_compat.py:97-115
model = payload.get("model")
if not isinstance(model, str) or not _is_routing_request(request, payload, model):
    return await proxy_request_with_body(request, body=body)
...
policy = _route_policy(request, payload, model, strategy)   # -> default_policy(model, ...)
selection = _router.select(policy, requested_model=model)   # -> _round_robin(..., policy.id)
```

`_router` is a process-lifetime singleton — there is exactly one, created at import and never reset outside tests:

```python
# src/vampire/api/openai_compat.py:27-28
router = APIRouter(prefix="/v1", tags=["openai-compatible"])
_router = Router(registry)
```

### Step-by-step manifestation
1. At least one node is registered and `online` (normal operating state — otherwise `_candidates` is empty and `select` returns `None` at `router.py:53-54` before reaching `_round_robin`, so no leak). The default policy's `targets` are non-empty.
2. A client POSTs `/v1/chat/completions` with `{"model": "vampire:probe-0001", ...}` (or any model with header `X-Vampire-Mode: route`). `_is_routing_request` returns `True` because the model starts with `vampire:`.
3. `_route_policy` finds no configured route (`route_registry.get_by_virtual_model("vampire:probe-0001")` is `None`) and synthesizes `default_policy("vampire:probe-0001", …)` with `id == "default:vampire:probe-0001"`.
4. `select` runs the default `round_robin` strategy → `_round_robin(candidates, "default:vampire:probe-0001")` → `self._cursors["default:vampire:probe-0001"]` is created.
5. The request completes normally (200, routed to a node). **The cursor entry is never removed.**
6. The client repeats with `vampire:probe-0002`, `vampire:probe-0003`, … Each distinct string adds a permanent entry. After N distinct names the map holds N entries forever; there is no TTL, no LRU cap, no clear-on-completion. Memory climbs monotonically for the life of the process.

Because `_cursors` is a plain `dict` mutated under `async` (no lock), high-concurrency rotation can also interleave the read-modify-write at lines 112–113 and momentarily skew/repeat round-robin selection — a secondary, lower-severity correctness wrinkle that any fix should keep in mind (the single-threaded asyncio event loop makes the two-statement window non-atomic only across `await` boundaries, and there is no `await` here, so today it is benign — but it is fragile state that a reviewer should not assume is safe to make async).

## Impact
- **What an operator observes:** RSS of the `vampire serve` process grows slowly and never recovers, with no corresponding increase in registered nodes, routes, or in-flight requests. `/vampire/v1/metrics` shows nothing — the leak is in a private map that no endpoint surfaces. Eventually the process is OOM-killed or the host starts swapping; restart "fixes" it until the traffic pattern recurs.
- **Blast radius:** the entire gateway process. One client, one endpoint, no special privileges beyond whatever auth the operator configured (and with `auth_token` unset — still the default — *zero* privileges). The attacker needs only the ability to send routing-opted requests, which is the gateway's primary public function.
- **When it triggers:** any deployment that (a) has at least one online node and (b) receives routing requests with high model-name cardinality. That includes benign cases too: a buggy client that templatizes the model name (e.g. embeds a request id or timestamp into `vampire:auto-<uuid>`) will leak just as effectively as a malicious one. The project's own design encourages virtual model names, so cardinality creep is plausible without any attacker at all.
- **Why tests miss it:** the suite exercises a handful of fixed model names and asserts on response bodies/headers; nothing inspects `Router._cursors` size, and `registry`/`route_registry` are cleared between tests but the singleton `_router._cursors` is **not** reset by the existing fixtures, so the leak is invisible.

## Fix
Bound the cursor map and evict least-recently-used entries. Replace the unbounded `defaultdict` with an `OrderedDict`-backed LRU of fixed capacity. This preserves the round-robin invariant for the hot, repeatedly-used route ids (they stay resident) while capping memory: rarely-seen one-off virtual-model names fall out of the cache and at worst restart their rotation from index 0 — a cosmetic, self-healing effect, not a correctness violation.

**Before** (`src/vampire/router.py`):

```python
from collections import defaultdict
...
class Router:
    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self._cursors: defaultdict[str, int] = defaultdict(int)
    ...
    def _round_robin(self, candidates: list[RouteTarget], route_id: str) -> RouteTarget:
        """Select the next candidate for ``route_id`` and advance its cursor."""
        index = self._cursors[route_id] % len(candidates)
        self._cursors[route_id] += 1
        return candidates[index]
```

**After**:

```python
from collections import OrderedDict
...
# Cap on retained round-robin cursors. Route ids are partly client-controlled
# (ephemeral ``default:<model>`` policies), so an unbounded map is a
# memory-exhaustion vector. An LRU keeps hot routes rotating correctly while
# evicting one-off virtual-model names; an evicted cursor simply restarts at 0.
_MAX_CURSORS = 4096


class Router:
    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self._cursors: "OrderedDict[str, int]" = OrderedDict()

    ...

    def _round_robin(self, candidates: list[RouteTarget], route_id: str) -> RouteTarget:
        """Select the next candidate for ``route_id`` and advance its cursor.

        Cursors are kept in a bounded LRU so client-controlled ephemeral route
        ids (``default:<model>``) cannot grow the map without limit. Touching a
        route marks it most-recently-used; once the cap is exceeded the
        least-recently-used cursor is dropped.
        """
        current = self._cursors.get(route_id, 0)
        index = current % len(candidates)
        self._cursors[route_id] = current + 1
        self._cursors.move_to_end(route_id)
        if len(self._cursors) > _MAX_CURSORS:
            self._cursors.popitem(last=False)  # evict least-recently-used
        return candidates[index]
```

Notes:
- No `# type: ignore` is involved; the change is purely the container type and eviction policy.
- Invariant preserved: for any route id that is hit more often than the cache turns over (i.e. all real/hot routes), the cursor still increments monotonically and rotation is unchanged. Only cold, single-use ids are ever evicted, and their reset-to-0 is harmless.
- A stricter alternative is to **not persist cursors for ephemeral `default:` policies at all** (e.g. seed the index from a fast hash of the candidate set, or fold rotation state into the registry keyed by stable node ids). That fully eliminates client-controlled keys but changes round-robin fairness semantics for the default path; the LRU is the minimal, behavior-preserving fix and is recommended first.
- No docs need updating — `_cursors` is private and undocumented. If the team later adds a metrics field for router state, expose `len(self._cursors)` so this class of leak becomes observable.

## Test
Add to `tests/test_phase3.py`. This drives the router directly (no network) and fails today (map grows to 5000) and passes after the fix (map capped at `_MAX_CURSORS`).

```python
# tests/test_phase3.py
from vampire.models import Node, ModelCard, RouteTarget
from vampire.registry import NodeRegistry
from vampire.router import Router, _MAX_CURSORS


def test_round_robin_cursor_map_is_bounded_under_distinct_virtual_models():
    """Distinct client-supplied virtual-model names must not grow router state without limit."""
    reg = NodeRegistry()
    reg.add(
        Node(
            id="n1",
            lmstudio_base_url="http://localhost:1234",
            status="online",
            models=[ModelCard(id="m1")],
        )
    )
    router = Router(reg)

    # Simulate an attacker (or a buggy templatizing client) sending many distinct
    # ``vampire:<n>`` model names, each producing an ephemeral ``default:<model>`` id.
    n_distinct = _MAX_CURSORS + 1000
    for i in range(n_distinct):
        policy = router.default_policy(f"vampire:probe-{i}", strategy="round_robin",
                                       requested_model=f"vampire:probe-{i}")
        sel = router.select(policy, requested_model=f"vampire:probe-{i}")
        assert sel is not None  # one online node => a candidate always exists

    # Before the fix this is == n_distinct (unbounded). After the fix it is capped.
    assert len(router._cursors) <= _MAX_CURSORS, (
        f"router cursor map grew to {len(router._cursors)} entries "
        f"for {n_distinct} distinct client model names (unbounded leak)"
    )
```

A complementary assertion that the *hot* route keeps rotating correctly after the cache churns (guards against the eviction breaking real round-robin):

```python
def test_hot_route_keeps_rotating_after_cursor_eviction():
    reg = NodeRegistry()
    for nid in ("a", "b"):
        reg.add(Node(id=nid, lmstudio_base_url=f"http://{nid}:1234",
                     status="online", models=[ModelCard(id="m")]))
    router = Router(reg)

    hot = router.default_policy("vampire:hot", requested_model="vampire:hot")
    first = router.select(hot, requested_model="vampire:hot").target.node

    # Churn the cache past capacity with cold one-off names.
    for i in range(_MAX_CURSORS + 50):
        cold = router.default_policy(f"vampire:cold-{i}", requested_model=f"vampire:cold-{i}")
        router.select(cold, requested_model=f"vampire:cold-{i}")

    # The hot route must still alternate between the two nodes on consecutive hits.
    seen = {router.select(hot, requested_model="vampire:hot").target.node for _ in range(4)}
    assert seen == {"a", "b"}, "hot route lost round-robin coverage after cache churn"
    assert first in {"a", "b"}
```

## Effort & risk
- **Lines changed:** ~12 in `src/vampire/router.py` (import swap, `__init__`, `_round_robin`, one module constant). One file touched in source; ~35 lines added in `tests/test_phase3.py`.
- **Backward-compat:** none broken. The public `Selection`/`select`/`default_policy` API is unchanged; `_cursors` is private. Round-robin output is identical for all routes within the LRU window; only cold, evicted ids reset their rotation to index 0, which is already non-deterministic from a client's perspective.
- **Risk:** very low. `OrderedDict.move_to_end`/`popitem(last=False)` are O(1) and the per-request overhead is negligible. The only behavioral change is the intended one (bounded memory). Consider documenting `_MAX_CURSORS` as tunable via settings if operators run very large configured-route fleets, though 4096 comfortably exceeds realistic stable-route counts.

---
- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~231k tok (sum of per-call `in=`, which double-counts conversation history across the run — treat as a loose upper bound) · output ~9k tok · est. cost ~$4.14 · run started 18:24 finished 18:27. Marked estimated; derived from `~/.hermes/logs/agent.log` for session `cron_c11148734d14_20260614_182447`.
