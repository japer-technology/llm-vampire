# Test suite

Pytest suite for `llm-vampire`. Tests mirror the build phases in
[IMPLEMENTATION-PLAN.md](../IMPLEMENTATION-PLAN.md): each implemented phase has
a dedicated `test_phaseN.py`, plus cross-cutting suites for the CLI, auth,
cluster helpers, SSRF protection, and smoke coverage.

## Running

From the repository root:

```bash
pip install -e ".[dev]"
python -m pytest
```

The suite is offline-friendly: downstream provider nodes are simulated with
mock ASGI apps and mocked HTTP clients — no real local LLM server is required.

## Layout

| File | Covers |
| --- | --- |
| [`conftest.py`](conftest.py) | Shared isolation for process-local Vampire state (settings cache, registry, share state) so tests don't leak into each other |
| [`test_smoke.py`](test_smoke.py) | The scaffold imports, the app builds, and core routes respond |
| [`test_phase0.py`](test_phase0.py) | Phase 0 scaffolding: installable package, `vampire` console script, app factory, configuration, core Pydantic models |
| [`test_phase1.py`](test_phase1.py) | Phase 1 transparent proxy: `/v1/*` passthrough, OpenAI-compatible streaming, and upstream error format |
| [`test_phase2.py`](test_phase2.py) | Phase 2 node registry: node CRUD, health/model interrogation, static discovery, model aggregation, metrics |
| [`test_phase3.py`](test_phase3.py) | Phase 3 virtual-model routing: route policies, router strategies, `/vampire/v1/routes`, opt-in routing, `X-Vampire-*` headers |
| [`test_phase4.py`](test_phase4.py) | Phase 4 browser UI: dashboard SPA served from `/` and the `vampire dashboard` / `vampire ui` launcher |
| [`test_cli.py`](test_cli.py) | CLI coverage for the control-plane commands |
| [`test_cluster.py`](test_cluster.py) | Cluster helpers: health checks, interrogation, discovery mechanics |
| [`test_providers.py`](test_providers.py) | Provider adapters, Ollama inventory normalization, provider detection, and multi-port local discovery |
| [`test_auth.py`](test_auth.py) | Bearer-token gating of `/v1/*` and `/vampire/v1/*` via `VAMPIRE_AUTH_TOKEN` |
| [`test_ssrf_protection.py`](test_ssrf_protection.py) | `is_allowed_target_url` SSRF guard for node target URLs |

## Conventions

- Tests are type-checked by mypy (strict) and linted by ruff, same as `src/`.
- Add a `tests/test_phaseN.py` suite alongside each new implementation phase;
  keep cross-cutting behaviour in the feature-named suites.
- CI runs the full suite on Python 3.10–3.12 (see
  [`.github/workflows/README.md`](../.github/workflows/README.md)).
