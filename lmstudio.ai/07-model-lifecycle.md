# 07 — Model Lifecycle: JIT Loading, Idle TTL, Auto-Evict

LM Studio nodes manage model memory autonomously. Vampire never controls this directly
— it must **predict** node behavior from these rules to route well.

## Just-In-Time (JIT) model loading — `[Default: enabled]`

When JIT loading is **ON**:

- `GET /v1/models` returns **all downloaded models**, not just loaded ones.
- An inference request for an unloaded model **loads it into memory first**, then
  serves the request (the first request pays the load time).

When JIT loading is **OFF**:

- `GET /v1/models` returns **only loaded models**.
- Models must be explicitly loaded (GUI, `lms load`, or `POST /api/v1/models/load`)
  before they can serve requests.

## Idle TTL — `[Default: 60 minutes]`

- TTL (Time-To-Live) defines how long a model may stay loaded **without receiving
  requests**. When it expires, the model is unloaded automatically.
- The idle timer **resets on every request**; a model in active use never expires.
- Precedence of TTL values:
  1. **Per-request:** a `"ttl": <seconds>` field in the inference payload (works on
     both OpenAI-compatible and REST endpoints) sets the TTL when that request JIT-loads
     the model:

     ```diff
     curl http://localhost:1234/api/v0/chat/completions \
       -H "Content-Type: application/json" \
       -d '{
         "model": "deepseek-r1-distill-qwen-7b",
     +   "ttl": 300,
         "messages": [ ... ]
     }'
     ```

  2. **App default:** configurable default TTL for all JIT-loaded models.
  3. **`lms load` models have no TTL by default** — they stay loaded until manually
     unloaded, unless loaded with `lms load <model> --ttl 3600`.

## Auto-Evict — `[Default: enabled]`

- **ON:** loading a new model via JIT first unloads previously JIT-loaded models — at
  most **1** JIT model stays in memory. Non-JIT (manually loaded) models are unaffected.
- **OFF:** JIT models accumulate in memory until their TTL expires or the owner
  unloads them.
- A related setting, **Only Keep Last JIT Loaded Model**, similarly bounds JIT memory
  use.

## Explicit lifecycle control

| Action | GUI | CLI | REST |
| --- | --- | --- | --- |
| Load | model loader (with per-load params) | `lms load <model> [--ttl N]` | `POST /api/v1/models/load` |
| Unload | server tab | `lms unload` | `POST /api/v1/models/unload` |
| Inspect | server tab | `lms ps` (loaded), `lms ls` (on disk) | `GET /api/v1/models`, `GET /api/v0/models` |

## Implications for Vampire

1. **Cold-start estimation.** For a `"not-loaded"` model on a JIT node, expected
   latency = load time + inference time. `load_time_seconds` from explicit loads and
   observed first-request latencies calibrate this per node/model.
2. **Auto-Evict means routing causes evictions.** Sending model B to a node serving
   model A (both JIT) evicts A. Naive round-robin across models on one node causes
   load thrashing; Vampire's router should prefer model-sticky node assignment.
3. **TTL pass-through.** Vampire forwards client `ttl` fields unchanged, and may apply
   its own policy TTL for requests it initiates (e.g. pre-warming).
4. **Inventory is time-sensitive.** A model `"loaded"` at interrogation time may be
   TTL-evicted minutes later; loaded-state data should be refreshed or treated as a
   hint, not a guarantee.
5. **JIT-off nodes are fixed-function.** If JIT is off, the set of usable models is
   exactly the loaded set; Vampire must not route other models there even if they are
   on disk.
