# `vampire discover`

Ask the gateway to discover reachable LM Studio nodes on the LAN.

## Synopsis

```bash
vampire discover [--gateway URL] \
                 [--method M]... [--subnet CIDR]... [--port N]... \
                 [--timeout-ms MS] [--trusted-only] [--base-url URL]...
```

## Description

`discover` runs the gateway's discovery routine and returns the nodes it could
reach. The current scaffold supports two methods:

- `static` (default) — probe the explicit `--base-url` targets you pass.
- `lan_scan` — scan the given `--subnet` CIDR ranges on the given `--port`s.

The probe checks each candidate's OpenAI-compatible `/v1/models` endpoint and
returns the nodes that answered. Discovery is **read-only**: it does not register
anything. To persist a discovered node, register it with
[`vampire nodes add`](nodes.md#vampire-nodes-add).

## Options

| Flag | Repeatable | Default | Description |
| --- | --- | --- | --- |
| `--gateway URL` | no | `http://127.0.0.1:7777` | Base URL of the running gateway. |
| `--method M` | yes | `static` | Discovery method(s): `static`, `lan_scan`. |
| `--subnet CIDR` | yes | (none) | CIDR subnet(s) to scan when using `lan_scan`. |
| `--port N` | yes | `1234` | Port(s) to probe. |
| `--timeout-ms MS` | no | `1500` | Per-node probe timeout in milliseconds. |
| `--trusted-only` | no | off | Only return nodes already marked trusted. |
| `--base-url URL` | yes | (none) | Explicit base URL(s) to probe directly. |

## Calls

`POST /vampire/v1/discover`

Request body:

```json
{
  "methods": ["static", "lan_scan"],
  "subnets": ["192.168.1.0/24"],
  "ports": [1234],
  "timeout_ms": 1500,
  "trusted_only": false,
  "base_urls": ["http://192.168.1.50:1234"]
}
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status, or could not be reached. |

## Examples

Probe two explicit endpoints directly:

```bash
vampire discover \
  --base-url http://192.168.1.50:1234 \
  --base-url http://192.168.1.51:1234
```

Scan a subnet on the LM Studio default port with a tighter timeout:

```bash
vampire discover --method lan_scan --subnet 192.168.1.0/24 --port 1234 --timeout-ms 800
```

Only return nodes already trusted:

```bash
vampire discover --method lan_scan --subnet 192.168.1.0/24 --trusted-only
```

## See also

- [nodes](nodes.md) — register a discovered node so it persists.
- [Nodes & discovery](../manual/06-nodes-and-discovery.md) — the full discovery guide.
