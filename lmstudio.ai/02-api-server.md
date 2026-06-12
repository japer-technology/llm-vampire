# 02 — The LM Studio API Server

The API server is the single mechanism by which LM Studio exposes compute to the
outside world — and therefore the only thing Vampire ever connects to. Everything about
it is owner-controlled.

## Starting the server

- **GUI:** Developer tab → toggle "Start server".
- **CLI:** `lms server start`
- The last server state is saved and restored on app/service launch.

```bash
lms server start                  # default settings (last used port, localhost)
lms server start --port 3000      # custom port
lms server start --cors           # enable CORS (security risk; pair with auth)
lms server start --bind 0.0.0.0   # listen on all IPv4 interfaces (LAN exposure)
```

- Default address: `http://localhost:1234`. The port is configurable; `1234` is only a
  convention. The bind host can also be set with the `LMS_SERVER_HOST` environment
  variable.
- `lms server status` reports whether the server is running; `lms server stop` stops it.
- `lms log stream` tails server logs.

## Server settings (owner controls)

These are the levers an LM Studio owner has. Vampire must function correctly under any
combination of them:

| Setting | Type | Effect |
| --- | --- | --- |
| **Server Port** | integer | Port the API server listens on |
| **Require Authentication** | switch | Require a valid API token via the `Authorization` header on every request ([06-authentication.md](06-authentication.md)) |
| **Serve on Local Network** | switch | Bind to a non-localhost address so other devices on the LAN can reach the server |
| **Allow per-request MCPs** | switch | Let API clients pass ephemeral remote MCP servers per request |
| **Allow calling servers from mcp.json** | switch | Let API clients invoke owner-defined MCP servers (requires authentication to be enabled) |
| **Enable CORS** | switch | Allow cross-origin browser clients |
| **Just-in-Time Model Loading** | switch | Load models dynamically at request time ([07-model-lifecycle.md](07-model-lifecycle.md)) |
| **Auto Unload Unused JIT Models** | switch | Unload JIT models after idle TTL |
| **Only Keep Last JIT Loaded Model** | switch | Keep at most the most recent JIT model in memory |

## Serve on Local Network

Enabling "Serve on Local Network" (GUI) or `--bind 0.0.0.0` (CLI) makes the server
reachable from other devices on the same LAN. LM Studio's documented use cases match
Vampire's premise exactly:

- use a local LLM from less powerful devices by connecting them to a stronger machine,
- let multiple people share a single LM Studio instance,
- serve IoT/edge devices and other services on the network.

LM Studio explicitly warns that any bind other than `127.0.0.1` exposes the server
beyond localhost and recommends enabling authentication.

## Implications for Vampire

1. **Reachability is opt-in.** A node is only discoverable if the owner started the
   server *and* enabled network serving (or Vampire runs on the same host). Vampire
   never works around this.
2. **Port is not fixed.** Node registration must carry a full `base_url`
   (host + port), not assume `1234`.
3. **Health probing.** A node can disappear at any time (owner toggles the server
   off). Vampire should treat connection failures as a normal state transition, not an
   error condition.
4. **Auth is per-node.** Each node may or may not require a token; Vampire's token
   vault stores per-node credentials and forwards them only to that node.
5. **MCP settings matter for proxying.** If a client request includes MCP
   integrations, it can only be routed to nodes whose owners enabled the corresponding
   MCP setting.
