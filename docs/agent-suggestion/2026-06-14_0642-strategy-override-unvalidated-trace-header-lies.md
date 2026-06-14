# The per-request `X-Vampire-Strategy` / `vampire.routing.strategy` override is accepted unvalidated and silently coerced to `round_robin`, yet the `X-Vampire-Strategy` response/trace header reports the *requested* strategy that was never applied — the routing audit trail lies

- **Severity:** High — the routing observability contract is broken in the most misleading way possible: the gateway tells the operator (via the `X-Vampire-Strategy` response header) that it ran a strategy it never ran. An operator debugging load imbalance, or an SRE auditing which policy served a request, gets a confident-but-false answer. Not Critical because it does not crash or leak data, but it actively corrupts the one signal the design (§25 `vampire.routing` trace) exists to provide, and it inconsistently bypasses the validation that the sibling control-plane endpoint already enforces.
- **Category:** api-correctness (observability/trace-contract violation) — with a co-equal input-validation dimension (an unvalidated free-form string flows into routing) and a code-consistency violation against `POST /vampire/v1/routes`, which *does* reject unsupported strategies.
- **Status:** Suggestion taken with notes.
- **Notes:** Implemented strategy override validation and effective-strategy reporting from router selections.

- **Summary:** A request can name a routing strategy three ways — the `X-Vampire-Strategy` header, the `vampire.routing.strategy` body field, or a stored route policy. `_strategy_override` extracts that string with **no validation against `MVP_STRATEGIES`** and stamps it onto the effective `RoutePolicy.strategy`. `Router.select` then silently rewrites any unknown strategy to `round_robin` for the *actual* node selection (`router.py:36-38`), but `_route_or_proxy` emits the **original, unvalidated** `policy.strategy` back to the client in the `X-Vampire-Strategy` response header (`openai_compat.py:128`). The result: ask for `weighted_round_robin` (a strategy the design documents at `DESIGN-API.md:633` but the MVP does not implement), or simply typo `least-busy`, and the gateway round-robins the request while reporting `X-Vampire-Strategy: weighted_round_robin`. The trace header — the audit surface — asserts something false.

- **Location:**
  - `src/vampire/api/openai_compat.py:155-161` — `_strategy_override`, which returns any `str` with no membership check against `MVP_STRATEGIES`.
  - `src/vampire/api/openai_compat.py:95-96` — `strategy = _strategy_override(...)` then `policy = _route_policy(...)`, where the raw string becomes the policy strategy.
  - `src/vampire/api/openai_compat.py:164-181` — `_route_policy`: both branches put the unvalidated `strategy` onto the policy (`default_policy(..., strategy=strategy or "round_robin", ...)` at 176-178, and `route.model_copy(update={"strategy": strategy})` at 180).
  - `src/vampire/api/openai_compat.py:126-131` — the response-header block that emits `"X-Vampire-Strategy": policy.strategy` — the *requested*, not the *effective*, strategy.
  - `src/vampire/router.py:36-38` — `Router.select`, the silent `if strategy not in MVP_STRATEGIES: strategy = "round_robin"` coercion that the header fails to reflect.
  - `src/vampire/api/control.py:130-135` — `create_route`, the sibling endpoint that **does** validate (`raise HTTPException(status_code=400, detail="unsupported routing strategy")`), establishing the contract this path violates.
  - `DESIGN-API.md:1140-1141` — the `event: vampire.routing` / `data: {"selected_node":...,"strategy":"least_busy"}` trace contract: the emitted `strategy` is meant to name the strategy that was actually used to select the node.

- **Evidence:**

  The unvalidated extraction — note there is no `MVP_STRATEGIES` check, only an `isinstance(str)` check:

  ```python
  # src/vampire/api/openai_compat.py:155-161
  def _strategy_override(request: Request, payload: dict[str, Any]) -> str | None:
      """Extract routing strategy from headers or the opt-in ``vampire`` object."""
      vampire = _vampire_object(payload)
      raw_routing = vampire.get("routing")
      routing = raw_routing if isinstance(raw_routing, dict) else {}
      strategy = request.headers.get("X-Vampire-Strategy") or routing.get("strategy")
      return strategy if isinstance(strategy, str) else None
  ```

  The raw string becomes the effective policy strategy in **both** branches of `_route_policy`:

  ```python
  # src/vampire/api/openai_compat.py:164-181
  def _route_policy(request, payload, model, strategy):
      vampire = _vampire_object(payload)
      route_id = request.headers.get("X-Vampire-Route") or vampire.get("route")
      route = route_registry.get(route_id) if isinstance(route_id, str) else None
      route = route or route_registry.get_by_virtual_model(model)
      if route is None:
          route = _router.default_policy(
              model, strategy=strategy or "round_robin", requested_model=model
          )                                         # <- unvalidated strategy onto fresh policy
      elif strategy is not None:
          route = route.model_copy(update={"strategy": strategy})  # <- overwrites a *validated*
      return route                                                 #    stored strategy with junk
  ```

  The router silently discards an unknown strategy for the real selection:

  ```python
  # src/vampire/router.py:35-38
  strategy = policy.strategy
  if strategy not in MVP_STRATEGIES:
      strategy = "round_robin"           # <- effective strategy diverges from policy.strategy here
  ```

  …but the response header reports the *policy* value, not the *effective* value:

  ```python
  # src/vampire/api/openai_compat.py:122-132
  return await proxy_request_with_body(
      request,
      downstream_base_url=registry.get(target.node).lmstudio_base_url,  # type: ignore[union-attr]
      body=json.dumps(routed_payload).encode("utf-8"),
      response_headers={
          "X-Vampire-Route": policy.id,
          "X-Vampire-Strategy": policy.strategy,   # <- reports requested, not effective, strategy
          "X-Vampire-Node": target.node,
          "X-Vampire-Model": target.model,
      },
  )
  ```

  Contrast the control-plane contract, which rejects the same junk with a clean 400:

  ```python
  # src/vampire/api/control.py:130-135
  @router.post("/routes")
  async def create_route(route: RoutePolicy) -> dict[str, Any]:
      if route.strategy not in MVP_STRATEGIES:
          raise HTTPException(status_code=400, detail="unsupported routing strategy")
      return route_registry.add(route).model_dump()
  ```

  **Step-by-step manifestation:**
  1. A client opts into routing and requests a strategy that is either a documented-but-non-MVP one (`weighted_round_robin`, `least_latency` typo'd as `least-latency`, `highest_tokens_per_second`, etc.) — e.g. `POST /v1/chat/completions` with header `X-Vampire-Mode: route`, `X-Vampire-Strategy: weighted_round_robin`, body `{"model": "vampire:auto", ...}`.
  2. `_strategy_override` returns `"weighted_round_robin"` verbatim (it is a `str`; no membership check).
  3. `_route_policy` builds `default_policy("vampire:auto", strategy="weighted_round_robin", ...)`, so `policy.strategy == "weighted_round_robin"`.
  4. `_router.select(policy, ...)` enters `Router.select`, sees `"weighted_round_robin" not in MVP_STRATEGIES`, and **silently** sets the working strategy to `"round_robin"`. The node is chosen by round-robin.
  5. `_route_or_proxy` dispatches and sets `X-Vampire-Strategy: weighted_round_robin` on the response.
  6. The client/operator reads the header and believes a weighted strategy ran. It did not. The same false value would be emitted in the §25 `vampire.routing` SSE trace once that trace is wired to `policy.strategy`.

  **Second manifestation — a *stored, validated* policy gets silently downgraded:** an operator creates `route-prod` with `strategy: least_busy` (accepted, validated by `create_route`). A client later sends that route with `X-Vampire-Strategy: lest_busy` (typo). Line 180 does `route.model_copy(update={"strategy": "lest_busy"})`, the router falls back to round_robin, and the header reports `lest_busy`. The carefully-validated `least_busy` policy was overridden by an unvalidated typo for this request, and nothing tells anyone.

- **Impact:** Concrete, operator-observable consequences:
  - **The routing audit trail is false.** `X-Vampire-Strategy` (and the future `vampire.routing` trace, `DESIGN-API.md:1140`) is the canonical answer to "which strategy served this request?" It reports the requested strategy regardless of whether it was honored, so every dashboard, log line, or support ticket built on it is wrong whenever a non-MVP/typo'd strategy is requested. An SRE chasing load skew will conclude `least_busy` is misbehaving when in fact `round_robin` ran.
  - **Inconsistent contract enforcement.** `POST /vampire/v1/routes` rejects an unsupported strategy with `400`; the per-request override accepts the identical junk and silently degrades. A client cannot rely on "the gateway validates strategies."
  - **Silent capability masking.** A client that legitimately asks for a documented strategy not yet in the MVP set gets round-robin with zero signal — no warning header, no 4xx — so the missing capability is undiscoverable from the API surface.
  - **Blast radius:** every routed `POST /v1/chat/completions`, `/completions`, `/responses`, `/embeddings` that supplies a strategy override via header or body. Triggers whenever the requested strategy is not exactly one of the five `MVP_STRATEGIES` strings (case-sensitive).

- **Fix:** Make the strategy contract single-sourced and honest. Two complementary changes, pick both:
  1. **Reject unknown overrides at the boundary** (mirrors `create_route`), so a client gets a clear 400 instead of a silent downgrade.
  2. **Always report the *effective* strategy** that the router actually used, never the raw request value — so even an internal fallback (e.g. `model_affinity` with no match degrading to round-robin) is reported truthfully.

  Have the router expose what it actually did, and report that:

  ```python
  # src/vampire/router.py  — return the effective strategy alongside the target
  from dataclasses import dataclass

  @dataclass(frozen=True)
  class Selection:
      target: RouteTarget
      strategy: str          # the strategy actually applied

  def select(self, policy, *, requested_model=None) -> Selection | None:
      strategy = policy.strategy if policy.strategy in MVP_STRATEGIES else "round_robin"
      candidates = self._candidates(policy)
      if strategy == "trusted_only":
          candidates = [t for t in candidates if self._node(t).trusted]
      if not candidates:
          return None
      if strategy == "least_busy":
          target = min(candidates, key=lambda t: self._busy_score(self._node(t)))
      elif strategy == "least_latency":
          target = min(candidates, key=lambda t: self._latency_score(self._node(t)))
      elif strategy == "model_affinity":
          target = self._model_affinity(candidates, requested_model) \
                   or self._round_robin(candidates, policy.id)
      else:
          target = self._round_robin(candidates, policy.id)
      return Selection(target=target, strategy=strategy)
  ```

  Validate the override and report the effective value in the handler:

  ```python
  # src/vampire/api/openai_compat.py
  from vampire.router import MVP_STRATEGIES

  def _strategy_override(request, payload):
      vampire = _vampire_object(payload)
      raw_routing = vampire.get("routing")
      routing = raw_routing if isinstance(raw_routing, dict) else {}
      strategy = request.headers.get("X-Vampire-Strategy") or routing.get("strategy")
      if strategy is not None and strategy not in MVP_STRATEGIES:
          raise StrategyError(strategy)            # -> 400 at the boundary, like create_route
      return strategy if isinstance(strategy, str) else None

  # in _route_or_proxy, after selection:
  selection = _router.select(policy, requested_model=model)
  ...
  response_headers={
      "X-Vampire-Route": policy.id,
      "X-Vampire-Strategy": selection.strategy,    # effective, never the raw request value
      "X-Vampire-Node": selection.target.node,
      "X-Vampire-Model": selection.target.model,
  }
  ```

  With a small boundary translation (mirroring `create_route`):

  ```python
  class StrategyError(ValueError):
      def __init__(self, strategy: str) -> None:
          super().__init__(f"unsupported routing strategy {strategy!r}")

  # at the top of _route_or_proxy / chat_completions, translate to HTTP 400:
  try:
      strategy = _strategy_override(request, payload)
  except StrategyError as exc:
      return JSONResponse(
          status_code=400,
          content={"error": {"message": str(exc), "type": "vampire_routing_error",
                             "code": "unsupported_strategy"}},
      )
  ```

  Notes:
  - **Invariant to preserve:** when no strategy is supplied, behavior is unchanged (default `round_robin`); a *valid* override still works exactly as today. The only behavioral change is (a) invalid override → 400 instead of silent round-robin, and (b) the header always equals the strategy the router applied.
  - This also fixes the related honesty gap where `model_affinity` with no matching model silently falls back to round-robin (`router.py:52-54`) yet still reports `model_affinity` — returning `selection.strategy` makes that case truthful too (and is a reason to keep change #2 even if you reject #1 for backward-compat).
  - **Docs:** if `DESIGN-API.md §25`/§24 is later wired to emit the live `vampire.routing` trace, source its `strategy` field from `selection.strategy`, not `policy.strategy`.
  - No `# type: ignore` is introduced; the pre-existing `# type: ignore[union-attr]` on the dispatch line is out of scope here (covered by `2026-06-14_0629`).

- **Test:** A regression test that fails today (the header advertises the un-run strategy and no 400 is raised) and passes after the fix. Uses the existing Phase-3 `client`/mock-cluster fixture.

  ```python
  # tests/test_phase3.py
  def test_unknown_strategy_override_is_rejected_not_silently_downgraded(client):
      """A non-MVP strategy must 400, not silently round-robin while lying in the header."""
      client.post("/vampire/v1/nodes",
                  json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"})
      resp = client.post(
          "/v1/chat/completions",
          headers={"X-Vampire-Mode": "route", "X-Vampire-Strategy": "weighted_round_robin"},
          json={"model": "node-a-model", "messages": [{"role": "user", "content": "hi"}]},
      )
      # Today: 200 with header "x-vampire-strategy: weighted_round_robin" (a strategy never run).
      assert resp.status_code == 400
      assert resp.json()["error"]["code"] == "unsupported_strategy"

  def test_reported_strategy_is_the_effective_one(client):
      """When model_affinity finds no match it degrades to round_robin; the header must say so."""
      client.post("/vampire/v1/nodes",
                  json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"})
      resp = client.post(
          "/v1/chat/completions",
          headers={"X-Vampire-Mode": "route", "X-Vampire-Strategy": "model_affinity"},
          # request a vampire: virtual model so model_affinity cannot match a physical id
          json={"model": "vampire:auto", "messages": [{"role": "user", "content": "hi"}]},
      )
      assert resp.status_code == 200
      # Today this asserts-fails: header says "model_affinity" though round_robin actually ran.
      assert resp.headers["x-vampire-strategy"] == "round_robin"
  ```

  The existing `test_x_vampire_headers_control_physical_model_routing` (which sends the *valid* `model_affinity` against a matching physical model and asserts the header equals `model_affinity`) still passes unchanged, because in that case the effective strategy genuinely is `model_affinity`.

- **Effort & risk:** ~25-35 lines across two files (`router.py` return-type change to a tiny `Selection`, `openai_compat.py` validation + effective-strategy reporting), plus ~20 lines of tests. The `Selection` return type touches `Router.select`'s two call sites (`openai_compat.py:97` and the fallback path at `104`) and any direct router test (`test_phase3.py` calls `router.select(...)` and unwraps via `_selected_node`); those helpers need a one-line `.target` adjustment. Backward-compat: response shapes for valid requests are unchanged; the only client-visible change is that a previously-silently-accepted bogus strategy now returns a structured 400 — arguably a bugfix clients should welcome, but flag it in release notes since a tolerant client relying on the silent downgrade would now see an error. Low risk; the validation logic is copied verbatim from the already-shipping `create_route` contract.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~692,510 tok · output ~18,498 tok (summed from this session `cron_c11148734d14_20260614_163646`'s logged `in=`/`out=` across 15 API calls) · est. cost ~$11.77 (input 692510/1e6·$15 = $10.39 + output 18498/1e6·$75 = $1.39) · run started 16:36 finished 16:42 UTC. Estimated — final output tokens are emitted after logging.
