# LM Studio Vampire API

**Vampire = LM Studio-compatible API + local-network orchestration extensions.**

This API design carries through the project vision in [VISION.md](VISION.md) (expanded in [ASPIRATION.md](ASPIRATION.md)): idle, LM Studio-compatible GPUs on a local network become one governed, private AI service behind a stable OpenAI-compatible endpoint. Each vision commitment maps to a concrete API surface:

| Vision commitment | API surface in this design |
| --- | --- |
| Stable OpenAI-compatible endpoint | §1 Base URL, §5–§6 `/v1/models` and `/v1/chat/completions`, §26 normal-client example |
| Wakes on the LAN and discovers approved endpoints | §12 node discovery, §13 node registration, Layer 3 node agent API |
| Verifies models and capabilities | §14 node list, §15 Vampire model inventory |
| Respects owner tokens and policy before routing | §4.3 route policy, §16 route creation, §21 security model and trust levels |
| Load-balances and fails over | §8.1 `route` mode, §8.2 `race` mode, §9 routing strategies |
| Coalesces identical prompts | request deduplication within routing strategies (§9) and modes (§8) |
| Fuses answers across machines | §8.4 `fusion`, §8.5 `debate`, §10 fusion strategies, §11 dedicated fusion endpoint |
| Optimizes for latency, privacy, cost, and quality | §9 routing strategies, §18 metrics, §19 traces |
| Owner decides when to contribute | §13 node registration (opt-in), §21 security model |
| Users simply see working, local-first AI | Compatibility-first principle (§2), opt-in Vampire extensions (§7) |

The key rule: **anything that already works against LM Studio should keep working unchanged.** LM Studio exposes OpenAI-compatible endpoints such as `/v1/models`, `/v1/responses`, `/v1/chat/completions`, `/v1/embeddings`, and `/v1/completions`; it also has native REST endpoints for chat and model management. Vampire should sit in front of those endpoints as a transparent proxy, then add optional orchestration controls. ([LM Studio][1])

---

## 1. Base URL

```txt
http://localhost:7777
```

Recommended default:

```txt
http://localhost:7777/v1
```

A normal OpenAI-compatible or LM Studio-compatible client should be able to point its base URL at Vampire:

```txt
http://localhost:7777/v1
```

instead of:

```txt
http://localhost:1234/v1
```

LM Studio commonly uses port `1234` for its local API server examples, and can serve APIs on localhost or the local network. ([LM Studio][2])

---

# 2. Design principle

## Compatibility first

These should behave like LM Studio/OpenAI-compatible routes:

```txt
GET  /v1/models
POST /v1/responses
POST /v1/chat/completions
POST /v1/completions
POST /v1/embeddings
```

## Vampire additions are opt-in

Vampire features can be enabled through:

1. **Extra request field**

```json
"vampire": {
  "mode": "fusion",
  "strategy": "best_of_n"
}
```

2. **Headers**

```txt
X-Vampire-Mode: route
X-Vampire-Trace: true
X-Vampire-Session: project-alpha
```

3. **Dedicated Vampire routes**

```txt
/vampire/v1/...
```

This keeps existing clients working while allowing advanced clients to use orchestration.

---

# 3. API layers

## Layer 1 — LM Studio-compatible API

These are drop-in routes.

```txt
GET  /v1/models
POST /v1/chat/completions
POST /v1/responses
POST /v1/completions
POST /v1/embeddings
```

## Layer 2 — Vampire control API

These manage nodes, routing, fusion, pipelines, health, and policies.

```txt
GET  /vampire/v1/status
GET  /vampire/v1/nodes
POST /vampire/v1/nodes
GET  /vampire/v1/nodes/{node_id}
PATCH /vampire/v1/nodes/{node_id}
DELETE /vampire/v1/nodes/{node_id}

GET  /vampire/v1/models
GET  /vampire/v1/routes
POST /vampire/v1/routes
POST /vampire/v1/discover
POST /vampire/v1/fusion
POST /vampire/v1/pipelines
GET  /vampire/v1/jobs/{job_id}
GET  /vampire/v1/traces/{trace_id}
GET  /vampire/v1/metrics
```

## Layer 3 — Node agent API

Optional lightweight agents running beside each LM Studio node.

```txt
GET  /agent/v1/health
GET  /agent/v1/models
GET  /agent/v1/load
POST /agent/v1/register
POST /agent/v1/heartbeat
POST /agent/v1/proxy
```

---

# 4. Core objects

## 4.1 Node

A node is a machine running LM Studio or an agent beside LM Studio.

```json
{
  "id": "node-mac-studio-01",
  "name": "Mac Studio M2 Ultra",
  "host": "192.168.1.41",
  "lmstudio_base_url": "http://192.168.1.41:1234",
  "agent_base_url": "http://192.168.1.41:7778",
  "status": "online",
  "trusted": true,
  "capabilities": {
    "chat": true,
    "responses": true,
    "completions": true,
    "embeddings": true,
    "vision": false,
    "tools": true,
    "streaming": true
  },
  "hardware": {
    "os": "macos",
    "cpu": "Apple M2 Ultra",
    "gpu": "integrated",
    "ram_gb": 128,
    "vram_gb": null
  },
  "load": {
    "active_requests": 2,
    "queue_depth": 1,
    "cpu_percent": 34,
    "gpu_percent": 71,
    "memory_percent": 62
  },
  "network": {
    "latency_ms": 4,
    "last_seen": "2026-06-12T10:12:00+10:00"
  }
}
```

---

## 4.2 Vampire model

A Vampire model is a virtual model name mapped to one or more real LM Studio models.

```json
{
  "id": "vampire:reasoning-large",
  "object": "model",
  "owned_by": "vampire",
  "type": "virtual",
  "targets": [
    {
      "node_id": "node-mac-studio-01",
      "model": "qwen/qwen3-32b"
    },
    {
      "node_id": "node-ubuntu-4090",
      "model": "deepseek-r1-distill-qwen-32b"
    }
  ],
  "routing": {
    "strategy": "least_latency",
    "fallback": "small-fast"
  },
  "context_window": 32768,
  "supports": {
    "chat": true,
    "responses": true,
    "streaming": true,
    "tools": true,
    "structured_output": true
  }
}
```

---

## 4.3 Route policy

```json
{
  "id": "coding-policy",
  "match": {
    "model": "vampire:code",
    "task_type": "coding"
  },
  "strategy": "best_available",
  "candidates": [
    "node-ubuntu-4090",
    "node-mac-studio-01"
  ],
  "constraints": {
    "min_context_window": 16384,
    "max_queue_depth": 4,
    "trusted_only": true
  },
  "fallback": {
    "model": "vampire:general",
    "strategy": "least_busy"
  }
}
```

---

# 5. `/v1/models`

## Standard behavior

Returns OpenAI-compatible model list.

```http
GET /v1/models
```

## Response

```json
{
  "object": "list",
  "data": [
    {
      "id": "vampire:auto",
      "object": "model",
      "created": 1781234567,
      "owned_by": "vampire"
    },
    {
      "id": "vampire:fast",
      "object": "model",
      "created": 1781234567,
      "owned_by": "vampire"
    },
    {
      "id": "vampire:fusion",
      "object": "model",
      "created": 1781234567,
      "owned_by": "vampire"
    },
    {
      "id": "qwen/qwen3-32b@node-mac-studio-01",
      "object": "model",
      "created": 1781234567,
      "owned_by": "node-mac-studio-01"
    }
  ]
}
```

## Vampire addition

Use a query parameter for detailed model inventory:

```http
GET /v1/models?vampire_detail=true
```

Response includes physical nodes, loaded state, context size, quantization, latency, and availability.

---

# 6. `/v1/chat/completions`

This remains the main compatibility route.

LM Studio supports chat completions with fields such as `model`, `messages`, `temperature`, `max_tokens`, `stream`, `top_p`, `top_k`, penalties, `seed`, and others. ([LM Studio][3])

## 6.1 Standard request

```http
POST /v1/chat/completions
Content-Type: application/json
```

```json
{
  "model": "vampire:auto",
  "messages": [
    {
      "role": "user",
      "content": "Explain local-network model orchestration."
    }
  ],
  "temperature": 0.3,
  "stream": true
}
```

## Standard response

By default, Vampire returns normal OpenAI-compatible output.

```json
{
  "id": "chatcmpl-vampire-01JZABC",
  "object": "chat.completion",
  "created": 1781234567,
  "model": "qwen/qwen3-32b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Local-network model orchestration means..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 23,
    "completion_tokens": 142,
    "total_tokens": 165
  }
}
```

---

# 7. Vampire request extension

Add a `vampire` object to request bodies.

```json
{
  "model": "vampire:auto",
  "messages": [
    {
      "role": "user",
      "content": "Design a secure local inference fabric."
    }
  ],
  "temperature": 0.2,
  "vampire": {
    "mode": "route",
    "trace": true,
    "session": "japer-inference-fabric",
    "routing": {
      "strategy": "least_busy",
      "trusted_only": true,
      "fallback": true
    },
    "constraints": {
      "min_context_window": 16000,
      "max_latency_ms": 150,
      "required_capabilities": ["chat", "streaming"]
    },
    "response": {
      "include_metadata": true
    }
  }
}
```

## Response with Vampire metadata

```json
{
  "id": "chatcmpl-vampire-01JZABC",
  "object": "chat.completion",
  "created": 1781234567,
  "model": "qwen/qwen3-32b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "A secure local inference fabric should..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 18,
    "completion_tokens": 276,
    "total_tokens": 294
  },
  "vampire": {
    "trace_id": "trace-01JZABC",
    "mode": "route",
    "selected_node": "node-mac-studio-01",
    "selected_model": "qwen/qwen3-32b",
    "routing_strategy": "least_busy",
    "fallback_used": false,
    "latency_ms": 1847,
    "time_to_first_token_ms": 311,
    "tokens_per_second": 38.4
  }
}
```

---

# 8. Vampire modes

## 8.1 `route`

Pick one best node/model.

```json
"vampire": {
  "mode": "route",
  "routing": {
    "strategy": "least_latency"
  }
}
```

Use cases:

* Normal chat.
* Coding assistant.
* Fast local tasks.
* Single best model.
* Failover protection.

---

## 8.2 `race`

Send the same request to multiple nodes and return the first acceptable answer.

```json
"vampire": {
  "mode": "race",
  "race": {
    "candidates": ["vampire:fast", "vampire:balanced"],
    "return": "first_valid",
    "cancel_losers": true
  }
}
```

Use cases:

* Low latency.
* Browser UI responsiveness.
* Fallback against slow nodes.

---

## 8.3 `parallel`

Send independent work to multiple nodes.

```json
"vampire": {
  "mode": "parallel",
  "parallel": {
    "split": "messages",
    "max_nodes": 4
  }
}
```

Use cases:

* Chunked document summarization.
* Batch classification.
* Embedding batches.
* Synthetic data generation.

---

## 8.4 `fusion`

Ask multiple models, then merge results.

```json
"vampire": {
  "mode": "fusion",
  "fusion": {
    "candidates": [
      "vampire:reasoning-large",
      "vampire:fast",
      "vampire:critic"
    ],
    "strategy": "judge_synthesis",
    "judge_model": "vampire:judge",
    "return_intermediates": false
  }
}
```

Use cases:

* Better answers.
* Cross-model verification.
* Critical reasoning.
* Design review.
* Code review.

---

## 8.5 `debate`

Models argue different positions before synthesis.

```json
"vampire": {
  "mode": "debate",
  "debate": {
    "participants": [
      {
        "model": "vampire:architect",
        "role": "proposer"
      },
      {
        "model": "vampire:security",
        "role": "critic"
      },
      {
        "model": "vampire:judge",
        "role": "arbiter"
      }
    ],
    "rounds": 2
  }
}
```

Use cases:

* Architecture decisions.
* Security design.
* Complex trade-offs.
* Product strategy.

---

## 8.6 `pipeline`

Multi-stage inference graph.

```json
"vampire": {
  "mode": "pipeline",
  "pipeline": {
    "id": "planner-executor-critic",
    "stages": [
      {
        "id": "plan",
        "model": "vampire:planner",
        "prompt": "Create a plan."
      },
      {
        "id": "execute",
        "model": "vampire:executor",
        "input_from": "plan"
      },
      {
        "id": "critic",
        "model": "vampire:critic",
        "input_from": "execute"
      },
      {
        "id": "final",
        "model": "vampire:writer",
        "input_from": ["plan", "execute", "critic"]
      }
    ]
  }
}
```

Use cases:

* Planner → executor → critic → final.
* Extract → validate → repair.
* Code → test → review.
* Summarize chunks → global synthesis.

---

# 9. Routing strategies

```txt
round_robin
weighted_round_robin
least_busy
least_latency
highest_tokens_per_second
best_available
model_affinity
context_window
trusted_only
power_saver
race
fallback_chain
quality_score
cost_score
privacy_policy
```

Example:

```json
"vampire": {
  "mode": "route",
  "routing": {
    "strategy": "best_available",
    "weights": {
      "latency": 0.25,
      "tokens_per_second": 0.25,
      "queue_depth": 0.25,
      "quality_score": 0.25
    }
  }
}
```

---

# 10. Fusion strategies

```txt
best_of_n
majority_vote
ranked_vote
judge_synthesis
claim_merge
contradiction_check
critic_refine
consensus_only
return_all
```

Example:

```json
"vampire": {
  "mode": "fusion",
  "fusion": {
    "strategy": "claim_merge",
    "candidates": [
      "vampire:general",
      "vampire:reasoning",
      "vampire:critic"
    ],
    "judge_model": "vampire:judge",
    "min_agreement": 2
  }
}
```

---

# 11. Dedicated fusion endpoint

```http
POST /vampire/v1/fusion
Content-Type: application/json
```

```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Find weaknesses in this distributed inference architecture."
      }
    ]
  },
  "candidates": [
    {
      "model": "vampire:architect",
      "role": "system designer"
    },
    {
      "model": "vampire:security",
      "role": "security reviewer"
    },
    {
      "model": "vampire:performance",
      "role": "performance engineer"
    }
  ],
  "fusion": {
    "strategy": "judge_synthesis",
    "judge_model": "vampire:judge",
    "include_dissent": true
  }
}
```

Response:

```json
{
  "id": "fusion-01JZABC",
  "object": "vampire.fusion",
  "final": {
    "role": "assistant",
    "content": "The main weaknesses are..."
  },
  "contributors": [
    {
      "model": "vampire:architect",
      "node": "node-mac-studio-01",
      "status": "completed"
    },
    {
      "model": "vampire:security",
      "node": "node-ubuntu-4090",
      "status": "completed"
    }
  ],
  "metrics": {
    "latency_ms": 8321,
    "total_tokens": 4921
  }
}
```

---

# 12. Node discovery

## Discover nodes

```http
POST /vampire/v1/discover
Content-Type: application/json
```

```json
{
  "methods": ["static", "mdns", "udp_broadcast", "lan_scan"],
  "subnets": ["192.168.1.0/24"],
  "ports": [1234, 7778],
  "timeout_ms": 1500,
  "trusted_only": false
}
```

Response:

```json
{
  "object": "vampire.discovery_result",
  "nodes": [
    {
      "id": "node-mac-studio-01",
      "host": "192.168.1.41",
      "lmstudio_base_url": "http://192.168.1.41:1234",
      "status": "online",
      "models": ["qwen/qwen3-32b", "nomic-embed-text"]
    }
  ]
}
```

---

# 13. Node registration

```http
POST /vampire/v1/nodes
Content-Type: application/json
```

```json
{
  "name": "Ubuntu RTX 4090",
  "lmstudio_base_url": "http://192.168.1.52:1234",
  "agent_base_url": "http://192.168.1.52:7778",
  "trust": {
    "mode": "manual",
    "fingerprint": "sha256:8fb2..."
  },
  "tags": ["gpu", "trusted", "office"]
}
```

Response:

```json
{
  "id": "node-ubuntu-4090",
  "status": "registered",
  "trusted": true
}
```

---

# 14. Node list

```http
GET /vampire/v1/nodes
```

Response:

```json
{
  "object": "list",
  "data": [
    {
      "id": "node-mac-studio-01",
      "status": "online",
      "models_loaded": 2,
      "active_requests": 1,
      "queue_depth": 0,
      "latency_ms": 4,
      "tokens_per_second": 41.2
    },
    {
      "id": "node-ubuntu-4090",
      "status": "online",
      "models_loaded": 3,
      "active_requests": 4,
      "queue_depth": 2,
      "latency_ms": 7,
      "tokens_per_second": 76.9
    }
  ]
}
```

---

# 15. Vampire model inventory

```http
GET /vampire/v1/models
```

Response:

```json
{
  "object": "list",
  "data": [
    {
      "virtual_model": "vampire:auto",
      "physical_models": [
        {
          "node": "node-mac-studio-01",
          "model": "qwen/qwen3-32b",
          "loaded": true,
          "context_window": 32768,
          "tokens_per_second": 38.4
        },
        {
          "node": "node-ubuntu-4090",
          "model": "deepseek-r1-distill-qwen-32b",
          "loaded": true,
          "context_window": 32768,
          "tokens_per_second": 61.7
        }
      ]
    }
  ]
}
```

---

# 16. Route creation

```http
POST /vampire/v1/routes
Content-Type: application/json
```

```json
{
  "id": "route-code",
  "virtual_model": "vampire:code",
  "targets": [
    {
      "node": "node-ubuntu-4090",
      "model": "qwen/qwen3-coder"
    },
    {
      "node": "node-mac-studio-01",
      "model": "deepseek-coder"
    }
  ],
  "strategy": "best_available",
  "fallback": "vampire:fast",
  "constraints": {
    "trusted_only": true,
    "min_context_window": 16000
  }
}
```

Response:

```json
{
  "id": "route-code",
  "status": "active"
}
```

---

# 17. Pipeline endpoint

```http
POST /vampire/v1/pipelines
Content-Type: application/json
```

```json
{
  "id": "secure-design-review",
  "input": {
    "text": "Design a LAN-based inference orchestrator."
  },
  "stages": [
    {
      "id": "architecture",
      "model": "vampire:architect",
      "instruction": "Propose the architecture."
    },
    {
      "id": "security",
      "model": "vampire:security",
      "instruction": "Review for security risks.",
      "input_from": "architecture"
    },
    {
      "id": "performance",
      "model": "vampire:performance",
      "instruction": "Review for performance bottlenecks.",
      "input_from": "architecture"
    },
    {
      "id": "final",
      "model": "vampire:judge",
      "instruction": "Synthesize final design.",
      "input_from": ["architecture", "security", "performance"]
    }
  ],
  "execution": {
    "parallelize_independent_stages": true,
    "stream": false
  }
}
```

Response:

```json
{
  "id": "job-01JZPIPE",
  "object": "vampire.pipeline_job",
  "status": "running",
  "trace_id": "trace-01JZPIPE"
}
```

Retrieve result:

```http
GET /vampire/v1/jobs/job-01JZPIPE
```

---

# 18. Metrics endpoint

```http
GET /vampire/v1/metrics
```

Response:

```json
{
  "object": "vampire.metrics",
  "cluster": {
    "nodes_online": 4,
    "nodes_offline": 1,
    "active_requests": 9,
    "queue_depth": 12,
    "tokens_per_second": 184.7
  },
  "models": [
    {
      "model": "vampire:fast",
      "requests_1h": 231,
      "avg_latency_ms": 911,
      "avg_tokens_per_second": 72.4,
      "error_rate": 0.004
    }
  ],
  "nodes": [
    {
      "node": "node-ubuntu-4090",
      "requests_1h": 129,
      "avg_latency_ms": 842,
      "error_rate": 0.002
    }
  ]
}
```

---

# 19. Trace endpoint

```http
GET /vampire/v1/traces/trace-01JZABC
```

Response:

```json
{
  "id": "trace-01JZABC",
  "object": "vampire.trace",
  "request": {
    "endpoint": "/v1/chat/completions",
    "model": "vampire:fusion",
    "mode": "fusion"
  },
  "routing": {
    "candidate_nodes": [
      "node-mac-studio-01",
      "node-ubuntu-4090"
    ],
    "selected_nodes": [
      "node-mac-studio-01",
      "node-ubuntu-4090"
    ],
    "strategy": "judge_synthesis"
  },
  "timing": {
    "received_at": "2026-06-12T10:20:00+10:00",
    "completed_at": "2026-06-12T10:20:08+10:00",
    "latency_ms": 8122
  },
  "stages": [
    {
      "id": "candidate-1",
      "node": "node-mac-studio-01",
      "model": "qwen/qwen3-32b",
      "status": "completed",
      "latency_ms": 4120
    },
    {
      "id": "candidate-2",
      "node": "node-ubuntu-4090",
      "model": "deepseek-r1-distill-qwen-32b",
      "status": "completed",
      "latency_ms": 5330
    },
    {
      "id": "judge",
      "node": "node-ubuntu-4090",
      "model": "vampire:judge",
      "status": "completed",
      "latency_ms": 2710
    }
  ]
}
```

---

# 20. Streaming behavior

For normal streaming, preserve OpenAI-compatible Server-Sent Events.

```txt
data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

data: [DONE]
```

For Vampire tracing, only add custom events if requested:

```http
X-Vampire-Trace: stream
```

Then stream:

```txt
event: vampire.routing
data: {"selected_node":"node-ubuntu-4090","strategy":"least_busy"}

event: vampire.model_start
data: {"node":"node-ubuntu-4090","model":"qwen/qwen3-32b"}

event: completion.chunk
data: {"id":"chatcmpl-...","choices":[...]}

event: vampire.metrics
data: {"tokens_per_second":42.1,"latency_ms":1832}

data: [DONE]
```

Default should remain plain OpenAI-compatible streaming.

---

# 21. Security model

## Required minimum

```txt
Authorization: Bearer <local-token>
```

## Suggested security controls

```json
{
  "auth": {
    "mode": "bearer",
    "required": true
  },
  "cors": {
    "allowed_origins": [
      "http://localhost:3000",
      "chrome-extension://..."
    ]
  },
  "nodes": {
    "allow_untrusted": false,
    "require_fingerprint": true
  },
  "logging": {
    "store_prompts": false,
    "store_outputs": false,
    "store_metrics": true
  }
}
```

## Trust levels

```txt
untrusted
local
trusted
verified
japer-secured
```

---

# 22. JAPER-compatible result envelope

For JAPER integration, Vampire can return signed outcome metadata.

```json
"vampire": {
  "trace_id": "trace-01JZABC",
  "selected_node": "node-ubuntu-4090",
  "selected_model": "qwen/qwen3-32b",
  "trust": {
    "node_trust_level": "verified",
    "model_hash": "sha256:...",
    "response_hash": "sha256:...",
    "signed": true,
    "signature": "..."
  },
  "outcome": {
    "schema": "japer.outcome.v1",
    "status": "valid",
    "validation_hash": "sha256:..."
  }
}
```

This is where Vampire becomes more than a router: it becomes a **verifiable inference fabric**.

---

# 23. Error format

Use OpenAI-style errors for compatibility.

```json
{
  "error": {
    "message": "No suitable Vampire node found for model vampire:reasoning-large.",
    "type": "vampire_routing_error",
    "param": "model",
    "code": "no_suitable_node"
  }
}
```

With Vampire detail:

```json
{
  "error": {
    "message": "No suitable Vampire node found.",
    "type": "vampire_routing_error",
    "code": "no_suitable_node",
    "vampire": {
      "required_model": "vampire:reasoning-large",
      "constraints": {
        "trusted_only": true,
        "min_context_window": 32000
      },
      "rejected_nodes": [
        {
          "node": "node-mac-mini",
          "reason": "context_window_too_small"
        },
        {
          "node": "node-laptop",
          "reason": "offline"
        }
      ]
    }
  }
}
```

---

# 24. Minimal MVP

The first working version only needs this:

```txt
GET  /v1/models
POST /v1/chat/completions
POST /v1/embeddings

GET  /vampire/v1/status
GET  /vampire/v1/nodes
POST /vampire/v1/nodes
GET  /vampire/v1/models
GET  /vampire/v1/metrics
```

And these modes:

```txt
route
fallback
race
fusion
```

And these routing strategies:

```txt
round_robin
least_busy
least_latency
model_affinity
trusted_only
```

---

# 25. Recommended route map

```txt
/v1/models
    Returns virtual + physical models.

/v1/chat/completions
    Drop-in LM Studio/OpenAI-compatible chat endpoint.

/v1/responses
    Drop-in LM Studio/OpenAI-compatible responses endpoint.

/v1/embeddings
    Drop-in embeddings endpoint.

/vampire/v1/status
    Cluster status.

/vampire/v1/nodes
    Node registry.

/vampire/v1/models
    Detailed virtual/physical model inventory.

/vampire/v1/routes
    Virtual model routing rules.

/vampire/v1/discover
    LAN discovery.

/vampire/v1/fusion
    Explicit ensemble endpoint.

/vampire/v1/pipelines
    Multi-stage inference workflows.

/vampire/v1/jobs/{id}
    Async job status/result.

/vampire/v1/traces/{id}
    Routing and execution trace.

/vampire/v1/metrics
    Performance and health metrics.
```

---

# 26. Example: normal client, no Vampire awareness

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:7777/v1",
  apiKey: "vampire-local"
});

const response = await client.chat.completions.create({
  model: "vampire:auto",
  messages: [
    {
      role: "user",
      content: "Explain what this API does."
    }
  ]
});

console.log(response.choices[0].message.content);
```

The client thinks it is talking to one LM Studio-compatible server.

---

# 27. Example: Vampire-aware client

```js
const response = await fetch("http://localhost:7777/v1/chat/completions", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer vampire-local",
    "X-Vampire-Trace": "true"
  },
  body: JSON.stringify({
    model: "vampire:fusion",
    messages: [
      {
        role: "user",
        content: "Review this architecture for security, performance, and reliability."
      }
    ],
    vampire: {
      mode: "fusion",
      fusion: {
        strategy: "judge_synthesis",
        candidates: [
          "vampire:security",
          "vampire:performance",
          "vampire:architect"
        ],
        judge_model: "vampire:judge"
      },
      response: {
        include_metadata: true
      }
    }
  })
});

const data = await response.json();
console.log(data);
```

---

# 28. Final shape

The **LM Studio Vampire API** is:

```txt
LM Studio-compatible at /v1/*
Vampire-orchestrated through optional request extensions
Vampire-managed through /vampire/v1/*
Node-aware through optional /agent/v1/*
```

The core abstraction is:

```txt
Client → Vampire API → Route/Fuse/Pipeline → LM Studio Nodes → Vampire Response
```

The strongest product identity:

> **Vampire turns multiple LM Studio instances into one local, secure, model-aware inference fabric.**

[1]: https://lmstudio.ai/docs/developer/openai-compat?utm_source=chatgpt.com "OpenAI Compatibility Endpoints | LM Studio"
[2]: https://lmstudio.ai/docs/developer/core/server?utm_source=chatgpt.com "LM Studio as a Local LLM API Server"
[3]: https://lmstudio.ai/docs/developer/openai-compat/chat-completions?utm_source=chatgpt.com "Chat Completions | LM Studio"
