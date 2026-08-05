"""Phase 2 node health, discovery, model inventory, and metrics helpers."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from datetime import datetime, timezone
from time import perf_counter
from urllib.parse import urlparse

import httpx

import vampire.proxy as proxy
from vampire.config import get_settings
from vampire.models import (
    DEFAULT_DISCOVERY_PORTS,
    DiscoveryRequest,
    ModelCard,
    ModelListResponse,
    Node,
    PhysicalModel,
)
from vampire.providers import probe_endpoint
from vampire.providers.openai_compatible import coerce_model_cards
from vampire.registry import registry

_MAX_SCAN_SUBNETS = 8
_MAX_SCAN_PORTS = 16
_MAX_SCAN_HOSTS_PER_SUBNET = 256
_MAX_SCAN_CANDIDATES = 1024
_DISCOVERY_CONCURRENCY = 16
_REFRESH_CONCURRENCY = 16
_REFRESH_TTL_SECONDS = 1.0
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_refresh_lock = asyncio.Lock()
_refresh_cache: list[Node] | None = None
_refresh_cache_at = 0.0
logger = logging.getLogger(__name__)


class DiscoveryInputError(ValueError):
    """Raised when a discovery request contains invalid input."""


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


def is_allowed_target_url(base_url: str) -> bool:
    """Return whether a caller-supplied probe/proxy target is in the safe scope."""
    parsed = urlparse(base_url)
    if parsed.scheme not in _ALLOWED_SCHEMES or parsed.hostname is None:
        return False
    host_ip = _host_ip_address(parsed.hostname)
    if host_ip is None:
        return True
    if host_ip.is_link_local or host_ip.is_reserved or host_ip.is_multicast:
        return False
    return bool(host_ip.is_loopback or host_ip.is_private)


def invalidate_refresh_cache() -> None:
    """Discard the short-lived registered-node refresh snapshot."""
    global _refresh_cache, _refresh_cache_at
    _refresh_cache = None
    _refresh_cache_at = 0.0


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
    """Retain the original model-card coercion seam for compatibility."""
    return coerce_model_cards(payload)


async def refresh_node(
    node: Node,
    *,
    timeout_ms: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> Node:
    """Interrogate a node through provider adapters and update health metadata."""
    timeout = httpx.Timeout((timeout_ms or 1500) / 1000)
    base_url = node.base_url.rstrip("/")
    http_client = client or proxy.build_async_client()
    started = perf_counter()
    try:
        probe = await probe_endpoint(
            http_client,
            base_url,
            timeout=timeout,
            provider_hint=node.provider,
        )
        latency_ms = round((perf_counter() - started) * 1000, 3)
        updated = node.model_copy(
            update={
                "status": "online",
                "provider": probe.provider,
                "api_format": probe.api_format,
                "models": probe.models,
                "capabilities": probe.capabilities,
                "request_count": node.request_count + 1,
                "latency_ms": latency_ms,
                "last_checked_at": _now(),
                "last_error": None,
            }
        )
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
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
        if client is None:
            await http_client.aclose()

    if registry.get(updated.id) is not None:
        registry.add(updated)
    return updated


async def refresh_registered_nodes(
    *,
    timeout_ms: int | None = None,
    client: httpx.AsyncClient | None = None,
    force: bool = False,
) -> list[Node]:
    """Refresh every registered node and return the updated snapshot."""
    nodes = registry.list()
    if not nodes:
        return []

    global _refresh_cache, _refresh_cache_at
    now = perf_counter()
    if not force and _refresh_cache is not None and now - _refresh_cache_at < _REFRESH_TTL_SECONDS:
        return _refresh_cache

    async with _refresh_lock:
        now = perf_counter()
        if (
            not force
            and _refresh_cache is not None
            and now - _refresh_cache_at < _REFRESH_TTL_SECONDS
        ):
            return _refresh_cache

        nodes = registry.list()
        if not nodes:
            invalidate_refresh_cache()
            return []

        semaphore = asyncio.Semaphore(_REFRESH_CONCURRENCY)

        async def _bounded_refresh(node: Node) -> Node | BaseException:
            async with semaphore:
                try:
                    if client is not None:
                        return await refresh_node(node, timeout_ms=timeout_ms, client=client)
                    return await refresh_node(node, timeout_ms=timeout_ms)
                except BaseException as exc:
                    return exc

        results = await asyncio.gather(*(_bounded_refresh(node) for node in nodes))
        refreshed: list[Node] = []
        for node, result in zip(nodes, results, strict=True):
            if isinstance(result, Node):
                refreshed.append(result)
                continue
            logger.warning("refresh of node %s failed: %r", node.id, result)
            refreshed.append(node)
        _refresh_cache = refreshed
        _refresh_cache_at = perf_counter()
        return refreshed


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
                    provider=node.provider,
                    api_format=node.api_format,
                    owned_by=model.owned_by,
                    capabilities=node.capabilities,
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
    urls: list[str] = []
    for url in request.base_urls:
        cleaned = url.rstrip("/")
        if not is_allowed_target_url(cleaned):
            raise DiscoveryInputError(f"disallowed discovery target {url!r}")
        urls.append(cleaned)
    methods = set(request.methods)
    if "static" in methods:
        urls.append(get_settings().default_base_url.rstrip("/"))
        urls.extend(node.base_url.rstrip("/") for node in registry.list())

    if "local" in methods:
        urls.append(get_settings().default_base_url.rstrip("/"))
        ports = request.ports or list(DEFAULT_DISCOVERY_PORTS)
        urls.extend(f"http://127.0.0.1:{port}" for port in ports[:_MAX_SCAN_PORTS])

    if "lan_scan" in methods:
        for subnet in request.subnets[:_MAX_SCAN_SUBNETS]:
            try:
                network = ipaddress.ip_network(subnet, strict=False)
            except ValueError as exc:
                raise DiscoveryInputError(f"invalid subnet {subnet!r}: {exc}") from exc
            if not (network.is_private or network.is_loopback):
                continue
            for index, host in enumerate(network.hosts()):
                if index >= _MAX_SCAN_HOSTS_PER_SUBNET or len(urls) >= _MAX_SCAN_CANDIDATES:
                    break
                for port in request.ports[:_MAX_SCAN_PORTS]:
                    if len(urls) >= _MAX_SCAN_CANDIDATES:
                        break
                    urls.append(f"http://{host}:{port}")

    return _dedupe_local_access_urls(list(dict.fromkeys(urls)))[:_MAX_SCAN_CANDIDATES]


def _provider_hint_for_url(base_url: str) -> str:
    """Return a safe provider hint for ports with a single dominant convention."""
    try:
        return "ollama" if urlparse(base_url).port == 11434 else "auto"
    except ValueError:
        return "auto"


async def discover_nodes(
    request: DiscoveryRequest, *, client: httpx.AsyncClient | None = None
) -> list[Node]:
    """Perform Phase 2 static/dev-subnet discovery and register online nodes."""
    semaphore = asyncio.Semaphore(_DISCOVERY_CONCURRENCY)

    async def _probe(base_url: str) -> Node | None:
        node_id = _node_id_for_url(base_url)
        current = registry.get(node_id)
        # Newly discovered nodes are UNTRUSTED by default, matching Node.trusted=False
        # and POST /vampire/v1/nodes. Trust is owner-granted (DESIGN-API.md §13), never
        # auto-assigned by reachability. An existing node keeps its established trust.
        node = current or Node(
            id=node_id,
            host=urlparse(base_url).hostname,
            base_url=base_url,
            provider=_provider_hint_for_url(base_url),
            trusted=False,
        )
        async with semaphore:
            if client is not None:
                refreshed = await refresh_node(node, timeout_ms=request.timeout_ms, client=client)
            else:
                refreshed = await refresh_node(node, timeout_ms=request.timeout_ms)
        if refreshed.status != "online":
            return None
        # trusted_only is a *filter* over results, not a grant of trust.
        if request.trusted_only and not refreshed.trusted:
            return None
        if current is not None and registry.get(refreshed.id) is None:
            return None
        registry.add(refreshed)
        return refreshed

    results = await asyncio.gather(*(_probe(base_url) for base_url in _candidate_urls(request)))
    return [node for node in results if node is not None]
