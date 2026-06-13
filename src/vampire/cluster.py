"""Phase 2 node health, discovery, model inventory, and metrics helpers."""

from __future__ import annotations

import asyncio
import ipaddress
from datetime import datetime, timezone
from time import perf_counter
from urllib.parse import urlparse

import httpx

import vampire.proxy as proxy
from vampire.config import get_settings
from vampire.models import DiscoveryRequest, ModelCard, ModelListResponse, Node, PhysicalModel
from vampire.registry import registry


def _now() -> str:
    """Return an ISO-8601 UTC timestamp for node health metadata."""
    return datetime.now(timezone.utc).isoformat()


def _node_id_for_url(base_url: str) -> str:
    """Derive a stable development discovery id from a base URL."""
    parsed = urlparse(base_url)
    host = (parsed.hostname or "localhost").replace(".", "-").replace(":", "-")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"node-{host}-{port}"


def _coerce_model_cards(payload: object) -> list[ModelCard]:
    """Extract OpenAI-compatible model cards from a ``/v1/models`` response."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    cards: list[ModelCard] = []
    for raw in data:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            cards.append(ModelCard.model_validate(raw))
    return cards


async def refresh_node(node: Node, *, timeout_ms: int | None = None) -> Node:
    """Interrogate a node's ``/v1/models`` endpoint and update health metadata."""
    timeout = httpx.Timeout((timeout_ms or 1500) / 1000)
    base_url = node.lmstudio_base_url.rstrip("/")
    client = proxy.build_async_client()
    started = perf_counter()
    try:
        response = await client.get(f"{base_url}/v1/models", timeout=timeout)
        latency_ms = round((perf_counter() - started) * 1000, 3)
        response.raise_for_status()
        updated = node.model_copy(
            update={
                "status": "online",
                "models": _coerce_model_cards(response.json()),
                "request_count": node.request_count + 1,
                "latency_ms": latency_ms,
                "last_checked_at": _now(),
                "last_error": None,
            }
        )
    except (httpx.HTTPError, ValueError) as exc:
        latency_ms = round((perf_counter() - started) * 1000, 3)
        updated = node.model_copy(
            update={
                "status": "offline",
                "request_count": node.request_count + 1,
                "error_count": node.error_count + 1,
                "latency_ms": latency_ms,
                "last_checked_at": _now(),
                "last_error": str(exc),
            }
        )
    finally:
        await client.aclose()

    registry.add(updated)
    return updated


async def refresh_registered_nodes(*, timeout_ms: int | None = None) -> list[Node]:
    """Refresh every registered node and return the updated snapshot."""
    nodes = registry.list()
    if not nodes:
        return []
    return list(
        await asyncio.gather(*(refresh_node(node, timeout_ms=timeout_ms) for node in nodes))
    )


def aggregate_model_cards(nodes: list[Node]) -> ModelListResponse:
    """Build a de-duplicated OpenAI ``/v1/models`` response across nodes."""
    cards: dict[str, ModelCard] = {}
    for node in nodes:
        for model in node.models:
            cards.setdefault(model.id, model)
    return ModelListResponse(data=list(cards.values()))


def physical_model_inventory(nodes: list[Node]) -> list[PhysicalModel]:
    """Return detailed node/model inventory for ``/vampire/v1/models``."""
    inventory: list[PhysicalModel] = []
    for node in nodes:
        for model in node.models:
            inventory.append(
                PhysicalModel(
                    node=node.id,
                    model=model.id,
                    owned_by=model.owned_by,
                    tokens_per_second=node.tokens_per_second,
                )
            )
    return inventory


def metrics_snapshot() -> dict[str, object]:
    """Return basic Phase 2 metrics from the in-memory registry."""
    nodes = registry.list()
    nodes_online = sum(1 for node in nodes if node.status == "online")
    tokens_per_second = sum(node.tokens_per_second or 0 for node in nodes)
    return {
        "object": "vampire.metrics",
        "cluster": {
            "nodes_online": nodes_online,
            "nodes_offline": len(nodes) - nodes_online,
            "active_requests": sum(node.active_requests for node in nodes),
            "queue_depth": sum(node.queue_depth for node in nodes),
            "tokens_per_second": tokens_per_second,
        },
        "models": [],
        "nodes": [
            {
                "node": node.id,
                "health": node.status,
                "requests_total": node.request_count,
                "errors_total": node.error_count,
                "avg_latency_ms": node.latency_ms,
            }
            for node in nodes
        ],
    }


def _candidate_urls(request: DiscoveryRequest) -> list[str]:
    """Expand static and development-subnet discovery inputs to base URLs."""
    urls = [url.rstrip("/") for url in request.base_urls]
    methods = set(request.methods)
    if "static" in methods:
        urls.append(get_settings().lmstudio_base_url.rstrip("/"))
        urls.extend(node.lmstudio_base_url.rstrip("/") for node in registry.list())

    if "lan_scan" in methods:
        for subnet in request.subnets:
            network = ipaddress.ip_network(subnet, strict=False)
            for index, host in enumerate(network.hosts()):
                if index >= 256:
                    break
                for port in request.ports:
                    urls.append(f"http://{host}:{port}")

    return list(dict.fromkeys(urls))


async def discover_nodes(request: DiscoveryRequest) -> list[Node]:
    """Perform Phase 2 static/dev-subnet discovery and register online nodes."""
    discovered: list[Node] = []
    for base_url in _candidate_urls(request):
        current = registry.get(_node_id_for_url(base_url))
        node = current or Node(
            id=_node_id_for_url(base_url),
            host=urlparse(base_url).hostname,
            lmstudio_base_url=base_url,
            trusted=not request.trusted_only,
        )
        refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
        if refreshed.status == "online" and (refreshed.trusted or not request.trusted_only):
            discovered.append(refreshed)
    return discovered
