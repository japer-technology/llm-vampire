# `vampire.api` — HTTP API layers

The gateway's HTTP surface, split along the DESIGN-API.md layering so
compatibility-first routes stay separate from Vampire-native control routes.

| Module | Layer | Routes | Purpose |
| --- | --- | --- | --- |
| [`openai_compat.py`](openai_compat.py) | Layer 1 | `/v1/*` | LM Studio / OpenAI-compatible surface that existing OpenAI and LM Studio clients can use unchanged. Proxies to the downstream node, supports opt-in virtual-model routing, and adds `X-Vampire-*` response headers |
| [`control.py`](control.py) | Layer 2 | `/vampire/v1/*` | Vampire control API: gateway status, node CRUD and interrogation, discovery, route policies, share mode, and metrics. Later-phase routes (fusion, pipelines, jobs, traces) are stubbed |
| [`_auth.py`](_auth.py) | — | — | Optional bearer-token dependency shared by control routes (constant-time comparison via `hmac.compare_digest`) |

Both surfaces are mounted by the application factory in
[`vampire/app.py`](../app.py). When `VAMPIRE_AUTH_TOKEN` is configured, both
`/v1/*` and `/vampire/v1/*` require the bearer token; an empty token keeps the
APIs open (see [`vampire/auth.py`](../auth.py)).

Related tests: [`tests/test_phase1.py`](../../../tests/test_phase1.py),
[`tests/test_phase2.py`](../../../tests/test_phase2.py),
[`tests/test_phase3.py`](../../../tests/test_phase3.py), and
[`tests/test_auth.py`](../../../tests/test_auth.py).
