# `PATCH /vampire/v1/nodes/{id}` silently un-drains a node: any unrelated field update re-probes health and flips a `draining`/`disabled`/`maintenance` node back to `online`

- **Severity:** High — `patch_node` honors a manual-unavailable status *only* on the request that sets it. Any subsequent partial patch that does **not** carry a `status` field (e.g. `--tag gpu`, `--trusted`, `--tokens-per-second`) triggers `refresh_node`, which unconditionally overwrites `status` with `online`/`offline` from a live probe. A node the operator deliberately pulled out of routing for maintenance is silently returned to the routing pool and starts serving traffic again, with no error and no warning. Not Critical only because it requires an authenticated control-plane call and the node must still answer `/v1/models`; but it is a direct violation of the documented drain/maintenance contract and is trivially reachable from the shipped `vampire nodes update` CLI.
- **Category:** api-correctness (node lifecycle / state-machine contract) — with a secondary error-handling dimension: the operator's intent is discarded without any signal.

## Summary

`patch_node` (`control.py:82-90`) applies the patch, then short-circuits the health re-probe **only when the incoming patch itself sets `status` to a manual-unavailable value** (`draining`/`disabled`/`maintenance`). It never consults the node's *current* status. So when an operator patches an unrelated field on an already-drained node, `patch.status` is `None`, the guard is skipped, and `refresh_node` runs and clobbers `status` back to `online` (or `offline`). The node silently re-enters the router's candidate set (`router._candidates` keeps only `status == "online"`), defeating the drain. The same gap exists for `disabled` and `maintenance`. The `drain` CLI verb and the generic `nodes update` CLI verb both route through this handler, so the resurrection is reachable end-to-end from the product CLI.

## Location

- `src/vampire/api/control.py:82-90` — `patch_node` (the offending guard).
- `src/vampire/api/control.py:34` — `MANUAL_UNAVAILABLE_STATUSES = {"draining", "disabled", "maintenance"}`.
- Drain semantics depended upon: `src/vampire/router.py:96-102` (`_candidates` keeps `node.status == "online"` only) and `src/vampire/router.py:80-88` (`default_policy` likewise filters `node.status == "online"`).
- Status-clobbering writer: `src/vampire/cluster.py:172-200` (`refresh_node` always sets `status` to `"online"`/`"offline"`).
- CLI entry points: `src/vampire/cli.py:116-150` (`_nodes_update`, `_nodes_drain`).

## Evidence

The guard only inspects the *incoming patch*, never the stored node (`src/vampire/api/control.py:82-90`):

```python
@router.patch("/nodes/{node_id}")
async def patch_node(node_id: str, patch: NodeUpdate, request: Request) -> dict[str, Any]:
    """Partially update a registered node and refresh its health metadata."""
    node = registry.update(node_id, patch)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    if patch.status in MANUAL_UNAVAILABLE_STATUSES:          # <-- only the *patch* is checked
        return node.model_dump()
    return (await refresh_node(node, client=_request_http_client(request))).model_dump()
```

`refresh_node` unconditionally rewrites `status` (`src/vampire/cluster.py:172-193`):

```python
        updated = node.model_copy(
            update={
                "status": "online",          # success path
                ...
            }
        )
    except (httpx.HTTPError, ValueError) as exc:
        ...
                "status": "offline",         # failure path
```

So whatever the operator set is overwritten. The router treats only `online` nodes as candidates (`src/vampire/router.py:96-102`):

```python
    def _candidates(self, policy: RoutePolicy) -> list[RouteTarget]:
        """Return online targets whose nodes are currently registered."""
        return [
            target
            for target in policy.targets
            if (node := self._registry.get(target.node)) is not None and node.status == "online"
        ]
```

### Step-by-step manifestation

1. Operator drains a node for maintenance:
   `vampire nodes drain node-a` → `PATCH /vampire/v1/nodes/node-a {"status": "draining"}`.
   `patch.status == "draining"` is in `MANUAL_UNAVAILABLE_STATUSES`, so the handler returns without probing. `node-a.status == "draining"`. The router now excludes it. **Correct.**
2. While the node is drained, the operator (or an automation/dashboard) issues *any* unrelated update — for example tagging the box being serviced:
   `vampire nodes update node-a --tag gpu` → `PATCH /vampire/v1/nodes/node-a {"tags": ["gpu"]}`.
   `_nodes_update` (`cli.py:116-134`) only includes non-`None` fields, so the body carries **no** `status`. Thus `patch.status is None`.
3. In `patch_node`, `None not in MANUAL_UNAVAILABLE_STATUSES`, so the guard is skipped and `await refresh_node(node, ...)` runs.
4. `node-a` is still a healthy LM Studio box (it is under *maintenance*, not down — e.g. the operator is swapping a disk in a sibling machine, or simply re-tagging). `/v1/models` answers 200, so `refresh_node` sets `status = "online"`.
5. `registry.add(updated)` persists `status == "online"`. `node-a` is now back in `_candidates`, and the very next `vampire:auto` request can be routed to the machine the operator believed was drained.

The operator receives a normal `200` with `{"tags": ["gpu"], "status": "online", ...}`; the `status` flip is buried in the response and there is no error or warning. The same sequence resurrects `disabled` and `maintenance` nodes.

**Contract this violates.** The handler explicitly encodes a "manual unavailable" state machine (`MANUAL_UNAVAILABLE_STATUSES`, `control.py:34`) whose purpose is to keep a node out of routing regardless of health. The drain CLI (`cli.py:142-150`) is documented as "Mark a node unavailable for routing … or restore it." Restoration is an explicit operator action (`vampire nodes drain node-a off` → `{"status": "online"}`); nothing in the contract says an unrelated metadata edit should restore it. The existing test `test_drained_node_stays_registered_but_is_not_route_candidate` (`tests/test_phase3.py:231-255`) only checks the drain transition and an *explicit* restore — it never patches an unrelated field on a drained node, so the gap is uncovered.

## Impact

- **What the operator observes:** A node taken down for maintenance silently rejoins the routing pool the moment any other attribute is patched (tagging, trust changes, capacity hints, throughput updates — all common during maintenance). Inference requests get routed to a machine that is supposed to be offline for service.
- **Blast radius:** Any deployment that uses drain/disable/maintenance for safe rolling maintenance — the headline operational feature of a LAN load-balancer. The control and data planes share one process (default), so a routed request immediately follows the resurrected `online` status. If the box is mid-reboot or its GPU is being pulled, those requests fail or hang; if it is serving stale/partial models, clients get wrong answers.
- **When it triggers:** Every `PATCH` (or `vampire nodes update`) on a node currently in a manual-unavailable state that does not itself re-set `status`. This is the *normal* way to edit node metadata, so the trap is easy to hit.

## Fix

Consult the node's *current* status, not just the incoming patch. When the patch does not explicitly change `status` and the stored node is already in a manual-unavailable state, preserve that state and skip the health probe. Explicit re-activation (`{"status": "online"}`) is unaffected because then `patch.status is not None`.

Before (`src/vampire/api/control.py:82-90`):

```python
@router.patch("/nodes/{node_id}")
async def patch_node(node_id: str, patch: NodeUpdate, request: Request) -> dict[str, Any]:
    """Partially update a registered node and refresh its health metadata."""
    node = registry.update(node_id, patch)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
        return node.model_dump()
    return (await refresh_node(node, client=_request_http_client(request))).model_dump()
```

After:

```python
@router.patch("/nodes/{node_id}")
async def patch_node(node_id: str, patch: NodeUpdate, request: Request) -> dict[str, Any]:
    """Partially update a registered node and refresh its health metadata.

    A node placed in a manual-unavailable state (draining/disabled/maintenance)
    stays there until the operator explicitly transitions it. An unrelated
    metadata patch must NOT re-probe health and silently flip it back online.
    """
    node = registry.update(node_id, patch)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    # An explicit patch into a manual-unavailable state wins and skips the probe.
    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
        return node.model_dump()
    # A patch that does not set status must not resurrect a node the operator
    # already drained/disabled/put into maintenance: preserve that status
    # instead of letting refresh_node overwrite it with the live probe result.
    if patch.status is None and node.status in MANUAL_UNAVAILABLE_STATUSES:
        return node.model_dump()
    return (await refresh_node(node, client=_request_http_client(request))).model_dump()
```

**Invariant preserved:** a node in `MANUAL_UNAVAILABLE_STATUSES` leaves that state only via an explicit `status` patch (the existing `restore` path `{"status": "online"}` still re-probes and comes back healthy, exactly as `test_drained_node_stays_registered_but_is_not_route_candidate` expects). No `# type: ignore` involved. No docs require changes, though `docs/command/nodes.md` could note that metadata edits do not alter a drained node's routing eligibility.

## Test

Add to `tests/test_phase3.py` (uses the existing `client` fixture whose mock `/v1/models` always returns `200`, so an erroneous re-probe would flip the node to `online`). This fails today (`status == "online"`) and passes after the fix:

```python
def test_patch_unrelated_field_does_not_undrain_node(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )

    drained = client.patch("/vampire/v1/nodes/node-a", json={"status": "draining"})
    assert drained.json()["status"] == "draining"

    # Editing unrelated metadata must NOT re-probe health and resurrect the node.
    body = client.patch("/vampire/v1/nodes/node-a", json={"tags": ["gpu"]}).json()
    assert body["tags"] == ["gpu"]
    assert body["status"] == "draining"  # fails today: refresh_node returns "online"

    # And it must stay out of the router's candidate set.
    assert registry.get("node-a").status == "draining"
    assert (
        Router(registry).select(
            RoutePolicy(
                id="r",
                virtual_model="vampire:auto",
                targets=[RouteTarget(node="node-a", model="node-a-model")],
            )
        )
        is None
    )

    # Explicit restore still re-probes and brings it back online.
    restored = client.patch("/vampire/v1/nodes/node-a", json={"status": "online"})
    assert restored.json()["status"] == "online"
```

## Effort & risk

- **Lines changed:** ~6 added in `src/vampire/api/control.py` (one guard clause + docstring), ~25 lines for the new test.
- **Files touched:** `src/vampire/api/control.py`; `tests/test_phase3.py` (optionally a note in `docs/command/nodes.md`).
- **Backward-compat:** Behavior changes *only* for patches issued against a node already in a manual-unavailable state that do not themselves set `status`. Previously those silently re-onlined the node; now they preserve operator intent. Explicit `{"status": ...}` transitions, normal patches on healthy nodes, and the existing drain/restore tests are unaffected. Low risk.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~1,267,753 tok · output ~14,285 tok · est. cost ~$20.09 · run started 01:00 finished 03:20. Marked estimated — input figure sums per-call `in=` from `agent.log` and is inflated by uncached cumulative context (large prompt-cache hit rates on later calls mean true billed cost is materially lower); long wall-clock gaps are upstream stream-retry timeouts, not compute.
