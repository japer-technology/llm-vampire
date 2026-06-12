# 10 — The `lms` CLI

`lms` is LM Studio's MIT-licensed command-line utility
([lmstudio-ai/lms](https://github.com/lmstudio-ai/lms)). It ships with LM Studio (run
the app at least once before first use) and is how owners script everything Vampire
relies on: server exposure, model loading, daemon management, and LM Link.

## Command map

### Local models

| Command | Purpose |
| --- | --- |
| `lms chat` | Interactive chat with a model in the terminal |
| `lms get <model>` | Search and download models |
| `lms load <model>` | Load a model (supports `--ttl <seconds>`, context/GPU options) |
| `lms unload` | Unload a model |
| `lms ls` | List models available on disk |
| `lms ps` | List models currently loaded in memory |
| `lms import` | Import a model file into LM Studio |

### Server

| Command | Purpose |
| --- | --- |
| `lms server start` | Start the API server (`--port <n>`, `--cors`, `--bind <addr>`) |
| `lms server status` | Check whether the server is running |
| `lms server stop` | Stop the server |
| `lms log stream` | Stream server logs |

`--bind 0.0.0.0` listens on all IPv4 interfaces (LAN exposure; pair with
authentication). The bind address can also come from the `LMS_SERVER_HOST`
environment variable.

### Daemon (llmster)

| Command | Purpose |
| --- | --- |
| `lms daemon up` | Start the headless llmster daemon |
| `lms daemon status` | Daemon status |
| `lms daemon down` | Stop the daemon |
| `lms daemon update` | Update llmster |

### LM Link

| Command | Purpose |
| --- | --- |
| `lms login` | Log in (required for LM Link on headless machines) |
| `lms link enable` / `disable` | Join or leave the link |
| `lms link status` | Link status |
| `lms link set-device-name` | Rename this device |
| `lms link set-preferred-device` | Pick the device that serves shared models |

### Runtime

| Command | Purpose |
| --- | --- |
| `lms runtime` | Manage inference runtimes (llama.cpp / MLX engine versions) |

## Implications for Vampire

1. **Owner onboarding is scriptable.** Everything an owner must do to make a machine
   Vampire-ready is a short, documentable `lms` sequence (see
   [08-headless.md](08-headless.md)).
2. **Vampire itself never shells out to `lms`** on remote machines — it has no such
   access. `lms` matters as the owner-side counterpart of every state change Vampire
   observes over HTTP (server up/down, models loaded/unloaded, link membership).
3. **`lms load` without TTL pins a model.** Owners can guarantee a model stays
   resident for Vampire traffic by loading it explicitly rather than relying on JIT.
