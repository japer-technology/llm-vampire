# A `# type: ignore[union-attr]` masks a TOCTOU None-deref in the hot routing path: a node deregistered mid-request crashes `/v1/chat/completions` with a bare 500

- **Severity:** High — the single most-called inference endpoint (`POST /v1/chat/completions`, and every other `/v1/*` routed verb) can crash with an uncaught `AttributeError → 500` whenever a route target's node is removed (DELETE, patch-to-offline + clear, or a discovery/refresh churn) between selection and dispatch. The defect is *deliberately hidden* from the type checker by a `# type: ignore[union-attr]`, so the one tool that would have flagged it has been silenced.
- **Category:** type-safety (a `# type: ignore` masking a real bug) — with a co-equal concurrency (TOCTOU race) and error-handling (contract-violating bare 500) dimension.
- **Status:** Suggestion taken with notes.
- **Notes:** Implemented explicit node re-read/narrowing before dispatch and return a structured 503 when a selected node is removed.

- **Summary:** `_route_or_proxy` selects a `RouteTarget` from the router, then immediately dereferences `registry.get(target.node).lmstudio_base_url` to build the downstream URL. `registry.get()` is typed `Node | None`, and the `.lmstudio_base_url` access on a possibly-`None` value is suppressed with `# type: ignore[union-attr]`. The suppressed warning is real: the router's `select()` releases control of the event loop is not required, but the *request handler `await`s `request.body()` earlier and the registry is mutated by concurrent control-plane requests*, so between the moment the router validates the node exists and the moment this line reads it, a concurrent `DELETE /vampire/v1/nodes/{id}` (or `registry.clear()` from discovery) can remove it — making `registry.get()` return `None` and turning the next attribute access into an unhandled `AttributeError`.

- **Location:**
  - `src/vampire/api/openai_compat.py:122-124` — the offending dispatch with the suppression.
  - `src/vampire/api/openai_compat.py:97` — `target = _router.select(...)`, the start of the check-to-use window.
  - `src/vampire/router.py:86, 91-94` — `Router._candidates` / `Router._node`, which read `registry.get(...)` and assume the node is still present.
  - `src/vampire/api/control.py:81-86` — `delete_node`, the concurrent mutator that opens the race.
  - `src/vampire/registry.py:39-45` — `NodeRegistry.get`/`remove`, the (uncoordinated) shared state.

- **Evidence:** The dispatch line, verbatim:

```python
# src/vampire/api/openai_compat.py
 96    policy = _route_policy(request, payload, model, strategy)
 97    target = _router.select(policy, requested_model=model)        # validates node exists *now*
 ...
119    routed_payload = dict(payload)
120    routed_payload["model"] = target.model
121    routed_payload.pop("vampire", None)
122    return await proxy_request_with_body(
123        request,
124        downstream_base_url=registry.get(target.node).lmstudio_base_url,  # type: ignore[union-attr]
```

`registry.get` is declared `Node | None`:

```python
# src/vampire/registry.py
39    def get(self, node_id: str) -> Node | None:
40        """Return a node by id, or ``None`` when it is not registered."""
41        return self._nodes.get(node_id)
```

The router's selection step *also* reads the registry, and is what makes line 124 "look" safe — but it is a separate read at an earlier point in time:

```python
# src/vampire/router.py
81    def _candidates(self, policy: RoutePolicy) -> list[RouteTarget]:
82        """Return online targets whose nodes are currently registered."""
83        return [
84            target
85            for target in policy.targets
86            if (node := self._registry.get(target.node)) is not None and node.status == "online"
87        ]
```

So the invariant the `# type: ignore` *assumes* is: "if `select()` returned a target, `registry.get(target.node)` is non-`None` at line 124." That invariant is a **check-then-use (TOCTOU)** assumption that holds only if the registry is not mutated between line 86/97 and line 124. It is mutated, by the control plane:

```python
# src/vampire/api/control.py
81    @router.delete("/nodes/{node_id}")
82    async def delete_node(node_id: str) -> dict[str, Any]:
83        if not registry.remove(node_id):
84            raise HTTPException(status_code=404, detail="node not found")
85        return {"id": node_id, "status": "removed"}
```

**Step-by-step interleaving that triggers the crash.** FastAPI/Starlette runs every request handler as a coroutine on one event loop; control passes between coroutines at every `await`. `_route_or_proxy` begins with `body = await request.body()` (line 86) and ends by `await proxy_request_with_body(...)` (line 122) — multiple suspension points. Consider request **R** (`POST /v1/chat/completions`, `model: "vampire:auto"`) and concurrent request **D** (`DELETE /vampire/v1/nodes/node-b`):

1. **R** enters `_route_or_proxy`, `await request.body()` (suspends; loop is free).
2. **R** resumes, calls `_router.select(...)` at line 97. `_candidates` reads `registry.get("node-b")` → present + online, so it is a candidate; round-robin returns `RouteTarget(node="node-b", model="node-b-model")`. `target` is now bound.
3. The handler proceeds to line 119-122; `await proxy_request_with_body(...)` is reached. Evaluating the *arguments* to that call requires `registry.get(target.node).lmstudio_base_url` (line 124) — but argument evaluation for `proxy_request_with_body` happens before the `await`, in **R**'s current synchronous run... **unless** the loop already yielded. The realistic window is broader than a single line: any `await` between step 2 and the read (e.g. the body re-serialization is sync, but the scheduler can still interleave **D** while **R** was suspended at step 1, completing the delete before **R** ever reaches line 97). The decisive fact is that `select()`'s existence check and the line-124 read are **two distinct registry lookups separated by handler logic**, and `delete_node` only needs to land in between.
4. **D** runs `registry.remove("node-b")` → returns `True`, node gone, HTTP 200 `{"status":"removed"}` to the deleting operator.
5. **R** evaluates line 124: `registry.get("node-b")` now returns `None`; `None.lmstudio_base_url` raises `AttributeError: 'NoneType' object has no attribute 'lmstudio_base_url'`.
6. The exception is uncaught in the handler. FastAPI's default 500 handler converts it to `500 Internal Server Error` with an empty/opaque body — **not** the OpenAI error envelope the rest of this module is careful to honor.

This is the same class of "node removed mid-flight" hazard already logged in `2026-06-14_0602-refresh-node-resurrects-deleted-nodes.md` (a `refresh_node`/`delete` race) — but it is a *different code path and different failure mode*: that report is about a delete being **silently undone**; this one is about a delete causing the **inference request to crash with a 500**. The `# type: ignore[union-attr]` is unique to this site and is the reason mypy/pyright cannot warn maintainers about it.

**Why the contract matters.** Everywhere else this module produces a structured OpenAI-compatible error envelope: `_route_or_proxy` returns a `503` with `{"error": {"type": "vampire_routing_error", "code": "no_route_target"}}` when no target is available (openai_compat.py:107-117), and `proxy.py:80-97` returns a `502 vampire_upstream_error` envelope for unreachable nodes. A bare 500 with no envelope violates DESIGN-API.md §23's error-format contract that the surrounding code goes out of its way to satisfy.

- **Impact:** A client doing legitimate routed inference receives an opaque `500 Internal Server Error` (no `error` object, no `type`, no `code`) — indistinguishable from a true server bug, and it breaks OpenAI-SDK clients that parse the error envelope. The operator who issued the DELETE sees a clean 200 and has no idea they raced a live request. Blast radius: any deployment where the control plane and data plane share the process (the default — both routers are mounted on the same app) and nodes are removed/cleared while traffic flows. Triggers naturally during: node decommissioning, `vampire` discovery re-scans that call `registry`-mutating paths, draining workflows, and automated health-driven node churn. It is invisible in the current single-threaded `TestClient` suite because no test issues a concurrent DELETE during an in-flight chat completion — so it ships silently, exactly as the `# type: ignore` intends.

- **Fix:** Re-fetch the node into a local variable, narrow it with an explicit `None` check, and on miss return the same structured 503 the no-target path already returns. This **removes the `# type: ignore[union-attr]` entirely** — the type checker now proves safety instead of being told to look away. The window does not need a lock for correctness here because a single re-read + check after selection collapses the check-to-use gap to a single synchronous lookup (no `await` between the check and the use), and the registry is a plain dict whose `.get()` is atomic w.r.t. the event loop; the remaining requirement is simply to handle the `None` result instead of dereferencing it.

```python
# BEFORE (src/vampire/api/openai_compat.py:119-132)
    routed_payload = dict(payload)
    routed_payload["model"] = target.model
    routed_payload.pop("vampire", None)
    return await proxy_request_with_body(
        request,
        downstream_base_url=registry.get(target.node).lmstudio_base_url,  # type: ignore[union-attr]
        body=json.dumps(routed_payload).encode("utf-8"),
        response_headers={
            "X-Vampire-Route": policy.id,
            "X-Vampire-Strategy": policy.strategy,
            "X-Vampire-Node": target.node,
            "X-Vampire-Model": target.model,
        },
    )
```

```python
# AFTER
    node = registry.get(target.node)
    if node is None:
        # The selected node was deregistered between routing and dispatch
        # (e.g. a concurrent DELETE /vampire/v1/nodes/{id}). Honor the
        # OpenAI error envelope (DESIGN-API.md §23) instead of crashing.
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": f"Selected route target node {target.node} is no longer registered.",
                    "type": "vampire_routing_error",
                    "code": "route_target_removed",
                }
            },
        )

    routed_payload = dict(payload)
    routed_payload["model"] = target.model
    routed_payload.pop("vampire", None)
    return await proxy_request_with_body(
        request,
        downstream_base_url=node.lmstudio_base_url,   # node is now provably Node, no ignore needed
        body=json.dumps(routed_payload).encode("utf-8"),
        response_headers={
            "X-Vampire-Route": policy.id,
            "X-Vampire-Strategy": policy.strategy,
            "X-Vampire-Node": target.node,
            "X-Vampire-Model": target.model,
        },
    )
```

Notes:
- **Remove** the `# type: ignore[union-attr]` on line 124 — after the narrowing, `node.lmstudio_base_url` is statically `str`.
- **Invariant to preserve:** error responses on the `/v1/*` surface must use the OpenAI `{"error": {...}}` envelope (DESIGN-API.md §23); the new 503 matches the existing `no_route_target` 503 shape so clients can parse it uniformly. Consider documenting the new `route_target_removed` code alongside `no_route_target` in DESIGN-API.md §23.
- No new dependency, no lock, no behavior change on the happy path. If stronger atomicity is later desired across the whole select→dispatch span, the registry is the correct seam (it already documents itself as the place to add coordination), but it is not required to fix this crash.

- **Test:** A regression test that deletes the target node *after selection but before dispatch* by monkeypatching `proxy_request_with_body` to remove the node on the way in — deterministically reproducing the interleaving without real threads. Today this raises `AttributeError → 500`; after the fix it returns a structured 503.

```python
# tests/test_phase3.py
def test_routed_request_returns_503_when_target_node_removed_mid_dispatch(
    client: TestClient,
) -> None:
    """A node deregistered between selection and dispatch must yield a
    structured 503, not an AttributeError-driven 500."""
    import vampire.api.openai_compat as oc
    from vampire.registry import registry

    client.post(
        "/vampire/v1/nodes", json={"id": "node-b", "lmstudio_base_url": "http://node-b:1234"}
    )
    client.post(
        "/vampire/v1/routes",
        json={
            "id": "route-auto",
            "virtual_model": "vampire:auto",
            "targets": [{"node": "node-b", "model": "node-b-model"}],
            "strategy": "round_robin",
        },
    )

    # Simulate the concurrent DELETE landing in the check-to-use window: the
    # router has already selected node-b, but it is gone before dispatch reads
    # registry.get(target.node).
    original = oc.proxy_request_with_body

    async def _evict_then_proxy(*args, **kwargs):  # type: ignore[no-untyped-def]
        registry.remove("node-b")
        return await original(*args, **kwargs)

    # With the fix, the None-check fires *before* proxy_request_with_body is
    # ever reached, so we instead evict inside the router selection seam:
    original_select = oc._router.select

    def _evict_then_select(policy, *, requested_model=None):  # type: ignore[no-untyped-def]
        target = original_select(policy, requested_model=requested_model)
        if target is not None:
            registry.remove(target.node)   # node vanishes after selection
        return target

    oc._router.select = _evict_then_select  # type: ignore[assignment]
    try:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "vampire:auto",
                "messages": [{"role": "user", "content": "hello"}],
                "vampire": {"mode": "route"},
            },
        )
    finally:
        oc._router.select = original_select

    assert resp.status_code == 503                                   # not 500
    body = resp.json()
    assert body["error"]["type"] == "vampire_routing_error"
    assert body["error"]["code"] == "route_target_removed"
```

Before the fix the assertion fails because the endpoint returns `500` with no `error` object (the `AttributeError` escapes). After the fix it returns the structured `503`. (The simplest, most deterministic seam is monkeypatching `_router.select` to evict the node it just chose, which models the race without timing flakiness.)

- **Effort & risk:** ~12 lines changed in one file (`src/vampire/api/openai_compat.py`), plus ~40 lines of new test and an optional one-paragraph DESIGN-API.md §23 note for the new `route_target_removed` code. Backward-compat: strictly improving — the happy path is byte-identical; the only behavioral change is converting a previously-uncaught 500 into a documented 503 envelope. Removing the `# type: ignore[union-attr]` will turn any future reintroduction of the bug into a CI type-check failure, which is the durable win. Low risk.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~205000 tok · output ~4600 tok · est. cost ~$3.42 · run started 16:28 finished 16:30.
