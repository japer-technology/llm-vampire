# `vampire.assets` — packaged static assets

Static files shipped inside the `vampire` package and served by the gateway.

| File | Purpose |
| --- | --- |
| [`vampire-dashboard.html`](vampire-dashboard.html) | The Phase 4 browser dashboard: a self-contained single-file SPA served at `/` by the FastAPI app ([`vampire/app.py`](../app.py)). It talks to the `/vampire/v1/*` control API to show gateway status, nodes, models, routes, and metrics |

Notes:

- Assets are included in wheels/sdists via the `package-data` configuration in
  [`pyproject.toml`](../../../pyproject.toml).
- Open the dashboard with `vampire dashboard` (or `vampire ui`), or browse to
  the gateway root (default `http://127.0.0.1:7777/`).
- The dashboard is the packaged product UI. The standalone HTML helper apps
  live outside the package (see [`packaging/html/`](../../../packaging/html/README.md)).
- Behaviour is covered by [`tests/test_phase4.py`](../../../tests/test_phase4.py).
