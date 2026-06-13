# `vampire route`

Inspect or set virtual-model routing rules.

## Synopsis

```bash
vampire route [--gateway URL] [SUBCOMMAND ...]
```

With no subcommand, `vampire route` defaults to [`list`](#vampire-route-list).

## Description

A *route policy* maps one `vampire:` **virtual model** that clients request onto
one or more physical `node:model` **targets**, chosen at request time by a
strategy. Routes are how Vampire turns a pool of LM Studio nodes into a single
load-balanced, failover-capable endpoint.

Routing is **opt-in**: a client must request the virtual model id (or send the
opt-in header) for a route to apply. See [Routing](../manual/07-routing.md) for
the opt-in signals and the `X-Vampire-*` response headers.

| Subcommand | Calls | Description |
| --- | --- | --- |
| [`list`](#vampire-route-list) | `GET /vampire/v1/routes` | List route policies. |
| [`add`](#vampire-route-add) | `POST /vampire/v1/routes` | Create or replace a route policy. |
| [`get`](#vampire-route-get) | `GET /vampire/v1/routes/{id}` | Show one route policy. |
| [`delete`](#vampire-route-delete) | `DELETE /vampire/v1/routes/{id}` | Remove a route policy. |

## Global options

| Flag | Default | Description |
| --- | --- | --- |
| `--gateway URL` | `http://127.0.0.1:7777` | Base URL of the running gateway. |

---

## `vampire route list`

List every route policy.

```bash
vampire route [--gateway URL] list
```

Calls `GET /vampire/v1/routes`.

---

## `vampire route add`

Create a new route policy, or replace an existing one with the same `ROUTE_ID`.

```bash
vampire route add ROUTE_ID VIRTUAL_MODEL \
  --target node:model [--target node:model]... \
  [--strategy STRATEGY] [--fallback VIRTUAL_MODEL]
```

| Argument / flag | Description |
| --- | --- |
| `ROUTE_ID` | Unique id for the route policy. |
| `VIRTUAL_MODEL` | The virtual model id clients request (e.g. `vampire:chat`). |
| `--target node:model` | A target pairing a registered node with one of its models. **Required, repeatable.** |
| `--strategy STRATEGY` | Target-selection strategy (see below). Default `round_robin`. |
| `--fallback VIRTUAL_MODEL` | Virtual model to fall back to when no target is available. |

Each `--target` must use the `node:model` form; a malformed target exits `2`.

### Strategies

| Strategy | Behaviour |
| --- | --- |
| `round_robin` (default) | Rotate evenly across targets. |
| `least_busy` | Pick the target with the fewest active requests. |
| `least_latency` | Pick the lowest-latency target. |
| `model_affinity` | Prefer targets already serving the requested model. |
| `trusted_only` | Restrict selection to trusted nodes. |

Calls `POST /vampire/v1/routes`. An unsupported strategy returns `400`.

---

## `vampire route get`

Show one route policy, or `404` if the id is unknown.

```bash
vampire route get ROUTE_ID
```

Calls `GET /vampire/v1/routes/{id}`.

---

## `vampire route delete`

Remove a route policy, or `404` if the id is unknown.

```bash
vampire route delete ROUTE_ID
```

Calls `DELETE /vampire/v1/routes/{id}`.

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The gateway responded `2xx`. |
| `1` | The gateway returned a non-success status (e.g. `400`/`404`), or could not be reached. |
| `2` | Invalid arguments (e.g. a `--target` that is not `node:model`). |

## Examples

Create a least-busy chat route across two nodes, with a fallback:

```bash
vampire route add chat vampire:chat \
  --target node-a:llama-3 \
  --target node-b:llama-3 \
  --strategy least_busy \
  --fallback vampire:backup
```

List routes, then inspect one:

```bash
vampire route
vampire route get chat
```

Remove a route:

```bash
vampire route delete chat
```

A client then requests the virtual model instead of a physical one:

```bash
curl http://127.0.0.1:7777/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "vampire:chat", "messages": [{"role": "user", "content": "hi"}]}'
```

## See also

- [models](models.md) — the physical `node:model` targets you wire into a route.
- [nodes](nodes.md) — register and tag the nodes referenced by targets.
- [Routing](../manual/07-routing.md) — opt-in signals, strategies, and response headers.
