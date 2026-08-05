# Implementation Plan — `llm-vampire` (METHOD-A)

This plan turns the design papers in this repository into a runnable project. It
follows the recommended construction in [METHOD-A.md](METHOD-A.md) (a single
Python/FastAPI process that serves the OpenAI-compatible API, the Vampire control
API, and the browser UI) and targets the **Minimal MVP** defined in
[DESIGN-API.md](DESIGN-API.md) §24.

End state: `pip install llm-vampire` → `vampire serve` → a process listening
on `http://localhost:7777/v1` that proxies and routes across approved local LLM
nodes, with a browser dashboard.

## Guiding constraints (from the design papers)

- **Compatibility first.** `/v1/*` routes must follow the OpenAI-compatible API;
  existing clients only change their base URL. Vampire
  features are strictly opt-in via the `vampire` request field, `X-Vampire-*`
  headers, or `/vampire/v1/*` routes.
- **Single artifact.** One process serves the OpenAI API, the Vampire control
  API, and the static UI.
- **Owner stays in control.** Vampire only talks to local LLM endpoints an owner
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

These phases follow the **METHOD-A build order** (the same numbered steps listed
in [METHOD-A.md](METHOD-A.md) §"Build order" and the [README](README.md#roadmap)).
That build order is an *engineering* sequence chosen for the shortest path to a
working demo; it is not the same numbering as the *thematic* MVP roadmap in
[ASPIRATION.md](ASPIRATION.md), which groups the work by capability. The two
relate as follows:

| METHOD-A build step (here) | ASPIRATION thematic phase |
| --- | --- |
| 0 — Scaffolding & foundations | Phase 0 (repo foundation) |
| 1 — Transparent proxy | Phase 2 (OpenAI-compatible proxy) |
| 2 — Node registry + discovery | Phase 1 (local discovery) + manual parts of Phase 6 |
| 3 — Routing | Phase 4 (routing) |
| 4 — Browser UI | dashboard build step (event UI lands in Phase 8) |
| 5 — Coalescing + cache | Phase 3 (request coalescing) |
| 6 — Policy + tokens | Phase 5 (policy and realms) |
| 7 — Fusion & advanced modes | fusion/advanced modes (beyond the thematic roadmap's MVP) |

Coalescing (build step 5) is intentionally sequenced *after* routing and the UI
here, even though ASPIRATION lists coalescing earlier (Phase 3): the proxy,
registry, routing, and dashboard together form the smallest shippable,
demonstrable product, and coalescing is a transparent optimization layered on
top once traffic flows.

### Phase 0 — Scaffolding & foundations
- Python package with the `vampire` console-script entry point.
- App factory, configuration (default port `7777`, configurable downstream URL),
  logging.
- Core Pydantic models for the objects in DESIGN-API §4 (Node, virtual model,
  route policy) and OpenAI request/response shapes.
- Testing (pytest), linting/formatting, type checking, CI.

### Phase 1 — Transparent proxy (build step 1)
- Drop-in `/v1/*` passthrough to a single configured local LLM node:
  `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`,
  `/v1/responses`.
- Preserve OpenAI-compatible streaming (DESIGN-API §20) and error format (§23).
- Acceptance: an existing OpenAI-compatible client works unchanged against
  `:7777/v1`.

### Phase 2 — Node registry + discovery (build step 2)
- In-memory registry (SQLite seam). `/vampire/v1/status`,
  `GET/POST /vampire/v1/nodes`, `GET/PATCH/DELETE /vampire/v1/nodes/{id}`.
- Manual registration first (§13), then health checks and capability/model
  interrogation. The MVP relies on manual registration only; automatic mDNS
  discovery and the node agent are deferred (ASPIRATION Phase 6).
- `POST /vampire/v1/discover` (§12): static/local multi-port scan first, mDNS later.
- Aggregate `/v1/models` and `/vampire/v1/models` across nodes (§15).
- Basic read-only `GET /vampire/v1/metrics` (§18): per-node request counts,
  health, and latency. This completes the "Minimal MVP" control surface in
  DESIGN-API §24 and MVP.md; richer, policy-aware metrics arrive in Phase 6.
- Manual node draining from POSSIBILITIES.md §14/§15 is exposed as
  `vampire nodes drain NODE_ID [off]`, backed by node status updates that keep
  drained nodes registered but unavailable to routing.

### Phase 3 — Routing (build step 3)
- Virtual models (`vampire:auto`, `vampire:fast`, …) and a router.
- MVP routing strategies (§24): `round_robin`, `least_busy`, `least_latency`,
  `model_affinity`, `trusted_only`, plus failover/`fallback`.
- Opt-in `vampire` request object and `X-Vampire-*` headers; return Vampire
  metadata in responses (§7).
- Routes management: `GET/POST /vampire/v1/routes` (§16).

### Phase 4 — Browser UI (build step 4)
- Static SPA served from `/`: dashboard for nodes, models, health, cluster
  status, plus a prompt playground that calls the gateway.
- Implemented: the plain static SPA drives the existing control API for status,
  nodes, discovery (with subnet/port/timeout/trusted-only options), models,
  routes, metrics, and owner share state (read and set), and posts playground
  prompts to `/v1/chat/completions`. The `vampire dashboard` / `vampire ui`
  command prints or opens the served dashboard URL.

### Phase 5 — Coalescing + cache (build step 5)
- In-flight deduplication of identical concurrent prompts.
- Exact-result cache. Keep CPU-bound work off the event loop.

### Phase 6 — Policy + tokens (build step 6)
- Bearer-token auth (§21), CORS allowlist, node allowlists, trust levels, owner
  share modes, token vault, realm policy, logging controls.
- Extend `GET /vampire/v1/metrics` (§18) with policy-aware, per-realm counters
  (the basic endpoint ships in Phase 2).

### Phase 7 — Fusion & advanced modes (build step 7)
- Async fan-out modes (§8): MVP `race` and `fusion`, then `parallel`, `debate`,
  `pipeline`.
- `POST /vampire/v1/fusion` (§11) and fusion strategies (§10).
- Pipelines (§17) with async jobs `/vampire/v1/jobs/{id}` and traces
  `/vampire/v1/traces/{id}` (§19).

## Cross-cutting concerns
- **Testing:** mock OpenAI-compatible and Ollama server fixtures so every phase can be tested
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
  proxy.py              Transparent /v1 passthrough to local LLM nodes
  registry.py           Node registry
  router.py             Virtual-model routing
  api/
    __init__.py
    openai_compat.py    Layer 1: /v1/* OpenAI-compatible routes
    control.py          Layer 2: /vampire/v1/* control routes
  assets/
    vampire-dashboard.html  Phase 4 single-file dashboard SPA (served at /)
  desktop/
    launcher.py          Desktop-friendly packaged app launcher
tools/
  html/                  Standalone helper browser tools
tests/
  __init__.py
  test_smoke.py         Imports + app-startup smoke test
```
