"""Virtual-model router (Phase 3 scaffold).

Selects a physical node/model for a virtual model such as ``vampire:auto`` using
one of the MVP routing strategies (DESIGN-API.md §24): round_robin, least_busy,
least_latency, model_affinity, trusted_only, plus fallback/failover.
"""

from __future__ import annotations

from vampire.models import Node
from vampire.registry import NodeRegistry

MVP_STRATEGIES = (
    "round_robin",
    "least_busy",
    "least_latency",
    "model_affinity",
    "trusted_only",
)


class Router:
    """Chooses a node for a request. Scaffold implementation only."""

    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry

    def select(self, strategy: str = "round_robin") -> Node | None:
        """Return a candidate node. Phase 3 will implement real strategies."""
        nodes = [n for n in self._registry.list() if n.status == "online"]
        return nodes[0] if nodes else None
