# `vampire dashboard` / `vampire ui`

Print or open the browser dashboard URL served by `vampire serve`.

## Synopsis

```bash
vampire dashboard [--gateway URL] [--open]
vampire ui        [--gateway URL] [--open]
```

`ui` is an alias for `dashboard`; the two are identical.

## Description

The gateway serves a static browser control plane at its root path (`/`). This
command is a **local utility**: it does not call the control API. It prints the
gateway URL and, with `--open`, asks the local desktop browser to open it.

Use it as a convenient launcher so you don't have to remember the host and port.

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `--gateway URL` | `http://127.0.0.1:7777` | Base URL of the running gateway. |
| `--open` | off | Open the URL in the local desktop browser. |

## Calls

Local. Prints the gateway URL; with `--open`, hands it to the OS browser opener.
It does **not** verify the gateway is actually running.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The URL was printed (and opened, if `--open`). |

## Examples

Print the dashboard URL:

```bash
vampire dashboard
# http://127.0.0.1:7777
```

Open it in a browser:

```bash
vampire ui --open
```

Target a remote gateway:

```bash
vampire dashboard --gateway http://192.168.1.10:7777 --open
```

## See also

- [serve](serve.md) — the process that hosts the dashboard.
- [status](status.md) — confirm the gateway is up before opening the UI.
