# `PATCH /vampire/v1/nodes/{id}` skips health refresh for metadata updates when node is in maintenance mode

- **Severity:** Medium — Metadata updates for nodes in `draining`, `disabled`, or `maintenance` status skip the health check/refresh cycle, violating the API's stated contract and preventing updates to `last_checked_at` and `status` when only non-status fields are modified.
- **Category:** api-correctness.
- **Summary:** The `patch_node` endpoint in `src/vampire/api/control.py` contains a conditional check that skips the `refresh_node` call if the incoming patch does not include a `status` field and the current node status is in `MANUAL_UNAVAILABLE_STATUSES`. While intended to avoid unnecessary probes for nodes intentionally taken offline, it prevents a `PATCH` request (e.g., updating a node's name or tags) from triggering a health check that would update its `last_checked_at` timestamp or transition it from `offline` to `online` if it has become reachable.
- **Location:** `src/vampire/api/control.py:99-100`
- **Evidence:**
```python
# src/vampire/api/control.py:98-101
98|    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
99|        return node.model_dump()
100|    if patch.status is None and node.status in MANUAL_UNAVAILABLE_STATUSES:
101|        return node.model_dump()
102|    refreshed = await refresh_node(node, client=_request_http_client(request))
```
1. If a user sends `PATCH /vampire/v1/nodes/node-123` with `{"name": "new-name"}`, `patch.status` is `None`.
2. If `node-123` is currently in `maintenance` status, line 100 evaluates to `True`.
3. The function returns `node.model_dump()` immediately, skipping the `refresh_node` call on line 102.
4. As a result, the node's `last_checked_at` is not updated, and the system cannot discover that the node has become reachable (status `online`) until a subsequent status-changing update or background refresh occurs.
- **Impact:** API consumers cannot reliably refresh node health metadata via metadata-only updates. This leads to stale `last_checked_at` timestamps and delayed detection of node recovery in the gateway's status views.
- **Fix:**
```python
# before
97|    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
98|        return node.model_dump()
99|    if patch.status is None and node.status in MANUAL_UNAVAILABLE_STATUSES:
100|        return node.model_dump()
101|    refreshed = await refresh_node(node, client=_request_http_client(request))

# after
97|    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
98|        return node.model_dump()
99|    refreshed = await refresh_node(node, client=_request_http_client(request))
```
*Note: Removing the second condition ensures that if the status is not being explicitly changed, we always perform the refresh as promised by the API contract.*
- **Test:**
```python
import pytest
from vampire.api.control import patch_node, router
from vampire.registry import registry
from vampire.models import Node, NodeUpdate

@pytest.mark.asyncio
async def test_patch_node_updates_metadata_and_refreshes_status():
    # 1. Setup: A node that is offline but reachable
    node = Node(id="test-node", lmstudio_base_url="http://localhost:1234", status="offline")
    registry.add(node)
    
    # 2. Act: Update only the name
    patch = NodeUpdate(name="Updated Name")
    # This should trigger a refresh_node call if fixed
    result = await patch_node("test-node", patch, None) 
    
    # 3. Assert: Check if metadata and health were updated
    assert result["name"] == "Updated Name"
    # Even if status remains 'offline' due to probe failure, 
    # last_checked_at should be updated (not null)
    assert result["last_checked_at"] is not None
```
- **Effort & risk:** 2 lines changed in 1 file. Low risk.

## Opus 4.8 Advice

This suggestion is the more accurate of the two siblings about this code block (cf. `1100`).
Crucially, the metadata is **not** lost: `registry.update(node_id, patch)` at control.py:93
merges and persists the patch *before* the early-return at lines 97-100 (see registry.py:29-38).
Only the `refresh_node` health probe — and therefore the `last_checked_at`/`status` update — is
skipped. So the real severity is low, and the framing here ("skips health refresh") is right
where `1100`'s ("silently fails to update metadata") is wrong.

Before removing the guard, decide whether skipping the probe is actually a bug. A node in
`maintenance`/`draining`/`disabled` was *deliberately* parked offline. Removing line 99-100 means
an unrelated edit (rename, retag) now probes the node and can flip it back to `online` — a
surprising side effect, and the inverse of what sibling suggestion `1720` was trying to prevent
(unintended un-draining). That is arguably worse than a stale timestamp.

Prefer a narrower fix that doesn't re-online a parked node:
- Stamp `last_checked_at` (or just return the freshly-merged node) without running the full
  probe for manual-unavailable statuses, **or**
- Gate the probe behind an explicit opt-in (e.g. `?refresh=true`) so metadata edits never
  silently change health state.

Also, resolve this together with `1100` — both target the same 4 lines; only one change should
land. And the included test will hit a real network call through `refresh_node`; stub the
transport the way the other `tests/test_phase2.py` cases do, and assert the *intended* behavior
(timestamp refreshed without an unintended `online` transition).

- **Receipt (estimated):** model `google/gemma-4-26b-a4b-qat` (lmstudio) · input ~1250 tok · output ~850 tok · run started 12:00 finished 12:05. _(Estimated from agent.log in=/out= for this run.)_
