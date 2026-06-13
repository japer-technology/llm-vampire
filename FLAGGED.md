# Flagged Issues

This document captures the currently flagged repository and roadmap issues, the
evidence in the repository, the risk if left unresolved, and the recommended
direction for each one.

## 1. Resolve the license discrepancy

### What is flagged

The repository currently communicates two different licensing positions:

- `README.md` shows a `License: TBD` badge and says a license has not yet been
  selected.
- `pyproject.toml` declares `license = { file = "LICENSE" }` and classifies the
  package as `License :: OSI Approved :: MIT License`.
- `LICENSE.md` contains the MIT License text.
- `CONTRIBUTING.md` tells contributors their work is licensed under the same
  terms as the project.
- `IMPLEMENTATION-PLAN.md` lists `LICENSE                 MIT` in the target
  repository layout.

### Why it matters

Licensing ambiguity is a governance blocker. The project is actively inviting
contributors and design feedback, so unclear rights can discourage adoption,
complicate contribution ownership, and make downstream packaging risky.

### Direction to go

Treat MIT as the selected project license unless the maintainer explicitly
chooses otherwise. The repository already contains the MIT license file and
package metadata, so the lowest-friction fix is to align public documentation
with that choice.

Recommended next steps:

1. Update the `README.md` license badge from `TBD` to `MIT`.
2. Replace the `README.md` license section with a short MIT statement linking to
   `LICENSE.md`.
3. Confirm whether `pyproject.toml` should point at `LICENSE.md` instead of
   `LICENSE`, because the repository file is named `LICENSE.md`.
4. Keep `CONTRIBUTING.md` as-is after the README is corrected, because it already
   references `LICENSE.md`.

## 2. Enhance testing dependencies for async code

### What is flagged

`pyproject.toml` currently includes these development dependencies:

- `mypy`
- `pytest`
- `ruff`

The runtime stack is asynchronous and HTTP-heavy:

- FastAPI serves the gateway and control API.
- Uvicorn runs the app.
- `httpx.AsyncClient` is used for downstream LM Studio requests and streaming.
- Phase 1 and later phases preserve streaming behavior and route requests across
  nodes.

The current test suite exists and exercises implemented phases, but the dev
extras do not include async-focused pytest support or coverage reporting.

### Why it matters

As routing, coalescing, caching, discovery, and streaming fan-out grow, tests
will need to await async routes and mock async HTTPX behavior cleanly. Without
explicit async test support, future tests may become awkward, rely on sync
wrappers too heavily, or miss event-loop edge cases. Without coverage reporting,
it will be harder to track whether new orchestration paths are actually tested.

### Direction to go

Add async and coverage testing dependencies when the next async-heavy feature
work begins, preferably before Phase 5 coalescing/cache is implemented.

Recommended next steps:

1. Add `pytest-asyncio` to `[project.optional-dependencies].dev`.
2. Add `pytest-cov` to `[project.optional-dependencies].dev`.
3. Configure pytest async mode if needed once async tests are introduced.
4. Start with targeted async tests for streaming proxy behavior, downstream
   timeout handling, route failover, and concurrent request coalescing.
5. Add coverage reporting to CI only after the baseline is useful; avoid blocking
   early development on an arbitrary percentage threshold.

## 3. Architecture for Phase 5 coalescing and caching

### What is flagged

Phase 5 is planned as:

- In-flight deduplication of identical concurrent prompts.
- Exact-result cache.
- Keeping CPU-bound work off the event loop.

The current stack points to an async implementation model:

- FastAPI/asyncio request handling.
- `httpx.AsyncClient` for downstream requests.
- `aiosqlite` is already a dependency and the implementation plan describes it
  as a persistence seam for state.

The concern is that using SQLite as the primary hot-path cache layer could add
avoidable disk I/O and contention to latency-sensitive LLM requests.

### Why it matters

Coalescing and exact-result caching can significantly reduce duplicate work, but
they sit on the request path. A slow cache path can erase the benefit of avoiding
duplicate inference. This is especially important for streaming and local-area
network workloads, where user-visible latency and tail latency matter.

### Direction to go

Use a memory-first design for Phase 5, with persistence treated as a secondary
durability layer rather than the first lookup path.

Recommended next steps:

1. Define a canonical request fingerprint for cacheable requests, including
   model, normalized messages/input, relevant generation parameters, routing
   options, and any policy-relevant fields.
2. Maintain an in-flight map keyed by fingerprint, with each key pointing to an
   awaitable result holder such as an `asyncio.Future`, `asyncio.Task`, or a
   small coalescing record guarded by an async lock.
3. Ensure duplicate concurrent requests await the existing in-flight result
   instead of opening another downstream connection.
4. Start with non-streaming exact-result caching only; streaming cache replay
   should be a separate design decision because chunk timing, cancellation, and
   partial failures are more complex.
5. Use a memory LRU/TTL cache as the primary exact-result cache. A small custom
   implementation may be enough initially; consider `cachetools` only if the
   project wants a maintained dependency for eviction behavior.
6. Use `aiosqlite` for optional persistence, warm-start, metrics, or audit data,
   not as the first hot-path lookup for every request.
7. Add explicit invalidation boundaries for model changes, route-policy changes,
   trust/policy changes, and generation-parameter differences.
8. Track cache and coalescing metrics separately: hit rate, coalesced request
   count, cache evictions, in-flight wait time, and downstream requests avoided.

## 4. Circuit breakers for network routing resilience

### What is flagged

The project routes across local and trusted-network LM Studio nodes. Those nodes
may be laptops, desktops, home GPUs, headless servers, or other personal devices.
Such machines can sleep, roam between networks, throttle, restart LM Studio, or
silently drop connections.

The current implementation and docs already include:

- Node health checks and model interrogation.
- Static/dev-subnet discovery.
- Route fallback policies.
- HTTP timeouts for discovery and downstream connection attempts.

The flagged gap is that fallback alone still depends on detecting failure at
request time. If a preferred node silently drops, users can pay the timeout
penalty repeatedly.

### Why it matters

Without circuit-breaking, one unstable preferred node can dominate tail latency.
Repeated connect/read failures can make a healthy fallback feel slow because the
gateway waits for the broken node first. This also makes the dashboard less
trustworthy if the route layer keeps selecting nodes that health checks should
have temporarily quarantined.

### Direction to go

Add a lightweight circuit-breaker state to node health and route selection before
advanced routing/fusion modes expand the number of downstream calls.

Recommended next steps:

1. Track consecutive failures, last failure time, and circuit state per node.
2. Use simple states first: `closed` for healthy, `open` for temporarily skipped,
   and `half_open` for one probe after a cooldown.
3. Trip the circuit after a small number of consecutive health-check or request
   failures.
4. While open, exclude the node from normal route selection immediately instead
   of waiting for another request timeout.
5. Allow health checks or a controlled probe to close the circuit again.
6. Surface circuit state in `/vampire/v1/nodes`, `/vampire/v1/metrics`, and the
   dashboard so owners understand why a node is skipped.
7. Prefer a custom minimal implementation first. Consider `tenacity` only if the
   project also needs richer retry/backoff policies; circuit-breaking and retry
   behavior should remain explicit and easy to reason about.

## 5. Validate mDNS discovery capabilities

### What is flagged

`pyproject.toml` already includes `zeroconf`, and METHOD-A lists mDNS as part of
the discovery stack. However, `IMPLEMENTATION-PLAN.md` states that MVP discovery
uses manual registration and static/dev-subnet scanning first, with mDNS and the
node agent deferred.

The open question is whether standard LM Studio instances natively advertise a
discoverable mDNS service that Vampire can consume. If they do not, `zeroconf`
alone will not discover ordinary LM Studio servers without an additional
advertiser.

### Why it matters

Discovery shapes onboarding. If Vampire assumes native LM Studio mDNS broadcasts
that do not exist, users will see unreliable or empty discovery results. If
Vampire requires its own advertiser, that should be explicit in the roadmap and
owner consent model.

### Direction to go

Validate mDNS before building a deep integration, and keep static/dev-subnet
discovery as the MVP path until the behavior is proven.

Recommended next steps:

1. Test current LM Studio desktop, headless, and CLI-managed server modes on a
   local network to see whether any mDNS service is advertised.
2. Record observed service names, TXT records, ports, authentication hints, and
   version differences if broadcasts exist.
3. If LM Studio does not broadcast, document that Vampire mDNS requires a
   Vampire-controlled advertiser.
4. Decide whether that advertiser belongs in the main gateway, a future optional
   node agent, or an owner-run companion process.
5. Preserve owner consent: do not advertise a node unless the owner explicitly
   opts in, and do not infer shareability from the mere presence of an open port.
6. Keep manual registration and subnet scanning as first-class discovery paths,
   because they work without relying on upstream LM Studio mDNS behavior.

## Recommended ordering

1. Resolve the license documentation mismatch immediately.
2. Add async and coverage test dependencies before the next async-heavy feature.
3. Design Phase 5 around memory-first coalescing/cache semantics.
4. Add circuit-breaker state before relying on fallback for unstable LAN nodes at
   scale.
5. Validate LM Studio mDNS behavior experimentally before committing to a
   zeroconf-based discovery user experience.
