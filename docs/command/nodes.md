# `vampire nodes`

Manage the gateway's in-memory node registry.

## Synopsis

```bash
vampire nodes [--gateway URL] [SUBCOMMAND ...]
```

With no subcommand, `vampire nodes` defaults to [`list`](#vampire-nodes-list).

## Description

A *node* is an owner-approved LM Studio endpoint the gateway is allowed to use.
The `nodes` command group registers those endpoints, inspects them, patches their
metadata, drains them from routing, and removes them. Every subcommand is a thin
client over the `/vampire/v1/nodes` control endpoints and prints the JSON response
with sorted keys.

| Subcommand | Calls | Description |
| --- | --- | --- |
| [`list`](#vampire-nodes-list) | `GET /vampire/v1/nodes` | List registered nodes. |
| [`add`](#vampire-nodes-add) | `POST /vampire/v1/nodes` | Register an owner-approved node. |
| [`get`](#vampire-nodes-get) | `GET /vampire/v1/nodes/{id}` | Show one node. |
| [`update`](#vampire-nodes-update) | `PATCH /vampire/v1/nodes/{id}` | Patch mutable node metadata. |
| [`drain`](#vampire-nodes-drain) | `PATCH /vampire/v1/nodes/{id}` | Drain a node, or restore it. |
| [`delete`](#vampire-nodes-delete) | `DELETE /vampire/v1/nodes/{id}` | Remove a node. |

## Global options

| Flag | Default | Description |
| --- | --- | --- |
| `--gateway URL` | `http://127.0.0.1:7777` | Base URL of the running gateway. |

---

## `vampire nodes list`

List every registered node.

```bash
vampire nodes [--gateway URL] list
```

Calls `GET /vampire/v1/nodes`, which returns `{ "object": "list", "data": [...] }`.

---

## `vampire nodes add`

Register an owner-approved LM Studio node. After registration the gateway
interrogates the node's `/v1/models` to populate its inventory.

```bash
vampire nodes add NODE_ID LMSTUDIO_BASE_URL \
  [--name NAME] [--host HOST] [--agent-base-url URL] [--trusted] [--tag TAG]...
```

| Argument / flag | Description |
| --- | --- |
| `NODE_ID` | Unique id for the node. |
| `LMSTUDIO_BASE_URL` | The node's OpenAI-compatible base URL (e.g. `http://host:1234`). |
| `--name NAME` | Friendly display name. |
| `--host HOST` | Host label. |
| `--agent-base-url URL` | Reserved for the optional node agent (post-MVP). |
| `--trusted` | Mark the node trusted. |
| `--tag TAG` | Add a capability/role tag (repeatable). |

Calls `POST /vampire/v1/nodes`.

---

## `vampire nodes get`

Show one registered node, or `404` if the id is unknown.

```bash
vampire nodes get NODE_ID
```

Calls `GET /vampire/v1/nodes/{id}`.

---

## `vampire nodes update`

Patch mutable node metadata. **Only the flags you pass are sent** in the `PATCH`
body; everything else is left unchanged.

```bash
vampire nodes update NODE_ID \
  [--name N] [--host H] [--lmstudio-base-url URL] [--agent-base-url URL] \
  [--status STATUS] [--trusted] [--tag TAG]... \
  [--active-requests N] [--queue-depth N] [--tokens-per-second F]
```

| Flag | Type | Description |
| --- | --- | --- |
| `--name` | string | Friendly display name. |
| `--host` | string | Host label. |
| `--lmstudio-base-url` | string | New OpenAI-compatible base URL. |
| `--agent-base-url` | string | Node-agent base URL. |
| `--status` | string | Node status (e.g. `online`, `draining`). |
| `--trusted` | flag | Mark the node trusted. |
| `--tag` | string | Replace tags (repeatable). |
| `--active-requests` | int | Override the active-request counter. |
| `--queue-depth` | int | Override the queue-depth counter. |
| `--tokens-per-second` | float | Override the measured throughput. |

Calls `PATCH /vampire/v1/nodes/{id}`.

---

## `vampire nodes drain`

Mark a node draining (no new routed work) or restore it to online service. This
is a convenience wrapper over `update --status`.

```bash
vampire nodes drain NODE_ID [on|off]
```

| State | Effect |
| --- | --- |
| `on` (default) | Sets status to `draining`. |
| `off` | Restores status to `online`. |

Calls `PATCH /vampire/v1/nodes/{id}`.

---

## `vampire nodes delete`

Remove a node from the registry, or `404` if the id is unknown.

```bash
vampire nodes delete NODE_ID
```

Calls `DELETE /vampire/v1/nodes/{id}`.

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status (e.g. `404`), or could not be reached. |

## Examples

Register a trusted GPU box and tag it:

```bash
vampire nodes add gpu-rig http://192.168.1.50:1234 --name "Studio GPU" --trusted --tag fast
```

List, then inspect one node:

```bash
vampire nodes
vampire nodes get gpu-rig
```

Drain a node before a restart, then bring it back:

```bash
vampire nodes drain gpu-rig on
vampire nodes drain gpu-rig off
```

Remove a node:

```bash
vampire nodes delete gpu-rig
```

## See also

- [discover](discover.md) — find nodes before registering them.
- [models](models.md) — the inventory aggregated across these nodes.
- [Nodes & discovery](../manual/06-nodes-and-discovery.md) — the full node guide.
