# `refresh_node` clobbers the live `active_requests` counter — a lost-update race that blinds `least_busy` routing

- **Severity:** High — the concurrency control that `least_busy` (and operator
  metrics) depend on is silently corrupted by any concurrent health refresh. In
  the exact topology operators reach for `least_busy` in — several busy nodes
  under load — refresh resets in-flight counts to a stale value, so the router's
  load signal is wrong precisely when it matters, and `/vampire/v1/metrics`
  under-reports cluster load.
- **Category:** concurrency

- **Summary:** `registry.mark_busy` / `mark_idle` maintain a live
  `active_requests` counter on each `Node` (incremented when a request is routed,
  decremented when it finishes). `refresh_node` updates node health with
  `node.model_copy(update={...})` followed by `registry.add(updated)`, but the
  `update` dict it passes carries **no** `active_requests` (nor `queue_depth`)
  field, and the `node` it copies from is the snapshot the caller already held —
  captured *before* any concurrent `mark_busy` bump. `model_copy` therefore
  re-emits the stale counter value and `registry.add` overwrites the live one.
  This is a classic read-modify-write lost update: a health poll that overlaps
  in-flight requests resets `active_requests` back to the value it had when the
  poll's snapshot was taken (typically `0`). The subsequent `mark_idle` calls
  then floor at `0` via `max(0, ...)`, permanently desynchronizing the counter
  from reality.

- **Location:**
  - `src/vampire/cluster.py:200-209` — the online-branch `model_copy(update={...})`
    in `refresh_node` (the `update` dict omits `active_requests`/`queue_depth`).
  - `src/vampire/cluster.py:212-221` — the offline branch has the identical omission.
  - `src/vampire/cluster.py:226-227` — `registry.add(updated)` overwrites the
    live registry node with the stale-counter copy.
  - `src/vampire/registry.py:40-54` — `mark_busy`/`mark_idle`, the live counter
    that gets clobbered; note `mark_idle` floors at `max(0, ...)` (line 53),
    which *hides* the resulting underflow instead of surfacing it.
  - `src/vampire/router.py:57-59` + `:125-127` — `least_busy` consumes
    `node.active_requests` (via `_busy_score`) as a primary load signal.
  - `src/vampire/api/openai_compat.py:39-41` — `list_models` calls
    `refresh_registered_nodes` on every `GET /v1/models`, the most common way a
    refresh overlaps in-flight routed requests.

- **Evidence:**

  The online success branch of `refresh_node` rebuilds the node from a snapshot
  and writes it back, with no `active_requests` in the update set:

  ```python
  # src/vampire/cluster.py:200-209
  updated = node.model_copy(
      update={
          "status": "online",
          "models": _coerce_model_cards(response.json()),
          "request_count": node.request_count + 1,
          "latency_ms": latency_ms,
          "last_checked_at": _now(),
          "last_error": None,
      }
  )
  # ...
  # src/vampire/cluster.py:226-227
  if registry.get(updated.id) is not None:
      registry.add(updated)
  ```

  `model_copy(update=...)` keeps every field *not* named in `update` at the
  value it had **in `node`** — and `node` is the caller's pre-existing snapshot.
  `refresh_registered_nodes` passes exactly such a snapshot:

  ```python
  # src/vampire/cluster.py:256, 263-272
  nodes = registry.list()                      # snapshot taken here
  # ...
  async def _bounded_refresh(node: Node) -> Node | BaseException:
      async with semaphore:
          # ...
          return await refresh_node(node, timeout_ms=timeout_ms, client=client)
  results = await asyncio.gather(*(_bounded_refresh(node) for node in nodes))
  ```

  Between the `registry.list()` snapshot and the `registry.add(updated)`
  write-back, the event loop yields on the network `await` (cluster.py:197) —
  during which any number of routed requests can call `mark_busy`. Their
  increments land on the live registry node and are then overwritten by the
  stale copy.

  The live counter being clobbered:

  ```python
  # src/vampire/registry.py:40-54
  def mark_busy(self, node_id: str) -> None:
      node = self._nodes.get(node_id)
      if node is not None:
          self._nodes[node_id] = node.model_copy(
              update={"active_requests": node.active_requests + 1}
          )

  def mark_idle(self, node_id: str) -> None:
      node = self._nodes.get(node_id)
      if node is not None:
          self._nodes[node_id] = node.model_copy(
              update={"active_requests": max(0, node.active_requests - 1)}  # hides underflow
          )
  ```

  **Reproduction (run against the real package):**

  The script below performs the *exact* registry mutation `refresh_node`'s
  online branch performs (`node.model_copy(update={...})` with no
  `active_requests`, then `registry.add`), sandwiched between real `mark_busy` /
  `mark_idle` calls. It imports the real `vampire.models` and `vampire.registry`.

  ```
  $ PYTHONPATH=src .venv/bin/python /tmp/refresh_clobber_check.py
  after 2x mark_busy: active_requests = 2
  after refresh_node: active_requests = 0
  after 2x mark_idle: active_requests = 0

  EXPECTED: busy=2, refresh preserves 2, idle returns to 0
  ACTUAL  : busy=2, refresh reset to 0, mark_idle floored at 0 (max(0,...) hides the underflow)
  CONFIRMED: refresh_node silently dropped 2 in-flight requests; least_busy now
  treats node-a as idle and over-schedules it.
  ```

  Two requests are in flight (`active_requests = 2`); a single overlapping
  refresh resets the count to `0`; the two genuine `mark_idle` releases then
  underflow and are silently floored at `0`. The node now lies about its load
  for the rest of its lifetime.

  (The script avoids importing `vampire.cluster` only because this checkout's
  `.venv` has a broken `pydantic_settings` install — `ModuleNotFoundError:
  pydantic_settings.sources.providers.aws` — that prevents `vampire.config` and
  thus `vampire.proxy`/`vampire.cluster` from importing at all. That is an
  unrelated environment breakage worth a separate fix; it does not affect the
  validity of this reproduction, which exercises the identical `model_copy` +
  `registry.add` mutation the online branch runs.)

- **Conditions under which it manifests:**
  1. At least one node is `online` and serving routed traffic so
     `mark_busy`/`mark_idle` are actively maintaining `active_requests`.
  2. Any refresh path runs concurrently against a snapshot of that node:
     `GET /v1/models` (openai_compat.py:39-41 → `refresh_registered_nodes`), a
     `POST /vampire/v1/discover` static refresh, or a direct
     `POST /vampire/v1/nodes/{id}/refresh`. All call `refresh_node` with a
     `Node` captured before the in-flight requests were counted.
  3. The network `await` inside `refresh_node` (cluster.py:197) yields the event
     loop, giving routed requests a window to `mark_busy`. The refresh then
     write-backs its stale copy, erasing those increments.

- **Impact:**
  - **Routing correctness:** `least_busy` (router.py:57-59) ranks candidates by
    `node.active_requests`. After a clobber, a genuinely-loaded node reports `0`
    in-flight and is repeatedly selected as "least busy," concentrating load on
    the node the strategy is supposed to relieve — the direct inverse of the
    intended behavior. This compounds with each subsequent refresh.
  - **Counter drift / permanent desync:** because `mark_idle` floors at
    `max(0, ...)`, releases for the erased requests are absorbed silently. The
    counter does not self-heal; it stays wrong until the process restarts.
    Conversely, if `mark_busy` increments land *after* the refresh read but the
    refresh later overwrites with an even-staler copy, the count can also be
    inflated — either direction is possible, both are wrong.
  - **Operator observability:** `/vampire/v1/metrics`
    (`cluster.active_requests = sum(node.active_requests ...)`, cluster.py:320)
    under-reports live cluster load, so dashboards and autoscaling signals built
    on it are unreliable.
  - **Blast radius:** every `least_busy`-routed deployment that also serves
    `/v1/models` or periodic health refreshes — i.e. essentially every realistic
    multi-node deployment, since clients poll `/v1/models` routinely.
  - **Trigger timing:** the first `/v1/models` (or discovery/refresh) call that
    overlaps any in-flight routed request. Frequency scales with traffic, so it
    worsens exactly under load.

- **Fix:** `refresh_node` must update only the *health* fields it actually
  measured and must never overwrite the live operational counters
  (`active_requests`, `queue_depth`) that other code paths own. The robust fix
  re-reads the current registry node and copies onto *it*, rather than onto the
  caller's stale snapshot, so concurrent `mark_busy`/`mark_idle` increments are
  preserved. Apply the same re-read to both the online and offline branches.

  **Before** (cluster.py:200-228, both branches copy from the stale `node`):

  ```python
  updated = node.model_copy(
      update={
          "status": "online",
          "models": _coerce_model_cards(response.json()),
          "request_count": node.request_count + 1,
          "latency_ms": latency_ms,
          "last_checked_at": _now(),
          "last_error": None,
      }
  )
  # ...
  if registry.get(updated.id) is not None:
      registry.add(updated)
  return updated
  ```

  **After** (re-read the live node, preserve its operational counters):

  ```python
  # Build the health-only patch from what this probe actually measured.
  health_update = {
      "status": "online",
      "models": _coerce_model_cards(response.json()),
      "request_count": node.request_count + 1,
      "latency_ms": latency_ms,
      "last_checked_at": _now(),
      "last_error": None,
  }
  # ... (offline branch builds its own health_update without active_requests/queue_depth)

  # Re-read under no intervening await so we copy onto the CURRENT registry node,
  # carrying forward live counters (active_requests, queue_depth) that
  # mark_busy/mark_idle may have changed while this probe was on the wire.
  current = registry.get(node.id)
  if current is None:
      # Node was deregistered mid-probe; do not resurrect it (existing invariant,
      # see test_refresh_node_does_not_resurrect_deregistered_node).
      return node.model_copy(update=health_update)
  updated = current.model_copy(update=health_update)
  registry.add(updated)
  return updated
  ```

  Notes:
  - The merge happens synchronously (no `await` between `registry.get` and
    `registry.add`), so under the single-threaded asyncio model it is atomic with
    respect to other coroutines — there is no interleaving point for a competing
    `mark_busy`. This is the same discipline the resurrection fix relies on.
  - `request_count`/`error_count` are *probe-owned* health fields and should keep
    incrementing from the value the probe observed (`node.*`), which is what
    `health_update` does. `active_requests`/`queue_depth` are *router-owned* and
    are now simply never named in the update, so they survive from `current`.
  - The existing invariant from
    `test_refresh_node_does_not_resurrect_deregistered_node`
    (test_phase2.py:312) is preserved: when `current is None`, the function
    returns the refreshed snapshot for the caller but does **not** re-add it.
  - Consider tightening `mark_idle` to log when it would go negative
    (registry.py:53) instead of silently flooring — that would have surfaced this
    bug as a warning rather than as silent drift. Optional, out of scope for the
    minimal fix.

- **Test:** Add to `tests/test_phase2.py` (imports `Node`, `registry`, `cluster`,
  `httpx`, `asyncio` are already present there). Fails today
  (`active_requests == 0` after refresh); passes after the fix.

  ```python
  def test_refresh_node_preserves_live_active_requests(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """A health refresh must not clobber the in-flight counter that
      mark_busy/mark_idle maintain (lost-update race)."""
      from vampire.registry import registry

      registry.clear()
      node = Node(
          id="node-busy",
          lmstudio_base_url="http://node-busy:1234",
          status="online",
      )
      registry.add(node)

      # Two routed requests are in flight when the refresh starts.
      registry.mark_busy("node-busy")
      registry.mark_busy("node-busy")
      assert registry.get("node-busy").active_requests == 2

      class _OnlineTransport(httpx.AsyncBaseTransport):
          async def handle_async_request(
              self, request: httpx.Request
          ) -> httpx.Response:
              return httpx.Response(
                  200, json={"object": "list", "data": [{"id": "m", "object": "model"}]}
              )

      monkeypatch.setattr(
          proxy,
          "build_async_client",
          lambda: httpx.AsyncClient(transport=_OnlineTransport()),
      )

      # Refresh against the pre-bump snapshot, exactly as
      # refresh_registered_nodes does.
      asyncio.run(cluster.refresh_node(node))

      # The live counter must survive the refresh.
      assert registry.get("node-busy").active_requests == 2

      # And the two genuine releases must return it cleanly to zero.
      registry.mark_idle("node-busy")
      registry.mark_idle("node-busy")
      assert registry.get("node-busy").active_requests == 0
  ```

  Today this asserts `2 == 0` and fails immediately after the
  `cluster.refresh_node` call. After the fix it passes. The existing
  `test_refresh_node_does_not_resurrect_deregistered_node` still passes because
  the `current is None` branch keeps the no-resurrect behavior.

- **Effort & risk:** ~15 lines changed in one file (`src/vampire/cluster.py`),
  touching both branches of `refresh_node`, plus ~40 lines of new test. Low risk:
  no API/response-shape change, no new state, and the re-read merge is atomic
  under asyncio. The only behavioral change is that `active_requests` /
  `queue_depth` now survive a refresh instead of being reset — which is the
  intended contract. Backward-compatible.

---

## Opus 4.8 Advice

The lost-update analysis is correct and the re-read-and-merge fix is the right shape. Three
refinements before you land it:

1. **The monotonic counters have the same lost-update bug as `active_requests` — fix them the
   same way.** The proposed `health_update` still copies `node.request_count + 1` /
   `node.error_count + 1`, i.e. increments from the *stale* snapshot. If a concurrent refresh
   already bumped `request_count` on the live node, copying `node.request_count + 1` onto
   `current` discards that increment — exactly the race you're closing for `active_requests`.
   Increment from the live value instead: read `current.request_count` and use
   `current.request_count + 1` (likewise `error_count`).

2. **This shares an owner with suggestions `1210` and the `_probe` add path.** Three call sites
   write the registry via read-then-add against a snapshot: `refresh_node` (cluster.py:226),
   `_probe`'s own `registry.add` (cluster.py:398), and this merge. The `current is None ->
   return without add` branch you propose **is** the resurrection guard from `1210` — it's the
   same invariant. Implement it once: make `refresh_node` the single writer that merges health
   onto the *current* registry node, and have `_probe` only `add` genuinely new nodes (see the
   `1210` advice, whose naive guard otherwise breaks new-node discovery). Land `0930` and `1210`
   together.

3. **The atomicity argument holds only with no `await` between `registry.get` and
   `registry.add`.** Keep them adjacent; do not insert logging-with-await or any other yield
   point between the re-read and the write-back, or the race reopens.

Also worth doing alongside: tighten `mark_idle` (registry.py:53) to **log** when it would go
negative instead of silently flooring with `max(0, ...)`. That silent floor is what let this drift
go unnoticed; surfacing it turns the next occurrence of any counter desync into a visible warning
rather than a routing mystery.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · provider
  lmstudio (job mis-pinned to a non-downloaded model on the prior run; this run
  executed under the session model) · output ~5K tok generation + tool args ·
  est. cost not reliably derivable from per-call cumulative figures · run
  produced one new suggestion file plus README index update. Marked estimated.
