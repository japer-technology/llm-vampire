# Possible Commands — the next 100 `vampire` commands

This document ranks the **next 100 CLI commands** to implement or expand for
`lmstudio-vampire`, in **descending order of importance**. It is derived from a
close reading of [POSSIBILITIES.md](POSSIBILITIES.md) (numbered items cited as
`P#`) and the operator manual in [`docs/manual/`](docs/manual/) (the current CLI
surface is [`05-cli-reference.md`](docs/manual/05-cli-reference.md); planned
endpoints are in [`09-api-reference.md`](docs/manual/09-api-reference.md) and
[DESIGN-API.md](DESIGN-API.md)).

## How this list is ordered

Importance is judged by the project's own stated priorities. POSSIBILITIES.md
closes by naming the highest-value possibilities: **single endpoint,
auto-discovery, load balancing, failover, model specialization, parallel jobs,
ensemble/fusion, multi-stage pipelines, local RAG, and a secure/verifiable
inference fabric**. The [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) phases
(Phase 5 coalescing/cache, Phase 6 policy/tokens, Phase 7 fusion/pipelines)
provide the engineering sequence. Commands that complete or harden the existing
MVP surface rank above net-new capability areas.

Each row records:

- **Command** — proposed CLI invocation.
- **Type** — `NEW` (does not exist) or `EXPAND` (extends a shipped command from
  [`05-cli-reference.md`](docs/manual/05-cli-reference.md)).
- **Why / maps to** — the POSSIBILITIES.md items (`P#`) and/or manual sections
  the command serves.

The current shipped command set is: `serve`, `status`, `discover`, `share`,
`nodes {list,add,get,update,drain,delete}`, `models`, `metrics`,
`route {list,add,get,delete}`, `dashboard`/`ui`. Everything below is in addition
to those.

---

## Tier 1 — Finish and harden the existing MVP surface (1–18)

The fastest value: close obvious gaps in the commands that already exist and make
the gateway usable end-to-end from the terminal.

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 1 | `vampire chat MODEL [--message TEXT] [--system TEXT] [--stream] [--file PATH]` | NEW | One-shot chat completion from the CLI so operators can exercise the gateway without a separate client. P21, P31, P57; manual §9 `/v1/chat/completions`. |
| 2 | `vampire route update ROUTE_ID [--target ...] [--strategy ...] [--fallback ...] [--add-target ...] [--remove-target ...]` | EXPAND | `route` has `add`/`get`/`delete` but no in-place patch; editing a policy today means replacing it. Manual §5 route map; P221, P456. |
| 3 | `vampire route test VIRTUAL_MODEL [--show-candidates] [--header ...]` | NEW | Dry-run a routing decision and explain which node/model would be picked and why. P105, P221, P534 (shadow), P472. |
| 4 | `vampire health [--node NODE_ID] [--watch]` | NEW | Run/refresh health checks and print a per-node health score. P4, P309, P310; manual §6. |
| 5 | `vampire nodes ping NODE_ID [--timeout-ms MS]` | EXPAND | Probe a single registered node's `/v1/models` and report reachability/latency. P4, P11, P233. |
| 6 | `vampire embed MODEL --input TEXT [--input TEXT]... [--file PATH]` | NEW | Generate embeddings from the CLI. P24, P42; manual §9 `/v1/embeddings`. |
| 7 | `vampire complete MODEL --prompt TEXT [--stream]` | NEW | One-shot legacy text completion. P22; manual §9 `/v1/completions`. |
| 8 | `vampire logs [--node NODE_ID] [--follow] [--since DUR] [--level LEVEL]` | NEW | Tail gateway and per-node request logs. P219, P215, P258, P266; manual §10 troubleshooting. |
| 9 | `vampire config show` | NEW | Print effective settings (host, port, downstream URL, `VAMPIRE_*`). Manual §4 configuration. |
| 10 | `vampire config set KEY VALUE` / `vampire config get KEY` | NEW | Read/write persisted configuration without editing `.env` by hand. Manual §4; P245 (configuration sync). |
| 11 | `vampire models --node NODE_ID [--refresh] [--json]` | EXPAND | Filter the aggregated inventory by node and force a re-interrogation. P10, P14, P235. |
| 12 | `vampire nodes refresh [NODE_ID]` | NEW | Force model-list/capability re-sync for one or all nodes. P235, P236, P245. |
| 13 | `vampire status --watch [--interval S]` | EXPAND | Live-refresh the status envelope for at-a-glance monitoring. P213, manual §5 status. |
| 14 | `vampire share status` | EXPAND | Read-only view of current owner share mode (`GET /vampire/v1/share`) as an explicit subcommand. P270; manual §8. |
| 15 | `vampire route get ROUTE_ID --explain` | EXPAND | Show a route plus a human-readable description of its strategy and fallbacks. P221, §30 routing strategies. |
| 16 | `vampire nodes add --from-discover` | EXPAND | Register nodes straight from the last `discover` result instead of re-typing URLs. P3, P231, P508. |
| 17 | `vampire version --full` | EXPAND | Report CLI, gateway, and per-node LM Studio versions together. P244 (version tracking). |
| 18 | `vampire doctor` | NEW | Self-diagnostic: gateway reachable, downstream reachable, nodes healthy, common misconfig hints. Manual §10 troubleshooting; P307. |

## Tier 2 — Routing, reliability, and failover (19–34)

Core differentiated value: load balancing, failover, and policy-aware routing.

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 19 | `vampire route strategy list` | NEW | Enumerate available routing strategies and their parameters. §30 (P517–P536); manual §7. |
| 20 | `vampire route set-default VIRTUAL_MODEL` | NEW | Choose the default virtual model used when a client asks for `vampire:auto`. P13, P105, P435. |
| 21 | `vampire failover show` | NEW | Display the active fallback chain across routes. P6, P291, P300–P302, P536. |
| 22 | `vampire failover test VIRTUAL_MODEL` | NEW | Simulate a node failure and confirm the request would re-route. P291, P298, P299. |
| 23 | `vampire nodes priority NODE_ID WEIGHT` | NEW | Set node priority weighting for weighted strategies. P240, P518. |
| 24 | `vampire nodes maintenance NODE_ID [on\|off]` | NEW | Maintenance mode distinct from `drain` (no new work, finishes in-flight). P241, P242. |
| 25 | `vampire nodes quarantine NODE_ID [--reason TEXT]` | NEW | Quarantine/blacklist a flapping node after repeated failures. P243, P308. |
| 26 | `vampire route canary ROUTE_ID --target node:model --percent N` | NEW | Canary-route a fraction of traffic to a new model. P535. |
| 27 | `vampire route shadow ROUTE_ID --target node:model` | NEW | Shadow-route (mirror) traffic for evaluation without affecting clients. P534. |
| 28 | `vampire queue status [--node NODE_ID]` | NEW | Show queue depth and in-flight counts. P8, P214, P238, P522. |
| 29 | `vampire queue drain [--node NODE_ID]` | NEW | Stop accepting new queued work and let queues empty. P294, P295, P296. |
| 30 | `vampire retry policy show` / `vampire retry policy set ...` | NEW | Inspect/set retry, timeout, and circuit-breaker thresholds. P7, P292, P293, P307. |
| 31 | `vampire route constraints set ROUTE_ID --max-context N --min-vram GB ...` | EXPAND | Attach routing constraints (the `constraints` object already exists in the route body). P15, P313, P314, P529; manual §9 route body. |
| 32 | `vampire nodes drain --all` | EXPAND | Drain the whole cluster for a rolling restart. P222, P242. |
| 33 | `vampire route benchmark VIRTUAL_MODEL [--n N]` | NEW | Measure realized latency/throughput of a route's targets. P11, P12, P311, P520, P521. |
| 34 | `vampire jobs cancel JOB_ID` | NEW | Cancel a long-running or queued request. P564, P305 (resume), §32 edge cases. |

## Tier 3 — Discovery and node lifecycle (35–46)

Auto-discovery is named a top-tier capability; the MVP only ships static + dev
subnet scan.

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 35 | `vampire discover --method mdns` | EXPAND | Add mDNS/Bonjour discovery alongside `static`/`lan_scan`. P2, P503, P510; IMPLEMENTATION-PLAN Phase 2. |
| 36 | `vampire discover --watch` | EXPAND | Continuously announce/listen for nodes joining or leaving. P233, P511, P512. |
| 37 | `vampire discover --method broadcast` / `--method multicast` | EXPAND | UDP broadcast/multicast discovery. P504, P505. |
| 38 | `vampire pair NODE_URL [--qr]` | NEW | QR-code / token node pairing with a trust handshake. P508, P513, P514. |
| 39 | `vampire nodes import FILE` / `vampire nodes export FILE` | NEW | Bulk node registration from a static config file. P3, P501, P245. |
| 40 | `vampire nodes prune [--stale] [--duplicates]` | NEW | Remove stale or duplicate nodes. P249, P250. |
| 41 | `vampire nodes tag NODE_ID --add TAG --remove TAG` | EXPAND | Manage capability/role tags as a first-class subcommand. P234, P523, P524. |
| 42 | `vampire discover --allowlist FILE` | EXPAND | Limit discovery to an allowlist or subnet. P515, P516, P248. |
| 43 | `vampire nodes wake NODE_ID` | NEW | Wake-on-LAN an idle/sleeping node. P346, P345. |
| 44 | `vampire nodes capabilities NODE_ID` | NEW | Show advertised hardware/model capabilities. P234, P237, P246. |
| 45 | `vampire topology` | NEW | Print LAN topology / subnet awareness (wired vs Wi-Fi, local subnet). P246, P247, P248. |
| 46 | `vampire nodes verify NODE_ID` | NEW | Verify node identity against the trusted-node registry. P451, P452, P453. |

## Tier 4 — Observability and dashboards (47–58)

The browser control plane (§14) has many panels; the CLI should expose the same
read surfaces for scripting and headless ops.

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 47 | `vampire metrics --node NODE_ID [--watch]` | EXPAND | Per-node drill-down of the metrics snapshot. P220, P237, P219. |
| 48 | `vampire history [--limit N] [--node NODE_ID]` | NEW | Request history log. P215, P258. |
| 49 | `vampire stats models` | NEW | Per-model statistics (calls, tokens, latency). P220, P312. |
| 50 | `vampire stats tokens [--by node\|model\|user]` | NEW | Token throughput dashboard data. P12, P216, P330. |
| 51 | `vampire errors [--since DUR]` | NEW | Error dashboard / taxonomy view. P217, P307, P363. |
| 52 | `vampire latency [--node NODE_ID]` | NEW | Latency charts data (p50/p95). P11, P218, P520. |
| 53 | `vampire bench run [--model M] [--prompt-size N]` | NEW | Token/sec benchmark, producing a per-model table. P311, P312, P427, P440. |
| 54 | `vampire bench compare --models a,b,c --prompt FILE` | NEW | Compare models on identical prompts. P466, P467, P475. |
| 55 | `vampire watch [--interval S]` | NEW | Combined live monitor (nodes + load + queues + errors). P213, P214, P364. |
| 56 | `vampire export metrics --format json\|csv` | NEW | Export metrics/usage for offline analysis. P333, P364. |
| 57 | `vampire power report` | NEW | Electricity/compute cost estimate per node/model. P331–P335. |
| 58 | `vampire leaderboard` | NEW | Per-task model ranking / leaderboard. P359, P360, P475. |

## Tier 5 — Security, policy, and access control (Phase 6) (59–72)

IMPLEMENTATION-PLAN Phase 6 (tokens, CORS, allowlists, trust, logging) and
POSSIBILITIES §16–§17.

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 59 | `vampire token create [--name N] [--scope ...] [--ttl DUR]` | NEW | Issue a local API key for a client. P230, P251, P252. |
| 60 | `vampire token list` / `vampire token revoke TOKEN_ID` | NEW | Manage issued tokens. P230, P251, P262. |
| 61 | `vampire auth enable [--require-token]` | NEW | Turn on bearer-token auth on the gateway. P251, P259; Phase 6. |
| 62 | `vampire policy show` / `vampire policy set ...` | NEW | View/set realm and routing policy. P253, P456, P532. |
| 63 | `vampire allowlist ip --add CIDR --remove CIDR` | NEW | IP allowlist for clients. P254, P273. |
| 64 | `vampire allowlist model --user USER --add MODEL` | NEW | Restrict models per user. P255, P256. |
| 65 | `vampire quota set --user USER --tokens N` / `--requests N` | NEW | Per-user/application quotas and rate limits. P262–P265, P342. |
| 66 | `vampire audit log [--since DUR]` | NEW | View tamper-evident audit logs. P258, P459. |
| 67 | `vampire cors set --origin URL [--origin URL]...` | NEW | Manage CORS / browser-origin allowlist. P272, P273. |
| 68 | `vampire redact rules ...` | NEW | Configure secret/PII redaction before routing. P267, P268. |
| 69 | `vampire privacy local-only [on\|off]` | NEW | Enforce no-cloud / LAN-only mode. P274, P275, P277. |
| 70 | `vampire session private [on\|off]` | NEW | Toggle ephemeral / no-log session mode. P270, P289, P290. |
| 71 | `vampire route privacy ROUTE_ID --trusted-only` | EXPAND | Privacy-policy-aware routing (confidential tasks only to trusted nodes). P286, P287, P532. |
| 72 | `vampire tls enable --cert PATH --key PATH` | NEW | TLS / mTLS for LAN traffic. P260, P261. |

## Tier 6 — Performance: coalescing and caching (Phase 5) (73–80)

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 73 | `vampire cache status` | NEW | Show cache hit-rate and size. P155, P157, P319. |
| 74 | `vampire cache clear [--scope answers\|embeddings\|tools]` | NEW | Invalidate caches. P155–P160. |
| 75 | `vampire coalesce status` | NEW | Show in-flight request deduplication. P306, P318; Phase 5. |
| 76 | `vampire warmup MODEL [--node NODE_ID]` | NEW | Pre-warm / keep-hot a model to avoid cold starts. P51, P52, P53, P224, P321. |
| 77 | `vampire models evict MODEL [--node NODE_ID]` | NEW | Smart eviction of inactive models. P322, P345. |
| 78 | `vampire prefetch MODEL` | NEW | Predictive/pre-load a likely-next model. P54, P323. |
| 79 | `vampire schedule set --batch-window "00:00-06:00"` | NEW | Schedule heavy/batch jobs off-hours. P338, P339, P347, P348. |
| 80 | `vampire route cost-aware [on\|off]` | NEW | Enable cost/power-aware routing. P327, P328, P330, P530. |

## Tier 7 — Fusion and ensemble (Phase 7) (81–88)

`POST /vampire/v1/fusion` is a designed-but-unbuilt endpoint (DESIGN-API §11).

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 81 | `vampire fusion run --prompt FILE --models a,b,c [--mode race\|fusion\|vote]` | NEW | Fan-out a prompt and fuse responses; the headline ensemble feature. P76–P95, P537–P552; DESIGN-API §11. |
| 82 | `vampire race --prompt FILE --models a,b,c` | NEW | Race nodes and return the fastest answer. P58, P537. |
| 83 | `vampire vote --prompt FILE --models a,b,c [--ranked]` | NEW | Majority / ranked voting across models. P79, P80, P539, P541. |
| 84 | `vampire judge --prompt FILE --candidates FILE --judge MODEL` | NEW | Use a judge model to select/synthesize the best answer. P82, P84, P540. |
| 85 | `vampire ensemble create NAME --members a,b,c --strategy ...` | NEW | Define a reusable named ensemble. P76, P436. |
| 86 | `vampire best-of N --prompt FILE --model M` | NEW | Best-of-N generation then rank. P86, P87, P93. |
| 87 | `vampire debate --prompt FILE --models a,b [--rounds N]` | NEW | Adversarial/debate mode between models. P90, P91, P370. |
| 88 | `vampire verify --answer FILE --verifier MODEL` | NEW | Cross-model verification / hallucination check. P350, P353, P377, P387. |

## Tier 8 — Pipelines, jobs, and traces (89–94)

DESIGN-API §17/§19 designs `pipelines`, `jobs`, and `traces` endpoints.

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 89 | `vampire pipeline run FILE [--input ...]` | NEW | Execute a multi-stage pipeline (planner→executor→critic→refiner). P96–P110; DESIGN-API §17. |
| 90 | `vampire pipeline list` / `vampire pipeline create FILE` | NEW | Manage stored pipeline definitions. P227, P441. |
| 91 | `vampire jobs list [--state running\|done\|failed]` | NEW | List async jobs. P123, P303, P305; `GET /vampire/v1/jobs`. |
| 92 | `vampire jobs get JOB_ID [--watch]` | NEW | Inspect/poll a job; resume interrupted long jobs. P304, P305. |
| 93 | `vampire trace get TRACE_ID` | NEW | Show the trace of contributing models/stages. P552, DESIGN-API §19. |
| 94 | `vampire batch run --input-dir DIR --model M` | NEW | Local batch processor over a folder of prompts/files. P35, P411, P412. |

## Tier 9 — Local RAG and knowledge (95–97)

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 95 | `vampire rag index DIR [--collection NAME]` | NEW | Build a local document index / embeddings across nodes. P129, P130, P229, P442. |
| 96 | `vampire rag query "..." [--collection NAME]` | NEW | Distributed vector search + answer with citations. P131, P135, P141, P207. |
| 97 | `vampire rag collections [list\|delete NAME]` | NEW | Manage per-machine/shared knowledge stores. P132, P133, P229. |

## Tier 10 — JAPER secure fabric and deployment (98–100)

| # | Command | Type | Why / maps to |
| --- | --- | --- | --- |
| 98 | `vampire sign verify TRACE_ID` | NEW | Verify signed inference results / response provenance (JAPER envelope). P449, P450, P458, P459; DESIGN-API §22. |
| 99 | `vampire trust score [--node NODE_ID]` | NEW | Trust scoring per node/model in the secure compute mesh. P464, P465. |
| 100 | `vampire daemon [start\|stop\|status]` | NEW | Run/manage the gateway as a headless background service (vs. foreground `serve`). P488, P489; §28 deployment patterns. |

---

## Sequencing notes

- **Build Tier 1 first.** Items 1–18 are mostly thin clients over endpoints that
  already exist or are trivial extensions, and they make the gateway fully usable
  from the terminal — the cheapest, highest-leverage work.
- **Tiers 2–4** turn Vampire from a proxy into an orchestrator (routing,
  discovery, observability) and align with the shipped Phase 2–4 surfaces.
- **Tiers 5–6** correspond to IMPLEMENTATION-PLAN **Phase 6** (policy/tokens) and
  **Phase 5** (coalescing/cache).
- **Tiers 7–8** correspond to **Phase 7** (fusion, pipelines, jobs, traces) and
  depend on the designed-but-unbuilt `/vampire/v1/{fusion,pipelines,jobs,traces}`
  endpoints.
- **Tiers 9–10** are the longer-horizon RAG and JAPER-secured-fabric bets named as
  top-tier possibilities but furthest from the current scaffold.

Each command should, per the manual's conventions
([`05-cli-reference.md`](docs/manual/05-cli-reference.md)), accept `--gateway URL`
when it calls the control API, print the JSON response (sorted keys), and use the
documented exit codes (`0` success, `1` gateway error/unreachable, `2` invalid
arguments).
