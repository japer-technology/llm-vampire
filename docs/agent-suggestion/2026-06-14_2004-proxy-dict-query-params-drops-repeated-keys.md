# Transparent proxy collapses repeated query parameters — `dict(request.query_params)` silently drops all but the last value

- **Severity:** High — silent, data-losing corruption of every forwarded request that uses repeated query keys; no error surfaced to the client, behaviour diverges from "transparent" contract.
- **Category:** api-correctness.
- **Summary:** `proxy_request_with_body` forwards the upstream query string via `params=dict(request.query_params)`. `request.query_params` is a Starlette `QueryParams` multidict; calling `dict(...)` on it keeps only the **last** value for each repeated key. Any request that legitimately repeats a query parameter (`?stop=a&stop=b`, `?include[]=x&include[]=y`, `?id=1&id=2`) reaches the downstream LM Studio node with the earlier occurrences silently deleted, so the proxy is not actually transparent.

- **Location:** `src/vampire/proxy.py:144` (inside `proxy_request_with_body`, used by every `/v1/*` route and the catch-all passthrough via `proxy_request`).

- **Evidence:**

  ```python
  # src/vampire/proxy.py:141-147
  upstream_request = client.build_request(
      request.method,
      url,
      params=dict(request.query_params),   # <-- line 144
      headers=headers,
      content=body,
  )
  ```

  Step by step:
  1. Starlette parses the incoming query string into `request.query_params`, an immutable **multidict** (`starlette.datastructures.QueryParams`) that preserves every `(key, value)` pair, including duplicate keys, and exposes them via `.multi_items()`.
  2. `dict(qp)` invokes the `Mapping` protocol: it iterates `qp.__iter__()` (which yields each **distinct** key once) and resolves each with `qp[key]`. `QueryParams.__getitem__` returns the value stored in the backing single-value `dict`, i.e. the **last** value seen for that key.
  3. Therefore `dict(QueryParams("stop=a&stop=b"))` evaluates to `{"stop": "b"}` — the value `"a"` is gone before httpx ever builds the request.
  4. `httpx.build_request(..., params={"stop": "b"})` then sends `?stop=b` upstream. The downstream model server receives a different request than the client sent.

  This is the same class of multidict-flattening bug the proxy already guards against for *headers* — note `_filter_request_headers` deliberately uses `headers.multi_items()` (proxy.py:80) precisely to preserve repeated header keys. The query-param path violates the same invariant that the header path honours.

  The existing regression test does **not** catch it, because it only uses **distinct** keys:

  ```python
  # tests/test_phase1.py:195-204
  def test_catch_all_preserves_query_and_end_to_end_headers(client: TestClient) -> None:
      resp = client.patch(
          "/v1/echo/custom/path?alpha=one&beta=two",   # no repeated key
          ...
      )
      assert body["query"] == {"alpha": "one", "beta": "two"}
  ```

  (`dict(request.query_params)` in the mock echo on test line 87 also re-collapses, so even the assertion shape hides the issue.)

- **Impact:**
  - **Who observes it:** any OpenAI-compatible client that sends repeated query parameters through the gateway, plus any LM Studio endpoint reachable via the `/v1/{path:path}` catch-all that uses array-style or repeated query keys. OpenAI-style array params (`?expand=a&expand=b`), pagination/filter params, and several LM Studio REST/admin surfaces use repeated keys.
  - **Symptom:** the request "works" (200 OK) but returns subtly wrong results — a filter is partially applied, only one of several requested fields is expanded, a multi-value selector is truncated to its last element. There is **no error, no log line, no trace header** indicating data was dropped, which makes it extremely hard to diagnose ("the gateway changes my results but the same request hits LM Studio directly fine").
  - **Blast radius:** every request method, every `/v1/*` route, and the catch-all — the defect sits in the single shared forwarding function. It triggers deterministically whenever a key repeats; single-value queries are unaffected, which is why it slipped past tests.
  - It directly contradicts the module's stated contract (proxy.py:116-118): *"The method, path, query string, headers and body are passed through unchanged."* They are not.

- **Fix:** Forward the query parameters as an order-preserving list of pairs (or the raw query string) instead of flattening through `dict`. `httpx` accepts `list[tuple[str, str]]` for `params` and preserves duplicates.

  Before:

  ```python
  upstream_request = client.build_request(
      request.method,
      url,
      params=dict(request.query_params),
      headers=headers,
      content=body,
  )
  ```

  After:

  ```python
  upstream_request = client.build_request(
      request.method,
      url,
      # Preserve repeated query keys (e.g. ?stop=a&stop=b). dict() would
      # collapse a Starlette QueryParams multidict to its last value per key,
      # mirroring the multi_items() preservation already used for headers.
      params=request.query_params.multi_items(),
      headers=headers,
      content=body,
  )
  ```

  Notes:
  - `request.query_params.multi_items()` returns `list[tuple[str, str]]` with decoded values; httpx re-encodes them correctly. Order and duplicates are preserved.
  - Alternative equally-correct fix: drop `params=` entirely and append the *raw* query string to the URL — `url = f"{base_url}{request.url.path}"` then `if request.url.query: url = f"{url}?{request.url.query}"`. This is the most byte-faithful (no decode/re-encode round-trip) and also fixes the rare case where httpx's re-encoding of an exotic param would differ from the client's. Either is acceptable; the `multi_items()` form is the minimal diff.
  - No `# type: ignore` to remove. Update the mock echo helper in `tests/test_phase1.py:87` to report `request.query_params.multi_items()` so the test can assert duplicate preservation.
  - **Invariant to preserve:** "query string passed through unchanged" — keep it aligned with the header-preservation invariant already enforced by `_filter_request_headers`.

- **Test:** Add a regression test that fails today (collapses to `{"stop": "b"}`) and passes after the fix. It uses the existing mock-injection fixture pattern.

  ```python
  # tests/test_phase1.py
  def test_proxy_preserves_repeated_query_parameters() -> None:
      seen: dict[str, list[tuple[str, str]]] = {}
      upstream = FastAPI()
      original = proxy.build_async_client

      @upstream.get("/v1/echo/q")
      async def echo_q(request: Request) -> JSONResponse:
          # multi_items() preserves every repeated key/value pair
          seen["pairs"] = list(request.query_params.multi_items())
          return JSONResponse({"ok": True})

      def _build() -> httpx.AsyncClient:
          return httpx.AsyncClient(transport=httpx.ASGITransport(app=upstream))

      proxy.build_async_client = _build
      try:
          with TestClient(create_app()) as client:
              resp = client.get("/v1/echo/q?stop=a&stop=b&single=x")
      finally:
          proxy.build_async_client = original

      assert resp.status_code == 200
      # Fails today: dict() collapse drops ("stop", "a"); only [("stop","b"),("single","x")] arrives.
      assert seen["pairs"] == [("stop", "a"), ("stop", "b"), ("single", "x")]
  ```

  Today this asserts against `[("stop", "b"), ("single", "x")]` (the `"a"` pair is missing) and fails; after the `multi_items()` fix it passes.

- **Effort & risk:** ~1 line changed in `src/vampire/proxy.py` (plus an optional 1-line mock tweak in `tests/test_phase1.py:87` and ~20 lines for the new test). One source file touched. Fully backward compatible: single-value queries serialize identically; only the previously-lost duplicate values are now correctly forwarded. No API shape change, no new dependency. Risk is negligible — `multi_items()` is a stable Starlette API already relied on elsewhere in the same module.

---
- **APPLIED 2026-06-14:** Set to Taken and implemented by forwarding `request.query_params.multi_items()` through the proxy, with regression coverage for repeated query keys.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~285k tok · output ~10k tok · est. cost ~$5.03 · run started 06:00 finished 06:05. _(Estimated: summed `in=`/`out=` for this run's API calls from agent.log; Opus pricing $15/1M in, $75/1M out.)_
