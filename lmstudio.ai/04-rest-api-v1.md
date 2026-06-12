# 04 — Native REST API v1 (`/api/v1/*`)

##### Requires LM Studio 0.4.0 or newer.

LM Studio's native v1 REST API is the recommended modern surface. It adds first-class
model management — exactly the read/control plane Vampire's interrogation layer needs.

## Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/v1/chat` | POST | Stateful chat (server-kept history, MCP integrations, streaming) |
| `/api/v1/models` | GET | Rich inventory of all models, loaded instances, capabilities |
| `/api/v1/models/load` | POST | Load a model with explicit configuration |
| `/api/v1/models/unload` | POST | Unload a loaded model instance |
| `/api/v1/models/download` | POST | Download a model |
| `/api/v1/models/download/status` | GET | Poll download progress |

All endpoints accept an `Authorization: Bearer $LM_API_TOKEN` header when authentication is on.

## `GET /api/v1/models` — the interrogation goldmine

Returns, per model:

- `type` — `"llm" | "embedding"`
- `key` — unique model identifier; `display_name`, `publisher`
- `architecture` (e.g. `"llama"`, `"mistral"`), `format` (`"gguf" | "mlx"`)
- `quantization` — `{ name, bits_per_weight }`
- `size_bytes`, `params_string` (e.g. `"7B"`)
- `max_context_length` — maximum supported context window
- `capabilities` — `{ vision, trained_for_tool_use, reasoning.allowed_options }`
- `loaded_instances[]` — currently loaded instances, each with:
  - `id` — instance identifier
  - `config` — `context_length`, `eval_batch_size`, **`parallel`** (max concurrent
    predictions the instance can handle), `flash_attention`, `num_experts`,
    `offload_kv_cache_to_gpu`

One call gives Vampire everything §14–§15 of [`../DESIGN-API.md`](../DESIGN-API.md)
require: inventory, loaded state, context limits, capabilities, and per-instance
concurrency.

## `POST /api/v1/models/load`

```bash
curl http://localhost:1234/api/v1/models/load \
  -H "Authorization: Bearer $LM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-20b",
    "context_length": 16384,
    "flash_attention": true,
    "echo_load_config": true
  }'
```

Request fields: `model` (required), `context_length`, `eval_batch_size`,
`flash_attention`, `num_experts`, `offload_kv_cache_to_gpu` (llama.cpp engine only),
`echo_load_config`.

Response: `type`, `instance_id`, `load_time_seconds`, `status: "loaded"`, and
(optionally) the final `load_config` actually applied.

## `POST /api/v1/models/unload`

```bash
curl http://localhost:1234/api/v1/models/unload \
  -H "Authorization: Bearer $LM_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "instance_id": "openai/gpt-oss-20b" }'
```

## `POST /api/v1/chat` — stateful chat

Request fields include: `model`, `input`, `system_prompt`, `integrations` (MCP
plugins with `allowed_tools`), `stream`, sampling parameters (`temperature`, `top_p`,
`top_k`, `min_p`, `repeat_penalty`), `max_output_tokens`, `reasoning`,
`context_length`, `store`, `previous_response_id`.

Distinctive features versus `/v1/chat/completions`:

- **Stateful**: pass `previous_response_id` instead of resending history.
- **MCP integrations** per request (when the owner allows them).
- **Model-load and prompt-processing streaming events** — the stream reports JIT
  loading progress before tokens arrive.
- **`context_length` specified per request.**
- Response includes `model_instance_id`, `output`, `stats`, `response_id`.

## Implications for Vampire

1. **Interrogation** = `GET /api/v1/models` per node, on registration and on a refresh
   interval.
2. **Pre-warming and rebalancing** = `models/load` / `models/unload`, but only when the
   node's token grants those permissions — these are owner-controlled actions.
3. **Statefulness is node-local.** `previous_response_id` only resolves on the node
   that produced it; if Vampire proxies `/api/v1/chat`, sticky routing per conversation
   is mandatory.
4. **Load-progress streaming events** let Vampire surface "node is loading the model"
   instead of an opaque delay.
