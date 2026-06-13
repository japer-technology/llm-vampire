# 01 — LM Studio Platform Overview

LM Studio is a desktop application and developer platform for downloading and running
open-weight LLMs locally (GGUF via llama.cpp, MLX on Apple Silicon). For Vampire, the
key fact is that LM Studio is not one binary but a family of components, and **any of
them can stand behind an API endpoint Vampire connects to**.

## Components

| Component | What it is | Relevance to Vampire |
| --- | --- | --- |
| **LM Studio (desktop app)** | GUI app for Mac/Windows/Linux with a Developer tab that runs the local API server | Most common node type; owner toggles the server on/off in the GUI |
| **llmster** | The core of LM Studio packaged as a standalone, server-native daemon — no GUI required (LM Studio 0.4.0+) | Headless nodes on Linux boxes, cloud servers, GPU rigs |
| **`lms` CLI** | MIT-licensed command-line utility that ships with LM Studio ([lmstudio-ai/lms](https://github.com/lmstudio-ai/lms)) | How owners script node behavior: server start, model load, link management |
| **lmstudio-python / lmstudio-js** | Official SDKs speaking LM Studio's native protocol ([lmstudio-ai/lmstudio-python](https://github.com/lmstudio-ai/lmstudio-python), [lmstudio-ai/lmstudio-js](https://github.com/lmstudio-ai/lmstudio-js)) | Alternative programmatic surfaces (Vampire primarily uses HTTP) |
| **LM Link** | End-to-end-encrypted device network (built on Tailscale) for using remote models as if local | The compute behind a node may not be on that machine — see [09-lm-link.md](09-lm-link.md) |

## Upstream repositories (github.com/lmstudio-ai)

LM Studio's open-source components live under the [`lmstudio-ai`](https://github.com/lmstudio-ai)
GitHub organisation. The repositories below are the authoritative sources behind the
mechanisms Vampire's design depends on; this folder's reference docs are derived from them.

| Repository | What it provides | How Vampire uses it |
| --- | --- | --- |
| [lmstudio-ai/docs](https://github.com/lmstudio-ai/docs) | Source for the official App and Developer docs at [lmstudio.ai/docs](https://lmstudio.ai/docs) | Authoritative source for every doc in this folder |
| [lmstudio-ai/lms](https://github.com/lmstudio-ai/lms) | The `lms` CLI (MIT) | Owner-side scripting of server start, model load, and links — see [10-cli.md](10-cli.md) |
| [lmstudio-ai/lmstudio-python](https://github.com/lmstudio-ai/lmstudio-python) | Official Python SDK | Reference for the native protocol; an alternative to HTTP interrogation |
| [lmstudio-ai/lmstudio-js](https://github.com/lmstudio-ai/lmstudio-js) | Official TypeScript SDK | Reference for the native protocol and the `lms` toolchain |
| [lmstudio-ai/configs](https://github.com/lmstudio-ai/configs) | JSON configuration file format and examples | Understanding per-model load/preset configuration Vampire observes |
| [lmstudio-ai/mlx-engine](https://github.com/lmstudio-ai/mlx-engine) | Apple MLX inference engine | Background on the MLX runtime a node may report |

## Inference engines and model formats

- **llama.cpp engine** — runs **GGUF** models on Mac, Windows, Linux; CPU and GPU
  (CUDA, Vulkan, Metal, ROCm depending on platform). Supports flash attention,
  KV-cache GPU offload, MoE expert configuration, and continuous batching.
- **MLX engine** — runs **MLX** models on Apple Silicon.
- Runtimes are versioned and managed independently of the app (`lms runtime`).

The model `format` (`"gguf"` or `"mlx"`) and the runtime name/version are reported by
the APIs (see [04-rest-api-v1.md](04-rest-api-v1.md) and
[05-rest-api-v0.md](05-rest-api-v0.md)), so Vampire can record per-node engine details
during interrogation.

## Model capabilities

LM Studio models expose machine-readable capabilities that Vampire's inventory layer
consumes directly:

- `vision` — accepts image input
- `trained_for_tool_use` — supports tool/function calling
- `reasoning.allowed_options` — allowed reasoning-effort settings
  (`"off" | "on" | "low" | "medium" | "high"`)
- `max_context_length` — maximum supported context window
- `quantization` (method name, bits per weight), `params_string` (e.g. `"7B"`),
  `size_bytes`, `architecture`

## One port, four API surfaces

A running LM Studio server (default `http://localhost:1234`) serves all API families on
the same port:

| Surface | Base path | Doc |
| --- | --- | --- |
| OpenAI-compatible | `/v1/*` | [03-openai-compat.md](03-openai-compat.md) |
| Anthropic-compatible | `/v1/messages` | [03-openai-compat.md](03-openai-compat.md) |
| Native REST v1 (0.4.0+) | `/api/v1/*` | [04-rest-api-v1.md](04-rest-api-v1.md) |
| Legacy REST v0 (0.3.6+) | `/api/v0/*` | [05-rest-api-v0.md](05-rest-api-v0.md) |

## Version landmarks

| LM Studio version | Capability introduced |
| --- | --- |
| 0.3.6 | REST API `/api/v0/*` with enhanced stats |
| 0.4.0 | Native REST API `/api/v1/*`, API-token authentication, llmster daemon, `lms daemon`, LM Link |

Vampire must tolerate nodes at different versions: a 0.3.x node offers `/v1/*` and
`/api/v0/*` only, with no token authentication; a 0.4.0+ node adds `/api/v1/*`,
tokens, llmster, and LM Link.
