# Agent Suggestions Index

Staff-engineer audit suggestions for the lmstudio-vampire gateway, one per run.

_Generated: 2026-06-14 09:05 UTC_

18 total · 10 open · 8 taken · 0 declined

| Date | Title | Severity | Category | Status | File |
|------|-------|----------|----------|--------|------|
| 2026-06-14 09:02 | Discovery auto-trusts every reachable node by default (`trusted = not request.trusted_only`) | High | security | Open | [link](2026-06-14_0902-discover-auto-trusts-every-node-by-default.md) |
| 2026-06-14 08:42 | NodeRegistry.update bypasses Pydantic validation, corrupting nested NodeCapabilities on PATCH | High | type-safety | Open | [link](2026-06-14_0842-node-update-model-copy-corrupts-capabilities.md) |
| 2026-06-14 08:42 | `/v1/models` cards omit OpenAI-required `created` field | High | api-correctness | Open | [link](2026-06-14_0842-models-listing-omits-required-created-field.md) |
| 2026-06-14 08:41 | `/v1/models` triggers uncoalesced full-cluster refresh — no TTL/single-flight/cap | High | performance | Open | [link](2026-06-14_0841-models-refresh-no-cache-no-singleflight-stampede.md) |
| 2026-06-14 08:28 | SSRF: `base_urls`/`lmstudio_base_url` probed with no scheme or host validation | High | security | Open | [link](2026-06-14_0828-ssrf-unvalidated-base-urls-bypass-lan-scan-guard.md) |
| 2026-06-14 08:28 | Blocking `.env` disk stat on the event loop via per-request `get_settings()` | High | concurrency | Open | [link](2026-06-14_0828-get-settings-blocking-env-stat-on-event-loop.md) |
| 2026-06-14 08:27 | Mid-stream upstream failure silently truncates SSE body with no error frame | High | error-handling | Open | [link](2026-06-14_0827-streaming-proxy-midstream-failure-silently-truncates.md) |
| 2026-06-14 08:26 | `Router._cursors` unbounded `defaultdict` keyed by client-controlled model strings | High | concurrency | Open | [link](2026-06-14_0826-router-cursor-unbounded-growth.md) |
| 2026-06-14 08:08 | Proxy forwards gateway bearer token to untrusted upstreams | High | security | Open | [link](2026-06-14_0808-proxy-forwards-gateway-bearer-token-to-untrusted-upstreams.md) |
| 2026-06-14 08:02 | `discover_nodes` permanently registers every scanned candidate IP (phantom nodes) | High | concurrency | Open | [link](2026-06-14_0802-discover-offline-phantom-node-pollution.md) |
| 2026-06-14 07:01 | Control-API bearer check uses non-constant-time comparison (timing side channel) | High | security | Taken | [link](2026-06-14_0701-control-auth-timing-side-channel.md) |
| 2026-06-14 06:42 | `X-Vampire-Strategy` override accepted unvalidated; trace header lies | High | api-correctness | Taken | [link](2026-06-14_0642-strategy-override-unvalidated-trace-header-lies.md) |
| 2026-06-14 06:33 | `discover_nodes` probes LAN-scan candidates sequentially; malformed subnet → 500 | High | performance | Taken | [link](2026-06-14_0633-discover-sequential-lan-scan-blocks.md) |
| 2026-06-14 06:29 | `# type: ignore` masks TOCTOU None-deref in routing path → bare 500 | High | type-safety | Taken | [link](2026-06-14_0629-route-node-deref-500-race.md) |
| 2026-06-14 06:12 | Fresh `httpx.AsyncClient` per request defeats connection pooling | High | performance | Taken | [link](2026-06-14_0612-per-request-httpx-client-no-pooling.md) |
| 2026-06-14 06:08 | `/v1/models` returns 500 on virtual/physical model id collision | High | error-handling | Taken | [link](2026-06-14_0608-models-id-collision-500.md) |
| 2026-06-14 06:02 | `refresh_node` resurrects concurrently-deleted nodes (zombie-node race) | High | concurrency | Taken | [link](2026-06-14_0602-refresh-node-resurrects-deleted-nodes.md) |
| 2026-06-14 05:48 | `auth_token` is a silently-ignored security control (dead code) | High | security | Taken | [link](2026-06-14_0548-auth-token-never-enforced.md) |
