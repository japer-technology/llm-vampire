"""Virtual-model router (Phase 3 scaffold).

Selects a physical node/model for a virtual model such as ``vampire:auto`` using
one of the MVP routing strategies (DESIGN-API.md §24): round_robin, least_busy,
least_latency, model_affinity, trusted_only, plus fallback/failover.
"""

from __future__ import annotations

from collections import defaultdict

from vampire.models import Node, RoutePolicy, RouteTarget
from vampire.registry import NodeRegistry

MVP_STRATEGIES = (
    "round_robin",
    "least_busy",
    "least_latency",
    "model_affinity",
    "trusted_only",
)


class Router:
    """Choose node/model targets for Phase 3 virtual-model routing."""

    def __init__(self, registry: NodeRegistry) -> None:
        """Bind the router to the registry that supplies candidate nodes."""
        self._registry = registry
        self._cursors: defaultdict[str, int] = defaultdict(int)

    def select(
        self, policy: RoutePolicy, *, requested_model: str | None = None
    ) -> RouteTarget | None:
        """Return a node/model pair selected by the policy's MVP strategy."""
        strategy = policy.strategy
        if strategy not in MVP_STRATEGIES:
            strategy = "round_robin"

        candidates = self._candidates(policy)
        if strategy == "trusted_only":
            candidates = [target for target in candidates if self._node(target).trusted]

        if not candidates:
            return None

        if strategy == "least_busy":
            return min(candidates, key=lambda target: self._busy_score(self._node(target)))
        if strategy == "least_latency":
            return min(candidates, key=lambda target: self._latency_score(self._node(target)))
        if strategy == "model_affinity":
            return self._model_affinity(candidates, requested_model) or self._round_robin(
                candidates, policy.id
            )
        return self._round_robin(candidates, policy.id)

    def default_policy(
        self,
        virtual_model: str,
        *,
        strategy: str = "round_robin",
        requested_model: str | None = None,
    ) -> RoutePolicy:
        """Create an ephemeral policy spanning all currently online node models."""
        targets = [
            RouteTarget(node=node.id, model=model.id)
            for node in self._registry.list()
            if node.status == "online"
            for model in node.models
            if requested_model is None
            or requested_model.startswith("vampire:")
            or model.id == requested_model
        ]
        return RoutePolicy(
            id=f"default:{virtual_model}",
            virtual_model=virtual_model,
            targets=targets,
            strategy=strategy,
        )

    def _candidates(self, policy: RoutePolicy) -> list[RouteTarget]:
        """Return online targets whose nodes are currently registered."""
        return [
            target
            for target in policy.targets
            if (node := self._registry.get(target.node)) is not None and node.status == "online"
        ]

    def _node(self, target: RouteTarget) -> Node:
        """Return a registered node for a known-valid target."""
        node = self._registry.get(target.node)
        if node is None:
            raise RuntimeError(f"route target references missing node {target.node}")
        return node

    def _round_robin(self, candidates: list[RouteTarget], route_id: str) -> RouteTarget:
        """Select the next candidate for ``route_id`` and advance its cursor."""
        index = self._cursors[route_id] % len(candidates)
        self._cursors[route_id] += 1
        return candidates[index]

    @staticmethod
    def _busy_score(node: Node) -> tuple[int, int, str]:
        """Sort least-busy candidates by queue depth, active requests, then id."""
        return (node.queue_depth, node.active_requests, node.id)

    @staticmethod
    def _latency_score(node: Node) -> tuple[float, str]:
        """Sort least-latency candidates, treating unknown latency as worst."""
        return (node.latency_ms if node.latency_ms is not None else float("inf"), node.id)

    @staticmethod
    def _model_affinity(
        candidates: list[RouteTarget], requested_model: str | None
    ) -> RouteTarget | None:
        """Prefer a target whose physical model matches the requested model."""
        if requested_model is None or requested_model.startswith("vampire:"):
            return None
        return next((target for target in candidates if target.model == requested_model), None)
