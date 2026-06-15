# Imagine: 100 x 4090 (24Gb) running Gemma 4 26B A4B QAT

All in takes is a LM Studio Vampire running on a network...

- 100 school children bring their notebooks to school...
- 100 workers login to LM Studio installed on their business desktops...
- 100 vibe coders link into the wifi of a conference....

The Vampire is an aggregator layer in front of the 100 RTX 4090s, each serving Gemma 4 26B A4B QAT**, I’d design it as a **single logical model endpoint backed by many independent replicas**, not as one 100-GPU tensor-parallel monster.

Gemma 4 26B A4B is a MoE model: about **26B total parameters**, but only about **4B active parameters per token**. Google’s model docs list the Q4_0 load memory for Gemma 4 26B A4B at roughly **14.4 GB**, but explicitly warn that this excludes runtime overhead and KV cache, so context length is the real limiter on 24 GB cards. ([Google AI for Developers][1]) The RTX 4090 has **24 GB GDDR6X**, **16,384 CUDA cores**, about **83 TFLOPS FP32**, and **1,321 AI TOPS**, with NVIDIA listing **450 W TGP**. Across 100 cards, that is roughly **2.4 TB aggregate VRAM** and **45 kW GPU board power before CPUs, networking, storage, and cooling**. ([NVIDIA][2])

## The mental model

```text
                      ┌────────────────────────────┐
Users / apps ───────▶ │  Gemma Aggregator Gateway  │
                      │  OpenAI-compatible API     │
                      └─────────────┬──────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
        ┌────────▼───────┐  ┌──────▼────────┐  ┌──────▼────────┐
        │ Replica Pool A │  │ Replica Pool B │  │ Replica Pool C │
        │ short chat     │  │ long context   │  │ vision/tooling │
        └───────┬────────┘  └──────┬────────┘  └──────┬────────┘
                │                  │                  │
         1-GPU workers      1/2/3-GPU workers   multimodal workers
         4090 replicas      reserved KV cache   image-enabled path
```

The interface should make **100 separate 4090s feel like one elastic model**, while still exposing the operational truth: every worker has its own queue, KV cache pressure, context budget, thermal state, and failure mode.

## Recommended topology

For this model on RTX 4090s, I’d start with **1 GPU = 1 inference replica** for the true 4-bit/GGUF-style QAT path, then group those replicas into pools:

| Pool                         | Suggested size | Purpose                                            | Why                                                   |
| ---------------------------- | -------------: | -------------------------------------------------- | ----------------------------------------------------- |
| **Fast chat pool**           |        60 GPUs | Normal chat, tools, coding, short prompts          | Lowest latency and highest concurrency                |
| **Long-context pool**        |        20 GPUs | 32K–128K context jobs                              | Prevents long KV-cache jobs from starving normal chat |
| **Batch/offline pool**       |        10 GPUs | summarization, evals, document sweeps              | Throughput-optimized, relaxed latency                 |
| **Canary/experimental pool** |         5 GPUs | new runtime flags, model updates, prompt templates | Safe rollout                                          |
| **Spare/failover pool**      |         5 GPUs | hot standby, maintenance absorption                | Keeps SLOs stable                                     |

The important routing rule: **do not route purely by round-robin**. Route by a weighted score:

```text
score =
  queue_depth_weight
+ kv_cache_pressure_weight
+ expected_output_tokens_weight
+ prefix_cache_affinity_weight
+ worker_health_weight
+ tenant_priority_weight
```

That gives you a cluster that behaves predictably under mixed workloads.

## Interface concept

Think of the aggregator as both a **developer API** and an **operator console**.

### 1. Public API

Expose one stable model name:

```http
POST /v1/chat/completions
model: gemma-4-26b-a4b-qat
```

Internally, map that to a pool:

```json
{
  "model": "gemma-4-26b-a4b-qat",
  "routing_policy": "latency_aware",
  "pool": "fast-chat",
  "max_context": 32768,
  "max_output_tokens": 4096,
  "tool_mode": "native",
  "priority": "standard"
}
```

The Hugging Face model page for the Gemma 4 26B A4B QAT unquantized checkpoint shows both vLLM and SGLang OpenAI-compatible examples, while Google’s QAT docs distinguish between GGUF, compressed-tensor, mobile, and unquantized QAT formats. ([Hugging Face][3]) For the **26B A4B MoE specifically**, vLLM’s Gemma 4 recipe says the W4A16 compressed-tensor QAT path is not included for 26B A4B because of quality loss, and recommends online `int8_per_channel_weight_only` quantization for that MoE model instead. ([vLLM][4]) So the runtime choice matters:

| Runtime path                             | Best fit                                                                                           |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| **llama.cpp / LM Studio / GGUF**         | Best for true Q4-style 4090 single-GPU replicas                                                    |
| **vLLM + base model + int8 per-channel** | Better if you want vLLM scheduling and OpenAI-compatible serving for 26B A4B                       |
| **SGLang**                               | Good if you want production routing, structured generation, multi-step agent flows, and DP routing |
| **Unquantized QAT checkpoint**           | Conversion/research/speculative path, not the memory-saving serving artifact                       |

## Operator dashboard

The UI should be brutally operational. Something like:

```text
GEMMA FABRIC / gemma-4-26b-a4b-qat

Cluster
  GPUs online:              97 / 100
  Active replicas:          92
  Hot spares:                5
  Total queued requests:   418
  p50 latency:             820 ms
  p95 latency:             3.8 s
  Output throughput:       xx tok/s
  KV cache pressure:       61%
  Power draw:              ~43 kW GPU board

Pools
  fast-chat        58/60 online    p95 2.1 s    queue 122
  long-context     19/20 online    p95 9.4 s    queue 41
  batch            10/10 online    p95 relaxed  queue 255
  canary            5/5 online     p95 2.4 s    queue 0
  spare             5/5 online     idle

Alerts
  gpu-037: thermal throttling
  gpu-044: high corrected memory errors
  host-09: network packet loss
  pool long-context: KV pressure > 85%
```

Each worker card should show:

```text
gpu-042
  model: gemma-4-26b-a4b-qat
  runtime: llama.cpp server / vLLM / SGLang
  state: healthy
  VRAM: 21.2 / 24 GB
  KV cache: 72%
  active requests: 6
  waiting requests: 14
  tokens/s: xx
  temp: 71 °C
  power: 382 W
  last error: none
```

vLLM already exposes production metrics through a `/metrics` endpoint on its OpenAI-compatible API server, including request counts and KV-cache usage, so the aggregator should scrape these into Prometheus/Grafana or an equivalent telemetry plane. ([vLLM][5])

## Scheduling policy

For 100 × 4090, the scheduler is the product. The model is only half the system.

I’d implement five routing classes:

| Class                 | Routing behaviour                                      |
| --------------------- | ------------------------------------------------------ |
| **Short interactive** | Lowest queue, low KV pressure, strict p95 latency      |
| **Long context**      | Route only to workers with enough KV headroom          |
| **Prefix-heavy**      | Sticky route by prompt/system prefix hash              |
| **Batch**             | Fill GPUs aggressively, optimize tokens/s over latency |
| **Premium/priority**  | Preempt queue position, reserve capacity               |

Example internal request annotation:

```json
{
  "request_id": "req_abc",
  "tenant": "team-red",
  "model": "gemma-4-26b-a4b-qat",
  "input_tokens_est": 8200,
  "output_tokens_max": 1200,
  "requires_image": false,
  "requires_tools": true,
  "latency_class": "interactive",
  "routing_hint": {
    "prefix_hash": "sys_91f4",
    "preferred_pool": "fast-chat",
    "avoid_workers": ["gpu-037"]
  }
}
```

## The big design choice: replicas vs parallelism

For this model and hardware, I’d avoid spreading a single request over many 4090s unless forced.

vLLM’s own scaling docs recommend single-GPU serving when the model fits, tensor parallelism when it does not, and pipeline parallelism for cases where GPU count is uneven or where GPUs lack high-speed interconnect such as NVLink. ([vLLM][6]) RTX 4090 clusters generally behave better as **many independent replicas** because consumer cards do not give you the same server-grade multi-GPU fabric as H100/H200/NVL systems.

The aggregator should therefore prefer:

```text
100 replicas × 1 GPU
```

over:

```text
1 replica × 100 GPUs
```

or even:

```text
25 replicas × 4 GPUs
```

unless the chosen serving artifact cannot fit on one 4090.

## Capacity framing

A useful way to think about the cluster:

```text
100 × 4090 = enormous concurrency
100 × 4090 ≠ one coherent 2.4 TB VRAM GPU
```

Aggregate VRAM is only useful when you run **many replicas**. It does not automatically become a shared memory pool. The user-facing win is that the system can serve many independent conversations at once, not that one conversation can use 2.4 TB of VRAM.

The practical constraints will be:

1. **KV cache**, especially if users push toward 128K–256K context.
2. **Cooling and power**, because 45 kW GPU board power likely means materially more wall power after CPUs, PSUs, fans, networking, and conversion losses.
3. **Queue management**, because one 200K-token request can poison a naïve scheduler.
4. **Runtime format**, because “QAT” could mean GGUF, unquantized QAT checkpoint, mobile CT, or W4A16 CT depending on exact model ID.
5. **Fault isolation**, because consumer GPU clusters fail in boring ways: risers, power cables, thermals, filesystem cache corruption, driver hangs.

## The clean product abstraction

Call it something like **Gemma Fabric**.

Externally:

```text
One endpoint.
One model name.
Streaming responses.
Tool calling.
Vision input where enabled.
Tenant quotas.
Usage accounting.
```

Internally:

```text
100 GPUs.
Multiple pools.
Per-worker health.
KV-aware routing.
Canary rollout.
Prefix affinity.
Autoshed under overload.
```

The north-star interface is not “here are 100 GPUs.” It is:

```text
gemma-4-26b-a4b-qat is available at 99.x% reliability,
with predictable latency bands,
controllable context tiers,
and transparent token economics.
```

## Minimal production architecture

```text
[API Gateway / Auth]
        │
        ▼
[Request Normalizer]
        │
        ▼
[Tokenizer + Token Estimator]
        │
        ▼
[Policy Engine]
  - tenant quota
  - context tier
  - abuse/rate controls
  - priority class
        │
        ▼
[KV/Queue-Aware Router]
        │
        ├── fast-chat pool
        ├── long-context pool
        ├── batch pool
        ├── canary pool
        └── spare pool
        │
        ▼
[Worker Runtime]
  - llama.cpp server, vLLM, or SGLang
  - one model replica per GPU where possible
        │
        ▼
[Telemetry + Billing + Eval Logs]
```

For SGLang-style deployments, its docs describe data parallelism as full model replicas processing independent batches, and recommend SGLang Model Gateway for production-grade DP routing rather than basic in-process DP. ([docs.sglang.io][7]) That maps very naturally onto a 100 × 4090 fabric.

## My preferred configuration

For your exact premise, I’d start here:

```text
Runtime:
  llama.cpp / GGUF if you want true QAT 4-bit single-4090 density
  vLLM if you choose base Gemma 4 26B A4B with int8 per-channel serving
  SGLang if agentic routing and production DP gateway matter most

Replica layout:
  1 GPU per replica wherever possible

Context tiers:
  8K default
  32K paid/explicit
  128K reserved pool
  256K only as a special queue

Routing:
  least-loaded + KV-aware + prefix-affinity

API:
  OpenAI-compatible chat completions
  streaming required
  structured output supported
  per-tenant quotas

Ops:
  Prometheus metrics
  per-GPU thermal/power monitoring
  canary deploys
  automatic worker quarantine
  request replay/eval harness
```

The main thing I would **not** do is expose this as a raw “pick a GPU” interface. Users should see a model. Operators should see the fabric.

[1]: https://ai.google.dev/gemma/docs/core "Gemma 4 model overview  |  Google AI for Developers"
[2]: https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/ "GeForce RTX 4090 Graphics Cards for Gaming | NVIDIA"
[3]: https://huggingface.co/google/gemma-4-26B-A4B-it-qat-q4_0-unquantized/tree/main "google/gemma-4-26B-A4B-it-qat-q4_0-unquantized at main"
[4]: https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html "Gemma 4 Usage Guide - vLLM Recipes"
[5]: https://docs.vllm.ai/en/v0.6.2/serving/metrics.html "Production Metrics — vLLM"
[6]: https://docs.vllm.ai/en/latest/serving/parallelism_scaling/ "Parallelism and Scaling - vLLM"
[7]: https://docs.sglang.io/docs/advanced_features/dp_dpa_smg_guide "DP, DPA and SGLang DP Router - SGLang Documentation"
