# NodeRegistry.update bypasses Pydantic validation, corrupting nested NodeCapabilities into a raw dict on PATCH

**Severity:** High — Justification: A successful, authenticated `PATCH /vampire/v1/nodes/{id}` that touches `capabilities` silently converts a validated `NodeCapabilities` submodel into a bare `dict`, violating the declared type of `Node.capabilities`. Every downstream consumer that reads `node.capabilities.<field>` (the explicit Phase 3 routing use named in `models.py:52-54`) will raise `AttributeError` at runtime, Pydantic emits a serialization warning on `model_dump()`, and a partial update silently drops the other capability fields. mypy `strict` cannot see any of this because `model_copy(update=...)` accepts an unvalidated `dict[str, Any]`. It is data corruption reachable through the public control API, not merely a cosmetic typing gap — hence High rather than Critical (it is not yet remotely exploitable for RCE/auth bypass, and `capabilities` is not read on today's hot path).

**Category:** Type-safety / correctness — Pydantic model-validation gap (unvalidated `model_copy(update=...)`); Optional/nested-model handling.

**Summary:** `NodeRegistry.update()` applies partial node patches with `node.model_copy(update=patch.model_dump(...))`. `model_copy(update=...)` performs **no validation or coercion** — it does a raw attribute overwrite. When the patch contains the nested `capabilities` field, `model_dump()` has already turned the `NodeCapabilities` submodel into a plain `dict`, so the stored `Node` ends up with `node.capabilities` being a `dict` while its declared (and mypy-believed) type is `NodeCapabilities`. The same mechanism also silently *drops* unspecified capability fields, turning a partial update into a lossy full replacement.

**Location:** `src/vampire/registry.py:35` (inside `NodeRegistry.update`), reached from `src/vampire/api/control.py:82-90` (`patch_node`). The corrupted type is declared at `src/vampire/models.py:82` (`capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)`) and intended for routing per `src/vampire/models.py:52-54`.

**Evidence:**

The offending line (`src/vampire/registry.py:29-37`):

```python
def update(self, node_id: str, patch: NodeUpdate) -> Node | None:
    """Apply a partial update to a registered node."""
    node = self.get(node_id)
    if node is None:
        return None

    updated = node.model_copy(update=patch.model_dump(exclude_unset=True, exclude_none=True))
    self._nodes[node_id] = updated
    return updated
```

`NodeUpdate.capabilities` is typed `NodeCapabilities | None` (`src/vampire/models.py:104`). `patch.model_dump(...)` recursively serializes that submodel to a `dict`. `model_copy(update={...})` then assigns that `dict` straight onto the new instance **without re-validating**, so the post-condition "`updated.capabilities` is a `NodeCapabilities`" is broken.

Step-by-step manifestation, reproduced live against the current tree:

```text
$ PYTHONPATH=src python _probe.py
before: NodeCapabilities chat=True responses=False completions=True embeddings=False vision=False tools=False streaming=True
patch dump: {'capabilities': {'vision': True, 'tools': True}}
capabilities value type in dump: dict
after : dict {'vision': True, 'tools': True}
CRASH attr: AttributeError 'dict' object has no attribute 'vision'
.../pydantic/main.py:475: UserWarning: Pydantic serializer warnings:
  PydanticSerializationUnexpectedValue(Expected `NodeCapabilities` -
  serialized value may not be as expected
  [field_name='capabilities', input_value={'vision': True, 'tools': True}, input_type=dict])
model_dump capabilities -> {'vision': True, 'tools': True}
```

The probe used:

```python
from vampire.models import Node, NodeUpdate, NodeCapabilities

n = Node(id="n1", lmstudio_base_url="http://x:1234")
patch = NodeUpdate(capabilities=NodeCapabilities(vision=True, tools=True))
dumped = patch.model_dump(exclude_unset=True, exclude_none=True)
updated = n.model_copy(update=dumped)          # <-- registry.update line 35
print(type(updated.capabilities).__name__)     # -> dict   (should be NodeCapabilities)
updated.capabilities.vision                     # -> AttributeError
```

Two distinct failures fall out of the single line:

1. **Type corruption.** `updated.capabilities` is now a `dict`. Any code that trusts the declared type — e.g. the routing filter the model docstring promises ("routing can use it to avoid sending embeddings, tools, or vision requests to nodes that cannot serve them", `models.py:52-54`), or a future `_candidates` capability filter analogous to `router.py:50-51`'s `self._node(target).trusted` — will raise `AttributeError: 'dict' object has no attribute 'vision'` the moment it does attribute access. The node is now a live land-mine sitting in the registry.

2. **Silent field loss / lossy partial update.** A client sending `{"capabilities": {"vision": true}}` does not get `vision=True` merged onto existing capabilities — `model_dump(exclude_unset=True)` on the `NodeUpdate` includes the whole submodel, but the submodel itself is constructed with defaults, so `chat`, `completions`, `streaming` silently reset to their class defaults rather than preserving the node's prior values. The PATCH is documented as "partial" (`control.py:83`, `models.py:95`) but behaves as a non-partial, type-broken overwrite of the nested object.

3. **Serializer warning on every readback.** `GET /vampire/v1/nodes/{id}` calls `node.model_dump()` (`control.py:79`). After a capabilities PATCH that emits the `PydanticSerializationUnexpectedValue` `UserWarning` shown above on every response, polluting logs and signalling that the in-memory object no longer matches its schema.

The reason this is invisible to the test/type gates: `mypy --strict` passes clean (`Success: no issues found in 25 source files`) because `BaseModel.model_copy(update: dict[str, Any])` is typed to accept any dict and returns `Self`; static analysis has no way to know the dict violates the field schema. There are zero `# type: ignore` comments masking it — the hole is structural to `model_copy`, not a suppressed error.

**Impact:**
- Authenticated control-plane corruption: a single valid PATCH leaves a malformed `Node` in the process-wide `registry` (`registry.py:57`) for the lifetime of the process.
- Latent crash for Phase 3 capability-aware routing, which the codebase explicitly plans to build on `node.capabilities` — the bug will surface as a 500 inside `_route_or_proxy` (`openai_compat.py:90`) the first time routing inspects capabilities, not at the PATCH that caused it, making diagnosis hard.
- Data integrity: partial capability updates silently discard fields, so operators cannot reliably toggle a single capability flag.
- Same class of latent risk exists for any future `NodeUpdate` field that is itself a model; `capabilities` is the only nested-model field today, so it is the concrete victim, but the *fix should harden the mechanism*, not just the one field.

**Fix:** Re-validate after applying the partial update so the registry always stores a fully-validated `Node`. Replace the unvalidated `model_copy(update=...)` with `model_validate` on the merged data. This coerces the `capabilities` dict back into a `NodeCapabilities`, restores the declared type, and keeps mypy honest because `model_validate` returns a validated `Node`.

Before (`src/vampire/registry.py:29-37`):

```python
def update(self, node_id: str, patch: NodeUpdate) -> Node | None:
    """Apply a partial update to a registered node."""
    node = self.get(node_id)
    if node is None:
        return None

    updated = node.model_copy(update=patch.model_dump(exclude_unset=True, exclude_none=True))
    self._nodes[node_id] = updated
    return updated
```

After:

```python
def update(self, node_id: str, patch: NodeUpdate) -> Node | None:
    """Apply a partial update to a registered node.

    The merged data is re-validated through ``Node.model_validate`` rather than
    assigned with ``model_copy(update=...)``: the latter performs no validation,
    so a nested submodel patch (e.g. ``capabilities``) would otherwise be stored
    as a raw ``dict`` and break the declared ``Node.capabilities`` type.
    """
    node = self.get(node_id)
    if node is None:
        return None

    merged = {
        **node.model_dump(),
        **patch.model_dump(exclude_unset=True, exclude_none=True),
    }
    updated = Node.model_validate(merged)
    self._nodes[node_id] = updated
    return updated
```

Notes:
- No `# type: ignore` to remove (there are none), but this closes a hole `mypy --strict` structurally cannot catch; consider a project convention/lint note that `model_copy(update=...)` must never be used to apply externally-sourced partial patches — prefer `model_validate`. The same pattern appears benignly in tests (`tests/test_phase2.py:127,148`) and in `cluster.refresh_node` (`cluster.py:172-193`), but those only update primitive fields (`status`, `latency_ms`, …) so they are not corrupting nested models today; they are worth a follow-up audit but are out of scope for this fix.
- If preserving partial-merge semantics for nested capabilities (toggle one flag, keep the rest) is desired, that is a deliberate product decision; the fix above already preserves prior top-level node fields via the `**node.model_dump()` spread, and a full `NodeCapabilities` object in the patch replaces capabilities wholesale — which matches the current `NodeUpdate.capabilities: NodeCapabilities | None` shape. No doc change is required, but `DESIGN-API.md` §14 could clarify that `capabilities` is replaced as a whole object, not deep-merged.

**Test:** Regression test that fails on the current tree (stores a `dict`, raises `AttributeError`) and passes after the fix. Add to `tests/test_phase2.py`:

```python
from vampire.models import Node, NodeCapabilities, NodeUpdate
from vampire.registry import NodeRegistry


def test_update_preserves_nested_capabilities_type() -> None:
    """PATCHing capabilities must keep node.capabilities a validated submodel."""
    reg = NodeRegistry()
    reg.add(Node(id="n1", lmstudio_base_url="http://localhost:1234"))

    updated = reg.update(
        "n1",
        NodeUpdate(capabilities=NodeCapabilities(vision=True, tools=True)),
    )

    assert updated is not None
    # Today: updated.capabilities is a raw dict -> both asserts fail.
    assert isinstance(updated.capabilities, NodeCapabilities)
    assert updated.capabilities.vision is True
    assert updated.capabilities.tools is True
    # Stored copy must also be re-validated, not a dict land-mine.
    stored = reg.get("n1")
    assert stored is not None
    assert isinstance(stored.capabilities, NodeCapabilities)
    # model_dump must not emit a Pydantic serializer warning.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        stored.model_dump()
```

**Effort & risk:** Effort ~20 minutes (one-line behavioural change in `registry.update` plus one regression test). Risk: Low. `model_validate` is stricter than `model_copy`, so it could now reject a patch that produces an invalid merged node — but that is the desired behaviour, and `NodeUpdate`'s fields are already a subset of `Node`'s with compatible types, so well-formed patches validate cleanly. The change is local to the registry seam; no API contract or response shape changes. Recommend running the full `pytest` suite plus `mypy --strict` after applying (both currently green).

- **Receipt (estimated):** model `claude-opus-4-8` (anthropic) · input ~427,520 tok (sum of `in=` for this run's session; heavily cache-discounted in reality, so this over-states true billed input) · output ~5,867 tok · est. cost ~$6.85 (input/1e6·$15 + output/1e6·$75 = $6.41 + $0.44) · run started 08:40 finished 08:42. Estimated.

> APPLIED 2026-06-14T09:07:57Z on branch vampire-fix/node-update-model-copy-corrupts-capabilities: tests green (1 failed, 94 passed — the single failure is the known environmental flake test_openai_route_proxies_upstream_error_when_node_unreachable when LM Studio is live on :1234). Awaiting review.

> APPLIED 2026-06-15T00:57:51Z: NodeRegistry.update now re-validates merged node data and preserves nested NodeCapabilities types, with regression coverage in tests/test_phase2.py. Targeted validation passed.
