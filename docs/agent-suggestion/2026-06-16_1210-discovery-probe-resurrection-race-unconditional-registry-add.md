# `discover_nodes._probe` suffers from a "resurrection" race condition: unconditional `registry.add` after `await refresh_node` allows a deleted node to be re-added to the registry.

- **Severity:** High — This is a direct consequence of the `refresh_node` fix, reintroducing a bug class that was already addressed. It can cause deleted nodes to reappear in the system, violating the expectation that a `DELETE` operation is final.
- **Category:** concurrency
- **Summary:** The `_probe` function in `src/vampire/cluster.py` performs an `await` on `refresh_node` and subsequently calls `registry.add(refreshed)` without verifying if the node still exists in the registry. If a node is removed from the registry via the Control API during the asynchronous refresh, the `_probe` function will unconditionally re-add it, resurrecting the deleted node.
- **Location:** `src/vampire/cluster.py:397`
- **Evidence:**
```python
# src/vampire/cluster.py:376-402
async def _probe(base_url: str) -> Node | None:
    node_id = _node_id_for_url(base_url)
    current = registry.get(node_id)
    # ... (omitted)
    node = current or Node(...)
    # ...
    async with semaphore:
        if client is not None:
            return await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
        else:
            return await refresh_node(node, timeout_ms=request.timeout_ms)
    if refreshed.status != "online":
        return None
    if request.trusted_only and not refreshed.trusted:
        return None
    registry.add(refreshed) # <--- Unconditional re-addition
```
1. `_probe` captures the current state or creates a new node.
2. It `await`s `refresh_node`, which is an I/O bound operation.
3. During this `await`, a user calls `DELETE /vampire/v1/nodes/{id}`, which removes the node from the registry.
4. Once `refresh_node` completes, `_probe` continues and calls `registry.add(refreshed)`, which adds the node back into the registry even though it was explicitly deleted.
- **Impact:** This creates a race condition where `DELETE` operations can be effectively ignored if a discovery/refresh scan is currently probing the node. It violates the integrity of the node lifecycle.
- **Fix:**
```python
# before
registry.add(refreshed)

# after
if registry.get(refreshed.id) is not None:
    registry.add(refreshed)
```
*Note: This ensures that if the node was removed while the async refresh was in progress, the discovery probe does not resurrect it.*
- **Test:**
```python
import pytest
import asyncio
from vampire.registry import registry
from vampire.cluster import _probe, _node_id_for_url
from vampire.models import Node
import httpx

@pytest.mark.asyncio
async def test_probe_prevents_resurrection(monkeypatch):
    node_id = "test-resurrection"
    node = Node(id=node_id, lmstudio_base_url="http://localhost:1234", status="online")
    registry.add(node)

    # Mock refresh_node to sleep so we can delete the node during the await
    async def slow_refresh(n, **kwargs):
        await asyncio.sleep(0.1)
        return n.model_copy(update={"status": "online"})
    
    import vampire.cluster as cluster
    monkeypatch.setattr(cluster, "refresh_node", slow_refresh)
    monkeypatch.setattr(cluster, "_candidate_urls", lambda request: ["http://localhost:1234"])

    # 1. Start probe
    probe_task = asyncio.create_task(cluster._probe("http://localhost:1234"))
    
    # 2. Wait for it to hit the sleep in slow_refresh
    await asyncio.sleep(0.05)
    
    # 3. Delete the node from registry
    registry.remove(node_id)
    assert registry.get(node_id) is None

    # 4. Wait for probe to finish
    await probe_task

    # 5. Assert node is STILL gone
    assert registry.get(node_id) is None, "Node was resurrected!"
```
- **Effort & risk:** 1 line changed in `src/vampire/cluster.py`. Extremely low risk.
- **Scout link:** AOI-C from `2026-06-15_1818-strategic-scout-lifecycle-namespace-and-config-drift.md`

## Opus 4.8 Advice

The diagnosis is correct: `_probe` (cluster.py:398) calls `registry.add(refreshed)`
unconditionally, even though `refresh_node` itself already carries the matching guard
(`if registry.get(updated.id) is not None`, cluster.py:226). So a node deleted during the
probe's network `await` is resurrected by `_probe`'s own add. Good catch, and mirroring the
existing `refresh_node` guard is the right instinct.

**But the proposed one-line fix is wrong — it silently breaks discovery of brand-new nodes.**
For a newly discovered URL, `current = registry.get(node_id)` is `None` (cluster.py:378), the
node is constructed fresh and is *not* in the registry. `refresh_node`'s line-226 guard
therefore declines to add it, which means `_probe`'s `registry.add(refreshed)` at line 398 is
the **only** code path that registers a newly discovered node. Guarding that add on prior
existence (`if registry.get(refreshed.id) is not None`) makes discovery a no-op for every node
that wasn't already known — exactly the nodes discovery exists to find.

The fix must distinguish "pre-existing node deleted mid-probe" (don't resurrect) from "genuinely
new node" (must add). Capture existence up front and branch on it:

```python
existed = current is not None  # captured before the await
...
if existed and registry.get(refreshed.id) is None:
    return None  # deleted during probe — do not resurrect
registry.add(refreshed)
return refreshed
```

Further notes:
- Keep the `registry.get` check and the `registry.add` adjacent with **no `await` between
  them** so they are atomic under single-threaded asyncio (the same discipline the
  `refresh_node` guard relies on). Any logging/`await` inserted between reintroduces the race.
- This bug shares an owner with suggestion `0930` (refresh clobber) and the `refresh_node`
  line-226 guard: three call sites perform read-then-add against the registry. The clean
  resolution is to make `refresh_node` the *single* writer that merges health onto the current
  registry node, and have `_probe` only add when it discovered a genuinely new node. Coordinate
  the two fixes rather than landing them independently.
- Add a regression test for the new-node case (a previously-unknown URL that comes back
  `online` must end up registered). The supplied resurrection test alone would pass even with
  the broken guard, hiding the discovery regression.

- **Receipt (estimated):** model `google/gemma-4-26b-a4b-qat` (lmstudio) · input ~2000 tok · output ~1200 tok · run started 12:10 finished 12:12. _(Estimated from agent.log in=/out= for this run.)_
