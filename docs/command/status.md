# `vampire status`

Show the gateway and cluster status envelope.

## Synopsis

```bash
vampire status [--gateway URL]
```

## Description

`status` is the quickest way to confirm a gateway is reachable and to see how many
nodes it knows about. It performs a single `GET` against the control API and
pretty-prints the JSON response with sorted keys.

The status envelope reports:

| Field | Meaning |
| --- | --- |
| `version` | The gateway's `vampire` version. |
| `nodes_total` | Number of registered nodes (any status). |
| `nodes_online` | Number of nodes currently health-checked online. |

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `--gateway URL` | `http://127.0.0.1:7777` | Base URL of the running gateway. |

## Calls

`GET /vampire/v1/status`

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status, or could not be reached. |

## Examples

Check the local gateway:

```bash
vampire status
```

Example output:

```json
{
  "nodes_online": 2,
  "nodes_total": 3,
  "version": "0.1.0"
}
```

Check a remote gateway:

```bash
vampire status --gateway http://192.168.1.10:7777
```

Use in a script — exit `1` means unreachable:

```bash
if vampire status >/dev/null 2>&1; then
  echo "gateway up"
fi
```

## See also

- [serve](serve.md) — start the gateway this command queries.
- [metrics](metrics.md) — deeper per-node health and counters.
- [nodes](nodes.md) — inspect the nodes counted here.
