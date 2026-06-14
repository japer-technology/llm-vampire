# Agent Suggestions Index

Automated deep-audit suggestions for `lmstudio-vampire`, produced by the
`vampire-suggestion` cron job (model: claude-opus-4-8). One file per run.
This index is rebuilt from the directory contents on every run.

_Generated: 2026-06-14 08:27 UTC_

11 total · 3 open · 8 taken · 0 declined

| Date | Title | Severity | Category | Status | File |
| --- | --- | --- | --- | --- | --- |
| 2026-06-14 0826 | `Router._cursors` is an unbounded `defaultdict` keyed by client-controlled model strings: any client can grow gateway memory without limit via distinct `vampire:<anything>` model names | High | concurrency / resource-leak | Open | [2026-06-14_0826-router-cursor-unbounded-growth.md](./2026-06-14_0826-router-cursor-unbounded-growth.md) |
| 2026-06-14 0808 | Transparent proxy forwards the client's `Authorization` header (the gateway's own `VAMPIRE_AUTH_TOKEN`) verbatim to every downstream LM Studio node | High | security | Open | [2026-06-14_0808-proxy-forwards-gateway-bearer-token-to-untrusted-upstreams.md](./2026-06-14_0808-proxy-forwards-gateway-bearer-token-to-untrusted-upstreams.md) |
| 2026-06-14 0802 | `discover_nodes` permanently registers every scanned candidate IP, flooding the registry with un-reapable offline "phantom" nodes that sabotage `/v1/models` | High | concurrency / resource-leak | Open | [2026-06-14_0802-discover-offline-phantom-node-pollution.md](./2026-06-14_0802-discover-offline-phantom-node-pollution.md) |
| 2026-06-14 0701 | Control-API bearer check uses non-constant-time comparison, leaking the gateway token via timing | High | security | Taken | [2026-06-14_0701-control-auth-timing-side-channel.md](./2026-06-14_0701-control-auth-timing-side-channel.md) |
| 2026-06-14 0642 | Per-request `X-Vampire-Strategy` override accepted unvalidated and coerced, yet the trace header reports the strategy never applied | High | api-correctness | Taken | [2026-06-14_0642-strategy-override-unvalidated-trace-header-lies.md](./2026-06-14_0642-strategy-override-unvalidated-trace-header-lies.md) |
| 2026-06-14 0633 | `discover_nodes` probes LAN-scan candidates sequentially, turning `/vampire/v1/discover` into a multi-minute hang; malformed subnet crashes with bare 500 | High | performance / error-handling | Taken | [2026-06-14_0633-discover-sequential-lan-scan-blocks.md](./2026-06-14_0633-discover-sequential-lan-scan-blocks.md) |
| 2026-06-14 0629 | A `# type: ignore[union-attr]` masks a TOCTOU None-deref in the hot routing path: a node deregistered mid-request crashes with a bare 500 | High | type-safety / concurrency | Taken | [2026-06-14_0629-route-node-deref-500-race.md](./2026-06-14_0629-route-node-deref-500-race.md) |
| 2026-06-14 0612 | A fresh `httpx.AsyncClient` is built and torn down per proxied request, defeating connection pooling | High | performance | Taken | [2026-06-14_0612-per-request-httpx-client-no-pooling.md](./2026-06-14_0612-per-request-httpx-client-no-pooling.md) |
| 2026-06-14 0608 | `/v1/models` returns HTTP 500 when a virtual model id collides with a physical model id | High | error-handling / api-correctness | Taken | [2026-06-14_0608-models-id-collision-500.md](./2026-06-14_0608-models-id-collision-500.md) |
| 2026-06-14 0602 | `refresh_node` unconditionally re-inserts into the registry, silently resurrecting a concurrently deregistered node | High | concurrency | Taken | [2026-06-14_0602-refresh-node-resurrects-deleted-nodes.md](./2026-06-14_0602-refresh-node-resurrects-deleted-nodes.md) |
| 2026-06-14 0548 | `auth_token` is a silently-ignored security control: no route enforces authentication, leaving the control plane wide open | High | security | Taken | [2026-06-14_0548-auth-token-never-enforced.md](./2026-06-14_0548-auth-token-never-enforced.md) |
