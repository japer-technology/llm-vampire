# LM Studio Vampire

> Private AI compute, offered through LM Studio, wherever the owner allows it.

**`lmstudio-vampire`** turns owner-approved **LM Studio API endpoints** into one governed, private AI service.

Vampire does not discover or control GPUs directly. It connects only to LM Studio servers that an owner has deliberately exposed — locally, on a trusted network, through headless LM Studio, or through LM Studio’s own remote-device routing.

The LM Studio owner stays in control. They decide whether the server is running, whether network access is enabled, which port is exposed, whether API-token authentication is required, which tokens are valid, which models are available, and whether models may be loaded on demand.

Vampire can only use what LM Studio offers. It interrogates reachable endpoints, verifies their model inventory, loaded instances, context limits, capabilities, and access requirements, then routes approved requests behind a single, stable OpenAI-compatible endpoint.

The compute behind an LM Studio endpoint may be local, remote, headless, GPU-backed, CPU-backed, or routed through LM Studio’s own link layer. Vampire does not need to know where the GPU is. LM Studio provides the connection; Vampire provides governance, routing, policy, and aggregation.

![Status: design stage](https://img.shields.io/badge/status-design%20stage-orange)
![Docs: design papers](https://img.shields.io/badge/docs-design%20papers-blue)
![License: TBD](https://img.shields.io/badge/license-TBD-lightgrey)

> [!IMPORTANT]
> This repository is currently a **design-stage project**. It contains the
> aspiration, API design, and candidate construction methods — not yet a runnable
> implementation. The usage examples below describe the **intended** experience and
> are documented here to guide implementation. See [Project status](#project-status).

---

## Table of contents

- [Why](#why)
- [Features](#features)
- [How it works](#how-it-works)
- [Project status](#project-status)
- [Intended usage](#intended-usage)
- [Documentation](#documentation)
- [Construction methods](#construction-methods)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Why

AI compute is already widely distributed. Millions of homes, offices, studios, labs,
classrooms, and gaming rooms contain GPUs that sit idle for much of the day, and many
can already run useful local models. The missing layer is not model execution — LM
Studio provides that with an OpenAI-compatible API — but **discovery, permission,
routing, policy, and coordination**.

`lmstudio-vampire` asks: *what useful AI work can be served first by compute we already
own, already trust, and already have nearby?*

- **Families** turn a home gaming PC into a shared, private AI appliance.
- **Small businesses** reuse workstation capacity before renting more cloud compute.
- **Classrooms and events** become AI-capable with one strong host.
- **Developers** get a stable local endpoint that load-balances across machines.

## Features

- 🧛 **Discovery** — wakes on the LAN and finds approved LM Studio-compatible endpoints.
- 🔌 **Drop-in compatibility** — exposes a stable OpenAI-compatible API; existing clients
  only change their base URL.
- 🧭 **Smart routing** — model-aware and load-aware routing, with failover across nodes.
- 🤝 **Request coalescing** — collapses concurrent identical prompts into one inference.
- ⚡ **Caching** — serves repeated requests from an exact result cache.
- 🧩 **Fusion modes** — parallel, race, and judge/refiner strategies across machines.
- 🔐 **Owner control** — respects tokens, realms, and policy before routing any request.
- 🏠 **Local-first & private** — prompts stay on trusted, nearby compute.

## How it works

`lmstudio-vampire` sits in front of one or more LM Studio nodes as a transparent proxy
and adds opt-in orchestration:

```text
        OpenAI-compatible clients
                  │
                  ▼
   ┌───────────────────────────────┐
   │        lmstudio-vampire        │
   │  • OpenAI-compatible gateway   │   /v1/...
   │  • Vampire control API         │   /vampire/v1/...
   │  • Node registry + router      │
   │  • Coalescer / cache           │
   │  • Policy + token vault        │
   └───────────────────────────────┘
                  │  OpenAI-compatible HTTP
        ┌─────────┼─────────┐
        ▼         ▼         ▼
    LM Studio  LM Studio  LM Studio   (approved LAN nodes)
```

- **Compatibility first.** Routes such as `/v1/models`, `/v1/chat/completions`,
  `/v1/completions`, and `/v1/embeddings` behave like LM Studio / OpenAI.
- **Vampire additions are opt-in.** Advanced behavior is enabled through an extra
  `vampire` request field, `X-Vampire-*` headers, or dedicated `/vampire/v1/...` routes,
  so existing clients keep working unchanged.

See [DESIGN-API.md](DESIGN-API.md) for the full API specification.

## Project status

This project is in the **design stage**. The repository captures the vision and the
engineering plan; implementation has not yet started. Nothing here is installable yet,
and the project is **not affiliated with LM Studio** unless explicitly adopted by that
team.

Track and shape the direction through the documents below and the repository's issues
and pull requests.

## Intended usage

> The following describes the planned experience once the recommended construction
> ([METHOD-A](METHOD-A.md)) is implemented. It does not work today.

```bash
# install (planned)
pip install lmstudio-vampire

# run the gateway (planned)
vampire serve
```

Once running, the gateway is intended to listen on:

```text
http://localhost:7777/v1
```

Point any OpenAI-compatible client at that base URL instead of a single LM Studio
instance (commonly `http://localhost:1234/v1`), and requests are discovered, governed,
and routed across approved nodes.

## Documentation

| Document | What it covers |
| --- | --- |
| [VISION.md](VISION.md) | One-paragraph vision for the project. |
| [ASPIRATION.md](ASPIRATION.md) | The full aspirations paper: thesis, audiences, and goals. |
| [DESIGN-API.md](DESIGN-API.md) | The OpenAI-compatible + Vampire orchestration API design. |
| [POSSIBILITIES.md](POSSIBILITIES.md) | Broader explorations and feature possibilities. |

## Construction methods

Several candidate architectures have been evaluated. Each is independently described:

| Method | Approach |
| --- | --- |
| [METHOD-A](METHOD-A.md) | Python service (FastAPI) + browser interface — **recommended starting point**. |
| [METHOD-B](METHOD-B.md) | Single compiled Go/Rust binary with embedded UI. |
| [METHOD-C](METHOD-C.md) | TypeScript full-stack (Node + shared types). |
| [METHOD-D](METHOD-D.md) | Distributed agent mesh with no central server. |
| [METHOD-E](METHOD-E.md) | Browser-first, near-serverless thin client. |

## Roadmap

The recommended build order (from [METHOD-A](METHOD-A.md)) is:

1. **Proxy** — forward `/v1/*` to a single LM Studio node.
2. **Registry + discovery** — manual registration, then mDNS discovery and health checks.
3. **Routing** — round-robin and failover, then model-aware and load-aware routing.
4. **UI** — dashboard for nodes, models, and health, plus a prompt playground.
5. **Coalescing + cache** — in-flight deduplication, then an exact result cache.
6. **Policy + tokens** — owner modes, realms, token vault, and allowlists.
7. **Fusion** — parallel, race, and judge/refiner modes via `/vampire/v1/fusion`.

Each step is intended to be independently shippable.

## Contributing

Contributions, ideas, and design feedback are welcome. Because the project is still at
the design stage, the most valuable contributions right now are:

- Reviewing and refining the design documents above.
- Discussing the construction trade-offs in the method papers.
- Prototyping the early steps of the [roadmap](#roadmap).

Please open an issue to start a discussion before submitting larger changes, and keep
pull requests focused.

## License

A license has not yet been selected for this project. Until one is added, all rights are
reserved by the authors. If you intend to use or build on this work, please open an
issue to discuss licensing.

## Acknowledgements

`lmstudio-vampire` builds on the local AI surface provided by
[LM Studio](https://lmstudio.ai):

- [OpenAI-compatible API](https://lmstudio.ai/docs/developer/openai-compat)
- [LM Link](https://lmstudio.ai/docs/developer/core/lmlink)
- [Authentication](https://lmstudio.ai/docs/developer/core/authentication)
