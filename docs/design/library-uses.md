# Uses for the Official LM Studio Code Libraries

LM Studio publishes two official, MIT-licensed client SDKs:

- **`lmstudio-js`** — TypeScript/JavaScript SDK ([lmstudio-ai/lmstudio-js](https://github.com/lmstudio-ai/lmstudio-js)).
- **`lmstudio-python`** — Python SDK ([lmstudio-ai/lmstudio-python](https://github.com/lmstudio-ai/lmstudio-python)).

[`lmstudio-libraries.md`](lmstudio-libraries.md) records the two links. This
document explains *how* those libraries could be useful — both inside
`lmstudio-vampire` and in the wider ecosystem around it.

Both SDKs wrap the same surfaces this repo already targets by hand: the
OpenAI-compatible `/v1/*` endpoints, the LM Studio REST API
([`../../lmstudio.ai/04-rest-api-v1.md`](../../lmstudio.ai/04-rest-api-v1.md)),
model lifecycle controls
([`../../lmstudio.ai/07-model-lifecycle.md`](../../lmstudio.ai/07-model-lifecycle.md)),
and the richer WebSocket-based control channel that the raw REST surface does
not expose.

---

## Where Vampire stands today

The gateway currently speaks to LM Studio nodes with **hand-written `httpx`
calls** against raw HTTP surfaces:

- `src/vampire/proxy.py` forwards `/v1/*` requests verbatim.
- `src/vampire/registry.py` / `src/vampire/cluster.py` interrogate nodes for
  inventory, health, and metrics.

This is deliberate — Vampire is a *gateway* that must degrade across version
heterogeneity (`/api/v1/models` → `/api/v0/models` → `/v1/models`) and must only
ever consume what an owner exposes over HTTP
([`../../lmstudio.ai/12-vampire-integration.md`](../../lmstudio.ai/12-vampire-integration.md),
constraints 2 and 3). The official SDKs are not a drop-in replacement for that
proxy seam, but they are valuable in several adjacent roles described below.

---

## 1. Uses inside this repository

### 1a. Node interrogation and model lifecycle (`lmstudio-python`)

`lmstudio-python` already models the things Vampire's registry interrogates:
listing downloaded vs. loaded models, reading context limits and capabilities,
and issuing `load` / `unload` with `ttl`. Where an owner's token permits
lifecycle control, the SDK could replace bespoke REST plumbing for **pre-warming
and rebalancing**, reducing the surface area Vampire has to maintain against LM
Studio API changes.

Caveat: the SDK targets LM Studio's native channel, so it cannot fully replace
the OpenAI-compat fallback chain Vampire needs for heterogeneous/older nodes.
The pragmatic split is **SDK for capable native nodes, raw HTTP fallback for the
rest**, behind the existing registry/cluster seam.

### 1b. Capability and concurrency probing

The SDK exposes structured access to per-model `parallel` slots, loaded
instances, and runtime stats (TPS/TTFT) that feed Vampire's routing strategies
(`least_loaded`, latency-/quality-aware). Using typed SDK responses instead of
ad-hoc JSON parsing would make
`src/vampire/router.py` inputs less brittle.

### 1c. Integration tests and fixtures

Even if production code keeps the raw proxy, `lmstudio-python` is useful in
**`tests/`** as a high-level client to stand up or drive a real/mock LM Studio
node, assert that Vampire's proxy preserves streaming and OpenAI semantics, and
generate realistic inventory fixtures — complementing the existing
`tests/test_phaseN.py` suites.

### 1d. Owner-side provisioning recipes

For headless/`llmster` nodes
([`../../lmstudio.ai/08-headless.md`](../../lmstudio.ai/08-headless.md)),
either SDK (or the `lms` CLI) can script "bring up a node, load these models,
set TTL, then register it with Vampire" — documentation and helper scripts that
live *outside* the gateway's request path but make a fleet reproducible.

### 1e. Reference for the JS/TS browser tooling

This repo ships a product-bundled dashboard (`src/vampire/assets/vampire-dashboard.html`)
and self-contained helper browser tools (`packaging/html/vampire-scanner.html`,
`packaging/html/landing.html`) that talk to LM Studio surfaces directly from the browser.
`lmstudio-js` is the canonical reference for the request/response shapes and identity
headers those tools rely on, and could back a future bundled dashboard build.

---

## 2. Uses beyond this repository

### 2a. Client SDKs for Vampire consumers

Because Vampire presents a **stable OpenAI-compatible endpoint**, anything that
speaks `lmstudio-js` / `lmstudio-python` against a single LM Studio node can be
pointed at the Vampire gateway instead by changing only the base URL — giving
downstream apps a one-node developer experience over a whole fleet.

### 2b. Agentic and `.act()` workflows

The SDKs expose higher-level agentic helpers (tool use, structured output,
`.act()`-style loops) that have no REST equivalent. Applications can keep using
those ergonomics while Vampire transparently provides routing, failover, and
aggregation underneath.

### 2c. Polyglot ecosystem

Two official SDKs mean the same Vampire-fronted fleet is reachable from both the
Python data/ML world and the JS/TS web/edge world without re-implementing a
client. This widens who can build on a Vampire deployment.

### 2d. Examples, docs, and onboarding

Linking the SDKs in onboarding material (READMEs, `LMSTUDIO-SETUP.md`) gives new
contributors and operators a sanctioned, typed way to explore LM Studio
behavior before wiring nodes into Vampire.

---

## 3. What the libraries do *not* solve

The SDKs are single-owner clients. They do **not** provide the layer that is
Vampire's reason to exist
([`../../lmstudio.ai/12-vampire-integration.md`](../../lmstudio.ai/12-vampire-integration.md)):
cross-owner federation, a trust/realm node registry, cross-server routing and
failover, request coalescing/caching, fusion modes, and fleet-level
observability. Adopting an SDK is an **implementation and ergonomics** choice for
the node-facing edge and for consumers — not a substitute for Vampire's
orchestration value.

---

## 4. Recommended posture

| Concern | Recommendation |
| --- | --- |
| Transparent `/v1` proxy | Keep raw `httpx` (must stay version-tolerant and side-channel-free) |
| Native node lifecycle / capability probing | Evaluate `lmstudio-python` behind the registry/cluster seam, with HTTP fallback |
| Tests & fixtures | Use `lmstudio-python` as a convenience client |
| Owner provisioning | Script with the SDKs or `lms` CLI, outside the request path |
| Downstream consumers | Document that both SDKs work against the Vampire endpoint by base-URL swap |
| Browser tooling | Treat `lmstudio-js` as the shape-of-truth reference |

In short: the official libraries are most useful to Vampire as **node-edge
clients, test tooling, provisioning helpers, and a reference for consumers** —
while the gateway's own request path stays intentionally low-level so it can
honor LM Studio's owner-controlled, heterogeneous, snapshot-in-time reality.
