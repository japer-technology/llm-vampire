# lmstudio.ai — LM Studio Technical Reference for Vampire

This folder is a deep technical study of [LM Studio](https://lmstudio.ai/) — the platform
that `lmstudio-vampire` builds on. It collects every LM Studio mechanism that Vampire's
design depends on: the API server, its endpoint surfaces, authentication, model lifecycle,
headless operation, remote-device routing (LM Link), the `lms` CLI, and concurrency.

All information is sourced from LM Studio's official documentation at
[lmstudio.ai/docs](https://lmstudio.ai/docs) (source repository:
[lmstudio-ai/docs](https://github.com/lmstudio-ai/docs)). LM Studio evolves quickly;
where versions matter, the required LM Studio version is noted.

> **Why this folder exists.** Vampire does not discover or control GPUs directly. It
> connects only to LM Studio servers an owner has deliberately exposed, interrogates
> what those servers offer, and routes approved requests behind one stable
> OpenAI-compatible endpoint (see [`../VISION.md`](../VISION.md) and
> [`../DESIGN-API.md`](../DESIGN-API.md)). Every Vampire capability therefore rests on a
> concrete LM Studio mechanism documented here.

## Contents

| Doc | What it covers | Why Vampire needs it |
| --- | --- | --- |
| [01-overview.md](01-overview.md) | LM Studio platform components: desktop app, llmster daemon, `lms` CLI, SDKs | Knowing every form an upstream node can take |
| [02-api-server.md](02-api-server.md) | Running the API server, port, network binding, CORS, server settings | How owners expose endpoints Vampire can reach |
| [03-openai-compat.md](03-openai-compat.md) | OpenAI-compatible `/v1/*` endpoints | The surface Vampire proxies transparently |
| [04-rest-api-v1.md](04-rest-api-v1.md) | Native REST API `/api/v1/*` (LM Studio 0.4.0+) | Rich model inventory, load/unload control |
| [05-rest-api-v0.md](05-rest-api-v0.md) | Legacy REST API `/api/v0/*` (LM Studio 0.3.6+) | Per-request stats (TPS, TTFT) and model state |
| [06-authentication.md](06-authentication.md) | API tokens, permissions, the `Authorization` header | Respecting owner access requirements |
| [07-model-lifecycle.md](07-model-lifecycle.md) | JIT loading, idle TTL, auto-evict, explicit load/unload | Predicting node behavior before routing |
| [08-headless.md](08-headless.md) | llmster daemon and headless desktop mode | Server-native nodes without a GUI |
| [09-lm-link.md](09-lm-link.md) | LM Link end-to-end-encrypted remote-device routing | LM Studio's own link layer behind an endpoint |
| [10-cli.md](10-cli.md) | The `lms` CLI | How owners script and operate nodes |
| [11-concurrency.md](11-concurrency.md) | Parallel requests via continuous batching | Node capacity for load-aware routing |
| [12-vampire-integration.md](12-vampire-integration.md) | Mechanism-by-mechanism mapping to Vampire's design | The synthesis: how Vampire uses all of the above |

## Executive architecture map

```mermaid
flowchart LR
    owner["Owner"]
    clients["OpenAI-compatible clients"]
    vampire["Vampire gateway<br/>single governed endpoint"]
    registry["Node registry<br/>health, models, metrics"]
    policy["Policy + credentials<br/>realms, trust, per-node tokens"]

    subgraph lmstudio["LM Studio nodes"]
        desktop["Desktop API server<br/>localhost or LAN"]
        headless["llmster daemon<br/>headless GPU host"]
        link["LM Link endpoint<br/>remote encrypted compute"]
    end

    owner -->|"Starts server, binds address, enables auth, sets JIT/TTL"| desktop
    owner -->|"Scripts with lms CLI"| headless
    owner -->|"Pairs devices"| link

    clients -->|"/v1/*"| vampire
    vampire --> registry
    vampire --> policy
    registry -->|"/api/v1/models<br/>/api/v0/models<br/>/v1/models"| lmstudio
    policy -->|"Authorization per node"| lmstudio
    vampire -->|"Selected /v1/* request"| lmstudio
```

## Documentation flow

```mermaid
flowchart TB
    overview["01 Overview"]
    server["02 API server"]
    compat["03 OpenAI / Anthropic compatibility"]
    native["04 Native REST v1"]
    legacy["05 Legacy REST v0"]
    auth["06 Authentication"]
    lifecycle["07 Model lifecycle"]
    headless["08 Headless"]
    link["09 LM Link"]
    cli["10 lms CLI"]
    concurrency["11 Concurrency"]
    integration["12 Vampire integration"]

    overview --> server
    server --> compat
    server --> native
    server --> legacy
    server --> auth
    native --> lifecycle
    legacy --> lifecycle
    lifecycle --> concurrency
    headless --> integration
    link --> integration
    cli --> integration
    compat --> integration
    native --> integration
    legacy --> integration
    auth --> integration
    lifecycle --> integration
    concurrency --> integration
```

## The mechanism in one page

An LM Studio node, as Vampire sees it:

```mermaid
flowchart TB
    owner["Owner controls"]

    subgraph node["LM Studio node<br/>desktop app, headless app, or llmster daemon"]
        settings["Server settings<br/>port, bind address, auth, CORS,<br/>JIT loading, TTL, auto-evict, parallelism"]
        surfaces["API surfaces on one port<br/>/v1/* OpenAI-compatible<br/>/v1/messages Anthropic-compatible<br/>/api/v1/* native REST<br/>/api/v0/* legacy REST with stats"]
        compute["Compute<br/>local hardware or LM Link remote device"]
    end

    owner --> settings
    settings --> surfaces
    surfaces --> compute
```

Vampire's job (per [`../DESIGN-API.md`](../DESIGN-API.md)) is to sit in front of one or
more of these nodes, interrogate them through the read-only surfaces above, honor the
owner's settings, and present a single governed endpoint to clients.
