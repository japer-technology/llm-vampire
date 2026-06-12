# METHOD-A — Python service + browser interface

This is the construction the project was originally hoped to take: **one Python
application that does the serving, paired with a browser interface.** It is the
most direct path from the [ASPIRATION](ASPIRATION.md) and
[DESIGN-API](DESIGN-API.md) papers to something runnable.

---

## Shape

```text
Browser UI (dashboard + playground)
        |  HTTP / WebSocket
        v
Python app  (single process: vampire serve)
   - OpenAI-compatible gateway   /v1/...
   - Vampire control API         /vampire/v1/...
   - Static UI host              /
   - Node registry + router
   - Coalescer / cache
   - Policy + token vault
        |  HTTP (OpenAI-compatible)
        v
Approved LM Studio nodes on the LAN
```

One process serves three things at once: the OpenAI-compatible API that clients
already speak, the Vampire control API the UI drives, and the static browser UI
itself. Downstream it speaks plain OpenAI-compatible HTTP to each LM Studio node.

---

## Suggested stack

- **Web framework:** FastAPI (async, OpenAI-shaped JSON, automatic OpenAPI docs).
- **Server:** Uvicorn.
- **HTTP client:** `httpx.AsyncClient` for fan-out to nodes, with streaming.
- **Discovery:** `zeroconf` for mDNS/Bonjour, plus a manual node allowlist.
- **State:** in-memory registry for v0; SQLite (via `aiosqlite`) for persistence
  of nodes, routes, aliases, and metrics.
- **UI:** a static single-page app served by the same FastAPI app under `/`.
  Start with plain HTML + a light framework; no separate build server needed.
- **Packaging:** a `vampire` console-script entry point (`vampire serve`,
  `vampire discover`, `vampire share on`), matching the CLI shape in ASPIRATION.

The whole thing installs with `pip install lmstudio-vampire` and runs with
`vampire serve`, listening on `http://localhost:7777/v1` as DESIGN-API specifies.

---

## Why this construction fits

- **Compatibility first.** FastAPI makes it trivial to mirror `/v1/models`,
  `/v1/chat/completions`, `/v1/completions`, and `/v1/embeddings` exactly, so any
  existing OpenAI/LM Studio client just swaps its base URL.
- **Streaming is native.** Server-sent events / chunked responses pass through
  cleanly, which the project needs for token streaming and "race" mode.
- **Async fan-out is the core workload.** Routing, racing, parallel, and fusion
  modes are all "call N nodes concurrently and combine," which `asyncio` +
  `httpx` express directly.
- **One artifact to run.** Hosting the UI from the same process means a family or
  classroom owner runs a single command — no separate frontend deployment.
- **Glue, not math.** This layer is orchestration and policy, not heavy numeric
  compute; the GPU work stays inside LM Studio, so Python's speed is rarely the
  bottleneck.

## Where it strains

- **Concurrency ceiling.** Very high simultaneous connection counts may need
  multiple Uvicorn workers; shared state (registry, cache, in-flight
  deduplication) must then move out of process memory into SQLite/Redis.
- **CPU-bound extras.** Semantic cache embeddings or local re-ranking can block
  the event loop and should run in a thread/process pool or be delegated to a node.
- **Coupled UI + API.** Serving the SPA from the API is simple but couples their
  release cycles; acceptable early, worth splitting later if the UI grows.

---

## Build order

1. **Proxy.** Forward `/v1/*` to a single hard-coded LM Studio node; verify an
   existing client works unchanged.
2. **Registry + discovery.** Add manual node registration, then mDNS discovery
   and health checks. Expose `/vampire/v1/nodes`.
3. **Routing.** Round-robin and failover across nodes; then model-aware and
   load-aware routing.
4. **UI.** Serve a dashboard showing nodes, models, and health, plus a prompt
   playground that calls the gateway.
5. **Coalescing + cache.** In-flight exact deduplication, then an exact result
   cache.
6. **Policy + tokens.** Owner modes, realms, token vault, CORS/node allowlists.
7. **Fusion.** Parallel, race, and judge/refiner modes via `/vampire/v1/fusion`.

Each step is independently shippable. These build-order steps cover the same
work as the thematic MVP roadmap in [ASPIRATION.md](ASPIRATION.md), but grouped
and ordered for fastest time-to-demo rather than by capability — notably,
coalescing and routing are sequenced differently and a dashboard UI step is
added here. See the mapping table in
[IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) for the exact correspondence.

---

## Verdict

METHOD-A is the recommended starting construction: lowest friction to a working
demo, strongest ecosystem fit for OpenAI-compatible serving, and a single
install/run story for non-technical owners. The alternatives in
[METHOD-B](METHOD-B.md), [METHOD-C](METHOD-C.md), [METHOD-D](METHOD-D.md), and
[METHOD-E](METHOD-E.md) trade that simplicity for performance, distribution, or
zero-install reach.
