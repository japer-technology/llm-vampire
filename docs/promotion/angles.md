# Promotion Angles

This guide turns the project vision into public-facing, GitHub-ready promotion
copy. It is deliberately conservative: promote what the repository can support
today, label roadmap features clearly, and keep every claim tied to the
project's actual architecture.

## Canonical Positioning

Use this as the default description in READMEs, release notes, social posts,
issue summaries, and directory listings:

> `lmstudio-vampire` turns owner-approved LM Studio API endpoints into one
> governed, private, OpenAI-compatible AI service.

Shorter variants:

- Private AI compute, wherever the owner allows it.
- One stable local AI endpoint for the LM Studio machines you already trust.
- A routing and governance layer for owner-approved LM Studio servers.

Longer variant:

> `lmstudio-vampire` sits in front of owner-approved LM Studio servers, verifies
> what each endpoint can provide, and exposes one OpenAI-compatible gateway for
> local-first AI applications. Owners keep control of server exposure, ports,
> authentication, model availability, and when their machines participate.

## Claim Discipline

The project is public-facing and early-stage, so promotion must distinguish
between shipped behavior and intended behavior.

| Claim class | How to describe it | Examples |
| --- | --- | --- |
| Implemented now | Use direct language. | Transparent `/v1/*` proxy, node registry, static/dev-subnet discovery, virtual-model routing, dashboard, metrics, share-state seam. |
| Supported by LM Studio | Attribute the capability to LM Studio and explain Vampire's role. | LM Link, `llmster`, OpenAI-compatible endpoints, API-token authentication, model metadata, heterogeneous runtimes. |
| Planned | Mark as planned, future, or roadmap. | Coalescing/cache, auth/policy/token vault, realms, allowlists, advanced fusion modes. |
| Avoid | Do not imply guarantees the code or architecture cannot provide. | "Absolute privacy", "bulletproof uptime", "never leaks", "exact right model", "secure for every deployment". |

Recommended status phrase:

> Current scaffold: proxy, node registry, discovery, routing, dashboard, and
> metrics. Roadmap: coalescing/cache, auth/policy/token vault, realms, and
> advanced fusion modes.

## Primary Promotion Pillars

### 1. Owner-Approved Local AI

**Audience:** privacy-conscious users, maintainers, local-first developers,
home-lab operators.

**Core message:** Vampire only works with LM Studio endpoints an owner has
chosen to expose. The project is built around owner control rather than
ambient network scraping.

**Pitch:** "Your machine contributes only when you offer an LM Studio endpoint."

**Use this copy:**

> Run local AI through hardware you already trust. Vampire connects to
> owner-approved LM Studio servers and keeps the owner in control of server
> exposure, authentication, ports, and model availability.

**Avoid:**

- "We guarantee prompts never leave the house."
- "Any LAN GPU becomes available automatically."
- "Vampire controls your GPUs."

**Source anchors:** [VISION.md](../../VISION.md),
[README.md](../../README.md), [security-design-thesis.md](../security-design-thesis.md).

### 2. Change the Base URL

**Audience:** developers, tool builders, IDE/TUI authors, automation users.

**Core message:** Existing OpenAI-compatible clients can point at Vampire's
stable `/v1` gateway and gain routing behavior without rewriting application
logic.

**Pitch:** "Do not rewrite your client. Change the base URL."

**Use this copy:**

> Point OpenAI-compatible clients at `http://localhost:7777/v1` and let Vampire
> proxy or route requests across approved LM Studio nodes behind one stable
> endpoint.

**Proof points today:**

- `/v1/models`
- `/v1/chat/completions`
- `/v1/completions`
- `/v1/embeddings`
- `/v1/responses`
- OpenAI-style errors for unreachable upstream nodes
- streaming passthrough

**Source anchors:** [DESIGN-API.md](../../DESIGN-API.md),
[docs/manual/03-quickstart.md](../manual/03-quickstart.md),
[docs/manual/09-api-reference.md](../manual/09-api-reference.md).

### 3. Reuse the Hardware You Already Own

**Audience:** families, small businesses, schools, workshops, clubs, events.

**Core message:** Useful AI workloads do not always need rented cloud
inference. Many homes and offices already have capable machines sitting idle.

**Pitch:** "Try the trusted compute you already own before renting more."

**Use this copy:**

> A gaming PC, creator workstation, classroom host, or office machine can become
> part of a private AI service when its owner exposes an LM Studio endpoint and
> registers it with Vampire.

**Avoid:**

- "Free cloud replacement."
- "Use every GPU on the network."
- "No need for cloud AI ever again."

**Source anchors:** [ASPIRATION.md](../../ASPIRATION.md),
[README.md](../../README.md), [docs/use-case/README.md](../use-case/README.md).

### 4. One Strong Host, Many Approved Users

**Audience:** households, classrooms, workshops, event organizers.

**Core message:** One strong LM Studio host can serve weaker devices through a
single local gateway.

**Pitch:** "One gaming PC, AI for the whole house."

**Use this copy:**

> Put the model on the strong machine and the API endpoint where everyone can
> use it. Vampire gives approved clients one local gateway instead of asking
> every laptop to run its own model.

**Current-state note:** The `vampire share` command records owner sharing
intent today. Policy enforcement through tokens, realms, and allowlists is a
planned Phase 6 layer, not current access control.

**Source anchors:** [docs/manual/08-sharing-modes.md](../manual/08-sharing-modes.md),
[docs/use-case/04-student-home-and-school.md](../use-case/04-student-home-and-school.md).

### 5. Model-Aware Routing Across Approved Nodes

**Audience:** developers, power users, small teams, operators.

**Core message:** Vampire can inspect registered nodes, aggregate their model
inventory, and route requests through virtual models and route policies.

**Pitch:** "One endpoint that knows which approved node should answer."

**Use this copy:**

> Register multiple LM Studio nodes, expose virtual models such as
> `vampire:auto`, and route requests with strategies like `round_robin`,
> `least_busy`, `least_latency`, `model_affinity`, and `trusted_only`.

**Avoid:**

- "The exact right model for every single prompt."
- "Autonomous perfect routing."
- "Guaranteed fastest response."

**Source anchors:** [docs/manual/07-routing.md](../manual/07-routing.md),
[DESIGN-API.md](../../DESIGN-API.md), [README.md](../../README.md).

### 6. Headless, Remote, and Heterogeneous LM Studio Nodes

**Audience:** home-lab users, IT teams, server operators, distributed families,
remote workers.

**Core message:** Vampire talks to LM Studio-compatible HTTP endpoints; the
compute behind those endpoints may be desktop, headless, local, remote, CPU,
GPU, or routed through LM Studio's own link layer.

**Pitch:** "If LM Studio can expose it, Vampire can route to it."

**Use this copy:**

> Vampire does not need to know where the GPU is. It talks to the LM
> Studio-compatible endpoint, while LM Studio handles the underlying runtime,
> local server, headless `llmster` daemon, or LM Link-backed remote device.

**Avoid:**

- "Vampire supports every GPU directly."
- "Vampire discovers GPUs."
- "Remote access is automatically secure in every network."

**Source anchors:** [lmstudio.ai/01-overview.md](../../lmstudio.ai/01-overview.md),
[lmstudio.ai/08-headless.md](../../lmstudio.ai/08-headless.md),
[lmstudio.ai/09-lm-link.md](../../lmstudio.ai/09-lm-link.md),
[lmstudio.ai/12-vampire-integration.md](../../lmstudio.ai/12-vampire-integration.md).

### 7. A Dashboard for Local AI Operations

**Audience:** maintainers, testers, operators, demo users.

**Core message:** The current scaffold is not just a paper design. It includes
a browser dashboard for inspecting status, nodes, discovery, models, routes,
metrics, share state, and a prompt playground.

**Pitch:** "Run the gateway and see your local AI fabric."

**Use this copy:**

> Start `vampire serve`, open the dashboard, register LM Studio nodes, inspect
> model inventory, create routes, watch metrics, and test prompts through the
> gateway.

**Source anchors:** [README.md](../../README.md),
[docs/manual/03-quickstart.md](../manual/03-quickstart.md),
[docs/manual/05-cli-reference.md](../manual/05-cli-reference.md).

## Roadmap Pillars

Use these only when the surrounding copy clearly says "planned", "roadmap", or
"future phase".

### Coalescing and Cache

**Planned pitch:** "Do not compute the same approved request twice."

**Planned value:** In shared settings such as classrooms, workshops, and
business chats, exact in-flight deduplication and result caching can reduce
wasted inference when policy allows reuse.

**Status language:** "planned coalescing/cache" or "Phase 5 roadmap".

### Policy, Tokens, and Realms

**Planned pitch:** "Set the house rules for local AI."

**Planned value:** Realm-scoped tokens, allowlists, trust levels, token vaulting,
and policy enforcement can turn current sharing intent into actual governance.

**Status language:** "planned policy layer" or "Phase 6 roadmap".

### Fusion and Advanced Modes

**Planned pitch:** "Run an ensemble when one answer is not enough."

**Planned value:** Race, parallel, fusion, judge/refiner, debate, and pipeline
modes can fan out work across approved nodes for latency, quality, or review.

**Status language:** "planned advanced modes" or "Phase 7 roadmap".

## Narrative Registers

The project has two useful narrative skins. Use them sparingly; the default
public copy should stay clear and technical.

| Register | Best use | Safe line |
| --- | --- | --- |
| Folklore / vampire | Project identity, blog posts, maintainer voice. | "Like the folklore rule, Vampire enters only where it is invited." |
| Federation / sci-fi | Governance, membership, coordinated nodes. | "Approved LM Studio endpoints become a governed federation of local AI capacity." |
| Plain technical | README, package index, security docs, enterprise users. | "A routing and governance layer for owner-approved LM Studio endpoints." |

Avoid jokes or metaphors where they could obscure consent, authentication,
security, or current implementation status.

## Audience Map

| Audience | Lead with | Secondary angle |
| --- | --- | --- |
| Developers | Change the base URL. | Model-aware routing. |
| Families | One strong host, many approved users. | Owner-approved local AI. |
| Small businesses | Reuse existing workstation capacity. | Dashboard and routing. |
| Schools/events | One strong local host for the room. | Planned coalescing/cache. |
| Home-lab operators | Headless and heterogeneous LM Studio nodes. | Dashboard and metrics. |
| Security-minded users | Owner-approved endpoints and explicit LM Studio exposure. | Planned policy/tokens/realms. |
| Open-source contributors | Runnable scaffold today, ambitious roadmap next. | Clear Phase 5-7 contribution areas. |

## Approved Copy Blocks

### GitHub Repository Description

> Governed local AI routing for owner-approved LM Studio endpoints.

### README Hero

> `lmstudio-vampire` turns owner-approved LM Studio API endpoints into one
> governed, private AI service behind a stable OpenAI-compatible URL.

### Release Note

> This release improves the runnable local AI gateway: proxying, node registry,
> discovery, routing, dashboard, metrics, and share-state controls continue to
> move the project from design paper toward practical operator tooling.

### Social Post

> Local AI should not mean every device runs alone. `lmstudio-vampire` puts a
> stable OpenAI-compatible gateway in front of the LM Studio machines you
> already own and trust.

### Contributor Call

> The current scaffold covers proxying, discovery, routing, and the dashboard.
> The next high-value work is coalescing/cache, auth/policy/token vaulting, and
> advanced fusion modes.

## Phrases to Prefer

- owner-approved LM Studio endpoints
- stable OpenAI-compatible gateway
- local-first AI service
- governed private AI compute
- route across approved nodes
- inspect model inventory and capabilities
- current scaffold
- planned policy layer
- roadmap fusion modes

## Phrases to Avoid

- absolute privacy
- bulletproof uptime
- unkillable
- guaranteed secure
- never leaks
- exact right model every time
- automatic GPU discovery
- free cloud replacement
- peer-to-peer compute marketplace
- use anyone's GPU

## Minimum Public Checklist

Before publishing promotion copy, verify that it:

- Says "LM Studio endpoint" rather than "GPU" when describing what Vampire
  directly connects to.
- Says "owner-approved", "registered", or "trusted" when describing nodes.
- Distinguishes implemented features from roadmap features.
- Avoids absolute security, privacy, latency, and uptime guarantees.
- Mentions that Vampire is independent and not affiliated with LM Studio unless
  that relationship changes.
- Links readers back to the README, manual, and design docs for current status.
