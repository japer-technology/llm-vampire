# Implementation Plan — `lmstudio-vampire` (METHOD-A)

This plan turns the design papers in this repository into a runnable project. It
follows the recommended construction in [METHOD-A.md](METHOD-A.md) (a single
Python/FastAPI process that serves the OpenAI-compatible API, the Vampire control
API, and the browser UI) and targets the **Minimal MVP** defined in
[DESIGN-API.md](DESIGN-API.md) §24.

End state: `pip install lmstudio-vampire` → `vampire serve` → a process listening
on `http://localhost:7777/v1` that proxies and routes across approved LM Studio
nodes, with a browser dashboard.

## Guiding constraints (from the design papers)

- **Compatibility first.** `/v1/*` routes must behave exactly like
  LM Studio / OpenAI; existing clients only change their base URL. Vampire
  features are strictly opt-in via the `vampire` request field, `X-Vampire-*`
  headers, or `/vampire/v1/*` routes.
- **Single artifact.** One process serves the OpenAI API, the Vampire control
  API, and the static UI.
- **Owner stays in control.** Vampire only talks to LM Studio endpoints an owner
  has deliberately exposed; it never controls GPUs directly.
- **Streaming is native.** SSE / chunked passthrough works from day one.

## Suggested stack (from METHOD-A)

- **Web framework:** FastAPI · **Server:** Uvicorn
- **HTTP client:** `httpx.AsyncClient` (streaming fan-out to nodes)
- **Discovery:** `zeroconf` (mDNS) plus a manual allowlist
- **State:** in-memory for v0, with a SQLite (`aiosqlite`) persistence seam
- **UI:** static single-page app served by the same FastAPI app under `/`
- **Packaging:** a `vampire` console-script (`serve`, `discover`, `share`,
  `nodes`, `status`, `route`)

## Phases

### Phase 0 — Scaffolding & foundations
- Python package with the `vampire` console-script entry point.
- App factory, configuration (default port `7777`, downstream LM Studio `1234`),
  logging.
- Core Pydantic models for the objects in DESIGN-API §4 (Node, virtual model,
  route policy) and OpenAI request/response shapes.
- Testing (pytest), linting/formatting, type checking, CI.

### Phase 1 — Transparent proxy (Roadmap step 1)
- Drop-in `/v1/*` passthrough to a single configured LM Studio node:
  `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`,
  `/v1/responses`.
- Preserve OpenAI-compatible streaming (DESIGN-API §20) and error format (§23).
- Acceptance: an existing OpenAI/LM Studio client works unchanged against
  `:7777/v1`.

### Phase 2 — Node registry + discovery (Roadmap step 2)
- In-memory registry (SQLite seam). `/vampire/v1/status`,
  `GET/POST /vampire/v1/nodes`, `GET/PATCH/DELETE /vampire/v1/nodes/{id}`.
- Manual registration first (§13), then health checks and capability/model
  interrogation.
- `POST /vampire/v1/discover` (§12): static, then mDNS.
- Aggregate `/v1/models` and `/vampire/v1/models` across nodes (§15).

### Phase 3 — Routing (Roadmap step 3)
- Virtual models (`vampire:auto`, `vampire:fast`, …) and a router.
- MVP routing strategies (§24): `round_robin`, `least_busy`, `least_latency`,
  `model_affinity`, `trusted_only`, plus failover/`fallback`.
- Opt-in `vampire` request object and `X-Vampire-*` headers; return Vampire
  metadata in responses (§7).
- Routes management: `GET/POST /vampire/v1/routes` (§16).

### Phase 4 — Browser UI (Roadmap step 4)
- Static SPA served from `/`: dashboard for nodes, models, health, cluster
  status, plus a prompt playground that calls the gateway.

### Phase 5 — Coalescing + cache (Roadmap step 5)
- In-flight deduplication of identical concurrent prompts.
- Exact-result cache. Keep CPU-bound work off the event loop.

### Phase 6 — Policy + tokens (Roadmap step 6)
- Bearer-token auth (§21), CORS allowlist, node allowlists, trust levels, owner
  share modes, token vault, realm policy, logging controls.
- `GET /vampire/v1/metrics` (§18).

### Phase 7 — Fusion & advanced modes (Roadmap step 7)
- Async fan-out modes (§8): MVP `race` and `fusion`, then `parallel`, `debate`,
  `pipeline`.
- `POST /vampire/v1/fusion` (§11) and fusion strategies (§10).
- Pipelines (§17) with async jobs `/vampire/v1/jobs/{id}` and traces
  `/vampire/v1/traces/{id}` (§19).

## Cross-cutting concerns
- **Testing:** a mock LM Studio server fixture so every phase can be tested
  without real GPUs; contract tests asserting `/v1/*` OpenAI parity.
- **Optional node agent** (`/agent/v1/*`, DESIGN-API Layer 3): defer until after
  MVP.
- **JAPER signed-result envelope** (§22): defer to a later milestone.
- **Docs:** update `README.md` status/usage as each increment lands.

## Repository layout

```
pyproject.toml          Packaging, dependencies, `vampire` console-script
LICENSE                 MIT
src/vampire/            Python package
  __init__.py
  __main__.py           `python -m vampire`
  cli.py                CLI commands (serve, discover, share, nodes, status, route)
  config.py             Settings (ports, downstream URL)
  app.py                FastAPI app factory; mounts API layers + static UI
  models.py             Pydantic models (Node, virtual model, route policy)
  proxy.py              Transparent /v1 passthrough to LM Studio nodes
  registry.py           Node registry
  router.py             Virtual-model routing
  api/
    __init__.py
    openai_compat.py    Layer 1: /v1/* OpenAI-compatible routes
    control.py          Layer 2: /vampire/v1/* control routes
web/
  index.html            Placeholder dashboard SPA
tests/
  __init__.py
  test_smoke.py         Imports + app-startup smoke test
```
