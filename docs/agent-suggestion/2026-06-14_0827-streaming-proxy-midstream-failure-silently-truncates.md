# Mid-stream upstream failure in the proxy silently truncates the SSE body with no error frame, breaking the streaming/error contract the module claims to uphold — and no test exercises it

**Severity:** High — justification: this is the gateway's core data path (`/v1/chat/completions` streaming is the single most-used endpoint of an OpenAI-compatible proxy). A failure here is *silent*: the client receives HTTP 200, a partial answer, **no** terminating `data: [DONE]`, and **no** error envelope. OpenAI-compatible SDKs treat the truncated stream as a *successful, complete* response, so the bug manifests as fabricated/cut-off model output with zero error signal — the worst failure mode for a trust-critical proxy. It is not Critical only because it requires the upstream LM Studio node to drop the connection mid-generation (crash, OOM-kill, network blip, node drained mid-stream) rather than occurring on every request; but on a flaky LAN of consumer GPUs that is a routine event, not a rare one.

**Category:** error-handling contract violation / testing gap / code-vs-doc drift

**Summary:** `proxy_request_with_body` carefully converts a *connect-time* upstream failure into a clean OpenAI-compatible `502 vampire_upstream_error` envelope (proxy.py:145-153), but the symmetric *mid-stream* failure is completely unhandled: once the first byte has been yielded, the response status (200) and headers are already on the wire, and an exception raised by `upstream.aiter_raw()` simply propagates out of the `body_stream()` async generator (proxy.py:155-163). Starlette can no longer change the status, so it aborts the TCP connection, leaving the client with a truncated SSE stream that has no `data: [DONE]` sentinel and no `{"error": ...}` frame. The module docstring claims it "preserves OpenAI-compatible streaming (DESIGN-API.md §20) and the OpenAI error format (DESIGN-API.md §23)", and §20 mandates the `data: [DONE]` terminator — but neither contract holds on the failure path, and the entire Phase 1 test suite only ever exercises a mock that streams to clean completion, so the gap is invisible to CI.

**Location:** `src/vampire/proxy.py:155-163` (the `body_stream()` inner generator), with the asymmetry visible against `src/vampire/proxy.py:143-153` (the handled connect-time path). Test gap: `tests/test_phase1.py:162-173` (`test_chat_completion_streaming_passthrough`) is the only streaming test and never fails mid-stream.

**Evidence:**

The connect-time failure is handled — note the `except httpx.RequestError` that produces a clean envelope:

```python
# proxy.py:143-153
try:
    upstream = await client.send(upstream_request, stream=True)
except httpx.RequestError as exc:
    if should_close_client:
        await client.aclose()
    # Log the underlying cause server-side; do not leak internals to clients.
    logger.warning("Downstream LM Studio node %s unreachable: %r", base_url, exc)
    response = _upstream_error(f"Could not reach downstream LM Studio node at {base_url}.")
    if response_headers:
        response.headers.update(response_headers)
    return response
```

But the mid-stream relay has **no `except`** — only a `finally` that closes sockets:

```python
# proxy.py:155-163
async def body_stream() -> AsyncIterator[bytes]:
    """Relay upstream bytes and close both sides of the upstream connection."""
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        await upstream.aclose()
        if should_close_client:
            await client.aclose()
```

`httpx.AsyncClient.send(..., stream=True)` returns *after only the response headers are read*; the body is pulled lazily by `aiter_raw()`. If the upstream node dies after the headers but during generation, `aiter_raw()` raises `httpx.RemoteProtocolError` (peer closed connection without a proper terminating chunk), `httpx.ReadError`, or `httpx.ReadTimeout`. None of these are caught here.

Step-by-step manifestation:
1. Client sends `POST /v1/chat/completions` with `"stream": true`.
2. `chat_completions` → `_route_or_proxy` → `proxy_request_with_body`. `client.send(...)` succeeds (the node accepted the request and returned `200 text/event-stream` headers).
3. `StreamingResponse(body_stream(), status_code=200, ...)` is returned. **FastAPI immediately commits status 200 and the response headers to the client socket** and begins iterating the generator.
4. A few chunks stream through fine. Then the LM Studio node is OOM-killed / its process crashes / the Wi-Fi drops / an operator runs `vampire nodes drain` and the box is power-cycled.
5. The next `async for chunk in upstream.aiter_raw()` raises `httpx.RemoteProtocolError`. The `finally` runs `aclose()`, then the exception propagates out of `body_stream`.
6. Starlette's `StreamingResponse` is mid-body; it cannot emit a 5xx (status already sent). It logs the exception server-side and tears down the client connection.
7. The OpenAI Python SDK on the other end sees the stream end **without** a `data: [DONE]` line and **without** an error object. Depending on version it either returns the partial accumulated text as if complete, or raises a generic transport error — but it never receives the structured `vampire_upstream_error` the gateway emits for the *connect-time* version of the very same failure. The user gets a silently truncated answer.

This also drifts from the spec the code cites. DESIGN-API.md §20 ("20. Streaming behavior"):

```txt
For normal streaming, preserve OpenAI-compatible Server-Sent Events.

data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

data: [DONE]
```

The `[DONE]` sentinel is the documented contract; the failure path never emits it. And §23's OpenAI error envelope — which `_upstream_error` honors for connect failures — is silently skipped mid-stream.

**Impact:**
- Silent data-integrity failure on the hottest endpoint: clients accept truncated generations as complete. For a project whose entire value proposition is being a *transparent, trustworthy* OpenAI-compatible gateway, "looks like a complete answer but isn't" is the highest-cost defect class.
- Operators get no client-visible signal; they must correlate against server logs (and the only log here is whatever Starlette emits for an unhandled task exception, not the purposeful `logger.warning` used for connect failures), so MTTR on flaky-node incidents is high.
- The asymmetry actively misleads future maintainers: the connect-time handling "proves" upstream errors are covered, while the mid-stream hole hides behind a green test suite.
- It guarantees a latent regression surface for Phase 3 routing/failover: you cannot implement mid-stream failover or even correct metrics (`error_count`) for streamed requests on top of a relay that swallows the very exception that signals the failure.

**Fix:** Catch streaming errors inside `body_stream()` and convert them into a *valid in-band SSE error frame followed by the mandated `data: [DONE]` sentinel*, so OpenAI-compatible clients receive a terminated stream carrying a structured error instead of a silent truncation. (We cannot change the HTTP status once bytes are flushed; emitting an error event + `[DONE]` is the OpenAI-compatible way to signal a mid-stream failure and satisfies §20's terminator requirement.) Log server-side with the same intent as the connect-time path. Only synthesize the SSE error frame when the response is actually an event stream; for a non-SSE response (e.g. a large non-streamed JSON body that gets cut) re-raise after logging, since injecting `data:` lines into JSON would corrupt it — there is no clean in-band recovery for that case and a torn connection is the honest signal.

Before (proxy.py:155-163):

```python
async def body_stream() -> AsyncIterator[bytes]:
    """Relay upstream bytes and close both sides of the upstream connection."""
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        await upstream.aclose()
        if should_close_client:
            await client.aclose()
```

After:

```python
is_event_stream = (upstream.headers.get("content-type") or "").startswith(
    "text/event-stream"
)

async def body_stream() -> AsyncIterator[bytes]:
    """Relay upstream bytes, surfacing a mid-stream upstream failure as a
    terminated OpenAI-compatible SSE error instead of a silent truncation."""
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    except httpx.HTTPError as exc:
        # Headers/status are already on the wire, so we cannot emit a 502 here.
        # For SSE, the OpenAI-compatible contract (DESIGN-API.md §20/§23) is an
        # in-band error frame terminated by `data: [DONE]`; anything else is a
        # silent truncation. Mirror the connect-time path's server-side logging.
        logger.warning(
            "Downstream LM Studio node %s failed mid-stream: %r", base_url, exc
        )
        if is_event_stream:
            error_frame = json.dumps(
                {
                    "error": {
                        "message": (
                            f"Downstream LM Studio node at {base_url} "
                            "failed mid-stream."
                        ),
                        "type": "vampire_upstream_error",
                        "code": "upstream_stream_interrupted",
                    }
                }
            )
            yield f"data: {error_frame}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"
        else:
            # No safe in-band recovery for a partial non-SSE body; let the torn
            # connection be the signal rather than corrupting the payload.
            raise
    finally:
        await upstream.aclose()
        if should_close_client:
            await client.aclose()
```

Add `import json` to proxy.py's imports (it currently imports only `logging` and `httpx` at the top; `json` is not yet imported in this module). No `# type: ignore` is involved. Docs to update: none strictly required, but the module docstring's claim that it "preserves … the OpenAI error format (§23)" becomes *true* on the streaming path only after this fix — consider tightening the proxy.py docstring to note that mid-stream failures surface as an in-band SSE error + `[DONE]`.

**Test:** This regression test drives a mock upstream that emits a couple of good SSE chunks and then aborts the connection mid-stream (simulating a node crash). It **fails today** — currently the client either sees a truncated body with no error frame and no `[DONE]`, or the test harness surfaces the unhandled `RemoteProtocolError` — and **passes after the fix** because the gateway appends a `vampire_upstream_error` frame and the mandated `data: [DONE]` terminator. Add to `tests/test_phase1.py` (it reuses that file's `client` fixture / mock pattern):

```python
def test_streaming_upstream_abort_emits_error_frame_and_done() -> None:
    """A node that dies mid-stream must yield an in-band SSE error + [DONE],
    not a silent truncation (DESIGN-API.md §20/§23)."""
    import httpx
    import pytest
    from fastapi.testclient import TestClient

    import vampire.proxy as proxy
    from vampire.app import create_app

    class _AbortingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            # Peer closes the connection without a terminating chunk.
            raise httpx.RemoteProtocolError("peer closed connection mid-stream")

        async def aclose(self) -> None:
            return None

    class _AbortingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_AbortingStream(),
            )

    original = proxy.build_async_client
    proxy.build_async_client = lambda: httpx.AsyncClient(transport=_AbortingTransport())
    try:
        with TestClient(create_app()) as client:
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
        assert resp.status_code == 200
        body = resp.text
        # The first good chunk made it through...
        assert '"delta"' in body
        # ...and the failure was surfaced in-band rather than silently dropped.
        assert "vampire_upstream_error" in body
        assert "upstream_stream_interrupted" in body
        # ...and the stream is properly terminated per §20.
        assert body.rstrip().endswith("data: [DONE]")
    finally:
        proxy.build_async_client = original
```

(If `httpx.AsyncByteStream` iteration shape differs across the pinned httpx version, the same behavior can be driven with an `ASGITransport` mock app whose `text/event-stream` generator `raise`s after the first chunk — the assertions are what matter.)

**Effort & risk:** Low effort — ~25 lines in one inner function plus one import, and one regression test. Low risk: the change is additive on a path that is currently *unhandled*, so it cannot regress any passing case (the happy path still yields chunks then runs `finally` exactly as before). The only behavioral change is on the previously-silent failure path. Worth a quick check that the synthesized error frame's `content-type` matches what clients expect (it inherits the upstream `text/event-stream`, which is correct). Recommend pairing with a follow-up to increment the selected node's `error_count` on mid-stream failure once routing owns the node handle, but that is out of scope for this fix.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~221,000 tok · output ~5,000 tok · est. cost ~$3.69 · run started 08:24 finished 08:28. Estimated: agent.log interleaves several concurrent sessions, so input/output were summed from one full comparable deep-audit session (8 API calls, Σin≈220,944, Σout≈4,915) as a representative proxy for this run; priced at Opus input $15/1M + output $75/1M = 220944/1e6·15 + 4915/1e6·75 ≈ $3.31 + $0.37 ≈ $3.69.
