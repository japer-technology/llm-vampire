# Feature Request: Native Multi-Node Gateway ("LM Studio Fleet")

> **TL;DR** — Add a first-party mode to LM Studio that lets one instance act as a
> governed gateway in front of **many** owner-approved LM Studio servers, exposing
> a single, stable OpenAI-compatible endpoint that interrogates, routes,
> load-balances, and fails over across the fleet. This is the mechanism that the
> third-party [`lmstudio-vampire`](README.md) project builds on top of LM Studio
> today; this document describes how LM Studio could implement it as a native
> feature instead.

- **Status:** Proposal / feature request
- **Audience:** LM Studio maintainers ([lmstudio-ai](https://github.com/lmstudio-ai))
- **Relationship to this repo:** `lmstudio-vampire` is an external orchestration
  layer. Everything below is achievable today only by sitting *outside* LM Studio.
  This request asks whether the most broadly useful parts belong *inside* it.

---

## 1. Summary

LM Studio already turns a single machine into a private, OpenAI-compatible
inference server. What it does **not** provide is a way to treat a *group* of LM
Studio servers — a home with two GPUs, a small office of workstations, a rack of
[llmster](lmstudio.ai/08-headless.md) daemons — as **one** endpoint.

This request proposes a native **Fleet Gateway** mode: an LM Studio instance (or
the `lms` CLI / llmster daemon) that:

1. holds a registry of other owner-approved LM Studio `base_url`s;
2. interrogates each node's models, capabilities, load, and version;
3. publishes one aggregated OpenAI-compatible `/v1/*` surface; and
4. routes each request to the best node, with failover when nodes vanish.

It is deliberately additive: existing single-node behavior is unchanged, and the
gateway only ever consumes endpoints an owner has already chosen to expose.

## 2. Motivation

AI compute is already widely distributed, but the missing layer is not model
execution — LM Studio solves that — it is **discovery, routing, policy, and
coordination across machines** (see [`VISION.md`](VISION.md)).

Concrete pain points that exist today with single-node LM Studio:

- **No single endpoint for many machines.** A developer with a laptop and a GPU
  desktop must point clients at one box at a time and hand-edit base URLs.
- **No load balancing or failover.** If the chosen node is busy, evicting a
  model ([JIT/TTL](lmstudio.ai/07-model-lifecycle.md)), or simply switched off,
  the client just fails — even when another node could have served the request.
- **No fleet-wide model view.** `/v1/models` reflects one server; there is no
  built-in way to ask "which of my machines can serve this model right now?"
- **Manual capacity management.** Continuous batching
  ([`parallel`](lmstudio.ai/11-concurrency.md)) is per-instance; nothing spreads
  concurrent requests across instances.

Users solve this today with external proxies (including this project). Bringing a
governed subset into LM Studio would make multi-machine setups a supported,
owner-controlled first-party experience.

## 3. Proposed feature

A new **Fleet Gateway** capability, opt-in and off by default.

### 3.1 Fleet node registry

- Owner registers peer nodes by `base_url` (the same address other clients use),
  optionally with a per-node API token from
  [LM Studio's token auth](lmstudio.ai/06-authentication.md).
- Each node carries owner-set metadata: a friendly name, a trust level, and
  whether the gateway may load/unload models on it.
- Registration is **owner opt-in only** — the gateway never scans or controls a
  machine that has not been deliberately added.

### 3.2 Node interrogation (degrading across versions)

Reuse the existing API surfaces to build a live picture of each node, degrading
gracefully across LM Studio versions
([overview](lmstudio.ai/01-overview.md), [v0 REST](lmstudio.ai/05-rest-api-v0.md)):

```
GET /api/v1/models   →  GET /api/v0/models   →  GET /v1/models
```

From these the gateway derives, per node: model inventory, `state`
(loaded vs. loadable), context limits, capability flags (`vision`,
`trained_for_tool_use`, `reasoning`), and free `parallel` slots
([v1 REST](lmstudio.ai/04-rest-api-v1.md), [concurrency](lmstudio.ai/11-concurrency.md)).

### 3.3 Aggregated OpenAI-compatible surface

The gateway exposes the familiar
[OpenAI-compatible](lmstudio.ai/03-openai-compat.md) routes — `/v1/models`,
`/v1/chat/completions`, `/v1/completions`, `/v1/embeddings` — where:

- `GET /v1/models` returns the **union** of models available across the fleet
  (de-duplicated by model id), so existing clients see one catalog.
- Chat/completions/embeddings requests are transparently forwarded to a selected
  node, preserving streaming and OpenAI-style error envelopes.

Clients change **only the base URL** — exactly the property that makes LM Studio's
single-node `/v1/*` surface so useful today.

### 3.4 Routing and failover

For each request, select a candidate node by:

- **model id** → nodes advertising that model;
- **capability** → vision / tools / reasoning requirements;
- **state / cold-start cost** → already loaded vs. JIT load
  ([model lifecycle](lmstudio.ai/07-model-lifecycle.md));
- **capacity** → free continuous-batching slots
  ([concurrency](lmstudio.ai/11-concurrency.md));
- **policy** → owner-assigned trust level.

Offer a small set of strategies (e.g. `round_robin`, `least_busy`,
`least_latency`, `model_affinity`) with **failover to the next candidate** when a
node is unreachable or evicts a model mid-flight. Because nodes can appear and
vanish freely, all inventory is treated as advisory and re-verified on failure.

### 3.5 Owner control and observability

- Every fleet behavior is owner-controlled: which nodes are in the fleet, their
  trust levels, whether the gateway may load/unload models, and which strategy is
  used — consistent with LM Studio's existing
  [owner switchboard](lmstudio.ai/02-api-server.md).
- Surface per-node and fleet-level status (reachability, loaded models, recent
  TPS/TTFT from [v0 stats](lmstudio.ai/05-rest-api-v0.md)) in the GUI and via the
  `lms` CLI.

## 4. How it maps onto existing LM Studio mechanisms

This feature is largely an **orchestration of mechanisms LM Studio already has**.
The mapping below is adapted from
[`lmstudio.ai/12-vampire-integration.md`](lmstudio.ai/12-vampire-integration.md):

| Existing LM Studio mechanism | Enables (in the Fleet Gateway) |
| --- | --- |
| API server with owner-set port/bind ([02](lmstudio.ai/02-api-server.md)) | Registering peer nodes by `base_url`; reachability stays owner opt-in |
| "Serve on Local Network" ([02](lmstudio.ai/02-api-server.md)) | LAN-wide fleets — the core premise |
| OpenAI-compatible `/v1/*` ([03](lmstudio.ai/03-openai-compat.md)) | Transparent forwarding; clients change only the base URL |
| `GET /api/v1/models` ([04](lmstudio.ai/04-rest-api-v1.md)) | Inventory, context limits, capabilities, concurrency per node |
| `POST /api/v1/models/load` / `unload` ([04](lmstudio.ai/04-rest-api-v1.md)) | Optional pre-warming / rebalancing when permitted |
| `GET /api/v0/models` `state` + `stats` ([05](lmstudio.ai/05-rest-api-v0.md)) | Loaded-vs-loadable and latency inputs for routing |
| API tokens with per-token permissions ([06](lmstudio.ai/06-authentication.md)) | Per-node credentials; owner consent and revocation |
| JIT / Idle TTL / Auto-Evict ([07](lmstudio.ai/07-model-lifecycle.md)) | Cold-start cost modeling; eviction-aware routing |
| llmster / headless ([08](lmstudio.ai/08-headless.md)) | Always-on, server-grade fleet nodes |
| LM Link ([09](lmstudio.ai/09-lm-link.md)) | Nodes whose compute lives elsewhere |
| `lms` CLI ([10](lmstudio.ai/10-cli.md)) | Owner-side scripting of fleet membership |
| Continuous batching `parallel` ([11](lmstudio.ai/11-concurrency.md)) | Per-instance capacity for `least_busy` routing |

The gap LM Studio would be closing is the **coordination layer above a single
owner's box**: a registry of nodes, an aggregated catalog, and cross-node routing
with failover.

## 5. Proposed API / UX surface (illustrative)

Owner-facing controls (names illustrative, not prescriptive):

- **GUI:** a "Fleet" tab where the owner adds peer nodes (`base_url` + optional
  token), sets a trust level per node, picks a routing strategy, and watches live
  per-node health.
- **CLI:** fleet management via `lms`, e.g. adding/removing nodes, draining a node
  out of routing for maintenance, and restoring it.
- **Endpoint:** the gateway serves standard `/v1/*` on the owner's chosen
  port/bind, so any OpenAI-compatible client works unchanged.

No new client-side protocol is required: the value is delivered entirely through
the existing OpenAI-compatible surface.

## 6. Owner control, privacy, and constraints

These constraints mirror those Vampire already binds itself to
([12](lmstudio.ai/12-vampire-integration.md) §"Constraints"), and should hold for
a native implementation too:

1. **The owner's switchboard is law.** Fleet membership, per-node tokens,
   load/unload permission, and routing strategy are all owner-controlled. The
   gateway only consumes what each node already offers.
2. **No side channels.** The gateway talks to nodes exclusively through the
   documented HTTP surfaces — never another machine's OS, files, or CLI.
3. **Version heterogeneity.** Interrogation degrades across
   `/api/v1/models` → `/api/v0/models` → `/v1/models`.
4. **Everything is a snapshot.** Models load, evict, and migrate behind the
   gateway's back; inventory is advisory and must be re-verified or failed over.
5. **Local-first by default.** Prompts stay on the owner's trusted nodes; nothing
   leaves the network unless the owner explicitly enables remote nodes.

## 7. Out of scope for this request

To keep the request focused on what most users need, the following — which remain
the domain of higher-level tools such as Vampire — are explicitly **not** part of
this proposal:

- **Cross-owner federation.** A single owner's fleet only; aggregating endpoints
  from *multiple* owners under shared policy is out of scope.
- **Request coalescing and result caching.**
- **Advanced fusion modes** (parallel/race/judge-refine/debate across nodes).
- **Fleet-wide governance, quotas, and audit** beyond basic status.

These could be future extensions, but the high-value core is the **single-owner
multi-node gateway** described in §3.

## 8. Alternatives considered

- **External reverse proxy (status quo).** Works (this is what `lmstudio-vampire`
  does), but every user must install and operate a separate tool, and it cannot
  offer the same in-GUI, owner-consented experience as a first-party feature.
- **Client-side load balancing.** Pushes node lists, health checks, and failover
  into every client/SDK; brittle and duplicated everywhere.
- **Do nothing.** Multi-machine owners keep hand-routing to one box at a time.

A native gateway mode is the only option that delivers the single-endpoint,
owner-controlled experience without external moving parts.

## 9. Open questions

- Should the gateway role live in the desktop app, in llmster, in `lms`, or all
  three?
- How should fleet node tokens be stored and rotated relative to existing
  [token auth](lmstudio.ai/06-authentication.md)?
- What is the minimum useful routing strategy set for a v1?
- Should `GET /v1/models` annotate which node(s) can serve each model, or stay
  strictly OpenAI-shaped?

---

*Filed in the context of [`lmstudio-vampire`](README.md), a third-party project
that implements this mechanism on top of LM Studio today. It is not affiliated
with LM Studio unless explicitly adopted by that team.*
