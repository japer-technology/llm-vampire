# Agent Suggestions Index

Automated deep-audit suggestions for `lmstudio-vampire`, produced by the
`vampire-suggestion` cron job (model: claude-opus-4-8). One file per run.
This index is rebuilt from the directory contents on every run.

_Generated: 2026-06-14 17:10 (seed) · 8 total · 8 open · 0 taken · 0 declined_

**Status legend:** **Open** = not yet implemented · **Taken** = fix verified present in source · **Declined** = operator added a `> DECLINED:` note or a `.declined` marker. When implementation is unverified, status stays **Open** (never fabricated).

| Date (UTC) | Title | Severity | Category | Status | File |
|---|---|---|---|---|---|
| 2026-06-14 07:01 | Control-API bearer check uses non-constant-time comparison, leaking the gateway token via timing | High | security | Open | [0701-control-auth-timing-side-channel.md](./2026-06-14_0701-control-auth-timing-side-channel.md) |
| 2026-06-14 06:42 | `X-Vampire-Strategy` override accepted unvalidated, coerced to round_robin, yet trace header reports the requested strategy — audit trail lies | High | api-correctness | Open | [0642-strategy-override-unvalidated-trace-header-lies.md](./2026-06-14_0642-strategy-override-unvalidated-trace-header-lies.md) |
| 2026-06-14 06:33 | `discover_nodes` probes LAN-scan candidates sequentially → multi-minute hang; malformed subnet crashes with bare 500 | High | performance | Open | [0633-discover-sequential-lan-scan-blocks.md](./2026-06-14_0633-discover-sequential-lan-scan-blocks.md) |
| 2026-06-14 06:29 | `# type: ignore[union-attr]` masks a TOCTOU None-deref in the hot routing path — node deregistered mid-request crashes with bare 500 | High | type-safety | Open | [0629-route-node-deref-500-race.md](./2026-06-14_0629-route-node-deref-500-race.md) |
| 2026-06-14 06:12 | A fresh `httpx.AsyncClient` is built/torn down per proxied request, defeating connection pooling | High | performance | Open | [0612-per-request-httpx-client-no-pooling.md](./2026-06-14_0612-per-request-httpx-client-no-pooling.md) |
| 2026-06-14 06:08 | `/v1/models` returns HTTP 500 when a virtual model id collides with a physical model id | High | error-handling | Open | [0608-models-id-collision-500.md](./2026-06-14_0608-models-id-collision-500.md) |
| 2026-06-14 06:02 | `refresh_node` unconditionally re-inserts, silently resurrecting a concurrently-deregistered node | High | concurrency | Open | [0602-refresh-node-resurrects-deleted-nodes.md](./2026-06-14_0602-refresh-node-resurrects-deleted-nodes.md) |
| 2026-06-14 05:48 | `auth_token` is a silently-ignored security control — no route enforces authentication | High | security | Open | [0548-auth-token-never-enforced.md](./2026-06-14_0548-auth-token-never-enforced.md) |
