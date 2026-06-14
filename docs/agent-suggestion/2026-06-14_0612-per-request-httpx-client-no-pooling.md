# A fresh `httpx.AsyncClient` is built and torn down on every proxied request, defeating connection pooling and adding a full TCP/TLS handshake to every model call

- **Severity:** High — on the gateway's single hottest path (`/v1/chat/completions`), it forces a brand-new TCP (and TLS, for `https` nodes) handshake per request, inflating tail latency and exhausting ephemeral ports/file descriptors under concurrent load; it is invisible in the localhost test suite, so it ships silently.
- **Category:** performance (with a secondary resource-leak / FD-exhaustion dimension).
- **Status:** Suggestion taken with notes.
- **Notes:** Implemented a lifespan-owned pooled `httpx.AsyncClient` and shared it through proxy and node-refresh paths when request state is available.
- **Summary:** `vampire.proxy.proxy_request_with_body` calls `build_async_client()` to create a *new* `httpx.AsyncClient` for every single request and `aclose()`s it after the response stream drains. httpx connection pooling and keep-alive are per-client, so a per-request client throws away the pool every time — each forwarded inference request pays a fresh connect (and TLS negotiation) to the downstream LM Studio node, and bursts of concurrent requests open an unbounded number of simultaneous client objects/sockets. The identical anti-pattern is duplicated in `cluster.refresh_node`, which `asyncio.gather`s one client-per-node on every `/v1/models` and `/vampire/v1/models` call.

- **Location:**
  - `src/vampire/proxy.py:51-57` (`build_async_client`), `:127` (per-request construction), `:138`, `:152-153` (teardown).
  - `src/vampire/cluster.py:151` and `:180` (`refresh_node` builds and closes one client per node).
  - `src/vampire/app.py:24-45` (`create_app` has no `lifespan`, so there is nowhere a long-lived client is created/owned/closed).

- **Evidence:**

  The client factory returns a fresh, fully-independent client object each call:

  ```python
  # src/vampire/proxy.py:51-57
  def build_async_client() -> httpx.AsyncClient:
      """Return the HTTP client used to reach downstream LM Studio nodes.

      Exposed as a seam so tests can inject a mock transport (a stand-in LM Studio
      server) without opening real network sockets.
      """
      return httpx.AsyncClient(timeout=_TIMEOUT)
  ```

  The hot path constructs one per request and closes it when the body stream finishes:

  ```python
  # src/vampire/proxy.py:127-153
  client = build_async_client()
  upstream_request = client.build_request(
      request.method,
      url,
      params=dict(request.query_params),
      headers=headers,
      content=body,
  )
  try:
      upstream = await client.send(upstream_request, stream=True)
  except httpx.RequestError as exc:
      await client.aclose()
      ...
  async def body_stream() -> AsyncIterator[bytes]:
      """Relay upstream bytes and close both sides of the upstream connection."""
      try:
          async for chunk in upstream.aiter_raw():
              yield chunk
      finally:
          await upstream.aclose()
          await client.aclose()        # <-- whole client (and its pool) discarded
  ```

  And the duplicate in the health-check fan-out:

  ```python
  # src/vampire/cluster.py:151, 180
  client = proxy.build_async_client()
  ...
  finally:
      await client.aclose()
  ```

  combined with the fan-out that creates N of them at once:

  ```python
  # src/vampire/cluster.py:186-193
  async def refresh_registered_nodes(*, timeout_ms: int | None = None) -> list[Node]:
      nodes = registry.list()
      if not nodes:
          return []
      return list(
          await asyncio.gather(*(refresh_node(node, timeout_ms=timeout_ms) for node in nodes))
      )
  ```

  **Why this is a real defect, step by step.** `httpx.AsyncClient` is explicitly documented as the pooling/keep-alive unit: it owns an `httpx.AsyncHTTPTransport` whose `httpcore` connection pool caches and reuses TCP connections across requests *made through that same client instance*. The official httpx docs state plainly: *"if you do anything more than experimentation, one-off scripts, or prototypes, then you should use a Client instance"* and warn that a new client per request means *"a new connection [is] established for each and every request."* Here:

  1. Request A arrives at `/v1/chat/completions`. `proxy_request_with_body` builds client A, opens a TCP connection to the LM Studio node, streams the completion, then `aclose()`s client A in the `finally` of `body_stream()`. The pooled keep-alive connection inside client A is destroyed with it.
  2. Request B arrives one millisecond later. It cannot reuse A's warm connection — A is gone. It builds client B and performs a *fresh* TCP three-way handshake (and, for an `https://` node, a fresh TLS handshake — multiple RTTs) before the first inference byte can flow.
  3. Under concurrency (say 50 simultaneous chat streams), 50 independent client objects exist at once, each holding ≥1 socket. Because streaming responses are long-lived (model generations can run for tens of seconds — note `read=None` at `proxy.py:48`), these clients are *not* short-lived; they pile up for the full duration of every in-flight generation. There is no shared pool ceiling (`max_connections`), so the only bound on concurrent sockets is the OS file-descriptor limit. When that is hit the gateway starts raising `OSError: [Errno 24] Too many open files` on `client.send`, which surfaces to the caller as a 502 `vampire_upstream_error` even though the node is perfectly healthy.
  4. `refresh_node` makes it worse on a different axis: every `/v1/models` call (proxy's `list_models` at `openai_compat.py:34` and control's `list_vampire_models` at `control.py:99`) fans out N clients simultaneously via `asyncio.gather`, again one-per-node, again each fully torn down. A dashboard polling `/vampire/v1/metrics`-adjacent endpoints multiplies this.

  This is invisible today because the entire test suite injects an in-process `ASGITransport` (`tests/test_phase1.py:114-117`), which has no sockets, no TCP, and no TLS — so the per-request-client cost is exactly zero in CI and the regression cannot be observed without a real socket server.

- **Impact:**
  - **Latency:** every forwarded request eats one extra TCP RTT to the node, and for any `https` LM Studio endpoint, a full TLS handshake (typically 2 RTTs) on top. On a LAN this is single-digit-ms; across the "wakes on the LAN / mesh layer" topologies the project's own docs advertise (`docs/use-case/01-lm-studio-mesh-layer.md`), or any remote/relayed node, this can add tens to hundreds of ms to *every* call — pure overhead that pooling would amortize to zero after the first request.
  - **Throughput / FD exhaustion:** with no shared pool and no `max_connections` limit, sustained concurrency scales sockets linearly and unbounded. Operators observe the gateway throwing 502s under load that look like node failures (`"Could not reach downstream LM Studio node"`) but are actually local FD exhaustion — a misleading and hard-to-diagnose blast radius affecting *all* nodes at once, not the one that "failed."
  - **Connection churn on the node:** LM Studio's server sees a new connection per request instead of reused keep-alives, increasing its accept/teardown overhead too.
  - **Triggers:** any production deployment with real sockets, especially (a) high request rate, (b) many concurrent streaming generations held open for seconds, or (c) `https` nodes. Never triggers in the test suite.

- **Fix:** Own a single, long-lived `AsyncClient` (with an explicit connection-limit and keep-alive config) on the FastAPI app via a `lifespan`, and forward through it. Do **not** `aclose()` the shared client after each request — only close the per-response stream. Keep `build_async_client()` as the construction seam (tests still monkeypatch it), but stop calling it per request on the hot path.

  **Before (per-request client, `proxy.py`):**

  ```python
  client = build_async_client()
  upstream_request = client.build_request(...)
  try:
      upstream = await client.send(upstream_request, stream=True)
  except httpx.RequestError as exc:
      await client.aclose()
      ...
  async def body_stream() -> AsyncIterator[bytes]:
      try:
          async for chunk in upstream.aiter_raw():
              yield chunk
      finally:
          await upstream.aclose()
          await client.aclose()
  ```

  **After:** create the pooled client once at startup and pass it in; the stream closes the *response*, never the shared client.

  ```python
  # src/vampire/proxy.py
  _LIMITS = httpx.Limits(max_connections=200, max_keepalive_connections=50)

  def build_async_client() -> httpx.AsyncClient:
      """Construct the pooled client used to reach downstream LM Studio nodes.

      Built once per process and stored on the app (see create_app's lifespan).
      Still the test seam: tests monkeypatch this to inject an ASGITransport.
      """
      return httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS)


  async def proxy_request_with_body(
      request: Request,
      *,
      downstream_base_url: str | None = None,
      body: bytes | None = None,
      response_headers: dict[str, str] | None = None,
  ) -> Response:
      settings = get_settings()
      base_url = (downstream_base_url or settings.lmstudio_base_url).rstrip("/")
      url = f"{base_url}{request.url.path}"
      body = body if body is not None else await request.body()
      headers = _filter_request_headers(httpx.Headers(request.headers.raw))

      client = request.app.state.http_client          # shared, pooled
      upstream_request = client.build_request(
          request.method, url,
          params=dict(request.query_params),
          headers=headers, content=body,
      )
      try:
          upstream = await client.send(upstream_request, stream=True)
      except httpx.RequestError as exc:
          logger.warning("Downstream LM Studio node %s unreachable: %r", base_url, exc)
          response = _upstream_error(f"Could not reach downstream LM Studio node at {base_url}.")
          if response_headers:
              response.headers.update(response_headers)
          return response

      async def body_stream() -> AsyncIterator[bytes]:
          try:
              async for chunk in upstream.aiter_raw():
                  yield chunk
          finally:
              await upstream.aclose()       # close the RESPONSE only — never the shared client
      ...
  ```

  **App wiring (`src/vampire/app.py`):** add a `lifespan` that creates exactly one client and closes it on shutdown.

  ```python
  from contextlib import asynccontextmanager
  from vampire.proxy import build_async_client

  @asynccontextmanager
  async def _lifespan(app: FastAPI):
      app.state.http_client = build_async_client()
      try:
          yield
      finally:
          await app.state.http_client.aclose()

  def create_app() -> FastAPI:
      app = FastAPI(title="lmstudio-vampire", version=__version__,
                    description="...", lifespan=_lifespan)
      app.include_router(openai_compat.router)
      app.include_router(control.router)
      ...
  ```

  **`cluster.refresh_node`:** accept an injected client (or read `app.state`) instead of building one per node, so the N-way `asyncio.gather` reuses one pool:

  ```python
  async def refresh_node(node: Node, *, client: httpx.AsyncClient, timeout_ms: int | None = None) -> Node:
      timeout = httpx.Timeout((timeout_ms or 1500) / 1000)
      base_url = node.lmstudio_base_url.rstrip("/")
      started = perf_counter()
      try:
          response = await client.get(f"{base_url}/v1/models", timeout=timeout)
          ...
      # NOTE: no `client.aclose()` here — the caller owns the client's lifecycle.
  ```

  with `refresh_registered_nodes` threading the shared client through the gather. (The call sites in `openai_compat.list_models` and `control.*` already run inside a request, so they can pass `request.app.state.http_client`.)

  **Invariant to preserve:** the `build_async_client` monkeypatch seam used by `tests/test_phase1.py:112-121` must keep working — it does, because `_lifespan` calls `build_async_client()`, so a test that patches the factory *before* the `TestClient` context manager enters startup still injects its `ASGITransport`. (One migration note: the existing fixture patches the module attribute and constructs the `TestClient` lazily; with a lifespan the patch must be in place before the `with TestClient(...)` block triggers startup — it already is, since the patch happens at fixture setup.)

  No `# type: ignore` is removed by this change (the one at `openai_compat.py:124` is a separate issue), and no public API shape changes — purely internal plumbing.

- **Test:** A regression test that exercises a *real* loopback socket server (not `ASGITransport`) and asserts the same TCP connection is reused across two sequential requests. This fails today (two distinct client objects ⇒ two connections) and passes after the fix (shared pooled client ⇒ keep-alive reuse). Concretely, count accepted connections on a stub server:

  ```python
  import asyncio, httpx, pytest
  from fastapi.testclient import TestClient
  import vampire.proxy as proxy
  from vampire.app import create_app

  @pytest.mark.anyio
  async def test_proxy_reuses_pooled_connection(monkeypatch):
      accepted = 0
      async def handle(reader, writer):
          nonlocal accepted
          accepted += 1
          # Read one request, reply with a minimal keep-alive HTTP/1.1 response, loop.
          while True:
              data = await reader.read(65536)
              if not data:
                  break
              body = b'{"object":"list","data":[]}'
              writer.write(
                  b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                  b"Content-Length: %d\r\nConnection: keep-alive\r\n\r\n%s" % (len(body), body)
              )
              await writer.drain()
      server = await asyncio.start_server(handle, "127.0.0.1", 0)
      port = server.sockets[0].getsockname()[1]
      monkeypatch.setenv("VAMPIRE_LMSTUDIO_BASE_URL", f"http://127.0.0.1:{port}")

      async with server:
          with TestClient(create_app()) as client:   # triggers lifespan -> one shared client
              client.get("/v1/models")                # registry empty -> proxy passthrough
              client.get("/v1/models")
      # With pooling, the second request reuses the keep-alive connection.
      assert accepted == 1     # FAILS today (==2: a fresh client/connection per request)
  ```

  (For a more direct unit-level assertion, patch `build_async_client` to return a client whose transport records `connect` calls and assert exactly one connect across two `proxy_request` invocations sharing `app.state.http_client`.)

- **Effort & risk:** ~30-45 lines changed across 3 files (`proxy.py`, `app.py`, `cluster.py`) plus 1 new test. Low backward-compat risk: no public HTTP API changes, error envelopes and streaming semantics are identical. The one behavioral subtlety to verify is that `app.state.http_client` is always present — guard the proxy with a fallback (`getattr(request.app.state, "http_client", None) or build_async_client()`) so any code path that constructs the app *without* the lifespan (e.g. a future direct `proxy_request` unit test) degrades gracefully rather than `AttributeError`. The `refresh_node` signature change is internal-only (all call sites are in-repo: `control.py`, `openai_compat.py`, `cluster.py`).

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~33,000 tok · output ~3,400 tok · est. cost ~$0.75 · run started 06:11 finished 06:13.
