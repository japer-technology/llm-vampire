# `vampire share`

Set the owner sharing mode for the gateway.

## Synopsis

```bash
vampire share [--gateway URL] MODE [on|off] [--duration DURATION] [--model MODEL]
```

## Description

`share` records how the owner intends to share this gateway — from fully private
(`off`) through `local`, `personal`, `family`, `business`, to a temporary `event`
mode. The setting is stored as gateway share state and surfaced to the dashboard
and clients.

> **Note.** In the current scaffold the share mode is recorded but **not yet
> enforced** — it expresses owner intent that later phases (auth/policy) will act
> on.

### Mode normalisation

| You type | Stored as |
| --- | --- |
| `on` | `local` (with `enabled = true`) |
| `stop` | `off` (with `enabled = false`) |
| `off` | `off` (with `enabled = false`) |
| any other mode | as typed, `enabled` from the optional state |

## Arguments and options

| Argument / flag | Description |
| --- | --- |
| `MODE` | One of `on`, `off`, `local`, `personal`, `family`, `business`, `event`, `stop`. |
| `on` / `off` (state) | Optional enable/disable state. **Not allowed** with `off` or `stop`. |
| `--gateway URL` | Base URL of the running gateway. Default `http://127.0.0.1:7777`. |
| `--duration DURATION` | Optional duration the share stays active (e.g. `8h`). |
| `--model MODEL` | Optional model to scope the share to. |

## Calls

`POST /vampire/v1/share`

Request body (example):

```json
{ "mode": "family", "enabled": true, "duration": "8h", "model": null }
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status, or could not be reached. |
| `2` | Invalid arguments (e.g. passing an `on`/`off` state to `share off`/`share stop`). |

## Examples

Share with the family for eight hours:

```bash
vampire share family --duration 8h
```

Turn sharing fully off:

```bash
vampire share off
# or equivalently
vampire share stop
```

Enable the default local share:

```bash
vampire share on
```

Scope a share to a single model:

```bash
vampire share business --model vampire:chat
```

The following is rejected with exit `2`, because `off`/`stop` take no state:

```bash
vampire share off on   # error: share off/stop do not accept an on/off state
```

## See also

- [status](status.md) — confirm the gateway is reachable.
- [Sharing modes](../manual/08-sharing-modes.md) — what each mode means.
