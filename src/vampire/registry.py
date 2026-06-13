"""In-memory node registry (Phase 2 scaffold).

Holds the set of approved LM Studio nodes. v0 keeps everything in process
memory; a SQLite (``aiosqlite``) persistence seam is planned per METHOD-A.md.
"""

from __future__ import annotations

from vampire.models import Node


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

    def get(self, node_id: str) -> Node | None:
        """Return a node by id, or ``None`` when it is not registered."""
        return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        """Remove a node by id and report whether anything was removed."""
        return self._nodes.pop(node_id, None) is not None

    def list(self) -> list[Node]:
        """Return registered nodes in insertion order as a snapshot list."""
        return list(self._nodes.values())


# Process-wide registry instance used by the control API.
registry = NodeRegistry()
