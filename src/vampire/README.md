# `vampire` package

The runnable core of **LM Studio Vampire**: a FastAPI gateway that turns
owner-approved LM Studio API endpoints into one governed, private AI service
behind a single OpenAI-compatible URL. The package is built in phases per
[IMPLEMENTATION-PLAN.md](../../IMPLEMENTATION-PLAN.md); Phases 0–4 (scaffolding,
transparent proxy, node registry + discovery, virtual-model routing, and the
browser dashboard) run today.

## Layout

| Path | Purpose |
| --- | --- |
| [`app.py`](app.py) | FastAPI application factory. One process serves the OpenAI-compatible API (`/v1/*`), the Vampire control API (`/vampire/v1/*`), and the static dashboard (`/`) |
| [`cli.py`](cli.py) / [`__main__.py`](__main__.py) | The `vampire` command-line interface (`serve`, `status`, `nodes`, `routes`, `discover`, `share`, `dashboard`/`ui`, …); also invocable as `python -m vampire` |
| [`config.py`](config.py) | Runtime settings. Vampire listens on port 7777 and proxies to a downstream LM Studio node (commonly port 1234); everything is overridable via `VAMPIRE_*` environment variables |
| [`models.py`](models.py) | Core Pydantic orchestration models (DESIGN-API.md §4) |
| [`proxy.py`](proxy.py) | Phase 1 transparent proxy: forwards `/v1/*` to a configured LM Studio node, preserving streaming responses and OpenAI-style upstream errors |
| [`registry.py`](registry.py) | In-memory registry of approved LM Studio nodes |
| [`cluster.py`](cluster.py) | Phase 2 node health checks, static/dev-subnet discovery, model inventory aggregation, metrics, and SSRF target validation |
| [`router.py`](router.py) | Phase 3 virtual-model router (`vampire:auto`, …) with MVP strategies: round_robin, least_busy, least_latency, model_affinity, trusted_only, plus fallback/failover |
| [`auth.py`](auth.py) | Bearer-token authentication. A configured `VAMPIRE_AUTH_TOKEN` gates `/v1/*` and `/vampire/v1/*`; an empty token keeps the APIs open |
| [`api/`](api/README.md) | HTTP route layers (OpenAI-compatible surface and Vampire control surface) |
| [`assets/`](assets/README.md) | Static assets, including the Phase 4 dashboard SPA |
| [`desktop/`](desktop/README.md) | Double-click friendly launcher for packaged desktop builds |

## Entry points

Declared in [`pyproject.toml`](../../pyproject.toml):

- `vampire` → `vampire.cli:main` — the primary CLI.
- `vampire-desktop` → `vampire.desktop.launcher:main` — the packaged desktop
  launcher.

## Development

From the repository root:

```bash
pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
```

See the [tests](../../tests/README.md) for the phase-aligned test suites and
the [user manual](../../docs/manual/README.md) for operator documentation.
