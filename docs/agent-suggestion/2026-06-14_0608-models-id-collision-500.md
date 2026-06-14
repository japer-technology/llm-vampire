# `/v1/models` returns HTTP 500 when a virtual model id collides with a physical model id

- **Severity:** High — a routine, operator-reachable configuration (a route whose `virtual_model` equals an existing physical model id) takes the single most-polled OpenAI-compatibility endpoint, `GET /v1/models`, completely offline with an opaque 500 for *all* clients, not just the colliding model.
- **Category:** error-handling / api-correctness.
- **Status:** Suggestion taken with notes.
- **Notes:** Implemented virtual/physical model de-duplication on `/v1/models` and route creation rejection for physical-id collisions.
- **Summary:** `list_models` concatenates the synthesized virtual model cards with the aggregated physical model cards and feeds the combined list straight into `ModelListResponse`, whose `keep_model_ids_unique` validator raises `ValueError` on any duplicate id. A virtual id (`vampire:auto`, or any route's `virtual_model`) that matches a physical model id served by a registered node is never reconciled, so model construction throws *inside the request handler*, FastAPI converts the uncaught `pydantic.ValidationError` into a bare `500 Internal Server Error`, and the endpoint is unusable until the collision is removed. The `POST /vampire/v1/routes` handler does nothing to prevent an operator from creating such a colliding route.
- **Location:**
  - `src/vampire/api/openai_compat.py:30-42` (the `list_models` handler that builds the combined list).
  - `src/vampire/models.py:40-46` (the `keep_model_ids_unique` validator that raises).
  - `src/vampire/api/control.py:130-135` (`create_route`, which validates `strategy` but never rejects a `virtual_model` that collides with a physical model id).

## Evidence

The handler unconditionally merges virtual + physical cards and constructs the response model in one expression:

```python
# src/vampire/api/openai_compat.py
30  @router.get("/models")
31  async def list_models(request: Request) -> Response:
32      """Return registered-node model aggregation, falling back to Phase 1 passthrough."""
33      if registry.list():
34          nodes = await refresh_registered_nodes()
35          physical = aggregate_model_cards(nodes).data
36          virtual_ids = {"vampire:auto"}
37          virtual_ids.update(route.virtual_model for route in route_registry.list())
38          virtual = [
39              ModelCard(id=virtual_id, owned_by="vampire") for virtual_id in sorted(virtual_ids)
40          ]
41          return JSONResponse(ModelListResponse(data=[*virtual, *physical]).model_dump())
42      return await proxy_request(request)
```

`aggregate_model_cards` (`cluster.py:196-202`) de-dupes *physical-vs-physical* ids via `cards.setdefault(...)`, and the `virtual_ids` `set` de-dupes *virtual-vs-virtual* ids. **Nothing** de-dupes *virtual-vs-physical*. The list at line 41 can therefore contain two cards with the same id, which the response model forbids:

```python
# src/vampire/models.py
40      @field_validator("data")
41      @classmethod
42      def keep_model_ids_unique(cls, data: list[ModelCard]) -> list[ModelCard]:
43          ids = [model.id for model in data]
44          if len(ids) != len(set(ids)):
45              raise ValueError("model ids must be unique")
46          return data
```

`create_route` accepts the colliding policy without complaint — it guards only the strategy:

```python
# src/vampire/api/control.py
130  @router.post("/routes")
131  async def create_route(route: RoutePolicy) -> dict[str, Any]:
132      """Create or replace a virtual-model route policy (§16)."""
133      if route.strategy not in MVP_STRATEGIES:
134          raise HTTPException(status_code=400, detail="unsupported routing strategy")
135      return route_registry.add(route).model_dump()
```

### Reproduction (executed against the repo at HEAD `4794d6b`)

A mock LM Studio node serving a model literally named `shared-model`, plus a route whose `virtual_model` is also `shared-model`:

```python
mock = FastAPI()
@mock.get('/v1/models')
async def models(request):
    return JSONResponse({'object':'list','data':[
        {'id':'shared-model','object':'model','owned_by':'lmstudio'}]})
proxy.build_async_client = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=mock))

c = TestClient(create_app())
c.post('/vampire/v1/nodes', json={'id':'node-a','lmstudio_base_url':'http://node-a:1234'})
c.post('/vampire/v1/routes', json={'id':'r1','virtual_model':'shared-model',
       'targets':[{'node':'node-a','model':'shared-model'}],'strategy':'round_robin'})
r = c.get('/v1/models')
```

Observed result — `r.status_code == 500`, body `Internal Server Error`, with this server-side traceback:

```
File ".../src/vampire/api/openai_compat.py", line 41, in list_models
    return JSONResponse(ModelListResponse(data=[*virtual, *physical]).model_dump())
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for ModelListResponse
data
  Value error, model ids must be unique [type=value_error, input_value=[ModelCard(id='shared-mod...', owned_by='lmstudio')], input_type=list]
```

### Conditions under which it manifests

1. At least one node is registered (so the branch at line 33 is taken rather than the Phase-1 passthrough).
2. Some id appears in **both** the virtual set and the physical aggregation. Two realistic ways this occurs:
   - **Operator route collision (primary):** an operator `POST`s a route whose `virtual_model` equals a model id a node actually serves. `create_route` has no guard, so this is accepted, then poisons every subsequent `GET /v1/models`.
   - **Downstream naming collision:** a node serves a model whose id is literally `vampire:auto` (the always-present built-in virtual id at line 36). No operator action is even required — just a node whose catalogue happens to use that string.

There is no `try/except` anywhere on the path, and `create_app()` (`app.py:24-45`) registers no exception handler for `ValueError`/`ValidationError`, so the exception escapes to Starlette and becomes a generic 500.

## Impact

- **Endpoint-wide outage, not per-model.** `GET /v1/models` is the discovery call almost every OpenAI-compatible client (the OpenAI SDK, LangChain, LM Studio's own UI, `litellm`, Open WebUI) issues on connect and on model-picker refresh. One colliding route makes the *entire* model list return 500, so clients can't enumerate **any** model — the blast radius is every model on every node, triggered by one bad row.
- **Opaque failure.** The client sees a bare `Internal Server Error` with no OpenAI error envelope, violating the project's own contract that gateway failures use the `{"error": {...}}` shape (DESIGN-API.md §23, honored e.g. by `proxy._upstream_error` at `proxy.py:80-97` and by the routing-error branch at `openai_compat.py:107-117`). Operators get no signal that a *route they created* is the cause.
- **Trivially reachable.** The collision is a plausible operator mistake — naming a virtual model after a popular physical model (e.g. a route `qwen2.5-coder` fronting nodes that also expose `qwen2.5-coder`) is a natural thing to do, and the system rewards it with a sitewide outage rather than a 400 at route-creation time.

## Fix

Two complementary changes — make the read path total (never 500 on a recoverable data condition), and make the write path reject the collision early with a proper 4xx.

**1. De-duplicate virtual-vs-physical in `list_models`, preferring the virtual card.** Virtual ids are Vampire's own namespace and should win; drop any physical card whose id is already claimed by a virtual id. This makes the endpoint total regardless of route configuration.

```python
# src/vampire/api/openai_compat.py  (after)
@router.get("/models")
async def list_models(request: Request) -> Response:
    """Return registered-node model aggregation, falling back to Phase 1 passthrough."""
    if registry.list():
        nodes = await refresh_registered_nodes()
        physical = aggregate_model_cards(nodes).data
        virtual_ids = {"vampire:auto"}
        virtual_ids.update(route.virtual_model for route in route_registry.list())
        virtual = [
            ModelCard(id=virtual_id, owned_by="vampire") for virtual_id in sorted(virtual_ids)
        ]
        # A virtual id may collide with a physical model id (e.g. an operator route
        # named after a real model). Virtual ids own the Vampire namespace, so the
        # virtual card wins and the duplicate physical card is dropped, keeping the
        # OpenAI `/v1/models` contract (unique ids) intact instead of raising a 500.
        physical = [card for card in physical if card.id not in virtual_ids]
        return JSONResponse(ModelListResponse(data=[*virtual, *physical]).model_dump())
    return await proxy_request(request)
```

**2. Reject colliding routes at creation with a 409/400** so operators get an actionable error instead of silently arming a landmine. (Defense in depth — the read path is now safe, but failing fast at write time is the better operator experience.)

```python
# src/vampire/api/control.py  (after)
@router.post("/routes")
async def create_route(route: RoutePolicy) -> dict[str, Any]:
    """Create or replace a virtual-model route policy (§16)."""
    if route.strategy not in MVP_STRATEGIES:
        raise HTTPException(status_code=400, detail="unsupported routing strategy")
    physical_ids = {model.id for node in registry.list() for model in node.models}
    if route.virtual_model in physical_ids:
        raise HTTPException(
            status_code=409,
            detail=f"virtual_model '{route.virtual_model}' collides with a physical model id",
        )
    return route_registry.add(route).model_dump()
```

- **Invariant to preserve:** every `ModelCard` id in a `ModelListResponse` is unique (the existing `keep_model_ids_unique` validator stays — fix #1 guarantees the handler never violates it). The validator is *correct*; the bug is that the caller fed it data it never reconciled.
- **`# type: ignore` note:** none on this path to remove, but the unrelated `# type: ignore[union-attr]` at `openai_compat.py:124` is masking the same class of latent crash (it asserts `registry.get(target.node)` is non-None; a refresh that drops the node between `select` and `get` would `AttributeError`). Out of scope here but worth a follow-up.
- **Docs:** none required; this restores the documented §23 error contract rather than changing it.

## Test

A regression test that fails today (500) and passes after fix #1 — drop it in `tests/test_phase3.py`, which already has the `client` + `_mock_cluster` fixtures that make every node serve a `"{host}-model"` card:

```python
def test_models_endpoint_survives_virtual_physical_id_collision(client: TestClient) -> None:
    # node-a serves a physical model id "node-a-model" (per _mock_cluster).
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )
    # Operator names a route's virtual_model after that exact physical id.
    client.post(
        "/vampire/v1/routes",
        json={
            "id": "collide",
            "virtual_model": "node-a-model",
            "targets": [{"node": "node-a", "model": "node-a-model"}],
            "strategy": "round_robin",
        },
    )

    resp = client.get("/v1/models")

    assert resp.status_code == 200  # FAILS today with 500
    ids = [card["id"] for card in resp.json()["data"]]
    assert len(ids) == len(set(ids))            # unique ids preserved
    assert ids.count("node-a-model") == 1       # collision collapsed, not duplicated
    # The surviving card is the virtual one (Vampire namespace wins).
    card = next(c for c in resp.json()["data"] if c["id"] == "node-a-model")
    assert card["owned_by"] == "vampire"
```

And for fix #2 (write-path guard):

```python
def test_create_route_rejects_physical_model_id_collision(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )
    resp = client.post(
        "/vampire/v1/routes",
        json={
            "id": "collide",
            "virtual_model": "node-a-model",
            "targets": [{"node": "node-a", "model": "node-a-model"}],
            "strategy": "round_robin",
        },
    )
    assert resp.status_code == 409
```

(Note: `node-a-model` only appears in the aggregation after the registration probe runs, which the `_mock_cluster` fixture handles synchronously during the `POST /vampire/v1/nodes` call, so both tests are deterministic.)

## Effort & risk

- **Lines changed:** ~3 lines added in `openai_compat.py:list_models`; ~5 lines in `control.py:create_route`; ~2 short tests (~35 lines) in `tests/test_phase3.py`. Two source files touched, one test file.
- **Backward-compat:** Fix #1 is strictly safer — it can only *remove* a duplicate that would otherwise 500; clients already could not see both cards (the endpoint was dead). Fix #2 changes one previously-accepted (200) `POST /vampire/v1/routes` outcome to 409; this is an intended hardening, but if any existing automation deliberately creates same-named routes it would now get a 4xx — acceptable since such a route was a latent outage. If strict backward-compat on the write path is required, ship fix #1 alone (sufficient to eliminate the 500) and downgrade fix #2 to a logged warning.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~unknown (Hermes `turn_context` logged no per-turn token counts for this session window; largest observable context not emitted) · output ~3400 tok (≈13.6 KB file content at ~4 chars/tok) · est. cost ~$0.26 (output-only: 3400/1e6×75; input not priced for lack of a logged figure) · run started 06:08 finished 06:10. Marked estimated — final output tokens are emitted after logging, so this is a close lower-bound, not an exact invoice.
