"""In-memory node registry (Phase 2 scaffold).

Holds the set of approved LM Studio nodes. v0 keeps everything in process
memory; a SQLite (``aiosqlite``) persistence seam is planned per METHOD-A.md.
"""

from __future__ import annotations

from vampire.models import Node


class NodeRegistry:
    """A minimal in-memory registry of approved nodes."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}

    def add(self, node: Node) -> Node:
        self._nodes[node.id] = node
        return node

    def get(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def remove(self, node_id: str) -> bool:
        return self._nodes.pop(node_id, None) is not None

    def list(self) -> list[Node]:
        return list(self._nodes.values())


# Process-wide registry instance used by the control API.
registry = NodeRegistry()
