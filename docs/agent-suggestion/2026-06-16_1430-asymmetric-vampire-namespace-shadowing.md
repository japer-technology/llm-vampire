# Asymmetric `vampire:` namespace protection leads to silent model shadowing and routing hijacking

- **Severity:** High — Causes legitimate downstream models starting with `vampire:` to be silently hidden from the API and hijacked by the router.
- **Category:** contract / namespace boundary.
- **Summary:** The `vampire:` prefix is intended as a reserved namespace for virtual routing targets. However, the protection is asymmetric: the API gateway prevents users from *creating* virtual models that collide with physical ones, but it does nothing to prevent downstream nodes from serving models with these names. Consequently, any physical model starting with `vampire:` is silently stripped from the `list_models` response and treated as a routing request by the `Router`, causing legitimate model access to fail or be misrouted.
- **Location:** `src/vampire/api/openai_compat.py:39` (listing), `src/vampire/api/openai_compat.py:202` (routing), and `src/vampire/cluster.py:181` (missing validation at ingestion).
- **Evidence:**
```python
# src/vampire/api/openai_compat.py:39
39|        physical = [card for card in physical if card.id not in virtual_ids]
```
```python
# src/vampire/api/openai_compat.py:202
202|        model.startswith("vampire:")
```

1. The `list_models` implementation explicitly removes any physical model whose ID is in the `virtual_ids` set (which includes all `vampire:*` IDs), making them invisible to the client.
2. The `_is_routing_request` function returns `True` for any model name starting with `vampire:`, causing the router to attempt to resolve it as a virtual model rather than proxying to the physical one.
- **Validation:** The offending code is quoted verbatim from the file. The bug is not guarded at the ingestion site (`src/vampire/cluster.py`), where model cards from downstream nodes are accepted without validating their IDs against the `vampire:` prefix. A sibling implementation, `create_route` in `src/vampire/api/control.py`, enforces this at the control plane, but the data plane (ingestion) does not. The trigger is simply having a node in the cluster that serves a model with a name starting with `vampire:`.
- **Impact:** Clients attempting to use legitimate models that happen to have names starting with `vampire:` will experience "404 Not Found" or "503 No Route Target" errors, as the gateway will treat them as routing requests. Additionally, it creates a potential for routing hijacking if an untrusted node claims a name that was meant for an internal gateway function.
- **Fix:**
```python
# src/vampire/cluster.py (Before)
179|    for raw in data:
180|        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
181|            cards.append(ModelCard.model_validate(raw))

# src/vampire/cluster.py (After)
179|    for raw in data:
180|        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
181|            if not raw.get("id", "").startswith("vampire:"):
182|                cards.append(ModelCard.model_validate(raw))
```
- **Fix validation:** This fix closes the defect by ensuring that the registry never contains physical models that belong to the `vampire:` namespace, preventing both the "silent deletion" in the listing and the "routing hijacking" in the router. It matches the design intent of the control plane's 409 check. An alternative would be to rename the models (e.g., `vampire_physical:foo`), but that would require more complex logic in both the listing and routing logic; filtering at ingestion is a minimal, correct, and least-blast-radius approach for a reserved namespace.
- **Test:**
```python
import pytest
from unittest.mock import MagicMock
from vampire.cluster import _coerce_model_cards
from vampire.models import ModelCard

def test_coerce_model_cards_filters_vampire_namespace():
    # Mocking response data where one model is in the reserved namespace
    payload = {
        "data": [
            {"id": "gpt-4", "name": "GPT-4"},
            {"id": "vampire:auto", "name": "Shadowed Model"}
        ]
    }
    cards = _coerce_model_cards(payload)
    
    assert len(cards) == 1
    assert cards[0].id == "gpt-4"
    assert not any(c.id.startswith("vampire:") for c in cards)
```
- **Effort & risk:** lines changed: 1, files touched: 1 (`src/vampire/cluster.py`), backward-compat: Low, risk level: Low.
- **Scout link:** Addresses `2026-06-15_1818-strategic-scout-lifecycle-namespace-and-config-drift.md` - Target: AOI-B (the `vampire:` reserved namespace).
- **Receipt (estimated):** model `google/gemma-4-26b-a4b` (lmstudio) · input ~2.1K tok · output ~1.1K tok · run started 14:30 finished 14:31. _(Estimated from agent.log in=/out= for this run.)_

> APPLIED 2026-06-16 02:49 UTC on main (commit ff59268): tests green (121 passed, 1 deselected known live-LM-Studio flake; full suite otherwise 121 passed, 1 known flake). Awaiting review.
