# `vampire metrics`

Show the dashboard metrics snapshot for cluster and per-node health.

## Synopsis

```bash
vampire metrics [--gateway URL]
```

## Description

`metrics` returns the same snapshot the browser dashboard renders: per-node health
and counters (request counts, latency, queue depth, tokens/second) plus
cluster-wide totals. Use it for at-a-glance health from the terminal or to feed a
monitoring script.

Where [`status`](status.md) is a tiny three-field envelope, `metrics` is the
detailed view.

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `--gateway URL` | `http://127.0.0.1:7777` | Base URL of the running gateway. |

## Calls

`GET /vampire/v1/metrics`

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status, or could not be reached. |

## Examples

Show the snapshot:

```bash
vampire metrics
```

Poll every few seconds with `watch(1)`:

```bash
watch -n 5 vampire metrics
```

## See also

- [status](status.md) — the compact status envelope.
- [models](models.md) — the model inventory behind these counters.
