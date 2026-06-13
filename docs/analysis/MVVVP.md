# MVVVP — Minimum Viable Valuable Validating Product

> The third of three product definitions following Guy Kawasaki's progression
> in *The Art of the Start 2.0*. Kawasaki's full prescription is not an MVP but
> an **MVVVP**: a product that is minimum, viable, **valuable**, and
> **validating** — it proves the vision is right (or wrong) with real evidence.
> Builds on [MVP.md](MVP.md) and [MVVP.md](MVVP.md).

This document defines the smallest version of `lmstudio-vampire` that
validates the vision in [VISION.md](VISION.md): every claim in that paragraph
becomes a testable hypothesis with a measurable result.

---

## What "validating" adds

Viability proves it runs. Value proves it matters. **Validation proves the
thesis** — that idle, LM Studio-compatible GPUs on a local network can become
one governed, private AI service that families, businesses, and events
actually adopt. The MVVVP exists to generate that proof.

---

## Scope: everything in MVVP.md, plus

1. **Realms and policy engine** (Phase 5 of ASPIRATION.md)
   - `personal / family / business / event` realms
   - Per-realm model allowlists, token rules, cache rules, rate limits
   - Audit logs — required to validate the governance claim
2. **Answer fusion across machines**
   - `race`, `fusion` (best-of-N), and consensus modes from DESIGN-API.md
   - Validates "fuses answers across machines"
3. **Event mode** (Phase 8)
   - QR onboarding, temporary guest tokens, safe model profile, auto-expiry,
     owner stop button
   - Validates "classrooms and events become AI-capable with just one strong host"
4. **Metrics and traces as first-class evidence**
   - `GET /vampire/v1/metrics`, `GET /vampire/v1/traces/{trace_id}`
   - Latency, cache-hit, coalescing, failover, and per-realm usage counters

---

## The hypotheses this product validates

Each sentence of VISION.md becomes a measurable test:

| Vision claim | Hypothesis | Evidence collected |
| --- | --- | --- |
| Idle GPUs become one governed service | Owners will opt machines in when control is one click away | Opt-in rate; stop-sharing usage; audit logs |
| Discovers and verifies endpoints | Discovery finds real nodes with zero manual config | Discovery success rate vs. manual entry |
| Respects tokens and policy before routing | No request reaches a node outside its realm/policy | Policy-denial audit entries; zero leakage in traces |
| Load-balances and fails over | Multi-node routing beats single-node on availability | Failover counts; uptime under node loss |
| Coalesces identical prompts | Shared rooms produce significant duplicate traffic | Coalescing and cache-hit ratios |
| Fuses answers across machines | Best-of-N/consensus measurably improves answer quality | Fusion mode usage; quality comparisons in traces |
| Optimizes latency, privacy, cost, quality | Routed requests are faster/cheaper than naive choice | Latency percentiles per strategy |
| Families share GPUs | A household runs it for a week without intervention | Family-realm retention |
| Events become AI-capable with one host | A room of guests is served by one machine via QR onboarding | Event-mode session counts; expiry behavior |
| Users simply see working, local-first AI | Unmodified OpenAI clients work with no support requests | Compatibility-route success rate |

---

## Definition of validated

The MVVVP succeeds when at least one real family, one real team, and one real
event run it on their own hardware and the metrics above confirm — or
honestly refute — the vision. Either outcome is a win: Kawasaki's "validating"
means the product teaches you whether the curve-jump is real before you scale
it.
