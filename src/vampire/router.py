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
    """Chooses a node for a request once virtual routing lands.

    Phase 3 will implement the DESIGN-API.md §24 strategies listed in
    ``MVP_STRATEGIES``: round-robin, least-busy, least-latency, model-affinity,
    and trusted-only selection, with fallback/failover. The scaffold keeps the
    dependency boundary in place without changing Phase 1 passthrough behavior.
    """

    def __init__(self, registry: NodeRegistry) -> None:
        """Bind the router to the registry that supplies candidate nodes."""
        self._registry = registry

    def select(self, strategy: str = "round_robin") -> Node | None:
        """Return the first online candidate until real strategies are implemented.

        ``strategy`` is accepted now so callers can be written against the final
        routing signature, but only the future Phase 3 implementation will
        distinguish between the MVP strategy names.
        """
        nodes = [n for n in self._registry.list() if n.status == "online"]
        return nodes[0] if nodes else None
