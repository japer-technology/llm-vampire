# `vampire serve`

Run the OpenAI-compatible Vampire gateway in the foreground.

## Synopsis

```bash
vampire serve [--host HOST] [--port PORT]
```

## Description

`serve` is the only command that starts a server in **this** process — every
other `vampire` command is a thin client that talks to a running gateway. It
launches the FastAPI app (`vampire.app:create_app`) under Uvicorn, exposing three
surfaces on a single port:

- `/v1/*` — the OpenAI-compatible gateway (proxy or, when opted in, routed).
- `/vampire/v1/*` — the Vampire control API used by all other CLI commands.
- `/` — the static browser dashboard.

Logging is configured from the active [settings](../manual/04-configuration.md)
before the server starts. The process runs until interrupted (Ctrl-C); on a clean
shutdown it exits `0`.

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `--host HOST` | `127.0.0.1` (from settings) | Address to bind. |
| `--port PORT` | `7777` (from settings) | Port to bind. |

Both flags **override** the corresponding `VAMPIRE_HOST` / `VAMPIRE_PORT`
settings. All other configuration comes from `VAMPIRE_*` environment variables
and `.env` (see [Configuration](../manual/04-configuration.md)).

## Calls

Local. Does not call the control API — it *is* the server the control API runs
on.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The server started and later exited cleanly. |

## Examples

Run on the defaults (`127.0.0.1:7777`):

```bash
vampire serve
```

Bind to all interfaces on a custom port so other LAN machines can reach the
gateway:

```bash
vampire serve --host 0.0.0.0 --port 8080
```

Point a control command at that gateway from another shell:

```bash
vampire status --gateway http://192.168.1.10:8080
```

## See also

- [status](status.md) — confirm the gateway is up.
- [dashboard](dashboard.md) — open the browser UI the server hosts.
- [Configuration](../manual/04-configuration.md) — `VAMPIRE_*` settings.
- [Quick start](../manual/03-quickstart.md) — serve your first request.
