# MVP — Minimum Viable Product

> The first of three product definitions following Guy Kawasaki's progression in
> *The Art of the Start 2.0*: don't stop at a Minimum **Viable** Product — build a
> Minimum **Viable Valuable** Product ([MVVP.md](MVVP.md)), and ideally a Minimum
> **Viable Valuable Validating** Product ([MVVVP.md](MVVVP.md)).

This document defines the smallest version of `lmstudio-vampire` that is
**viable**: it works, it can be shipped, and it can be used end-to-end. It is
the floor, not the goal. It serves the vision in [VISION.md](VISION.md) and the
MVP roadmap in [ASPIRATION.md](ASPIRATION.md), and implements the "Minimal MVP"
API surface in [DESIGN-API.md](DESIGN-API.md).

---

## What "minimum" and "viable" mean here

- **Minimum:** the least scope that produces a working, honest product — no
  fusion, no optimizer, no event mode, no policy engine.
- **Viable:** a developer can install it, point an existing OpenAI-compatible
  client at it, and get answers from one or more LM Studio nodes today.

---

## Scope

### In scope

1. **OpenAI-compatible gateway** on `http://localhost:7777/v1`:
   - `GET /v1/models`
   - `POST /v1/chat/completions` (including streaming passthrough)
   - `POST /v1/embeddings`
2. **Manual node management** (no automatic discovery):
   - `GET /vampire/v1/status`
   - `GET /vampire/v1/nodes`, `POST /vampire/v1/nodes`
   - `GET /vampire/v1/models`
   - `GET /vampire/v1/metrics`
3. **Basic routing**: preferred node with fallback; bearer tokens forwarded
   upstream; basic health checks.
4. **CLI**: `vampire serve`, `vampire nodes add`, `vampire nodes list`.

This corresponds to Phases 1–2 of the ASPIRATION.md roadmap and §24 "Minimal
MVP" of DESIGN-API.md. Note that this MVP **intentionally narrows** §24: the
`race` and `fusion` modes listed there are deferred (see "Out of scope" below),
because they are not part of the smallest *viable* proxy. This MVP implements
§24's API surface and the `route`/`fallback` modes only; fusion arrives in the
MVVVP.

### Out of scope (deferred to MVVP/MVVVP)

- Request coalescing and caching
- mDNS discovery and node agents
- Realms, policy engine, owner modes
- Fusion, race, debate, pipelines
- Event mode, QR onboarding
- Model optimizer and benchmarking

---

## Definition of done

- A normal OpenAI-compatible client works unchanged when its base URL is
  switched from `http://localhost:1234/v1` to `http://localhost:7777/v1`.
- Requests fail over from a downed preferred node to a fallback node.
- The control endpoints respond: `GET /vampire/v1/status`,
  `GET /vampire/v1/nodes` (and `POST`), `GET /vampire/v1/models`, and
  `GET /vampire/v1/metrics`.
- `pip install -e ".[dev]"` installs, and `python -m pytest` passes.

---

## Why an MVP is not enough

Kawasaki's warning: a product that is merely minimum and viable can be
uninteresting and unloved. An OpenAI proxy with manual node lists is viable but
not yet *valuable* — many proxies exist. The value and the validation of the
vision come next: see [MVVP.md](MVVP.md) and [MVVVP.md](MVVVP.md).
