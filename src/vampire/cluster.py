"""Phase 2 node health, discovery, model inventory, and metrics helpers."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
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


def _local_ip_addresses() -> set[str]:
    """Return loopback and interface IP addresses for this host."""
    addresses = {"127.0.0.1", "::1"}
    try:
        addrinfo = socket.getaddrinfo(socket.gethostname(), None)
    except OSError:
        return addresses

    for family, _, _, _, sockaddr in addrinfo:
        if family in {socket.AF_INET, socket.AF_INET6}:
            addresses.add(str(sockaddr[0]))
    return addresses


def _host_ip_address(host: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse ``host`` as an IP address when possible."""
    if host is None:
        return None
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _url_with_host(base_url: str, host: str) -> str:
    """Return ``base_url`` with its hostname replaced by ``host``."""
    parsed = urlparse(base_url)
    netloc = f"[{host}]" if ":" in host else host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


def _local_access_key(base_url: str, local_ips: set[str]) -> tuple[str, int] | None:
    """Group equivalent localhost, loopback, and local-interface discovery URLs."""
    parsed = urlparse(base_url)
    host = parsed.hostname
    host_ip = _host_ip_address(host)
    is_localhost = host is not None and host.lower() == "localhost"
    is_loopback = host_ip is not None and host_ip.is_loopback
    is_local_ip = host_ip is not None and str(host_ip) in local_ips
    if not (is_localhost or is_loopback or is_local_ip):
        return None

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return (parsed.scheme, port)


def _local_access_rank(base_url: str, local_ips: set[str]) -> tuple[int, str]:
    """Rank local-access URLs so LAN IPs win, then 127.0.0.1, then localhost."""
    parsed = urlparse(base_url)
    host = parsed.hostname
    host_ip = _host_ip_address(host)
    if host_ip is not None and not host_ip.is_loopback and str(host_ip) in local_ips:
        return (0, str(host_ip))
    if host_ip is not None and str(host_ip) == "127.0.0.1":
        return (1, "")
    if host is not None and host.lower() == "localhost":
        return (2, "")
    return (3, str(host_ip) if host_ip is not None else base_url)


def _preferred_local_access_url(urls: list[str], local_ips: set[str]) -> str:
    """Choose the display/probe URL for a group of local access aliases."""
    best = min(urls, key=lambda url: _local_access_rank(url, local_ips))
    host_ip = _host_ip_address(urlparse(best).hostname)
    if host_ip is not None and not host_ip.is_loopback and str(host_ip) in local_ips:
        return best
    return _url_with_host(best, "127.0.0.1")


def _dedupe_local_access_urls(urls: list[str]) -> list[str]:
    """Collapse localhost, 127.0.0.1, and local-interface IP aliases per port."""
    local_ips = _local_ip_addresses()
    local_groups: dict[tuple[str, int], list[str]] = {}
    for url in urls:
        key = _local_access_key(url, local_ips)
        if key is not None:
            local_groups.setdefault(key, []).append(url)

    deduped: list[str] = []
    emitted_urls: set[str] = set()
    emitted_local_keys: set[tuple[str, int]] = set()
    for url in urls:
        key = _local_access_key(url, local_ips)
        if key is not None:
            if key in emitted_local_keys:
                continue
            candidate = _preferred_local_access_url(local_groups[key], local_ips)
            emitted_local_keys.add(key)
        else:
            candidate = url

        if candidate not in emitted_urls:
            deduped.append(candidate)
            emitted_urls.add(candidate)
    return deduped


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

    return _dedupe_local_access_urls(list(dict.fromkeys(urls)))


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
