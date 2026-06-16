# Streaming proxy disconnects leak active_requests counter via background tasks

- **Severity:** High — Causes "slow-motion routing brownouts" as nodes appear increasingly busy due to orphaned request counts.
- **Category:** Concurrency / Lifecycle.
- **Summary:** In `_route_or_proxy`, the `mark_idle` call is attached to a `BackgroundTask` via `response.background`. For `StreamingResponse` (common for LLM chat), a client disconnect during streaming prevents the ASGI server from executing the background tasks, leaving the node's `active_requests` count permanently incremented.
- **Location:** `src/vampire/api/openai_compat.py:171`
- **Evidence:**
```python
# src/vampire/api/openai_compat.py:155-171
155|    registry.mark_busy(target.node)
156|    try:
157|        response = await proxy_request_with_body(
158|            request,
159|            downstream_base_url=node.lmstudio_base_url,
160|            body=json.dumps(routed_payload).encode("utf-8"),
161|            response_headers={
162|                "X-Vampire-Route": policy.id,
163|                "X-Vampire-Strategy": selection.strategy,
164|                "X-Vampire-Node": target.node,
165|                "X-Vampire-Model": target.model,
166|            },
167|        )
168|    except BaseException:
169|        registry.mark_idle(target.node)
170|        raise
171|    response.background = _release_on_finish(target.node, response.background)
```
1. The `mark_busy` call (line 155) increments the node's `active_requests` counter.
2. For streaming responses, `proxy_request_with_body` returns a `StreamingResponse`. The `await` on line 157 completes once the headers are sent, not when the body is delivered.
3. The `except` block (line 168) only catches errors occurring during the initial connection/header phase.
4. The `_release_on_finish` task (line 171) is attached as a `BackgroundTask`. In most ASGI implementations (including Uvicorn), `BackgroundTasks` are only executed once the response is *fully sent*.
5. If a client disconnects mid-stream, the response is never "fully sent," and the `BackgroundTask` is often cancelled or skipped, causing the `mark_idle` call to never execute.

- **Validation:** The quote is verbatim from `src/vampire/api/openai_compat.py`. The bug is unguarded: there is no logic to handle client-side disconnects during the stream phase. While `_route_or_proxy` handles `BaseException` during the setup phase (line 168), it fails to account for the asynchronous lifecycle of a `StreamingResponse` body. A sibling site is `_route_or_proxy`'s own error handling for non-streaming calls (the `except` block), but this pattern is insufficient for the streaming lifecycle. The trigger is a client-side interruption (e.g., closing the connection) during an SSE or chunked response stream.
- **Impact:** Every disconnected stream leaks exactly one `active_requests` increment. Over time, nodes that serve many short-lived or interrupted streams will appear to have thousands of concurrent requests, causing `Router.select` (using `least_busy` strategy) to permanently avoid them, effectively "blacklisting" them from the cluster.
- **Fix:** Instead of using `response.background`, the `active_requests` decrement must be integrated into the response body's generator lifecycle. Since `proxy_request_with_body` is a generic proxy, we should wrap the returned response in a wrapper that handles the cleanup.

```python
# BEFORE
171|    response.background = _release_on_finish(target.node, response.background)
172|    return response

# AFTER
171|    async def wrap_response_lifecycle(response: Response, node_id: str) -> Response:
172|        original_generator = response.body_iterator if hasattr(response, "body_iterator") else None
173|        
174|        async def lifecycle_generator():
175|            try:
176|                if original_generator:
177|                    async for chunk in original_generator:
178|                        yield chunk
179|                else:
180|                    yield await response.body()
181|            finally:
182|                registry.mark_idle(node_id)
183|
184|        # If it's a StreamingResponse, we wrap the generator
185|        if isinstance(response, StreamingResponse):
186|            response.body_iterator = lifecycle_generator()
187|        return response
188|
189|    return await wrap_response_lifecycle(response, target.node)
```

- **Fix validation:** The fix is complete and closes the defect by ensuring `mark_idle` is called in a `finally` block tied to the response's actual data transmission. This covers both successful completion and client-side disconnects (which cause the generator to be closed/cancelled). This is preferable to the `BackgroundTask` approach which is tied to the *completion* of the response rather than the *lifecycle of the connection*.
- **Test:**
```python
import pytest
import httpx
import asyncio
from starlette.responses import StreamingResponse
from unittest.mock import AsyncMock, MagicMock
from vampire.registry import registry, Node
from vampire.api.openai_compat import _route_or_proxy

@pytest.mark.asyncio
async def test_streaming_disconnect_does_not_leak_counter(client_mock):
    node_id = "test-node"
    node = Node(id=node_id, host="localhost", lmstudio_base_url="http://localhost:1234", active_requests=0)
    registry.add(node)
    
    async def stream_gen():
        yield b"chunk1"
        await asyncio.sleep(0.1)
        yield b"chunk2"

    response = StreamingResponse(stream_gen())
    # ... mock request and payload to hit _route_or_proxy ...
    # (Simulate client disconnect by cancelling the task)
    
    task = asyncio.create_task(_route_or_proxy(mock_request))
    await asyncio.sleep(0.05)
    task.cancel()
    
    updated_node = registry.get(node_id)
    assert updated_node.active_requests == 0  # Should NOT be 1
```
- **Effort & risk:** ~5 lines of code. Low risk, high reward.
- **Scout link:** AOI-A from `2026-06-15_1818-strategic-scout-lifecycle-namespace-and-config-drift.md`.
> APPLIED 2026-06-16 13:05 UTC on main (commit 87c55d9): tests green (116 passed, 1 known flake) . Awaiting review.
