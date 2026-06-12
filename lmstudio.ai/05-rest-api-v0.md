# 05 — Legacy REST API v0 (`/api/v0/*`)

##### Requires LM Studio 0.3.6 or newer. Superseded by the v1 REST API, but still served.

The v0 REST API predates `/api/v1/*` and remains valuable to Vampire for two reasons:
it is the richest machine-readable surface available on pre-0.4.0 nodes, and it returns
**per-request performance stats** that feed Vampire's routing metrics.

## Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/v0/models` | GET | List all loaded **and** downloaded models, with state |
| `/api/v0/models/{model}` | GET | Info about a specific model |
| `/api/v0/chat/completions` | POST | Chat completions (OpenAI-like + extra stats) |
| `/api/v0/completions` | POST | Text completions |
| `/api/v0/embeddings` | POST | Text embeddings |

## `GET /api/v0/models` — explicit load state

```json
{
  "object": "list",
  "data": [
    {
      "id": "qwen2-vl-7b-instruct",
      "object": "model",
      "type": "vlm",
      "publisher": "mlx-community",
      "arch": "qwen2_vl",
      "compatibility_type": "mlx",
      "quantization": "4bit",
      "state": "not-loaded",
      "max_context_length": 32768
    }
  ]
}
```

Key fields per model:

- `type` — `"llm"`, `"vlm"` (vision), or `"embeddings"`
- `state` — `"loaded"` or `"not-loaded"` (the distinction `/v1/models` cannot give)
- `compatibility_type` — `"gguf"` or `"mlx"`
- `arch`, `publisher`, `quantization`, `max_context_length`

## Inference responses include enhanced stats

Beyond the OpenAI-style `choices` and `usage`, v0 inference responses add:

```json
"stats": {
  "tokens_per_second": 51.43,
  "time_to_first_token": 0.111,
  "generation_time": 0.954,
  "stop_reason": "eosFound"
},
"model_info": {
  "arch": "granite",
  "quant": "Q4_K_M",
  "format": "gguf",
  "context_length": 4096
},
"runtime": {
  "name": "llama.cpp-mac-arm64-apple-metal-advsimd",
  "version": "1.3.0"
}
```

- `stats.tokens_per_second` and `stats.time_to_first_token` are direct inputs to
  latency-aware routing.
- `runtime.name` reveals the engine, platform, and acceleration backend
  (e.g. Apple Metal vs CUDA) without any privileged access to the node.
- The `ttl` request field is accepted here too (see
  [07-model-lifecycle.md](07-model-lifecycle.md)).

## Implications for Vampire

1. **Version fallback chain:** interrogate `/api/v1/models` first; if absent
   (pre-0.4.0 node), fall back to `/api/v0/models`; if that is absent too, degrade to
   `/v1/models` with reduced fidelity.
2. **Free telemetry:** routing requests through `/api/v0/*` (when compatible with the
   client's request shape) yields TPS/TTFT samples per node per model — the empirical
   data behind `lowest_latency` and `best_quality` strategies in
   [`../DESIGN-API.md`](../DESIGN-API.md) §9.
3. **`state` enables cold-start-aware routing:** prefer nodes where the model is
   already `"loaded"`; treat `"not-loaded"` + JIT as a higher-latency option.
