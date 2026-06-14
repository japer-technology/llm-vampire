# `/v1/models` cards omit the OpenAI-required `created` field, breaking strict clients and drifting from DESIGN-API.md §5

**Severity:** High — This is the single most-hit read endpoint of the OpenAI compatibility surface (every SDK calls it at startup/model-pick time), the omission is a hard spec violation, and it is silently inconsistent: the *passthrough* path returns LM Studio's real `created` timestamps while the *aggregation* path strips them. Clients that validate the model object (OpenAI Python `Model` requires `created: int`; LangChain, LiteLLM, and several TUI/IDE pickers deserialize into typed structs) raise on the aggregated response but not the passthrough one, so the bug only manifests once the operator registers a node — i.e. exactly when Vampire stops being a dumb proxy and starts being Vampire. Not Critical because it does not corrupt inference traffic or leak data; it breaks discovery/model-listing for strict clients.

**Category:** API-correctness / OpenAI compatibility / spec drift

**Summary:** `GET /v1/models` synthesizes its response from `ModelCard` objects (`src/vampire/models.py:24`), and `ModelCard` has no `created` field. The OpenAI `/v1/models` schema and DESIGN-API.md §5 both require every model object to carry `created` (a Unix timestamp). As soon as one node is registered, `list_models` (`openai_compat.py:38-47`) builds the response purely from these `created`-less cards, so the gateway emits `{"id":...,"object":"model","owned_by":...}` with no `created` key — a malformed model object that diverges from both the spec sample and from what the same gateway returns in bare passthrough mode.

**Location:**
- `src/vampire/models.py:24-31` — `ModelCard` definition (no `created` field).
- `src/vampire/api/openai_compat.py:38-47` — `list_models` aggregation path that serializes those cards directly via `ModelListResponse(...).model_dump()`.
- `src/vampire/cluster.py:142-154` — `_coerce_model_cards` drops `created` on ingest from upstream nodes.
- `src/vampire/cluster.py:43-47` (virtual card construction at `openai_compat.py:43-45`) — synthesized `vampire:*` cards never get a `created`.
- Spec: `DESIGN-API.md:273-302` (§5 response sample, every entry has `"created": 1781234567`).

**Evidence:**

The model card model has exactly three declared fields and an `extra="allow"` config — but no `created`:

```python
# src/vampire/models.py:24
class ModelCard(BaseModel):
    """OpenAI-compatible model listing item."""

    id: str
    object: Literal["model"] = "model"
    owned_by: str = "lmstudio-vampire"

    model_config = ConfigDict(extra="allow")
```

The aggregation path builds the entire response from those cards and dumps it directly. Virtual cards are constructed inline with only `id` and `owned_by`; physical cards come from `aggregate_model_cards` → `_coerce_model_cards`:

```python
# src/vampire/api/openai_compat.py:35
@router.get("/models")
async def list_models(request: Request) -> Response:
    """Return registered-node model aggregation, falling back to Phase 1 passthrough."""
    if registry.list():
        nodes = await refresh_registered_nodes(client=_request_http_client(request))
        physical = aggregate_model_cards(nodes).data
        virtual_ids = {"vampire:auto"}
        virtual_ids.update(route.virtual_model for route in route_registry.list())
        virtual = [
            ModelCard(id=virtual_id, owned_by="vampire") for virtual_id in sorted(virtual_ids)
        ]
        physical = [card for card in physical if card.id not in virtual_ids]
        return JSONResponse(ModelListResponse(data=[*virtual, *physical]).model_dump())
    return await proxy_request(request)
```

`extra="allow"` would *preserve* a `created` value if one survived ingestion — but it does not survive, because `_coerce_model_cards` validates each upstream entry through `ModelCard.model_validate(raw)`:

```python
# src/vampire/cluster.py:142
def _coerce_model_cards(payload: object) -> list[ModelCard]:
    """Extract OpenAI-compatible model cards from a ``/v1/models`` response."""
    ...
    for raw in data:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            cards.append(ModelCard.model_validate(raw))
    return cards
```

`extra="allow"` means an upstream `created` *would* be retained when present — but LM Studio's `/v1/models` does emit `created`, so for physical models the bug is "only" that virtual cards lack it... except `aggregate_model_cards` (`cluster.py:221-227`) keys solely on `id` and the synthesized virtual cards at `openai_compat.py:43-45` are built with **no** `created` at all. So the response is guaranteed to contain at least the `vampire:auto` card with no `created` key the moment any node is registered.

Step-by-step manifestation:
1. Operator registers one node: `POST /vampire/v1/nodes` (or runs discovery). `registry.list()` is now non-empty.
2. A client calls `GET /v1/models`. Branch at `openai_compat.py:38` is taken (no longer passthrough).
3. `virtual = [ModelCard(id="vampire:auto", owned_by="vampire"), ...]` — each serializes to `{"id":"vampire:auto","object":"model","owned_by":"vampire"}`. **No `created`.**
4. Response is returned via `ModelListResponse(...).model_dump()` — `created` is absent for every virtual card (and for any physical model whose upstream happened not to send one).
5. A strict client deserializes. OpenAI Python's `openai.types.Model` declares `created: int` (required). `Model.construct`/validation raises `ValidationError: created field required`, or LiteLLM/LangChain model enumeration drops/errors on the entry. The user sees "no models available" or a hard crash at the model-picker — *only after* they registered a node, which makes it look like registration broke the gateway.
6. Reproduce the inconsistency directly:

```bash
# Bare passthrough (no nodes registered) — LM Studio's created flows through untouched:
curl -s localhost:8000/v1/models | jq '.data[0] | has("created")'   # -> true

# After registering one node — aggregation path strips/omits created:
curl -s localhost:8000/vampire/v1/nodes -d '{"id":"n1","lmstudio_base_url":"http://localhost:1234"}'
curl -s localhost:8000/v1/models | jq '.data[] | {id, created: (has("created"))}'
# vampire:auto -> created:false   (and any node model card lacking upstream created -> false)
```

The contract sample the code claims to implement is unambiguous (`DESIGN-API.md:273`):

```json
{
  "object": "list",
  "data": [
    { "id": "vampire:auto", "object": "model", "created": 1781234567, "owned_by": "vampire" },
    ...
  ]
}
```

Every entry in the spec carries `created`. The aggregation path produces entries that do not.

**Impact:**
- Strict OpenAI clients (OpenAI Python ≥1.x typed `Model`, LiteLLM, LangChain `ChatOpenAI` model listing, many IDE/TUI model pickers) fail to parse the aggregated model list, so model discovery breaks precisely when Vampire's orchestration is in use.
- Behavioral inconsistency between the passthrough and aggregation code paths: the same endpoint returns spec-valid objects before a node is registered and spec-invalid objects after. This is a silent regression that surfaces far from its cause and is painful to debug.
- Spec drift: the implementation contradicts its own cited contract (DESIGN-API.md §5), eroding the "drop-in compatible" guarantee that is the project's headline promise (§Overview line 20).
- Tests give false confidence: `test_phase3._mock_cluster` returns model cards without `created` (`tests/test_phase3.py:30-36`), so the suite asserts on a fixture that is itself non-compliant and the gap is invisible to CI.

**Fix:** Give `ModelCard` a `created` field with a sane default, preserve upstream `created` on ingest (already works via `extra="allow"` once the field exists, but make it explicit and typed), and stamp synthesized virtual cards with a timestamp. Use a single process-start epoch for virtual/synthetic cards so the value is stable across calls (OpenAI clients sometimes cache keyed on `created`); fall back to it for physical cards whose upstream omitted the field.

Before:

```python
# src/vampire/models.py:24
class ModelCard(BaseModel):
    """OpenAI-compatible model listing item."""

    id: str
    object: Literal["model"] = "model"
    owned_by: str = "lmstudio-vampire"

    model_config = ConfigDict(extra="allow")
```

After:

```python
# src/vampire/models.py
import time

# Stable epoch for synthesized cards: clients may cache keyed on `created`,
# so a per-process constant avoids the value changing on every /v1/models call.
_SYNTHETIC_CREATED = int(time.time())


class ModelCard(BaseModel):
    """OpenAI-compatible model listing item.

    ``created`` is required by the OpenAI ``/v1/models`` schema (DESIGN-API.md
    §5). Upstream LM Studio cards carry it through unchanged; synthesized
    virtual/physical cards fall back to the process-start epoch.
    """

    id: str
    object: Literal["model"] = "model"
    created: int = _SYNTHETIC_CREATED
    owned_by: str = "lmstudio-vampire"

    model_config = ConfigDict(extra="allow")
```

That single change fixes every path, because:
- Virtual cards at `openai_compat.py:43-45` now serialize with `created=_SYNTHETIC_CREATED`.
- `_coerce_model_cards` (`cluster.py:153`) validates upstream entries: when LM Studio sends `created`, Pydantic binds it to the new field (preserved); when it doesn't, the default fills in.
- `aggregate_model_cards` and `physical_model_inventory` are unaffected in shape but now propagate `created`.

No `# type: ignore` exists to remove here. Docs to update: none required for the contract (the spec already mandates `created`); optionally add a one-line note to `DESIGN-API.md` §5 clarifying that synthesized `vampire:*` cards use the gateway process-start epoch. Also fix the misleading test fixture `tests/test_phase3.py:30-36` to include `created`, so it matches real LM Studio responses.

**Test:** Add to `tests/test_phase3.py` (reuses the existing `client` fixture and a registered node). Fails today (KeyError/assert on missing `created`), passes after the fix.

```python
def test_models_listing_includes_created_for_every_card(client: TestClient) -> None:
    """Every /v1/models entry must carry an int `created` (OpenAI schema, DESIGN-API.md §5)."""
    # Register a node so list_models takes the aggregation branch, not passthrough.
    registry.add(
        Node(
            id="node-a",
            lmstudio_base_url="http://node-a:1234",
            status="online",
            trusted=True,
            models=[ModelCard(id="node-a-model")],
        )
    )

    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data, "expected at least the synthesized vampire:auto card"

    # The synthesized virtual card and every physical card must be spec-valid.
    for card in data:
        assert "created" in card, f"model card {card.get('id')!r} is missing required 'created'"
        assert isinstance(card["created"], int)

    virtual = next(c for c in data if c["id"] == "vampire:auto")
    assert virtual["created"] > 0
```

To make the fixture itself compliant (so it mirrors real LM Studio and can't mask future regressions), also update `_mock_cluster`:

```python
# tests/test_phase3.py:30  (inside the mock /v1/models data list)
{
    "id": f"{host}-model",
    "object": "model",
    "created": 1781234567,
    "owned_by": "lmstudio",
},
```

**Effort & risk:** Effort ~15 minutes (one field, one fixture line, one test). Risk: very low. The change is purely additive — `extra="allow"` already tolerated unknown keys, so no existing serialization shrinks; the only observable difference is that responses now *gain* a required field. The single subtlety is choosing a per-process constant vs. `Field(default_factory=...)`: a `default_factory=lambda: int(time.time())` would make `created` drift on every instantiation, which can defeat client-side caches keyed on `created`; the module-level constant avoids that. No public type signatures change; `model_dump()` output is a strict superset of today's.

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~170,000 tok · output ~4,500 tok · est. cost ~$2.89 · run started 08:40 finished 08:42. Estimated from `agent.log` session `20260614_184033` (sum of `in=`/`out=` across this run's API calls, plus the final compose call); Opus pricing $15/1M input, $75/1M output.
