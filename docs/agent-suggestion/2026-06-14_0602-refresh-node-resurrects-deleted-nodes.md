# `refresh_node` unconditionally re-inserts into the registry, silently resurrecting a node that was concurrently deregistered (zombie-node race + delete-contract violation)

- **Severity:** High — a successful `DELETE /vampire/v1/nodes/{id}` (HTTP 200, `{"status":"removed"}`) can be silently undone by an in-flight health refresh, re-registering a node the owner explicitly revoked. On a control plane whose entire job is to gate which LM Studio backends receive traffic, an "un-deletable" node is a trust/security and correctness failure, not a cosmetic one.
- **Category:** concurrency (async data-integrity race) — with a secondary error-handling/contract violation against the delete API.

- **Summary:** `cluster.refresh_node` finishes by calling `registry.add(updated)` unconditionally (`cluster.py:182`). Because the function `await`s a network probe in the middle, a concurrent `DELETE /vampire/v1/nodes/{id}` (or any `registry.remove`) that lands during that await is overwritten when `refresh_node` resumes and re-inserts the stale node copy. The deleted node reappears in the registry with pre-deletion metadata, the operator's delete is reverted with no error, and routing/`/v1/models` can subsequently dispatch traffic to a backend the owner removed.

- **Location:**
  - `src/vampire/cluster.py:147-183` — `refresh_node`, specifically the unconditional `registry.add(updated)` at **line 182**.
  - `src/vampire/cluster.py:186-193` — `refresh_registered_nodes`, which fans `refresh_node` out concurrently via `asyncio.gather` over a snapshot taken at line 188.
  - `src/vampire/cluster.py:269-283` — `discover_nodes`, the one caller that legitimately relies on `refresh_node` to *insert* a brand-new node (this is why a naive guard would break discovery — see Fix).
  - `src/vampire/api/control.py:81-86` — `delete_node`, whose 200/`removed` contract this race violates.
  - `src/vampire/api/openai_compat.py:33-35` — `/v1/models` triggers `refresh_registered_nodes` on any client request, making the race reachable from the **unauthenticated** OpenAI surface, not just operator actions.

- **Evidence:**

  The unconditional re-insert at the end of `refresh_node`:

  ```python
  # src/vampire/cluster.py:147-183
  async def refresh_node(node: Node, *, timeout_ms: int | None = None) -> Node:
      """Interrogate a node's ``/v1/models`` endpoint and update health metadata."""
      timeout = httpx.Timeout((timeout_ms or 1500) / 1000)
      base_url = node.lmstudio_base_url.rstrip("/")
      client = proxy.build_async_client()
      started = perf_counter()
      try:
          response = await client.get(f"{base_url}/v1/models", timeout=timeout)   # <-- await: control yields here
          ...
          updated = node.model_copy(update={... "status": "online", ...})
      except (httpx.HTTPError, ValueError) as exc:
          ...
          updated = node.model_copy(update={... "status": "offline", ...})
      finally:
          await client.aclose()

      registry.add(updated)   # <-- line 182: ALWAYS re-inserts, even if the node was deleted during the await
      return updated
  ```

  The registry mutators that race against it — both are synchronous and run between the awaits above:

  ```python
  # src/vampire/registry.py:24-45
  def add(self, node: Node) -> Node:
      self._nodes[node.id] = node      # last writer wins
      return node
  ...
  def remove(self, node_id: str) -> bool:
      return self._nodes.pop(node_id, None) is not None
  ```

  The delete endpoint that promises removal:

  ```python
  # src/vampire/api/control.py:81-86
  @router.delete("/nodes/{node_id}")
  async def delete_node(node_id: str) -> dict[str, Any]:
      if not registry.remove(node_id):
          raise HTTPException(status_code=404, detail="node not found")
      return {"id": node_id, "status": "removed"}   # contract: the node is gone
  ```

  **The interleaving (single-threaded asyncio event loop, so the race is purely await-boundary, not CPU-level):**

  1. **T1** — A client hits `GET /v1/models`. `list_models` (`openai_compat.py:33`) sees a non-empty registry and calls `refresh_registered_nodes()`. That snapshots `nodes = registry.list()` (`cluster.py:188`) which includes `node-a`, then `asyncio.gather`s `refresh_node(node-a)`. Inside, execution reaches `await client.get(.../v1/models)` (`cluster.py:154`) — a real network I/O — and **the event loop yields**.
  2. **T2** — While T1 is parked on that await, the owner (or any unauthenticated caller — there is no auth, per the standing `auth-token-never-enforced` finding) issues `DELETE /vampire/v1/nodes/node-a`. `delete_node` runs `registry.remove("node-a")` → `True`, returns **HTTP 200 `{"id":"node-a","status":"removed"}`**. The registry no longer contains `node-a`.
  3. **T1 resumes** — the probe completes (or times out). `refresh_node` builds `updated` from the **stale `node` copy it closed over in step 1**, then executes `registry.add(updated)` (`cluster.py:182`). `node-a` is re-inserted.
  4. **Net result:** the delete the operator was told succeeded is silently reverted. `node-a` is back, carrying whatever status the probe produced, and is once again eligible for routing.

  The same class of overwrite also corrupts a legitimate concurrent **re-registration**: if T2 instead `POST`s an updated `node-a` (new `lmstudio_base_url`, new `trusted` flag) during T1's await, T1's tail `registry.add(updated)` clobbers the fresh registration with stale pre-probe fields — a lost update.

  This is a *different* defect from the already-logged routing TOCTOU (`openai_compat.py:124`, `vampire-suggestions.md` 15:08 entry): that one dereferences `None` and 500s on the **read** side at dispatch time; this one is a lost-write on the **registry mutation** side and produces *no* error at all — it corrupts persisted state. They share a root cause (the registry is mutable shared state crossed by awaits) but need separate fixes.

- **Impact:**
  - **Operator-observable:** A node deleted via the documented API reappears in `GET /vampire/v1/nodes`, `GET /vampire/v1/status` (`nodes_total`), `/metrics`, and `/v1/models` aggregation. The delete looks successful (200) but doesn't stick; under steady `/v1/models` traffic the window is hit repeatedly, so the node may be effectively impossible to remove without stopping client traffic first.
  - **Security/trust blast radius:** Revoking a node is precisely the action an owner takes when a backend is compromised, misbehaving, or being decommissioned. Resurrection routes generation requests back to a revoked backend. Because `/v1/models` (which fires the refresh fan-out) is on the unauthenticated OpenAI surface, an attacker who can reach `/v1/models` can *keep the refresh race hot* while a deletion is attempted.
  - **Lost-update corruption:** Concurrent re-registration during a refresh silently reverts to stale `lmstudio_base_url`/`trusted`/`tags`, which can send traffic to an old endpoint or restore a `trusted` flag the owner just cleared.
  - **Trigger frequency:** Any deployment with more than one concurrent client and an occasionally-changing node set. The await window is a full network round-trip (default 1500 ms timeout, `cluster.py:149`), which is enormous in event-loop terms — easy to hit, not a microsecond-wide theoretical race.

- **Fix:** Make the persist step a guarded compare-and-set: only re-store the health update if the node id is *still registered* at the moment of writing. The `registry.get(...)`/`registry.add(...)` pair contains **no `await`**, so under the single-threaded event loop it is atomic — a concurrent `remove`/`add` cannot interleave between the check and the write. The one caller that depends on `refresh_node` to *create* a node (`discover_nodes`) must pre-register the candidate first, exactly as `register_node` (`control.py:56-57`) and `patch_node` (`control.py:73`) already do, preserving discovery semantics (including the existing behavior of registering offline-but-probed discovery nodes).

  **Before (`cluster.py:179-183`):**
  ```python
      finally:
          await client.aclose()

      registry.add(updated)
      return updated
  ```

  **After:**
  ```python
      finally:
          await client.aclose()

      # Only persist health if the node is still registered. The probe above
      # crosses an await, during which a concurrent DELETE /vampire/v1/nodes/{id}
      # (or a re-registration) may have removed or replaced this node. Re-adding
      # would resurrect a node the owner explicitly deregistered, silently
      # reverting the delete. The get()/add() pair has no await between it, so it
      # is atomic under the single-threaded event loop.
      if registry.get(updated.id) is not None:
          registry.add(updated)
      return updated
  ```

  **And in `discover_nodes` (`cluster.py:272-282`), pre-register the candidate so the guarded refresh persists it:**
  ```python
  # before
          node = current or Node(
              id=_node_id_for_url(base_url),
              host=urlparse(base_url).hostname,
              lmstudio_base_url=base_url,
              trusted=not request.trusted_only,
          )
          refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)

  # after
          node = current or Node(
              id=_node_id_for_url(base_url),
              host=urlparse(base_url).hostname,
              lmstudio_base_url=base_url,
              trusted=not request.trusted_only,
          )
          registry.add(node)  # register before probing so the guarded refresh persists health
          refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
  ```

  Notes:
  - `register_node`, `patch_node`, and `refresh_registered_nodes` already operate on nodes that are present in the registry at call time, so the guard is a no-op for them in the common case and the correct safety net in the racing case. Only `discover_nodes` constructed a not-yet-registered node and leaned on `refresh_node`'s side-effect to insert it — hence the one-line pre-register.
  - This preserves the existing invariant that discovery registers a probed node even when it comes back `offline` (the guard sees the pre-registered id and persists the offline status).
  - No `# type: ignore` to remove here, but this is the same shared-mutable-registry hazard family as the `openai_compat.py:124` ignore; fixing both closes the registry-race surface.
  - **Stronger alternative (optional, larger):** give `NodeRegistry` a dedicated `update_health(node_id, **fields) -> Node | None` method that performs the get-or-skip atomically and returns `None` when absent, so the guard lives in the registry rather than every caller. That also gives a clean seam for the planned SQLite persistence (`registry.py:3-4`) to do a single `UPDATE ... WHERE id=?` instead of an unconditional upsert. The inline guard above is the minimal fix; the method is the durable one.

- **Test:** A regression test that drives a concurrent delete into the middle of `refresh_node` by removing the node from inside the mock transport (the transport runs during the `await client.get(...)`), then asserts the node stays deleted. The project has no async-test plugin configured (all tests use the sync `TestClient`), so drive the coroutine with `asyncio.run`.

  ```python
  # tests/test_phase2.py (new test)
  import asyncio
  import httpx
  from vampire import cluster
  from vampire.models import Node
  from vampire.registry import registry


  def test_refresh_node_does_not_resurrect_a_deregistered_node(monkeypatch):
      node = Node(id="node-z", lmstudio_base_url="http://node-z:1234")
      registry.add(node)

      class _DeletingTransport(httpx.AsyncBaseTransport):
          async def handle_async_request(self, request):
              # Simulate a DELETE /vampire/v1/nodes/node-z landing while the
              # health probe is in flight (this runs during refresh_node's await).
              registry.remove("node-z")
              return httpx.Response(200, json={"object": "list", "data": []})

      monkeypatch.setattr(
          cluster.proxy,
          "build_async_client",
          lambda: httpx.AsyncClient(transport=_DeletingTransport()),
      )

      asyncio.run(cluster.refresh_node(node))

      # Fails today: refresh_node's unconditional registry.add(updated) puts
      # node-z back. Passes after the get()-guarded persist.
      assert registry.get("node-z") is None
  ```

  Today this fails on the final assertion (`node-z` is resurrected by `cluster.py:182`); after the fix the guarded persist sees the node is gone and skips the write, so the assertion holds. A companion test should register `node-z`, run `refresh_node` with a non-deleting transport, and assert `registry.get("node-z").status == "online"` to prove the normal persist path is unchanged; and a third should call `discover_nodes` against the in-process mock cluster and assert the discovered node is registered, proving the `discover_nodes` pre-register keeps discovery working.

- **Effort & risk:** ~3 lines changed in `refresh_node` plus 1 line in `discover_nodes` (2 files, `cluster.py` only); ~25 lines of new test. Backward-compatible: the guard is a no-op for every existing caller except in the racing case it is meant to fix, and the `discover_nodes` pre-register reproduces the prior insert behavior (including offline-node registration). The optional `NodeRegistry.update_health` refactor would touch `registry.py` + 4 call sites (~40 lines) and is the recommended follow-up once SQLite persistence lands, but is not required to close the race. Low risk; the main thing to preserve is discovery's "register even when offline" semantics, which the pre-register line maintains.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~unknown (Hermes `agent.log` logged only `turn_context` lines with no `tokens=` figure for this cron session `cron_c11148734d14_20260614_160045`; conservatively the loaded source + suggestion context is on the order of ~38k input tok) · output ~3.5k tok (this file ≈ 14k chars ÷ 4) · est. cost ~$0.83 (input ~38k×$15/1M ≈ $0.57 + output ~3.5k×$75/1M ≈ $0.26) · run started 06:02 finished 06:03. Estimated, not an exact invoice — final output tokens are emitted after logging.
