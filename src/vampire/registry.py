"""In-memory node registry (Phase 2 scaffold).

Holds the set of approved LM Studio nodes. v0 keeps everything in process
memory; a SQLite (``aiosqlite``) persistence seam is planned per METHOD-A.md.
"""

from __future__ import annotations

from vampire.models import Node, NodeUpdate, RoutePolicy, ShareStatus, ShareUpdate


class NodeRegistry:
    """A minimal in-memory registry of owner-approved LM Studio nodes.

    The registry is intentionally process-local for the Phase 0/1 scaffold. It
    is the seam where Phase 2 can add SQLite persistence without changing the
    control API handlers or routing code that already depend on this interface.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._nodes: dict[str, Node] = {}

    def add(self, node: Node) -> Node:
        """Store or replace ``node`` by id and return the stored model."""
        self._nodes[node.id] = node
        return node

    def update(self, node_id: str, patch: NodeUpdate) -> Node | None:
        """Apply a partial update to a registered node."""
        node = self.get(node_id)
        if node is None:
            return None

        merged = {**node.model_dump(), **patch.model_dump(exclude_unset=True, exclude_none=True)}
        updated = Node.model_validate(merged)
        self._nodes[node_id] = updated
        return updated

    def mark_busy(self, node_id: str) -> None:
        """Record one in-flight request for a registered node."""
        node = self._nodes.get(node_id)
        if node is not None:
            self._nodes[node_id] = node.model_copy(
                update={"active_requests": node.active_requests + 1}
            )

    def mark_idle(self, node_id: str) -> None:
        """Release one in-flight request for a registered node."""
        node = self._nodes.get(node_id)
        if node is not None:
            self._nodes[node_id] = node.model_copy(
                update={"active_requests": max(0, node.active_requests - 1)}
            )

    def get(self, node_id: str) -> Node | None:
        """Return a node by id, or ``None`` when it is not registered."""
        return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        """Remove a node by id and report whether anything was removed."""
        return self._nodes.pop(node_id, None) is not None

    def list(self) -> list[Node]:
        """Return registered nodes in insertion order as a snapshot list."""
        return list(self._nodes.values())

    def clear(self) -> None:
        """Remove all process-local registrations."""
        self._nodes.clear()


# Process-wide registry instance used by the control API.
registry = NodeRegistry()


class RouteRegistry:
    """In-memory registry of virtual-model route policies."""

    def __init__(self) -> None:
        """Create an empty route-policy registry."""
        self._routes: dict[str, RoutePolicy] = {}

    def add(self, route: RoutePolicy) -> RoutePolicy:
        """Store or replace ``route`` by id and return the stored model."""
        self._routes[route.id] = route
        return route

    def get(self, route_id: str) -> RoutePolicy | None:
        """Return a route policy by id, or ``None`` when it is not registered."""
        return self._routes.get(route_id)

    def get_by_virtual_model(self, virtual_model: str) -> RoutePolicy | None:
        """Return the first route policy matching ``virtual_model``."""
        return next(
            (route for route in self._routes.values() if route.virtual_model == virtual_model),
            None,
        )

    def list(self) -> list[RoutePolicy]:
        """Return registered routes in insertion order as a snapshot list."""
        return list(self._routes.values())

    def remove(self, route_id: str) -> bool:
        """Remove a route policy by id and report whether anything was removed."""
        return self._routes.pop(route_id, None) is not None

    def clear(self) -> None:
        """Remove all process-local route policies."""
        self._routes.clear()


# Process-wide route-policy registry used by Phase 3 routing and control API.
route_registry = RouteRegistry()


class ShareRegistry:
    """In-memory owner share-mode state for the required CLI command seam."""

    def __init__(self) -> None:
        """Create the default non-sharing state."""
        self._status = ShareStatus()

    def get(self) -> ShareStatus:
        """Return the current share mode snapshot."""
        return self._status

    def set(self, update: ShareUpdate) -> ShareStatus:
        """Replace the current share mode with a validated update."""
        self._status = ShareStatus(**update.model_dump())
        return self._status

    def clear(self) -> None:
        """Reset sharing to the safe default off state."""
        self._status = ShareStatus()


# Process-wide owner sharing state used by the CLI/control API.
share_registry = ShareRegistry()
