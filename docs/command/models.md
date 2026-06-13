# `vampire models`

List the gateway's aggregated physical model inventory.

## Synopsis

```bash
vampire models [--gateway URL]
```

## Description

`models` shows every physical model the gateway has discovered across all
registered nodes, matching the browser dashboard's Models panel. The response
pairs each `model` with the `node` that serves it, so you can see which machine
hosts which weights.

This is the **physical** inventory (`/vampire/v1/models`). The OpenAI-compatible
`GET /v1/models` surface additionally exposes the `vampire:` *virtual* model ids
created by [routes](route.md).

## Options

| Flag | Default | Description |
| --- | --- | --- |
| `--gateway URL` | `http://127.0.0.1:7777` | Base URL of the running gateway. |

## Calls

`GET /vampire/v1/models`

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status, or could not be reached. |

## Examples

List the aggregated inventory:

```bash
vampire models
```

Pipe into `jq` to pull out just the model ids:

```bash
vampire models | jq '.data[].model'
```

## See also

- [nodes](nodes.md) — the nodes whose models are aggregated here.
- [route](route.md) — group physical models behind a `vampire:` virtual model.
- [API reference](../manual/09-api-reference.md) — `/v1/models` vs `/vampire/v1/models`.
