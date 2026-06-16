# Strategic Scout Report — Request-Lifecycle, Namespace & Config-Plane Drift

**Run:** 2026-06-15 18:18 UTC · Strategic Scout (high-level audit)
**HEAD:** `1c720e3` (working tree carries 4 open suggestions + modified README index)
**Scope:** `src/vampire/` — `proxy.py`, `cluster.py`, `router.py`, `auth.py`,
`registry.py`, `api/control.py`, `api/openai_compat.py`, `app.py` — cross-checked
against `DESIGN-API.md` §5, §13, §21.
**Purpose:** Identify strategic *boundaries* (the hints) where the next defect is
most likely to hide — NOT line-by-line bugs. A Suggestion Worker should deep-dive
these seams to extract concrete, evidence-driven defects.

---

## Survey Context

- **Churn (last 15 commits):** `cluster.py` (2), `api/control.py` (2),
  `router.py`, `registry.py`, `models.py`, `config.py`, `api/openai_compat.py`
  (1 each). The recent fixes cluster around node-status preservation
  (`d34bc9c`, `738357e`), malformed-URL handling (`b65a1f4`), and proxy query
  params (`e070a5e`, `b9b8219`). The mutation/lifecycle plane is still moving.
- **Backlog:** 28 suggestions, 24 taken, **4 open** — all four open items
  (`refresh-node clobbers active_requests`, `ssrf DNS hostname`, `patch silent
  fail`, `patch skips health refresh`) plus the prior Strategic Scout report
  (`2026-06-15_1016`, AOI-1…5: auth-plane, trust-in-routing, SSRF use-time,
  registry lost-update, cache/dedup hotspot) are **already on the board**.
- **This report deliberately targets seams the prior scout did NOT cover:**
  request-lifecycle counter accounting, the `vampire:` namespace boundary, the
  `/v1/models` dual-contract, the *untaken twin* of an already-fixed race, and
  the missing config/trust-taxonomy surface mandated by `DESIGN-API.md §21`.

---

## Areas of Interest

### AOI-A — In-flight counter accounting is coupled to background-task delivery, which streaming + client-disconnect can skip *(concurrency / lifecycle · HIGH)*

`_route_or_proxy` (`openai_compat.py:155-172`) acquires the in-flight slot with
`registry.mark_busy(target.node)` **synchronously**, but releases it only via
`response.background = _release_on_finish(...)` — a Starlette `BackgroundTask`
that fires *after the response is fully delivered*. The synchronous `except
BaseException: mark_idle` guard (line 168) only covers failures *before* the
StreamingResponse object is returned; once streaming begins, release depends
entirely on the background task running to completion.

**Why this is a boundary worth a deep-dive:**
- The hot path is `chat/completions` **with SSE streaming**. Starlette runs a
  response's `background` only after `stream_response` finishes sending. If the
  client disconnects mid-stream (extremely common with LLM streaming — user
  hits stop, browser tab closes, proxy timeout), the question is whether the
  `mark_idle` background task still fires or is cancelled with the send task.
- `proxy.py`'s `body_stream()` has its own `finally` that closes the *upstream*
  connection, but that `finally` lives in a **different** generator than the
  `_release_on_finish` task attached to the outer response — closing upstream
  does not decrement `active_requests`.
- **Net risk:** every disconnected stream leaks one `active_requests` count that
  never returns to zero. `least_busy` (`router.py:57-59`, scores on
  `active_requests`) then **permanently routes away** from any node that has
  served disconnected streams — the busiest-looking node is the one clients
  abandoned, not the one actually loaded. This is a slow-motion routing
  brownout, distinct from the *lost-update* race in the open
  `refresh-node-clobbers-active_requests` suggestion (that one is write/write;
  this one is a missing-decrement leak).

**Hint for worker:** Trace the exact Starlette semantics: does a
`StreamingResponse.background` task execute when the ASGI send loop is cancelled
by client disconnect? Write a test that opens an SSE route, reads one frame,
then drops the connection, and assert `active_requests` returns to 0. If it does
not, the release must move into the stream generator's `finally` (paired with
the upstream close) rather than the response background — so busy/idle bracket
the *same* lifecycle, not two different ones.

---

### AOI-B — The `vampire:` reserved namespace is defended in one direction only *(contract / namespace boundary · HIGH)*

The gateway treats any model id starting with `vampire:` as a *virtual* routing
target. That reservation is enforced **at route creation** —
`create_route` (`control.py:170-175`) returns 409 if a `virtual_model` collides
with a physical model id. But the reverse direction — a downstream LM Studio
node that legitimately serves a physical model whose id starts with `vampire:`
— is **unguarded**, and two code paths then misbehave:

1. `/v1/models` aggregation (`openai_compat.py:42-47`) computes
   `virtual_ids = {"vampire:auto", ...}` and then does
   `physical = [card for card in physical if card.id not in virtual_ids]`.
   A real model literally named `vampire:auto` on a node is **silently deleted
   from the listing** — the client never sees it.
2. `_is_routing_request` (`openai_compat.py:194-202`) returns `True` for any
   `model.startswith("vampire:")`. A client asking for that *physical* model by
   its real name is **hijacked into the router** instead of being proxied
   through, and `model_affinity`/default policy will try to resolve it as a
   virtual model — likely yielding `no_route_target` (503) for a model that
   demonstrably exists.

**Why this is a boundary worth a deep-dive:** the namespace is a trust/contract
seam between "names Vampire owns" and "names downstream owns." Today the
boundary is asymmetric: Vampire refuses to let *operators* collide with the
namespace, but happily lets *downstream nodes* collide and then mis-handles the
collision. `register_node`/`refresh_node` ingest model cards
(`cluster.py:170-182`) with **no namespace validation at all**.

**Hint for worker:** Decide the canonical rule — either reject/anonymize
`vampire:*` physical model ids at ingestion (`_coerce_model_cards`), or make the
listing + routing classifier robust to physical models that shadow the
namespace. Check `DESIGN-API.md §4.2 / §5` for whether `vampire:` is a formally
reserved prefix; the one-sided 409 guard suggests the design intends it to be,
but ingestion never enforces it.

---

### AOI-C — `discover_nodes` carries the *untaken twin* of the already-fixed `refresh_node` resurrection race *(concurrency · HIGH)*

Suggestion `2026-06-14_0602` ("`refresh_node` resurrects concurrently-deleted
nodes") was **taken** — and the fix is visible: `refresh_node` now guards its
write with `if registry.get(updated.id) is not None: registry.add(updated)`
(`cluster.py:226-227`). But the **discovery probe path was not given the same
guard.** `discover_nodes._probe` (`cluster.py:388-399`) does:

```python
async with semaphore:
    refreshed = await refresh_node(node, ...)   # await → yield point
if refreshed.status != "online":
    return None
...
registry.add(refreshed)                          # UNCONDITIONAL re-add
```

Between the `await` and the `registry.add`, an owner `DELETE
/vampire/v1/nodes/{id}` (`control.py:107-112`) can remove the node. The
unconditional `add` then **resurrects it** — the exact defect class the
`refresh_node` fix was meant to close, reintroduced one call frame up. Worse,
`refresh_node` (called inside `_probe`) now *won't* re-add (its guard sees the
node gone), but `_probe` re-adds afterward anyway, so the guard is defeated by
its own caller.

**Hint for worker:** This is a self-contained, high-confidence finding: apply
the same `registry.get(...) is not None` presence check (or a single atomic
"insert-if-still-present" registry primitive) to `_probe`'s `registry.add`. Then
generalize: grep for **every** `registry.add(` after an `await` and confirm each
re-checks presence. The structural fix is a registry method like
`add_if_present` / `upsert(..., require_existing=True)` so the invariant lives
in one place instead of being re-derived at each call site — this also
subsumes the prior fix and AOI-4 of the previous scout report.

---

### AOI-D — `/v1/models` answers with two structurally different contracts depending on registry state *(error-handling / contract · MEDIUM-HIGH)*

`list_models` (`openai_compat.py:36-49`) has a hard branch:

- **Registry non-empty:** curated aggregation — injects virtual models
  (`vampire:auto` + configured routes), de-dupes, strips the `vampire:`
  namespace, returns a normalized `ModelListResponse`.
- **Registry empty:** `return await proxy_request(request)` — a **transparent
  passthrough** that returns the downstream node's raw `/v1/models` body
  verbatim.

These two responses are **not the same contract**:
- `vampire:auto` is documented as an always-present Vampire addition
  (`DESIGN-API.md §5`, "Vampire addition"), yet it **vanishes** the moment no
  nodes are registered — a Vampire-aware client probing capabilities at startup
  (before discovery populates the registry) sees no virtual models and may
  conclude routing is unsupported.
- The aggregated path applies the `created`-field normalization that a *taken*
  suggestion (`2026-06-14_0842`) added; the passthrough path returns whatever
  the downstream sent, so the **OpenAI-required-field guarantees hold in one
  branch and not the other.**

**Hint for worker:** Decide whether `vampire:auto` (and configured route
virtual models) should be advertised **unconditionally**, independent of
registry population, and whether the empty-registry branch should still wrap the
downstream list in the normalized envelope rather than passing it through raw.
The strategic defect is "same endpoint, two contracts" — a client cannot rely on
the shape of `/v1/models` across the gateway's lifecycle.

---

### AOI-E — The config plane mandated by `DESIGN-API.md §21` does not exist; trust is binary, not the specified 5-level taxonomy *(architectural drift / security · MEDIUM-HIGH)*

`DESIGN-API.md §21` specifies an explicit security-control surface:

```json
"nodes": { "allow_untrusted": false, "require_fingerprint": true }
```
and a **five-level trust taxonomy**: `untrusted / local / trusted / verified /
japer-secured`.

The implementation has **none of it**:
- `Node.trusted` is a **boolean** (`models.py`) — the 5-level taxonomy is
  collapsed to true/false, so `local`, `verified`, and `japer-secured` (which
  the §22 JAPER envelope depends on for `node_trust_level`) have **no
  representation**.
- There is **no `allow_untrusted` setting** in `config.py` / `Settings`. The
  prior scout's AOI-2 ("trust not enforced in routing") proposes filtering
  untrusted nodes — but there is **no operator knob** to express the policy, and
  no graduated trust to filter on. Even a correct routing-time filter would be
  hard-coded rather than configurable per §21.
- `require_fingerprint` and the `cors.allowed_origins` control (also §21, and
  relevant because the static UI is mounted at `/` and §21 explicitly lists
  `chrome-extension://` origins) are absent — the app installs **no CORS
  middleware** (`app.py`), so cross-origin browser clients / extensions are
  governed by FastAPI defaults, not the design's allow-list.

**Why this is a strategic boundary, not a feature request:** §22's
verifiable-inference envelope (`trust.node_trust_level: "verified"`,
`signed: true`) is structurally **unbuildable** on a boolean trust field. This
is the seam where the "verifiable inference fabric" thesis silently degrades to
a yes/no flag. The drift is invisible today because routing ignores trust
anyway (AOI-2) — but the moment trust enforcement lands, it will need a config
surface and a trust enum that don't exist.

**Hint for worker:** Map `DESIGN-API.md §21/§22` against `config.py` and
`models.py`. The actionable, contained first step is the **trust-level enum**
(`Node.trusted: bool` → `trust_level: Literal["untrusted","local","trusted",
"verified","japer-secured"]`) plus an `allow_untrusted` setting, because every
other trust/JAPER feature is blocked on those two types. Confirm against §4.1
(`"trusted": true` example) whether the wire contract must stay boolean-
compatible — if so, the enum needs a serialization shim.

---

## Recommended worker order

1. **AOI-C** (discovery resurrection twin) — highest confidence, self-contained,
   directly closes a gap left by a *taken* fix; smallest blast radius.
2. **AOI-A** (in-flight counter leak on disconnect) — high impact on routing
   correctness, distinct from the open lost-update race, testable in isolation.
3. **AOI-B** (`vampire:` namespace one-sided guard) — concrete misbehavior in
   two code paths, clear canonical-rule decision.
4. **AOI-D** (`/v1/models` dual contract) — contract-stability defect, moderate
   effort.
5. **AOI-E** (config/trust-taxonomy drift) — largest design decision; unblocks
   the trust-enforcement and JAPER work but needs an owner ruling on wire compat.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · audit run over
  `src/vampire/` · output ~5.5K tok · est. cost ~$0.42. Derived from
  `agent.log` — this run issued ~10 API calls (cumulative in ≈ 600K with
  61–100% cache hit, out ≈ 5.5K including this write); priced at Opus
  $15/Mtok-out + cached-input discount.
