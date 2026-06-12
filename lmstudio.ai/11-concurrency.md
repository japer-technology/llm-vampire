# 11 — Concurrency: Parallel Requests via Continuous Batching

A single LM Studio node is not strictly serial. Understanding per-instance concurrency
is essential for Vampire's load-aware routing.

## The mechanism

- When loading a model, the owner can set **Max Concurrent Predictions** (model loader
  → advanced settings). **Default: 4.**
- Implemented via **continuous batching**: the server dynamically combines multiple
  in-flight requests into a single batch, enabling concurrent workflows and higher
  total throughput.
- Supported by LM Studio's **llama.cpp engine** (requires GGUF runtime llama.cpp
  v2.0.0+); MLX support is planned.
- Requests beyond the concurrency limit are **queued** on the node.
- Parallel requests also work **across LM Link**, so one endpoint can serve multiple
  clients from remote devices simultaneously.

## Where Vampire reads it

`GET /api/v1/models` reports, for each loaded LLM instance, a `parallel` field in
`loaded_instances[].config` — the maximum number of parallel predictions that instance
can handle (see [04-rest-api-v1.md](04-rest-api-v1.md)).

## Implications for Vampire

1. **Capacity model per instance:** `capacity = parallel`, with Vampire tracking its
   own in-flight count per instance. Route to instances with free slots
   (`least_loaded` strategy in [`../DESIGN-API.md`](../DESIGN-API.md) §9); requests
   beyond capacity either queue at the node or are diverted to another node.
2. **Throughput vs latency trade-off.** Continuous batching raises aggregate
   throughput but individual request latency can rise as the batch fills. Latency-
   sensitive routing may deliberately leave headroom on an instance.
3. **Per-node, per-load setting.** Concurrency is chosen by the owner at model load
   time and varies across nodes and across loads — interrogate, don't assume.
4. **Pre-0.4.0 or MLX nodes** may not expose or support parallelism; treat the
   default as 1 unless discovered otherwise.
