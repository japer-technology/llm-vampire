"""Layer 2 — Vampire control API (DESIGN-API.md §3, §12-19).

The ``/vampire/v1/*`` routes manage nodes, routes, discovery, fusion, pipelines,
jobs, traces, and metrics. This scaffold implements ``status`` and basic node
registry CRUD; remaining routes are stubbed for later phases.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from vampire import __version__
from vampire.api._auth import require_control_auth
from vampire.cluster import (
    DiscoveryInputError,
    discover_nodes,
    metrics_snapshot,
    physical_model_inventory,
    refresh_node,
    refresh_registered_nodes,
)
from vampire.models import DiscoveryRequest, Node, NodeUpdate, RoutePolicy, ShareUpdate
from vampire.registry import registry, route_registry, share_registry
from vampire.router import MVP_STRATEGIES

router = APIRouter(
    prefix="/vampire/v1",
    tags=["vampire-control"],
    dependencies=[Depends(require_control_auth)],
)
MANUAL_UNAVAILABLE_STATUSES = {"draining", "disabled", "maintenance"}


def _request_http_client(request: Request) -> httpx.AsyncClient | None:
    client = getattr(request.app.state, "http_client", None)
    return client if isinstance(client, httpx.AsyncClient) else None


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
async def register_node(node: Node, request: Request) -> dict[str, Any]:
    """Register or replace an owner-approved LM Studio node (§13).

    Pydantic validates required fields such as ``id`` and
    ``lmstudio_base_url``. Phase 2 immediately interrogates ``/v1/models`` to
    populate health and model metadata, while keeping offline nodes registered.
    """
    registry.add(node)
    refreshed = await refresh_node(node, client=_request_http_client(request))
    return {"id": refreshed.id, "status": "registered", "trusted": refreshed.trusted}


@router.get("/nodes/{node_id}")
async def get_node(node_id: str) -> dict[str, Any]:
    """Return a registered node or a 404 when the id is unknown."""
    node = registry.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump()


@router.patch("/nodes/{node_id}")
async def patch_node(node_id: str, patch: NodeUpdate, request: Request) -> dict[str, Any]:
    """Partially update a registered node and refresh its health metadata."""
    node = registry.update(node_id, patch)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    if patch.status in MANUAL_UNAVAILABLE_STATUSES:
        return node.model_dump()
    return (await refresh_node(node, client=_request_http_client(request))).model_dump()


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: str) -> dict[str, Any]:
    """Remove an in-memory node registration or return 404 if it is absent."""
    if not registry.remove(node_id):
        raise HTTPException(status_code=404, detail="node not found")
    return {"id": node_id, "status": "removed"}


@router.post("/discover")
async def discover(
    request: Request, request_data: DiscoveryRequest | None = None
) -> dict[str, Any]:
    """Run Phase 2 static/dev-subnet discovery for reachable LM Studio APIs (§12)."""
    try:
        nodes = await discover_nodes(
            request_data or DiscoveryRequest(),
            client=_request_http_client(request),
        )
    except DiscoveryInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"object": "vampire.discovery_result", "nodes": [node.model_dump() for node in nodes]}


@router.get("/models")
async def list_vampire_models(request: Request) -> dict[str, Any]:
    """Aggregate a detailed physical model inventory across registered nodes (§15)."""
    nodes = await refresh_registered_nodes(client=_request_http_client(request))
    return {
        "object": "list",
        "data": [model.model_dump() for model in physical_model_inventory(nodes)],
    }


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Return basic per-node health, request-count, and latency metrics (§18)."""
    return metrics_snapshot()


@router.get("/share")
async def get_share() -> dict[str, Any]:
    """Return the current owner sharing mode for the required CLI command."""
    return share_registry.get().model_dump()


@router.post("/share")
async def set_share(update: ShareUpdate) -> dict[str, Any]:
    """Set the owner sharing mode without enabling Phase 6 policy enforcement yet."""
    return share_registry.set(update).model_dump()


@router.get("/routes")
async def list_routes() -> dict[str, Any]:
    """Return configured Phase 3 virtual-model route policies (§16)."""
    return {"object": "list", "data": [route.model_dump() for route in route_registry.list()]}


@router.post("/routes")
async def create_route(route: RoutePolicy) -> dict[str, Any]:
    """Create or replace a virtual-model route policy (§16)."""
    if route.strategy not in MVP_STRATEGIES:
        raise HTTPException(status_code=400, detail="unsupported routing strategy")
    physical_ids = {model.id for node in registry.list() for model in node.models}
    if route.virtual_model in physical_ids:
        raise HTTPException(
            status_code=409,
            detail=f"virtual_model {route.virtual_model!r} collides with a physical model id",
        )
    return route_registry.add(route).model_dump()


@router.get("/routes/{route_id}")
async def get_route(route_id: str) -> dict[str, Any]:
    """Return a configured route policy or 404 when it is unknown."""
    route = route_registry.get(route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="route not found")
    return route.model_dump()


@router.delete("/routes/{route_id}")
async def delete_route(route_id: str) -> dict[str, Any]:
    """Remove a configured route policy or return 404 if it is absent."""
    if not route_registry.remove(route_id):
        raise HTTPException(status_code=404, detail="route not found")
    return {"id": route_id, "status": "removed"}
