# 03 — OpenAI-Compatible Endpoints (`/v1/*`)

LM Studio implements OpenAI-compatible endpoints so existing OpenAI clients work by
changing only the base URL. This is the surface Vampire mirrors one-for-one: anything
that works against LM Studio's `/v1/*` must keep working unchanged against Vampire's
`/v1/*` (see [`../DESIGN-API.md`](../DESIGN-API.md) §2).

## Supported endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/v1/models` | GET | List models visible to the server |
| `/v1/responses` | POST | OpenAI Responses API (stateful; enables Codex support) |
| `/v1/chat/completions` | POST | Chat completions (text and images), streaming via SSE |
| `/v1/completions` | POST | Text completions |
| `/v1/embeddings` | POST | Text embeddings |

LM Studio also provides an **Anthropic-compatible** endpoint on the same server:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/v1/messages` | POST | Anthropic Messages API (enables Claude Code support) |

## Base URL switching

```diff
from openai import OpenAI

client = OpenAI(
+    base_url="http://localhost:1234/v1"
)
```

```diff
- curl https://api.openai.com/v1/chat/completions \
+ curl http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
-     "model": "gpt-4o-mini",
+     "model": "use the model identifier from LM Studio here",
     "messages": [{"role": "user", "content": "Say this is a test!"}],
     "temperature": 0.7
   }'
```

Vampire's value proposition reuses this exact pattern: clients re-point the base URL
once more, from a single LM Studio node to Vampire's gateway.

## `GET /v1/models` semantics depend on JIT

This is a crucial subtlety for Vampire's inventory layer:

- **JIT loading ON:** `/v1/models` returns **all downloaded models**, not only those
  loaded in memory. A request for any listed model will trigger an on-demand load.
- **JIT loading OFF:** `/v1/models` returns **only loaded models**. Requests for
  unlisted models fail until the owner loads them.

So `/v1/models` alone cannot distinguish "loaded" from "loadable". To know actual
memory state, Vampire must use `/api/v0/models` (`state` field) or `/api/v1/models`
(`loaded_instances`) — see [04-rest-api-v1.md](04-rest-api-v1.md) and
[05-rest-api-v0.md](05-rest-api-v0.md).

## Features carried by the chat completions endpoint

- **Streaming** via `"stream": true` (SSE chunks, OpenAI format).
- **Vision input** — image content parts for vision-capable models.
- **Tool / function calling** — OpenAI `tools` array; models trained for tool use
  advertise it via capabilities.
- **Structured output** — `response_format` with a JSON schema.
- **LM Studio extensions accepted in the payload** — notably `"ttl": <seconds>`
  (idle TTL for the JIT-loaded model serving this request, see
  [07-model-lifecycle.md](07-model-lifecycle.md)).

## Authentication

When the owner enables "Require Authentication", all `/v1/*` requests must carry
`Authorization: Bearer $LM_API_TOKEN` ([06-authentication.md](06-authentication.md)).
Otherwise no API key is required (clients may send any placeholder key).

## Implications for Vampire

1. **Transparent proxying is sufficient** for the entire compatibility surface —
   request and response bodies pass through unchanged, including SSE streams.
2. **Model namespace collisions:** two nodes can serve the same model `id`. Vampire's
   aggregated `/v1/models` must merge inventories and remember which nodes back each id.
3. **Capability-aware routing:** a request with image parts must route only to
   vision-capable instances; a `tools` request only to tool-use models.
4. **The `ttl` extension passes through** so clients can keep controlling node memory
   behavior end to end.
