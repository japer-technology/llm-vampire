# 10. Troubleshooting

A field guide to the problems you are most likely to hit, and how to resolve
them. Start with the decision tree, then jump to the matching section.

```mermaid
flowchart TD
    start{"What is failing?"}
    start -->|"vampire command not found"| a["§ Command not found"]
    start -->|"Can't reach the gateway"| b["§ Gateway unreachable"]
    start -->|"Requests fail / upstream error"| c["§ Upstream errors"]
    start -->|"No models listed"| d["§ Empty model list"]
    start -->|"Routing returns 503"| e["§ Routing 503"]
    start -->|"share rejected"| f["§ Share argument errors"]
```

---

## Command not found: `vampire`

The console script is not on your `PATH`.

- Confirm the install succeeded: `pip install -e ".[dev]"` from the repo root.
- If you used a virtual environment, activate it first
  (`source .venv/bin/activate`).
- Verify with `vampire --version`.

---

## Gateway unreachable

Symptom — control commands print:

```text
Could not reach Vampire gateway at http://127.0.0.1:7777: ...
```

```mermaid
flowchart TD
    q["Could not reach gateway"] --> r1{"Is vampire serve running?"}
    r1 -->|"no"| fix1["Start it: vampire serve"]
    r1 -->|"yes"| r2{"Right host/port?"}
    r2 -->|"no"| fix2["Pass --gateway http://host:port"]
    r2 -->|"yes"| r3{"Port in use / firewalled?"}
    r3 -->|"yes"| fix3["Change VAMPIRE_PORT or free the port"]
```

- Start the gateway: `vampire serve`.
- If it runs on a non-default address, target it: `vampire status --gateway http://host:port`.
- If the port is already in use, set `VAMPIRE_PORT` or `vampire serve --port 8080`.

---

## Upstream errors when sending requests

Symptom — a `/v1/*` request returns an OpenAI-style error envelope even though
the gateway is up. Vampire forwards requests to LM Studio, so this usually means
the downstream node is the problem.

- Confirm LM Studio's server is running and reachable (default
  `http://localhost:1234`).
- Confirm the configured downstream URL is correct:
  `VAMPIRE_LMSTUDIO_BASE_URL`. See [Configuration](04-configuration.md).
- Confirm the `model` id you sent matches one from `GET /v1/models`.
- If LM Studio requires a token, the request must carry the owner's
  `Authorization` header — Vampire passes headers through transparently. See
  [`lmstudio.ai/06-authentication.md`](../../lmstudio.ai/06-authentication.md).

---

## Empty model list

`GET /v1/models` returns nothing useful.

```mermaid
flowchart TD
    q["Empty / unexpected /v1/models"] --> r1{"Any nodes registered?"}
    r1 -->|"no"| p["Falls back to proxying the<br/>single configured downstream node"]
    p --> r2{"Is that node online<br/>with a model loaded?"}
    r2 -->|"no"| fix1["Start LM Studio + load a model"]
    r1 -->|"yes"| r3{"Are nodes online?"}
    r3 -->|"no"| fix2["Check vampire nodes list →<br/>status / last_error"]
    r3 -->|"yes"| ok["Models aggregate across nodes"]
```

- With no nodes registered, ensure the single downstream node is up and has a
  model loaded.
- With nodes registered, run `vampire nodes list` and check each node's `status`
  and `last_error`. Offline nodes contribute no models.

---

## Routing returns 503

Symptom:

```json
{ "error": { "type": "vampire_routing_error", "code": "no_route_target" } }
```

- The route resolved to **no online target**. Check that the route's target
  nodes are registered and online: `vampire route get <id>` and
  `vampire nodes list`.
- Add a `--fallback` virtual model when creating the route so traffic can
  divert. See [Routing](07-routing.md).
- Confirm the strategy is one of the accepted MVP strategies; an unsupported
  strategy is rejected at route-creation time with HTTP `400`.

---

## Share argument errors

Symptom:

```text
share off/stop do not accept an on/off state
```

- `off` and `stop` cannot take an `on`/`off` state argument. Use just
  `vampire share off`.
- Valid modes are `on`, `off`, `local`, `personal`, `family`, `business`,
  `event`, `stop`. See [Sharing modes](08-sharing-modes.md).

---

## Diagnostics checklist

```mermaid
flowchart LR
    a["vampire --version"] --> b["vampire status"]
    b --> c["vampire nodes list"]
    c --> d["vampire route list"]
    d --> e["VAMPIRE_LOG_LEVEL=DEBUG vampire serve"]
```

Run these in order to localise an issue: confirm the install, the gateway, the
registry, the routes, and finally re-run the server with debug logging for the
fullest detail.

## Still stuck?

- Re-read the relevant chapter — most behaviour is documented with examples.
- Cross-check against [DESIGN-API.md](../../DESIGN-API.md) and
  [IMPLEMENTATION-PLAN.md](../../IMPLEMENTATION-PLAN.md) to confirm whether a
  feature is implemented or planned.
- Open an issue on the [repository](https://github.com/japer-technology/lmstudio-vampire).
