"""Layer 2 — Vampire control API (DESIGN-API.md §3, §12-19).

The ``/vampire/v1/*`` routes manage nodes, routes, discovery, fusion, pipelines,
jobs, traces, and metrics. This scaffold implements ``status`` and basic node
registry CRUD; remaining routes are stubbed for later phases.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from vampire import __version__
from vampire.models import Node
from vampire.registry import registry

router = APIRouter(prefix="/vampire/v1", tags=["vampire-control"])


@router.get("/status")
async def status() -> dict[str, Any]:
    """Return the gateway's minimal cluster status envelope (§25)."""
    nodes = registry.list()
    return {
        "object": "vampire.status",
        "version": __version__,
        "nodes_total": len(nodes),
        "nodes_online": sum(1 for n in nodes if n.status == "online"),
    }


@router.get("/nodes")
async def list_nodes() -> dict[str, Any]:
    """Return all manually registered nodes in an OpenAI-style list envelope (§14)."""
    return {"object": "list", "data": [n.model_dump() for n in registry.list()]}


@router.post("/nodes")
async def register_node(node: Node) -> dict[str, Any]:
    """Register or replace an owner-approved LM Studio node (§13).

    Pydantic validates required fields such as ``id`` and
    ``lmstudio_base_url``. Health checks and automatic ``online`` status updates
    are intentionally deferred to Phase 2.
    """
    registry.add(node)
    return {"id": node.id, "status": "registered", "trusted": node.trusted}


@router.get("/nodes/{node_id}")
async def get_node(node_id: str) -> dict[str, Any]:
    """Return a registered node or a 404 when the id is unknown."""
    node = registry.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump()


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str) -> dict[str, Any]:
    """Remove an in-memory node registration or return 404 if it is absent."""
    if not registry.remove(node_id):
        raise HTTPException(status_code=404, detail="node not found")
    return {"id": node_id, "status": "removed"}
