# METHOD-C — TypeScript full-stack (Node + shared types)

Build gateway and UI in **one TypeScript codebase**, sharing request/response
types end to end.

```text
React/Svelte UI  (Vite)
        |  typed client
        v
Node gateway  (Fastify / Hono)
   - OpenAI-compatible gateway
   - Vampire control API
        |
        v
LM Studio nodes on the LAN
```

## Idea

The LM Studio / OpenAI ecosystem is JavaScript-heavy, and the project leans hard
on a **browser control plane** (see POSSIBILITIES §14). One language across API
and UI lets the node manifest, route policy, and Vampire request extension be
defined once as TypeScript types and reused by both sides, with Zod for runtime
validation at the edge.

## Why consider it

- **Shared contracts.** API objects and UI models never drift apart.
- **Best-in-class UI.** Full access to React/Svelte, streaming hooks, and rich
  dashboards/playgrounds for nodes, traces, and fusion.
- **Streaming-native.** Web standards (SSE, `fetch` streams, WebSockets) line up
  with the OpenAI streaming format.
- **Big contributor pool** for web-facing work.

## Costs

- Two build toolchains (server + UI bundler) unless unified with one framework.
- Node single-threaded model needs clustering for heavy fan-out; CPU-bound extras
  belong in workers.
- Dependency tree is larger and faster-moving than Go/Rust.

**Best when** the browser experience is the centerpiece and a single-language,
typed contract between UI and API is worth the heavier toolchain.
