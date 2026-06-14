# `model_affinity` routing pins 100% of traffic to the first replica — no load distribution across nodes hosting the same model

- **Severity:** High — a documented MVP load-balancing strategy is effectively a single-node hotspot; in any multi-node deployment of the same model it overloads one node while peers sit idle, defeating the core purpose of the gateway.
- **Category:** api-correctness

- **Summary:** When several online nodes host the requested physical model, the `model_affinity` strategy deterministically selects the *first* matching candidate on every request via `next(...)`, so all traffic is funneled to one node and the other replicas receive nothing. The strategy is advertised in `MVP_STRATEGIES`, the CLI `--strategy` choices, and DESIGN-API.md §9, but it does not balance across affinity matches the way an operator selecting a load-balancing strategy reasonably expects. The reported `X-Vampire-Strategy: model_affinity` header tells the client the request was load-balanced by affinity when in fact it was pinned.

- **Location:**
  - `src/vampire/router.py:63-69` (the `model_affinity` branch in `select`).
  - `src/vampire/router.py:131-138` (`_model_affinity`, which returns the first match via `next(...)`).

- **Evidence:**

  The `select` dispatch for `model_affinity`:

  ```python
  # src/vampire/router.py:63-69
  if strategy == "model_affinity":
      affinity_target = self._model_affinity(candidates, requested_model)
      if affinity_target is not None:
          return Selection(target=affinity_target, strategy=strategy)
      return Selection(
          target=self._round_robin(candidates, policy.id), strategy="round_robin"
      )
  ```

  The helper it calls:

  ```python
  # src/vampire/router.py:131-138
  @staticmethod
  def _model_affinity(
      candidates: list[RouteTarget], requested_model: str | None
  ) -> RouteTarget | None:
      """Prefer a target whose physical model matches the requested model."""
      if requested_model is None or requested_model.startswith("vampire:"):
          return None
      return next((target for target in candidates if target.model == requested_model), None)
  ```

  `next(... )` returns the **first** element of the candidate list that matches. Candidate ordering is stable: `_candidates` (router.py:96-102) preserves `policy.targets` order, and `default_policy` (router.py:80-88) builds targets in registry insertion order. Therefore, given N online nodes all serving model `qwen-32b`, every `model_affinity` request resolves to the same single target for the lifetime of the registry ordering. Round-robin's cursor advance (router.py:111-119) is **never reached** on the affinity path — `_model_affinity` short-circuits before any rotation.

  **Reproduction (run against the real package):**

  ```
  $ PYTHONPATH=src .venv/bin/python /tmp/affinity_check.py
  model_affinity picks: ['node-a', 'node-a', 'node-a', 'node-a', 'node-a', 'node-a']
  distinct nodes used: {'node-a'}
  ```

  Three online nodes, all hosting `qwen-32b`; six `model_affinity` selections; every one lands on `node-a`. The other two replicas receive zero traffic.

  **Conditions under which it manifests:**
  1. Two or more registered nodes are `online` and host the same physical model id (the common HA / horizontal-scale case — e.g. two Mac Studios both running `qwen/qwen3-32b`).
  2. A client sends a *physical* model id (not a `vampire:` alias) with routing opted in (`X-Vampire-Mode: route`, or `vampire.mode == "route"`, or an `X-Vampire-Route` header — see `_is_routing_request`, openai_compat.py:176-184) **and** selects `model_affinity` via `X-Vampire-Strategy` or the route policy's `strategy`.
  3. Every such request resolves to the first-ordered matching node. The contract honored by the *other* MVP strategies — `round_robin` rotates (router.py:111-119), `least_busy`/`least_latency` spread by live score (router.py:57-62) — is silently violated here: `model_affinity` does no spreading at all when multiple matches exist.

- **Impact:**
  - **Operator observation:** one node's `active_requests`/`queue_depth`/latency climbs under load while sibling nodes hosting the identical model report near-zero utilization in `/vampire/v1/metrics`. The cluster appears "unbalanced for no reason."
  - **Client observation:** elevated latency and queueing on affinity-routed requests despite spare capacity elsewhere; the `X-Vampire-Strategy: model_affinity` response header (openai_compat.py:160) misleadingly asserts affinity-based selection occurred.
  - **Blast radius:** every multi-replica `model_affinity` route in the deployment. This is precisely the topology operators stand up replicas *for*. The single pinned node becomes a throughput ceiling and a single point of failure for that model's traffic until it goes offline (only then does `_candidates` drop it and the next-ordered node inherit 100% of the load — again unbalanced).
  - **Trigger timing:** immediately, on the first concurrent burst; worsens monotonically with load.

- **Fix:** `model_affinity` should *narrow* the candidate set to the affinity matches and then **round-robin within that subset**, falling back to round-robin over all candidates when there is no match. This preserves the affinity guarantee (never route a concrete model to a node that lacks it) while restoring load distribution across replicas — the same rotation contract the other strategies honor.

  **Before** (router.py:63-69 + 131-138):

  ```python
  if strategy == "model_affinity":
      affinity_target = self._model_affinity(candidates, requested_model)
      if affinity_target is not None:
          return Selection(target=affinity_target, strategy=strategy)
      return Selection(
          target=self._round_robin(candidates, policy.id), strategy="round_robin"
      )
  ...
  @staticmethod
  def _model_affinity(
      candidates: list[RouteTarget], requested_model: str | None
  ) -> RouteTarget | None:
      """Prefer a target whose physical model matches the requested model."""
      if requested_model is None or requested_model.startswith("vampire:"):
          return None
      return next((target for target in candidates if target.model == requested_model), None)
  ```

  **After:**

  ```python
  if strategy == "model_affinity":
      affinity = self._model_affinity_candidates(candidates, requested_model)
      if affinity:
          # Round-robin *within* the affinity subset so replicas of the same
          # model share load instead of pinning every request to the first one.
          # Use a strategy-scoped cursor key so affinity rotation does not
          # collide with plain round_robin rotation for the same route id.
          return Selection(
              target=self._round_robin(affinity, f"{policy.id}#affinity"),
              strategy=strategy,
          )
      return Selection(
          target=self._round_robin(candidates, policy.id), strategy="round_robin"
      )
  ...
  @staticmethod
  def _model_affinity_candidates(
      candidates: list[RouteTarget], requested_model: str | None
  ) -> list[RouteTarget]:
      """Return all targets whose physical model matches the requested model."""
      if requested_model is None or requested_model.startswith("vampire:"):
          return []
      return [target for target in candidates if target.model == requested_model]
  ```

  Notes:
  - Rename `_model_affinity` → `_model_affinity_candidates` (returns a `list`, not a single `RouteTarget | None`). No other caller exists (verified: the only reference is router.py:64).
  - The `#affinity` cursor-key suffix keeps the affinity rotation independent from the route's plain round-robin cursor and is still bounded by the existing `_MAX_CURSORS` LRU (router.py:117-118), so this does not reopen the unbounded-cursor concern already fixed in suggestion `2026-06-14_0826`.
  - **Invariant preserved:** affinity never selects a node lacking the requested model — the subset is filtered by `target.model == requested_model` exactly as before. The only behavioral change is *which* of the equally-valid matches is chosen on each call.
  - No `# type: ignore` involved. No docs change strictly required, but DESIGN-API.md §9 could note that `model_affinity` round-robins among matching replicas.

- **Test:** Add to `tests/test_phase3.py`. Fails today (all six picks are `node-a`); passes after the fix (rotates across the three replicas).

  ```python
  def test_model_affinity_load_balances_across_replicas_of_same_model() -> None:
      """model_affinity must rotate among all nodes hosting the requested model,
      not pin every request to the first-ordered replica."""
      reg = NodeRegistry()
      for node_id in ("node-a", "node-b", "node-c"):
          reg.add(_online_node(node_id, "qwen-32b"))
      router = Router(reg)
      targets = [
          RouteTarget(node="node-a", model="qwen-32b"),
          RouteTarget(node="node-b", model="qwen-32b"),
          RouteTarget(node="node-c", model="qwen-32b"),
      ]
      policy = RoutePolicy(
          id="affinity-lb",
          virtual_model="vampire:auto",
          targets=targets,
          strategy="model_affinity",
      )

      picks = [
          _selected_node(router.select(policy, requested_model="qwen-32b"))
          for _ in range(9)
      ]

      # All three replicas must receive traffic, and the effective strategy
      # reported must still be model_affinity (affinity matched).
      assert set(picks) == {"node-a", "node-b", "node-c"}
      # Each replica should get a roughly equal share over a full rotation.
      assert picks.count("node-a") == 3
      assert picks.count("node-b") == 3
      assert picks.count("node-c") == 3
      assert router.select(policy, requested_model="qwen-32b").strategy == "model_affinity"
  ```

  (`NodeRegistry`, `Router`, `Node`, `ModelCard`, `RoutePolicy`, `RouteTarget`, `_online_node`, `_selected_node` are all already imported/defined in `tests/test_phase3.py`.) The existing `test_router_mvp_strategies` case (router.py-driven, single match on `node-c`) still passes because with exactly one affinity match the subset has length 1 and round-robin trivially returns it, and `strategy` remains `"model_affinity"`.

- **Effort & risk:** ~12 lines changed in one file (`src/vampire/router.py`) plus ~30 lines of new test. Backward-compatible at the API level — request/response shapes and the `X-Vampire-Strategy` header semantics are unchanged; only the node chosen among equally-valid matches differs, which is exactly the intended behavior of a routing strategy. Low risk: no new state, reuses the already-bounded cursor map, single internal caller renamed.

---

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~unknown (per-call `in=` figures are cumulative-context, not incremental; not summable into a meaningful total) · output ~3.0K tok (sum of this run's `out=`: 287+133+115+171+162+213+530+350+1692+902 ≈ 4.6K across calls #1-#10, of which generation+tool args ≈ 3K) · est. cost ~$0.35 (output 4.6K × $75/1M ≈ $0.34; input not reliably derivable) · run started 19:01 finished 19:33 UTC. Marked estimated.
