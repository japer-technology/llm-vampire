# LM Studio Setup for Vampire

This is the owner checklist for preparing an LM Studio installation so it can be
found, trusted, and used by `lmstudio-vampire`.

The short version:

1. Install or update LM Studio.
2. Download and load at least one model.
3. Start the LM Studio API server.
4. Disable prompt/response and verbose server logging.
5. Keep the server bound to `localhost` unless LAN sharing is intentional.
6. If the server is reachable by anyone except the local machine, enable
   authentication.
7. Enable CORS only when a browser scanner or browser client needs readable
   cross-origin responses.
8. Verify from the Vampire host with `/v1/models`, then register or scan the
   endpoint.

Vampire never bypasses LM Studio owner controls. If the LM Studio server is off,
bound to localhost, blocked by a firewall, protected by a token Vampire does not
have, or has no usable model, Vampire cannot use it.

## Trust Standard

A Vampire-ready LM Studio node has three independent properties:

| Property | Required state |
| --- | --- |
| Reachability | The LM Studio API server is reachable from the Vampire host at a known base URL, commonly `http://localhost:1234` or `http://LAN-IP:1234`. |
| Consent | The owner intentionally enabled that reachability, and revokes it by stopping the server, changing the bind address, firewalling the port, or deleting the API token. |
| Log minimisation | LM Studio prompt/response logging and verbose developer/server logging are disabled where the installed LM Studio version exposes those controls. |

Log minimisation is not the same as a mathematical guarantee that no metadata is
ever persisted anywhere. LM Studio documents local server logs and the `lms log
stream` command can inspect model I/O, so sensitive deployments must treat the
setup below as a minimum privacy posture, not a zero-logging proof.

Official references:

- [LM Studio server settings](https://lmstudio.ai/docs/developer/core/server/settings)
- [LM Studio authentication](https://lmstudio.ai/docs/developer/core/authentication)
- [LM Studio `lms log stream`](https://lmstudio.ai/docs/cli/serve/log-stream)
- [LM Studio `lms server start`](https://lmstudio.ai/docs/cli/serve/server-start)

## Choose a Deployment Mode

| Mode | Use when | Bind address | Authentication | CORS |
| --- | --- | --- | --- | --- |
| Local only | Vampire runs on the same computer as LM Studio. | `localhost` / `127.0.0.1` | Optional for personal development; recommended if other local users or apps are not trusted. | Usually off. |
| Trusted LAN | Vampire runs on another trusted machine on the same network. | LAN-enabled / `0.0.0.0` | Required. | Enable only if using browser-based scanning or browser clients. |
| Headless node | A server, GPU box, VM, or dedicated account runs LM Studio without routine desktop use. | Usually LAN-enabled, firewall-scoped. | Required. | Only when needed. |
| Sensitive/private | Prompts may contain confidential data. | Prefer localhost, isolated VM, or dedicated OS account. | Required. | Avoid unless needed; disable after verification. |

## Desktop Setup

### 1. Install and Update LM Studio

Install LM Studio from the official site:

```text
https://lmstudio.ai/
```

Run the application at least once. This initialises the app, model store, and the
`lms` CLI integration used by scripted/headless workflows.

Use a recent LM Studio build. Vampire works best with LM Studio 0.4.0 or newer
because that line adds the native `/api/v1/*` API, API-token authentication, and
headless `llmster` support. Older 0.3.x nodes can still expose `/v1/*` and
`/api/v0/*`, but do not provide the same authentication and inventory surface.

### 2. Download a Model

In LM Studio, download at least one model that fits the machine. For a practical
first node, choose a small chat model that can fully load on the available CPU/GPU
memory.

Confirm the model can load and answer a local prompt before involving Vampire.
Vampire can route to a model only after LM Studio can serve it.

### 3. Open Developer Server Settings

In LM Studio:

```text
Developer -> Server Settings
```

Configure these controls deliberately:

| Setting | Recommended state |
| --- | --- |
| Server Port | Keep `1234` unless there is a port conflict. If changed, record the exact port for Vampire. |
| Serve on Local Network | Off for local-only use. On only when Vampire or clients run on another machine. |
| Require Authentication | On for every LAN, shared, headless, business, school, event, or sensitive deployment. |
| Enable CORS | Off by default. On only for browser-based scanner/client access. |
| Just-in-Time Model Loading | Optional. Useful for convenience, but fixed loaded models are easier to reason about for routing. |
| MCP-related server settings | Off unless explicitly required by the owner and protected by authentication. |

### 4. Disable LM Studio Request Logging

In `Developer -> Server Settings`, disable every detailed request logging option
available in your LM Studio version, including:

- `Log Prompts and Responses`
- verbose developer logging
- verbose server logging
- any option that records exact request bodies, response bodies, prompts, messages,
  completions, tool calls, images, embeddings input, or model I/O

Do not run this in sensitive environments:

```bash
lms log stream
```

That command exists to inspect local server logs and model I/O. It is valuable for
debugging, but it is not compatible with a privacy posture where other Vampires
must trust that prompt and response content is not being observed or retained.

If policy requires cleanup, periodically clear local LM Studio logs, developer
logs, temporary files, and model/server caches according to your OS and LM Studio
version. LM Studio does not currently expose a single documented "never persist
any request metadata anywhere" switch, so your documented promise to the network
should be "prompt/response logging disabled and logs minimised", not "provably
zero logging".

### 5. Bind the Server Correctly

For local-only use, keep the server local:

```text
http://localhost:1234
http://127.0.0.1:1234
```

For LAN use, enable `Serve on Local Network` in the GUI, or start the server from
the CLI with a LAN bind:

```bash
lms server start --port 1234 --bind 0.0.0.0
```

LAN binding exposes the server beyond the local machine. Pair it with
authentication and OS/firewall restrictions.

### 6. Enable Authentication for Shared Nodes

LM Studio 0.4.0+ supports API tokens.

In `Developer -> Server Settings`:

1. Enable `Require Authentication`.
2. Open `Manage Tokens`.
3. Create a token for the specific Vampire gateway or trusted client.
4. Record the token immediately. LM Studio shows token values only when created.
5. Give each Vampire instance its own token so access can be revoked per gateway.
6. Delete the token to withdraw consent.

Authenticated requests must include:

```text
Authorization: Bearer <LM_STUDIO_TOKEN>
```

The current Vampire scaffold does not yet provide a production token vault. For
direct testing, pass the LM Studio token from the client or from the scanner's
per-run token field. Future Vampire policy phases will store per-node owner
tokens and forward them only to the node that issued them.

### 7. Enable CORS Only When Needed

The HTML scanner runs in a browser. Browsers require CORS permission before they
can read cross-origin responses from `http://host:1234`.

If the scanner reports a node as `CORS blocked`, the browser proved that a server
responded but could not read the model/status response. On the LM Studio host,
enable:

```text
Serve on Local Network
Enable CORS
```

or start with:

```bash
lms server start --port 1234 --bind 0.0.0.0 --cors
```

Only leave CORS enabled for origins and networks you trust. CORS is not
authentication; it merely controls whether browser JavaScript may read responses.

### 8. Load or Pin a Model

For predictable routing, explicitly load the model that Vampire should use. You
can do this in the LM Studio UI or with:

```bash
lms load <model>
lms ps
```

If just-in-time loading is enabled, `/v1/models` may list downloaded models that
are not currently resident in memory. If just-in-time loading is disabled,
`/v1/models` normally lists only loaded models. Vampire's richer interrogation
prefers `/api/v1/models` or `/api/v0/models` when available so it can see load
state.

## Verify the Node

Run these checks on the machine that will run Vampire.

### Local Node

```bash
curl http://localhost:1234/v1/models
```

Expected result: JSON with an OpenAI-compatible `data` list.

### Authenticated Node

```bash
curl http://HOST:1234/v1/models \
  -H "Authorization: Bearer <LM_STUDIO_TOKEN>"
```

Expected result: model JSON. A `401` or `403` means the token is missing, invalid,
or lacks permission.

### Native LM Studio Inventory

For LM Studio 0.4.0+:

```bash
curl http://HOST:1234/api/v1/models \
  -H "Authorization: Bearer <LM_STUDIO_TOKEN>"
```

For older nodes:

```bash
curl http://HOST:1234/api/v0/models \
  -H "Authorization: Bearer <LM_STUDIO_TOKEN>"
```

These surfaces expose richer model/load-state information than plain `/v1/models`.

## Verify with the Vampire Scanner

Open:

```text
tools/html/vampire-scanner.html
```

or serve it from the repository if your browser blocks local-file requests.

Use the scanner as follows:

1. Set the subnet and port range, or add manual targets such as
   `http://10.0.0.5:1234`.
2. If the node requires authentication, paste the LM Studio token into
   `Authorization token for this run`.
3. Click `Scan`.
4. Confirm the node appears as `online`.
5. Confirm model count, loaded models, API surface, auth status, and CORS status.
6. Check the logging/privacy panel on each node.

The scanner displays logging status as one of:

| Scanner status | Meaning |
| --- | --- |
| `logging off` | A readable header or Vampire status body advertises prompt/response and/or verbose logging as disabled. |
| `logging on` | A readable header or status body advertises prompt/response or verbose logging as enabled. Do not trust this node for sensitive prompts. |
| `logging partial` | One logging control is advertised as disabled, but not every relevant logging control is visible. Owner verification is still required. |
| `logging unknown` | LM Studio did not expose logging status over the probed HTTP surface, CORS blocked the read, auth was missing, or the node was offline. Verify in LM Studio settings. |

Current LM Studio model endpoints do not guarantee that server logging settings are
readable over HTTP. Therefore `logging unknown` is expected for many correctly
configured nodes. It is not proof of unsafe logging; it is proof that the browser
scanner cannot independently verify the setting.

## Register with Vampire

Start Vampire:

```bash
vampire serve
```

For a local LM Studio node on the default port, no extra configuration is needed:

```text
http://localhost:7777/v1
```

For a different downstream node:

```bash
VAMPIRE_LMSTUDIO_BASE_URL=http://HOST:1234 vampire serve
```

Register an owner-approved node with the control API/CLI:

```bash
vampire nodes add home-gpu http://HOST:1234 --name "Home GPU" --trusted --tag lmstudio --tag logging-minimised
```

Then inspect:

```bash
vampire status
vampire nodes list
vampire models
```

The current scaffold can discover and route among registered nodes, but production
policy, client authentication, and per-node token vaulting are still planned
future phases. Until those land, expose authenticated LAN nodes only inside a
trusted environment and avoid sharing LM Studio tokens broadly.

## Headless Setup

For a GPU box, VM, or server:

1. Install LM Studio / `llmster` support for the target OS.
2. Run LM Studio at least once if using the bundled `lms` CLI.
3. Start the daemon:

   ```bash
   lms daemon up
   lms daemon status
   ```

4. Start the server:

   ```bash
   lms server start --port 1234 --bind 0.0.0.0
   ```

5. Enable authentication in LM Studio server settings.
6. Disable prompt/response and verbose logging.
7. Load the desired model:

   ```bash
   lms load <model>
   lms ps
   ```

8. Restrict the port with the host firewall so only the Vampire gateway or trusted
   subnet can connect.

For sensitive headless deployments, use a dedicated OS user, encrypted disk, and
an isolated VM/container where practical.

## Firewall Rules

Only open the LM Studio API port to hosts that need it.

Typical allowed flows:

| Source | Destination | Port | Purpose |
| --- | --- | --- | --- |
| Vampire host | LM Studio node | `1234/tcp` or chosen port | Model API access |
| Browser scanner host | LM Studio node | `1234/tcp` or chosen port | Temporary verification |
| Client apps | Vampire gateway | `7777/tcp` or chosen port | OpenAI-compatible gateway |

Do not expose LM Studio directly to the public internet. Put it behind VPN,
firewall rules, SSH tunnel, or a future authenticated Vampire policy layer.

## Owner Privacy Checklist

Before calling a node trusted, confirm:

- LM Studio is installed from the official source and is up to date.
- The node owner intentionally enabled the server.
- The bind address is `localhost` unless LAN sharing is deliberate.
- LAN sharing is protected by `Require Authentication`.
- Token values are unique per Vampire/client and stored privately.
- `Log Prompts and Responses` is disabled.
- Verbose developer/server logging is disabled.
- `lms log stream` is not running during sensitive use.
- CORS is off unless a browser scanner/client requires it.
- Local logs/cache are cleared according to policy.
- Wrapper apps, proxies, shells, terminals, process managers, and observability
  tools around LM Studio are not separately logging request bodies.
- The machine uses a dedicated OS user, encrypted disk, or isolated VM/container
  if the prompts require stronger controls.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Vampire cannot connect | LM Studio server is stopped, wrong host/port, firewall block, or LAN serving is off. | Start the server, confirm the port, enable LAN serving if needed, and test with `curl`. |
| Scanner shows `CORS blocked` | Browser can reach the server but cannot read responses. | Enable CORS on the LM Studio host while scanning. |
| `/v1/models` returns 401/403 | Authentication is enabled and no valid token was supplied. | Provide `Authorization: Bearer <token>`. |
| `/v1/models` is empty | No model is loaded and JIT is off, or no model is downloaded. | Load/download a model or enable JIT. |
| Logging status is `unknown` | LM Studio did not advertise logging settings over the probed HTTP surface. | Verify manually in `Developer -> Server Settings`; treat this as owner-attested. |
| A node was trusted and later fails | Owner stopped the server, revoked token, changed port, unloaded model, or changed firewall/bind settings. | Refresh discovery, update the node record, or remove it from routing. |

## Trust Statement Template

Owners can publish or attach this statement when offering a node:

```text
I intentionally expose this LM Studio server to the named Vampire gateway.
The server is bound only to the advertised interface and port.
Authentication is enabled for any non-local access.
Prompt/response logging and verbose server/developer logging are disabled where
my LM Studio version exposes those controls.
I am not running lms log stream or other tooling that records model I/O during
sensitive use.
I understand that this is log minimisation, not a vendor-certified zero-logging
guarantee, and I can revoke access by stopping the server, changing the bind
address, firewalling the port, or deleting the API token.
```

That is the standard Vampire should rely on until LM Studio exposes a documented,
remote-verifiable server logging status endpoint.
