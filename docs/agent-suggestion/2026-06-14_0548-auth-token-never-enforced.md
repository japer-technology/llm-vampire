# `auth_token` is a silently-ignored security control: no route enforces authentication, leaving the control plane (and an SSRF surface) wide open

- **Severity:** High — a configured credential (`VAMPIRE_AUTH_TOKEN`) is defined, documented, and surfaced to operators but is **dead code**: nothing reads it, so setting it provides zero protection while creating a false sense of security. The unauthenticated control API additionally exposes a server-side request-forgery (SSRF) primitive. Not rated Critical only because the default `host` binds to `127.0.0.1`; the moment an operator follows the project's own LAN-sharing use-cases and binds to `0.0.0.0`, this becomes Critical.
- **Category:** security (with secondary code-vs-doc drift).
- **Status:** Suggestion taken with notes.
- **Notes:** Implemented bearer-token enforcement for configured `VAMPIRE_AUTH_TOKEN` values across `/v1/*` and `/vampire/v1/*`, while preserving the empty-token drop-in mode and leaving the static UI open. The follow-up SSRF hardening mentioned below remains out of scope for this suggestion.

- **Summary:** `vampire/config.py` defines `auth_token` and its docstring states a "Local API key required on requests," and `DESIGN-API.md §21` lists `Authorization: Bearer ***` as the **"Required minimum"** security control. However, a repository-wide search finds exactly **one** reference to `auth_token` — its own definition. No FastAPI dependency, middleware, or handler ever inspects the `Authorization` header. Every route — the OpenAI proxy *and* the full `/vampire/v1/*` control plane (register node, delete node, run LAN discovery, change share mode) — is reachable with no credential, so an operator who exports `VAMPIRE_AUTH_TOKEN=secret` is no more protected than one who does not.

- **Location:**
  - `src/vampire/config.py:36-38` — the unused setting.
  - `src/vampire/app.py:24-45` — `create_app()`, where no auth dependency/middleware is wired.
  - `src/vampire/api/control.py:48-93` — unauthenticated, state-mutating + SSRF-capable endpoints (`register_node`, `discover`).
  - `DESIGN-API.md:1159-1174` — the spec clause this violates.

- **Evidence:**

  The setting and its promise (note the wording "required on requests"):

  ```python
  # src/vampire/config.py:36-38
      # Local API key required on requests once Phase 6 policy lands. Empty keeps
      # Phase 1 drop-in OpenAI compatibility unauthenticated by default.
      auth_token: str = ""
  ```

  The spec it is meant to satisfy:

  ```text
  # DESIGN-API.md:1159-1165
  # 21. Security model

  ## Required minimum

  Authorization: Bearer ***
  ```

  The application factory wires routers and static files but installs **no** authentication seam — there is no `app.add_middleware(...)`, no `dependencies=[Depends(require_auth)]`, nothing:

  ```python
  # src/vampire/app.py:33-45
      app = FastAPI(
          title="lmstudio-vampire",
          version=__version__,
          description="OpenAI-compatible gateway + LAN orchestration for LM Studio.",
      )

      app.include_router(openai_compat.router)
      app.include_router(control.router)

      if WEB_DIR.is_dir():
          app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

      return app
  ```

  Proof that the field is never consumed — a content search for the symbol and for any auth machinery across `src/` returns only the definition line:

  ```text
  $ search src/ for: auth_token|Depends|middleware|add_middleware|Security
  src/vampire/config.py:38:    auth_token: str = ""
  ```

  No `Depends`, no `add_middleware`, no `Security`. The credential is read into `Settings` and then discarded.

  **Why this manifests / the SSRF amplifier.** Because nothing authenticates, *any* client that can open a TCP connection to the gateway can drive the control plane. Two endpoints turn the open gateway into an SSRF engine that fetches attacker-chosen URLs from inside the gateway's network position:

  ```python
  # src/vampire/api/control.py:48-58
  @router.post("/nodes")
  async def register_node(node: Node) -> dict[str, Any]:
      registry.add(node)
      refreshed = await refresh_node(node)          # fetches node.lmstudio_base_url
      return {"id": refreshed.id, "status": "registered", "trusted": refreshed.trusted}
  ```

  `Node.lmstudio_base_url` (`models.py:78`) is an unvalidated free-form `str`. `refresh_node` (`cluster.py:147-156`) immediately issues `GET {base_url}/v1/models`. So `POST /vampire/v1/nodes {"id":"x","lmstudio_base_url":"http://169.254.169.254/latest/meta-data"}` makes the gateway dial an arbitrary internal address, and the response body (model cards / error text via `last_error`) is reflected back through `GET /vampire/v1/nodes`. The discovery endpoint is worse — it accepts arbitrary subnets and ports and sweeps them:

  ```python
  # src/vampire/cluster.py:257-264  (inside _candidate_urls)
      if "lan_scan" in methods:
          for subnet in request.subnets:
              network = ipaddress.ip_network(subnet, strict=False)
              for index, host in enumerate(network.hosts()):
                  if index >= 256:
                      break
                  for port in request.ports:
                      urls.append(f"http://{host}:{port}")
  ```

  `POST /vampire/v1/discover {"methods":["lan_scan"],"subnets":["10.0.0.0/24"],"ports":[22,80,443,1234,8080]}` turns the gateway into an unauthenticated internal port scanner whose latency/last_error fields leak which host:port pairs answered. None of this requires a credential today, and supplying one does not change the behaviour because the credential is never checked.

- **Impact:** Concrete consequences an operator/attacker observes:
  - An operator who sets `VAMPIRE_AUTH_TOKEN` and tells their family/colleagues "the endpoint is protected" is wrong: requests with a missing or *wrong* `Authorization` header succeed identically. This is the most dangerous failure mode — a security control that appears configured but is inert.
  - Anyone with network reach to port 7777 can: register/delete nodes, flip `vampire share` mode, enumerate models, drive routing, and proxy arbitrary inference (consuming GPU/compute on every node in the cluster).
  - SSRF blast radius: the gateway can be coerced to probe `169.254.169.254` (cloud metadata), loopback-only admin services, and entire LAN subnets, with results reflected back to the caller. The project's stated use-cases (`docs/use-case/*`, share modes `family`/`business`/`event`) explicitly push operators toward LAN-exposed deployments, where the default `127.0.0.1` bind is changed to a routable address and this gap goes live.
  - Triggers immediately on any non-loopback deployment; no special timing or race required.

- **Fix:** Introduce a single auth dependency that enforces the bearer token **whenever `auth_token` is non-empty**, and attach it to the routers (or the whole app). This honours the existing "empty = unauthenticated drop-in" contract while making a configured token actually required — closing both the dead-control bug and the unauthenticated-SSRF path in one move.

  New module `src/vampire/auth.py`:

  ```python
  """Bearer-token authentication for the Vampire gateway (DESIGN-API.md §21)."""
  from __future__ import annotations

  import hmac

  from fastapi import Request
  from fastapi.responses import JSONResponse
  from starlette.responses import Response

  from vampire.config import get_settings


  def _unauthorized(message: str) -> JSONResponse:
      # OpenAI-compatible error envelope (DESIGN-API.md §23).
      return JSONResponse(
          status_code=401,
          content={"error": {"message": message, "type": "vampire_auth_error",
                             "code": "missing_or_invalid_token"}},
          headers={"WWW-Authenticate": "Bearer"},
      )


  async def require_auth(request: Request) -> None:
      """Reject requests lacking a valid bearer token when one is configured.

      Empty ``auth_token`` preserves Phase 1 drop-in OpenAI compatibility
      (the documented default). A configured token is now actually enforced.
      """
      token = get_settings().auth_token
      if not token:
          return
      header = request.headers.get("authorization", "")
      scheme, _, presented = header.partition(" ")
      if scheme.lower() != "bearer" or not presented:
          raise _AuthError("Missing bearer token.")
      # Constant-time compare to avoid leaking the token via timing.
      if not hmac.compare_digest(presented, token):
          raise _AuthError("Invalid bearer token.")
  ```

  Because FastAPI dependencies cannot return a `Response` to short-circuit, raise a small exception and register one handler (cleaner than returning). Concretely, wire it in `app.py` as a global dependency so it covers proxy *and* control routes, while leaving the static UI mount and an allowlist (`/`, docs) open:

  ```python
  # src/vampire/app.py  (after) — before/after on include_router
  from fastapi import Depends, FastAPI
  from vampire.auth import require_auth, AuthError, auth_exception_handler

  app = FastAPI(..., dependencies=[Depends(require_auth)])
  app.add_exception_handler(AuthError, auth_exception_handler)
  app.include_router(openai_compat.router)
  app.include_router(control.router)
  ```

  Independently (and ideally), tighten the SSRF surface even when authenticated by validating that discovery/registration URLs resolve to permitted ranges — but auth enforcement is the load-bearing fix and the one this suggestion scopes. Update `config.py:36-38` docstring to drop "once Phase 6 policy lands" (it is enforced now) and update any doc that implies auth is unimplemented. Invariant to preserve: **empty `auth_token` ⇒ fully open drop-in proxy** (so existing Phase 1 tests and the LM Studio compatibility promise keep passing); only a *configured* token changes behaviour.

- **Test:** A regression test that fails today (every request currently 200s regardless of header) and passes after the fix. It monkeypatches the settings to carry a token, then asserts unauthenticated/wrong-token requests are rejected and the correct token is accepted:

  ```python
  # tests/test_auth.py
  from __future__ import annotations

  import pytest
  from fastapi.testclient import TestClient

  import vampire.config as config
  from vampire.app import create_app
  from vampire.config import Settings


  @pytest.fixture
  def token_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
      monkeypatch.setattr(
          config, "get_settings", lambda: Settings(auth_token="s3cret")
      )
      # auth.py imports get_settings from vampire.config; patch the module attr
      monkeypatch.setattr("vampire.auth.get_settings", config.get_settings)
      return TestClient(create_app())


  def test_control_plane_rejects_missing_token(token_client: TestClient) -> None:
      resp = token_client.get("/vampire/v1/status")
      assert resp.status_code == 401
      assert resp.json()["error"]["type"] == "vampire_auth_error"


  def test_control_plane_rejects_wrong_token(token_client: TestClient) -> None:
      resp = token_client.get(
          "/vampire/v1/status", headers={"Authorization": "Bearer nope"}
      )
      assert resp.status_code == 401


  def test_correct_token_is_accepted(token_client: TestClient) -> None:
      resp = token_client.get(
          "/vampire/v1/status", headers={"Authorization": "Bearer s3cret"}
      )
      assert resp.status_code == 200


  def test_empty_token_preserves_open_drop_in(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      # Default auth_token == "" must keep the gateway open (Phase 1 contract).
      monkeypatch.setattr("vampire.auth.get_settings", lambda: Settings())
      client = TestClient(create_app())
      assert client.get("/vampire/v1/status").status_code == 200
  ```

  Today `test_control_plane_rejects_missing_token` and `test_control_plane_rejects_wrong_token` both fail (the endpoint returns 200); after the fix all four pass. The fourth test pins the backward-compatibility invariant so the fix cannot accidentally break drop-in mode.

- **Effort & risk:** ~70-90 lines added across 3 files: a new `src/vampire/auth.py` (~40 lines incl. the `AuthError` exception + handler), ~5 lines in `src/vampire/app.py`, a one-line docstring touch in `config.py`, plus the new `tests/test_auth.py` (~50 lines). **Backward-compat:** zero behavioural change when `auth_token` is empty (the documented and tested default), so existing Phase 0-4 suites are unaffected; only deployments that set the token gain enforcement — which is the intended, spec-required behaviour. Low risk; the only subtlety is ensuring the static-UI mount (`/`) and OpenAPI docs remain reachable if you choose app-wide enforcement (use a small path allowlist inside `require_auth`, or attach the dependency to the two API routers rather than the app).

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~unknown (session token counts not emitted to `~/.hermes/logs/agent.log` for this run; rough working-context estimate ~45k tok from files read) · output ~2200 tok · est. cost ~$0.17 (output-based: 2200/1e6×75 = $0.165; add ~$0.68 if the ~45k input estimate holds → ~$0.85 all-in) · run started 05:48 finished 05:50. Marked **estimated** — final output tokens are emitted after logging, so this is a close lower-bound, not an invoice.
