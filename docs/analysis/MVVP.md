# MVVP — Minimum Viable Valuable Product

> The second of three product definitions following Guy Kawasaki's progression
> in *The Art of the Start 2.0*: an MVP that is also **valuable** — something
> people genuinely want, that jumps a curve rather than competing on the same
> one. Builds on [MVP.md](MVP.md); leads to [MVVVP.md](MVVVP.md).

This document defines the smallest version of `lmstudio-vampire` that is not
just viable but **valuable**: it does something for users that no plain proxy
does, and that they would miss if it were taken away. It carries the vision in
[VISION.md](VISION.md) further into reality.

---

## What "valuable" adds

Kawasaki's point: viability proves the product runs; value proves it matters.
The MVVP must deliver the parts of the vision that make people care:

> "...it load-balances, fails over, coalesces identical prompts... Families
> share GPUs... The owner decides when to contribute; users simply see
> working, local-first AI."

A proxy is a commodity. **One governed, private AI service made from GPUs the
user already owns** is a curve-jump.

---

## Scope: everything in MVP.md, plus

1. **Automatic discovery (opt-in)**
   - mDNS service advertisement by a lightweight node agent
   - `POST /vampire/v1/discover`
   - Capability verification: probe `GET /v1/models`, record capabilities
2. **Request coalescing and caching** (Phase 3 of ASPIRATION.md)
   - Exact request fingerprinting and in-flight deduplication
   - Streaming multiplex to concurrent identical requests
   - TTL result cache with a disable flag
3. **Real routing** (Phase 4)
   - `round_robin`, `least_busy`, `least_latency`, `model_affinity`
   - Model aliasing, retry, basic circuit breaker
4. **Owner control — the heart of the value**
   - Owner modes: `Off / Local only / Family share / ...`
   - One-click stop-sharing
   - Token vault: per-node tokens stored locally, never leaked downstream
5. **Simple local dashboard** showing nodes, models, health, and live traffic.

### Still out of scope (deferred to MVVVP)

- Realms and full policy engine
- Fusion, debate, pipelines
- Event mode
- Model optimizer and benchmarks

---

## Definition of valuable (acceptance signals)

- A family can share one gaming PC's GPU with other household devices, and the
  owner can stop sharing instantly.
- Two devices asking the same question at the same time trigger **one**
  inference.
- A weak laptop gets first-token latency close to talking to the strong host
  directly.
- Users choose Vampire over pointing clients at LM Studio directly — because it
  is better, not just compatible.

---

## Why valuable is still not enough

A valuable product can still be built on unproven assumptions. The final step
is a product that **validates** the vision with evidence: see
[MVVVP.md](MVVVP.md).
