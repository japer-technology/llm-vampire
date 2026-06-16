# `PATCH /vampire/v1/nodes/{id}` silently fails to update metadata when node is in maintenance/draining status

- **Severity:** Medium — Prevents users from updating node metadata (tags, capabilities, name, etc.) while a node is in a `draining` or `maintenance` state, as the update is silently discarded.
- **Category:** api-correctness.
- **Summary:** The `patch_node` endpoint in `control.py` contains logic that checks if a node's status is in `MANUAL_UNAVAILABLE_STATUSES`. If a user submits a patch that does not include a `status` field (meaning they only want to update other fields like `tags`), but the node is currently in a maintenance state, the request is silently ignored and the original node is returned. This breaks the expectation that partial updates should work regardless of the current status, unless the status itself is being changed.
- **Location:** `src/vampire/api/control.py:98-101`
- **Evidence:**
```python
# src/vampire/api/control.py:98-101
98:    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
99:        return node.model_dump()
100:    if patch.status is None and node.status in MANUAL_UNAVAILABLE_STATUSES:
101:        return node.model_dump()
```
1. When a client sends `PATCH /vampire/v1/nodes/{id}` with `{"tags": ["new-tag"]}`, the `patch.status` field is `None`.
2. If the node in the registry is currently in `"maintenance"` status, `node.status in MANUAL_UNAVAILABLE_STATUSES` evaluates to `True`.
3. Line 100 triggers, and the function returns the current state of the node (`node.model_dump()`) without applying the `patch` to the registry.
4. The user receives a `200 OK` with the old data, and the requested tag update is lost.

- **Impact:** Users cannot perform administrative maintenance (e.g., updating node tags for routing or updating capabilities) on a node without first taking it offline or using an explicit status change. This results in "silent failures" where updates appear successful but are never applied. The blast radius is all users interacting with the Control API on nodes in `draining`, `disabled`, or `maintenance` status.
- **Fix:** The check should only return early if the user is *attempting to change the status* to something else, or it should simply be removed to allow metadata updates. The minimal fix is to allow the update to proceed if `patch.status` is `None`.

**Before** (src/vampire/api/control.py:98-101):
```python
    if patch.status in MANUAL_UNAVAILABLE_STATUSes:
        return node.model_dump()
    if patch.status is None and node.status in MANUAL_UNAVAILABLE_STATUSES:
        return node.model_dump()
    refreshed = await refresh_node(node, client=_request_http_client(request))
```

**After**:
```python
    # If status is not being changed, we don't need to skip the refresh/return early.
    # We only block the refresh if the user is attempting to set it to an unavailable status.
    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
        return node.model_dump()
    
    # If status is None, the user is only updating other fields;
    # we should proceed to refresh and return the updated node.
    refreshed = await refresh_node(node, client=_request_http_client(request))
```

- **Test:**
```python
import pytest
import httpx
from vampire.api.control import router, registry, Node, NodeUpdate
from starlette.applications import Starlette
from fastapi.testclient import TestClient

# Mocking environment for testing
app = Starlette()
app.add_router(router)
client = TestClient(app)

def test_patch_tags_on_maintenance_node():
    from vampire.models import Node, NodeUpdate
    from vampire.api.control import MANUAL_UNAVAILABLE_STATUSES
    
    # 1. Setup: Register a node in maintenance mode
    node_id = "test-node"
    node = Node(id=node_id, name="Test Node", lmstudio_base_url="http://localhost:1234", status="maintenance", tags=[])
    registry.add(node)
    
    # 2. Action: Attempt to update tags without changing status
    payload = {"tags": ["new-tag"]}
    response = client.patch(f"/vampire/v1/nodes/{node_id}", json=payload)
    
    # 3. Assertion
    assert response.status_code == 200
    updated_node = registry.get(node_id)
    assert "new-tag" in updated_node.tags, "Tags were not updated! (Silent failure)"
    assert updated_node.status == "maintenance"
```

- **Effort & risk:** ~5 lines changed in `src/vampire/api/control.py`. Low risk; the fix simply allows metadata updates on maintenance-status nodes. Backward-compatible.

---
- **Receipt (estimated):** model `google/gemma-4-26b-a4b-qat` (lmstudio) · input ~2K tok · output ~1.5K tok · run started 11:05 finished 11:06. _(Estimated from agent.log in=/out= for this run.)_
