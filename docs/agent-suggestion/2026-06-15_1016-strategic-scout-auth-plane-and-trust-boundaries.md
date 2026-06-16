# Strategic Scout Report — Auth-Plane Drift & Trust Boundaries

**Run:** 2026-06-15 10:16 UTC · Strategic Scout (high-level audit)
**Scope:** `src/vampire/` — `cluster.py`, `proxy.py`, `router.py`, `auth.py`, `api/control.py`, `api/openai_compat.py`, `app.py`, `api/_auth.py`, `registry.py`
**Purpose:** Identify strategic *boundaries* (the hints) where defects are most likely to hide — NOT line-by-line bugs. The Suggestion Worker should deep-dive these areas to extract concrete, evidence-driven defects.

---

## Survey Context

- `HEAD = 1c720e3`; working tree carries two **already-open** suggestions:
  - `2026-06-15_0930-refresh-node-clobbers-live-active-requests-counter.md` (concurrency)
  - `2026-06-15_0934-ssrf-dns-hostname-bypass-and-rebinding.md` (security)
- Backlog: 26 suggestions, 24 taken, 2 open. The cheap/obvious findings (per-request client, type-ignore deref, models 500s, sequential scan, timing side-channel, strategy-override lies) are **already mined**. This report deliberately targets *uncovered architectural seams*, not the picked-over ones.
- **Churn hotspots (last 30 commits):** `proxy.py` (4), `cluster.py` (4), `router.py` (2), `api/control.py` (2). These files are where the design is still moving — and where the next regression will land.

---

## Areas of Interest

### AOI-1 — Auth-plane drift: two independent bearer implementations, double-wrapped control router *(architecture / security · HIGH)*

The single most important strategic boundary in the repo right now. There are **two separate, divergent auth implementations** guarding the same gateway:

| | `vampire/auth.py :: require_auth` | `vampire/api/_auth.py :: require_control_auth` |
|---|---|---|
| Mechanism | manual `Authorization` header parse + `hmac.compare_digest` | FastAPI `HTTPBearer(auto_error=False)` + `hmac.compare_digest` |
| Failure type | raises `AuthError` → custom handler | raises `HTTPException(401)` |
| Error envelope | `{"error":{"type":"vampire_auth_error","code":"missing_or_invalid_token"}}` (OpenAI-style) | `{"detail":"missing or invalid bearer token"}` (FastAPI default) |

In `app.py` the **control router is wrapped by BOTH**:
```python
app.include_router(control.router, dependencies=[Depends(require_auth)])   # app-level
# ...and control.router itself already declares:
APIRouter(prefix="/vampire/v1", dependencies=[Depends(require_control_auth)])
```
**Why this is a boundary worth a deep-dive:**
- The control plane runs **two** auth checks per request. FastAPI evaluates `include_router` dependencies before the router's own, so `require_auth` (OpenAI envelope) wins and `require_control_auth` becomes **dead/redundant code that nonetheless still runs**. A worker should confirm exact ordering and decide which implementation is canonical.
- The `/vampire/v1/*` 401 contract is therefore **non-deterministic across refactors** — delete one wrapper and the error envelope silently changes shape, breaking any client that matched on `error.code`.
- Two `hmac.compare_digest` call sites against `get_settings().auth_token` means any future hardening (token rotation, scopes, per-plane tokens) must be applied in two places or drift. This is exactly the seam where the *previous* "auth_token never enforced" bug lived (see `2026-06-14_0548`); the fix introduced redundancy rather than consolidation.

**Hint for worker:** Decide on ONE auth dependency. The data plane (`/v1/*`) and control plane (`/vampire/v1/*`) arguably need *different* trust levels (a shared inference token vs. an owner/admin token) — today they share the *same* `auth_token`, which conflates "may I call the model" with "may I register/delete nodes." That conflation is the real defect.

---

### AOI-2 — Trust is defined but not enforced on the default routing path *(security · HIGH)*

`discover_nodes` correctly registers new nodes as `trusted=False` (the recently-fixed auto-trust bug). But the **routing path does not honor that flag unless the caller explicitly opts into `trusted_only`:**

- `Router.default_policy` (`router.py:82`) enumerates **every** `node.status == "online"` node — trusted or not.
- `Router.select` only filters on trust when `strategy == "trusted_only"` (`router.py:51`). The default strategy is `round_robin`.
- `_route_or_proxy` builds the default policy with `strategy="round_robin"` for `vampire:auto`.

**Net effect:** a `vampire:auto` request will happily fan out to an **untrusted, auto-discovered LAN node**, forwarding the prompt body to it. Trust is computed, stored, surfaced in the API — and then ignored by the one code path that matters. This is a classic "control exists but isn't on the enforcement path" defect, structurally identical to the original `auth_token` dead-control bug.

**Hint for worker:** Determine whether `trusted` should be a default *filter* (untrusted nodes excluded unless explicitly opted-in) vs. opt-in. Cross-check against `DESIGN-API.md §13/§24` for the intended trust semantics. Look for the asymmetry: discovery is paranoid, routing is permissive.

---

### AOI-3 — SSRF: entry-time validation vs. use-time trust (the gap the open suggestion only half-covers) *(security · HIGH)*

There is an **open** suggestion on `is_allowed_target_url` waving through DNS hostnames (`2026-06-15_0934`). The strategic boundary is broader than that one function:

- `is_allowed_target_url` is checked at **ingress** (`POST/PATCH /nodes`, `discover`) — but `refresh_node` (`cluster.py:193`) and `proxy_request_with_body` (`proxy.py:135`) consume `node.lmstudio_base_url` **with no re-validation**. Any path that mutates a node's URL *after* registration, or any registry entry seeded by a code path that skips the guard, becomes an unguarded SSRF sink.
- `is_allowed_target_url` returns `True` for **any non-IP hostname** (`cluster.py:81-82`). Combined with use-time trust of the stored URL, this is a **TOCTOU/DNS-rebinding seam**: validate `evil.example.com` → A-record resolves public/metadata at fetch time.
- `_url_with_host` / `_candidate_urls` rewrite hosts for LAN scan; a worker should confirm the rewritten URLs are *also* re-validated before `refresh_node` probes them.

**Hint for worker:** The defect class is "validate at the boundary, trust forever after." Map every producer of `node.lmstudio_base_url` and every consumer, and find the consumer that trusts an unvalidated producer. Don't just re-file the DNS-literal issue.

---

### AOI-4 — Registry is a lock-free shared-mutable-state hot path *(concurrency · HIGH)*

`NodeRegistry` (`registry.py`) is a process-wide singleton backed by a plain `dict` with **no synchronization**, mutated concurrently from:
- `mark_busy` / `mark_idle` — read-modify-write of `active_requests` via `model_copy` (lines 40-54).
- `refresh_node` — full-node replace via `registry.add(updated)` (`cluster.py:227`).
- control CRUD — `add` / `update` / `remove`.
- `refresh_registered_nodes` — concurrent `asyncio.gather` over all nodes.

The **open** `refresh-node-clobbers-active-requests` suggestion is one instance of a *whole class*: any `model_copy(update={...})` that snapshots a node, mutates one field, and writes the whole object back will **lose concurrent updates to every other field**. `mark_idle` racing `refresh_node` racing `patch_node` is the same lost-update pattern three ways. Single-threaded asyncio doesn't save you here because every `await` is a yield point and these are all `async` handlers interleaving on one event loop.

**Hint for worker:** Treat the registry as the concurrency epicenter. The strategic question is architectural: should counters (`active_requests`, `queue_depth`, `request_count`) live as **separate atomic fields / a lock-guarded mutator**, decoupled from the whole-object replace that `refresh_node` does? The current "snapshot → copy → write whole object" pattern is fundamentally incompatible with concurrent partial updates.

---

### AOI-5 — Complexity hotspot: `cluster.py` refresh cache & local-access dedup *(error-handling / maintainability · MEDIUM-HIGH)*

`cluster.py` is the highest-churn logic file and concentrates two intricate, interacting mechanisms:

1. **The TTL/single-flight refresh cache** (`_refresh_cache`, `_refresh_lock`, `invalidate_refresh_cache`, `_REFRESH_TTL_SECONDS`). It is invalidated from *seven* call sites in `control.py`. Module-level mutable globals + a lock + a TTL + manual invalidation scattered across handlers is a classic stale-read / missed-invalidation breeding ground. A worker should check: does every node-mutating path invalidate? (e.g., does `mark_busy`/`mark_idle` — which changes node state — leave a stale cached snapshot that `least_busy` then reads?)
2. **The local-access dedup graph** (`_local_access_key/_rank/_preferred/_dedupe`, ~60 lines). Dense host-equivalence logic with multiple `urlparse` round-trips and ranking tiebreaks — high cyclomatic density, easy to get an edge case (IPv6 bracketing, default-port collisions, mixed scheme) wrong.

**Hint for worker:** The cache and the routing scorers (`least_busy`, `least_latency`) form an implicit contract — scorers read node fields that the cache may have frozen. Look for the **stale-snapshot-feeds-routing-decision** seam: `refresh_registered_nodes` returns the cached list, but `Router` reads live `registry.get()`; confirm whether these two views can disagree and mis-route.

---

## Recommended worker order
1. **AOI-1** (auth-plane consolidation) — highest blast radius, touches the security contract of both planes.
2. **AOI-2** (trust not enforced in routing) — high-value, self-contained, mirrors a known defect class.
3. **AOI-4** (registry lost-update class) — generalizes the existing open suggestion into a structural fix.
4. **AOI-3** (validate-then-trust SSRF seam) — extends, don't duplicate, the open DNS suggestion.
5. **AOI-5** (cache/dedup hotspot) — maintainability + stale-read risk.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · audit run over `src/vampire/` · output ~5.4K tok · est. cost ~$0.36. Derived from `agent.log` run `cron_cf99802f8811` (7 API calls, cumulative in≈67K with 55–95% cache hit, out≈4.1K + this write).
