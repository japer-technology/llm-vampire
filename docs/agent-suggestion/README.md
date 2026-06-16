# Agent Suggestions Index

Staff-engineer audit suggestions for the lmstudio-vampire gateway, one per run.

_Generated: 2026-06-16 12:10 UTC_

29 total · 5 open · 24 taken · 0 declined

| Date | Title | Severity | Category | Status | File |
|------|-------|----------|----------|--------|------|
| 2026-06-16 12:10 | `discover_nodes._probe` suffers from a "resurrection" race condition: unconditional `registry.add` after `await refresh_node` allows a deleted node to be re-added to the registry. | High | concurrency | Open | [link](2026-06-16_1210-discovery-probe-resurrection-race-unconditional-registry-add.md) |
| 2026-06-15 12:00 | `PATCH /vampire/v1/nodes/{id}` skips health refresh for metadata updates when node is in maintenance mode | Medium | api-correctness | Open | [link](2026-06-15_1200-patch-node-skips-health-refresh-for-unavailable-nodes.md) |
| 2026-06-15 11:00 | `PATCH /vampire/v1/nodes/{id}` silently fails to update metadata when node is in maintenance/draining status | Medium | api-correctness | Open | [link](2026-06-15_1100-silent-patch-failure-on-maintenance-nodes.md) |
| 2026-06-15 09:34 | `is_allowed_target_url` waves through every DNS hostname — SSRF guard only blocks IP literals (metadata-by-name, internal services, DNS rebinding) | High | security | Open | [link](2026-06-15_0934-ssrf-dns-hostname-bypass-and-rebinding.md) |
| 2026-06-15 09:30 | `refresh_node` clobbers the live `active_requests` counter — lost-update race that blinds `least_busy` routing | High | concurrency | Open | [link](2026-06-15_0930-refresh-node-clobbers-live-active-requests-counter.md) |
| 2026-06-14 20:04 | Transparent proxy collapses repeated query parameters (`dict(request.query_params)` drops all but last) | High | api-correctness | Taken | [link](2026-06-14_2004-proxy-dict-query-params-drops-repeated-keys.md) |
| 2026-06-14 19:01 | `model_affinity` routing pins 100% of traffic to the first replica — no load distribution across nodes hosting the same model | High | api-correctness | Taken | [link](2026-06-14_1901-model-affinity-pins-all-traffic-first-replica.md) |
| 2026-06-14 17:20 | `PATCH /vampire/v1/nodes/{id}` silently un-drains a node on any unrelated field update | High | api-correctness | Taken | [link](2026-06-14_1720-patch-node-undrains-on-unrelated-field-update.md) |
| 2026-06-14 10:00 | `refresh_node` lets `httpx.InvalidURL` escape its `except` — one malformed node URL 500s every cluster endpoint | High | error-handling | Taken | [link](2026-06-14_1000-refresh-node-invalid-url-uncaught-500.md) |
| 2026-06-14 09:40 | `least_busy` routing is a no-op in production — proxy never tracks in-flight requests | High | api-correctness | Taken | [link](2026-06-14_0940-least-busy-no-inflight-tracking-degenerates.md) |
| 2026-06-14 09:13 | Prompt playground output not announced to assistive tech (ARIA live region) | Medium | ux | Taken | [link](2026-06-14_0913-html-ux-playground-live-region.md) |
| 2026-06-14 09:02 | Discovery auto-trusts every reachable node by default (`trusted = not request.trusted_only`) | High | security | Taken | [link](2026-06-14_0902-discover-auto-trusts-every-node-by-default.md) |
| 2026-06-14 08:42 | NodeRegistry.update bypasses Pydantic validation, corrupting nested NodeCapabilities on PATCH | High | type-safety | Taken | [link](2026-06-14_0842-node-update-model-copy-corrupts-capabilities.md) |
| 2026-06-14 08:42 | `/v1/models` cards omit OpenAI-required `created` field | High | api-correctness | Taken | [link](2026-06-14_0842-models-listing-omits-required-created-field.md) |
| 2026-06-14 08:41 | `/v1/models` triggers uncoalesced full-cluster refresh — no TTL/single-flight/cap | High | performance | Taken | [link](2026-06-14_0841-models-refresh-no-cache-no-singleflight-stampede.md) |
| 2026-06-14 08:28 | SSRF: `base_urls`/`lmstudio_base_url` probed with no scheme or host validation | High | security | Taken | [link](2026-06-14_0828-ssrf-unvalidated-base-urls-bypass-lan-scan-guard.md) |
| 2026-06-14 08:28 | Blocking `.env` disk stat on the event loop via per-request `get_settings()` | High | concurrency | Taken | [link](2026-06-14_0828-get-settings-blocking-env-stat-on-event-loop.md) |
| 2026-06-14 08:27 | Mid-stream upstream failure silently truncates SSE body with no error frame | High | error-handling | Taken | [link](2026-06-14_0827-streaming-proxy-midstream-failure-silently-truncates.md) |
| 2026-06-14 08:26 | `Router._cursors` unbounded `defaultdict` keyed by client-controlled model strings | High | concurrency | Taken | [link](2026-06-14_0826-router-cursor-unbounded-growth.md) |
| 2026-06-14 08:08 | Proxy forwards gateway bearer token to untrusted upstreams | High | security | Taken | [link](2026-06-14_0808-proxy-forwards-gateway-bearer-token-to-untrusted-upstreams.md) |
| 2026-06-14 08:02 | `discover_nodes` permanently registers every scanned candidate IP (phantom nodes) | High | concurrency | Taken | [link](2026-06-14_0802-discover-offline-phantom-node-pollution.md) |
| 2026-06-14 07:01 | Control-API bearer check uses non-constant-time comparison (timing side channel) | High | security | Taken | [link](2026-06-14_0701-control-auth-timing-side-channel.md) |
| 2026-06-14 06:42 | `X-Vampire-Strategy` override accepted unvalidated; trace header lies | High | api-correctness | Taken | [link](2026-06-14_0642-strategy-override-unvalidated-trace-header-lies.md) |
| 2026-06-14 06:33 | `discover_nodes` probes LAN-scan candidates sequentially; malformed subnet → 500 | High | performance | Taken | [link](2026-06-14_0633-discover-sequential-lan-scan-blocks.md) |
| 2026-06-14 06:29 | `# type: ignore` masks TOCTOU None-deref in routing path → bare 500 | High | type-safety | Taken | [link](2026-06-14_0629-route-node-deref-500-race.md) |
| 2026-06-14 06:12 | Fresh `httpx.AsyncClient` per request defeats connection pooling | High | performance | Taken | [link](2026-06-14_0612-per-request-httpx-client-no-pooling.md) |
| 2026-06-14 06:08 | `/v1/models` returns 500 on virtual/physical model id collision | High | error-handling | Taken | [link](2026-06-14_0608-models-id-collision-500.md) |
| 2026-06-14 05:48 | `auth_token` is a silently-ignored security control (dead code) | High | security | Taken | [link](2026-06-14_0548-auth-token-never-enforced.md) |
