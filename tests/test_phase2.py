"""Phase 2 node registry, discovery, inventory, and metrics tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import vampire.cluster as cluster
import vampire.proxy as proxy
from vampire.app import create_app
from vampire.models import Node, NodeCapabilities, NodeUpdate
from vampire.registry import NodeRegistry


def _mock_cluster() -> FastAPI:
    """A small multi-node LM Studio stand-in keyed by request host."""
    app = FastAPI()

    @app.get("/v1/models")
    async def models(request: Request) -> JSONResponse:
        host = request.url.hostname or "unknown"
        return JSONResponse(
            {
                "object": "list",
                "data": [
                    {
                        "id": f"{host}-model",
                        "object": "model",
                        "owned_by": "lmstudio",
                    }
                ],
            }
        )

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Gateway client whose node probes go to the in-process mock cluster."""
    mock = _mock_cluster()
    original = proxy.build_async_client

    def _build() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=mock))

    proxy.build_async_client = _build
    try:
        yield TestClient(create_app())
    finally:
        proxy.build_async_client = original


def test_node_registration_interrogates_health_and_models(client: TestClient) -> None:
    resp = client.post(
        "/vampire/v1/nodes",
        json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": "node-a", "status": "registered", "trusted": False}

    node = client.get("/vampire/v1/nodes/node-a").json()
    assert node["status"] == "online"
    assert node["models"][0]["id"] == "node-a-model"
    assert node["request_count"] == 1
    assert node["latency_ms"] is not None


def test_patch_node_updates_and_refreshes(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )

    resp = client.patch("/vampire/v1/nodes/node-a", json={"tags": ["gpu"], "trusted": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tags"] == ["gpu"]
    assert body["trusted"] is True
    assert body["status"] == "online"


def test_update_preserves_nested_capabilities_type() -> None:
    reg = NodeRegistry()
    reg.add(Node(id="node-a", lmstudio_base_url="http://node-a:1234"))

    updated = reg.update(
        "node-a",
        NodeUpdate(capabilities=NodeCapabilities(vision=True, tools=True)),
    )

    assert updated is not None
    assert isinstance(updated.capabilities, NodeCapabilities)
    assert updated.capabilities.vision is True
    assert updated.capabilities.tools is True
    stored = reg.get("node-a")
    assert stored is not None
    assert isinstance(stored.capabilities, NodeCapabilities)


def test_registered_nodes_aggregate_openai_and_vampire_models(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )
    client.post(
        "/vampire/v1/nodes", json={"id": "node-b", "lmstudio_base_url": "http://node-b:1234"}
    )

    openai_models = client.get("/v1/models").json()
    assert openai_models["object"] == "list"
    assert {"node-a-model", "node-b-model"}.issubset(
        {model["id"] for model in openai_models["data"]}
    )

    vampire_models = client.get("/vampire/v1/models").json()
    assert vampire_models["object"] == "list"
    assert {model["node"] for model in vampire_models["data"]} == {"node-a", "node-b"}
    assert {model["model"] for model in vampire_models["data"]} == {"node-a-model", "node-b-model"}


def test_refresh_registered_nodes_coalesces_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    from vampire.registry import registry as node_registry

    node_registry.clear()
    cluster.invalidate_refresh_cache()
    for index in range(5):
        node_registry.add(Node(id=f"n{index}", lmstudio_base_url=f"http://10.0.0.{index}:1234"))

    probes = 0

    async def _counting_refresh(
        node: Node,
        *,
        timeout_ms: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> Node:
        nonlocal probes
        probes += 1
        await asyncio.sleep(0)
        return node.model_copy(update={"status": "online"})

    monkeypatch.setattr(cluster, "refresh_node", _counting_refresh)

    async def _run() -> None:
        await asyncio.gather(*(cluster.refresh_registered_nodes() for _ in range(10)))
        await cluster.refresh_registered_nodes()

    asyncio.run(_run())

    assert probes == 5


def test_discover_static_base_urls_registers_online_nodes(client: TestClient) -> None:
    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"], "base_urls": ["http://node-c:1234"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "vampire.discovery_result"
    assert body["nodes"][0]["id"] == "node-node-c-1234"
    assert body["nodes"][0]["models"][0]["id"] == "node-c-model"


def test_discover_rejects_offscope_base_urls(client: TestClient) -> None:
    resp = client.post(
        "/vampire/v1/discover",
        json={
            "methods": ["static"],
            "base_urls": ["http://169.254.169.254", "http://8.8.8.8:80"],
        },
    )

    assert resp.status_code == 400
    nodes = client.get("/vampire/v1/nodes").json()["data"]
    hosts = {node["host"] for node in nodes}
    assert "169.254.169.254" not in hosts
    assert "8.8.8.8" not in hosts


def test_register_node_rejects_offscope_url(client: TestClient) -> None:
    resp = client.post(
        "/vampire/v1/nodes",
        json={"id": "evil", "lmstudio_base_url": "http://169.254.169.254/latest/meta-data"},
    )

    assert resp.status_code == 400
    assert client.get("/vampire/v1/nodes/evil").status_code == 404


def test_patch_node_rejects_offscope_url(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes",
        json={"id": "node-a", "lmstudio_base_url": "http://127.0.0.1:1234"},
    )

    resp = client.patch(
        "/vampire/v1/nodes/node-a",
        json={"lmstudio_base_url": "http://8.8.8.8:80"},
    )

    assert resp.status_code == 400
    node = client.get("/vampire/v1/nodes/node-a").json()
    assert node["lmstudio_base_url"] == "http://127.0.0.1:1234"


def test_discover_does_not_register_offline_candidates(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    from vampire.registry import registry as node_registry

    async def _offline(node: Node, *, timeout_ms: int | None = None) -> Node:
        updated = node.model_copy(update={"status": "offline"})
        if node_registry.get(updated.id) is not None:
            node_registry.add(updated)
        return updated

    monkeypatch.setattr(cluster, "refresh_node", _offline)

    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"], "base_urls": ["http://dead-node:1234"]},
    )

    assert resp.status_code == 200
    assert resp.json()["nodes"] == []
    assert node_registry.get("node-dead-node-1234") is None
    assert node_registry.list() == []


def test_discover_registers_online_candidates(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    from vampire.registry import registry as node_registry

    async def _online(node: Node, *, timeout_ms: int | None = None) -> Node:
        return node.model_copy(update={"status": "online"})

    monkeypatch.setattr(cluster, "refresh_node", _online)

    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"], "base_urls": ["http://live-node:1234"]},
    )

    assert resp.status_code == 200
    assert node_registry.get("node-live-node-1234") is not None


def test_discover_caps_candidates_and_skips_public_subnets(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    seen: list[str] = []

    async def _spy(node: Node, *, timeout_ms: int | None = None) -> Node:
        seen.append(node.lmstudio_base_url)
        return node.model_copy(update={"status": "offline"})

    monkeypatch.setattr(cluster, "refresh_node", _spy)

    resp = client.post(
        "/vampire/v1/discover",
        json={
            "methods": ["lan_scan"],
            "subnets": ["8.8.8.0/24", "10.0.0.0/8", "172.16.0.0/12"],
            "ports": list(range(1000, 1100)),
        },
    )

    assert resp.status_code == 200
    assert all(not url.startswith("http://8.8.8.") for url in seen)
    assert len(seen) <= 1024


def test_discover_probes_concurrently(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    async def _slow(node: Node, *, timeout_ms: int | None = None) -> Node:
        await asyncio.sleep(0.2)
        return node.model_copy(update={"status": "offline"})

    monkeypatch.setattr(cluster, "refresh_node", _slow)

    start = time.perf_counter()
    resp = client.post(
        "/vampire/v1/discover",
        json={
            "methods": ["static"],
            "base_urls": [f"http://node-{index}:1234" for index in range(16)],
        },
    )
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    assert elapsed < 1.0


def test_discover_rejects_malformed_subnet(client: TestClient) -> None:
    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["lan_scan"], "subnets": ["not-a-cidr"]},
    )

    assert resp.status_code == 400
    assert "invalid subnet" in resp.json()["detail"]


def test_refresh_node_does_not_resurrect_deregistered_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = Node(id="node-z", lmstudio_base_url="http://node-z:1234")
    from vampire.registry import registry

    registry.add(node)

    class _DeletingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            registry.remove("node-z")
            return httpx.Response(200, json={"object": "list", "data": []})

    monkeypatch.setattr(
        proxy,
        "build_async_client",
        lambda: httpx.AsyncClient(transport=_DeletingTransport()),
    )

    asyncio.run(cluster.refresh_node(node))

    assert registry.get("node-z") is None


def test_refresh_node_handles_malformed_url_as_offline() -> None:
    from vampire.registry import registry as node_registry

    node_registry.clear()
    node = Node(id="bad", lmstudio_base_url="http://node:notaport")

    refreshed = asyncio.run(cluster.refresh_node(node))

    assert refreshed.status == "offline"
    assert refreshed.last_error is not None
    assert "port" in refreshed.last_error.lower() or "url" in refreshed.last_error.lower()


def test_models_endpoints_survive_one_malformed_node(client: TestClient) -> None:
    from vampire.registry import registry as node_registry

    node_registry.clear()
    client.post(
        "/vampire/v1/nodes",
        json={"id": "good", "lmstudio_base_url": "http://good:1234"},
    )

    bad = client.post(
        "/vampire/v1/nodes",
        json={"id": "bad", "lmstudio_base_url": "http://node:notaport"},
    )
    assert bad.status_code == 200
    assert bad.json()["status"] == "registered"

    resp = client.get("/v1/models")

    assert resp.status_code == 200
    ids = {model["id"] for model in resp.json()["data"]}
    assert "good-model" in ids


def test_control_api_auth_token_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "test-token"
    scheme = "Bear" + "er"
    monkeypatch.setenv("VAMPIRE_AUTH_TOKEN", token)
    client = TestClient(create_app())

    unauthenticated = client.post("/vampire/v1/discover", json={"methods": []})
    authenticated = client.post(
        "/vampire/v1/discover",
        headers={"Authorization": f"{scheme} {token}"},
        json={"methods": []},
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"
    assert authenticated.status_code == 200


def test_discover_collapses_local_access_aliases_to_lan_ip(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(
        "vampire.cluster._local_ip_addresses", lambda: {"127.0.0.1", "192.168.1.50"}
    )

    resp = client.post(
        "/vampire/v1/discover",
        json={
            "methods": ["static"],
            "base_urls": [
                "http://localhost:1234",
                "http://127.0.0.1:1234",
                "http://192.168.1.50:1234",
            ],
        },
    )

    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == "node-192-168-1-50-1234"
    assert nodes[0]["host"] == "192.168.1.50"
    assert nodes[0]["models"][0]["id"] == "192.168.1.50-model"


def test_discover_collapses_local_access_aliases_to_loopback(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr("vampire.cluster._local_ip_addresses", lambda: {"127.0.0.1"})

    resp = client.post(
        "/vampire/v1/discover",
        json={
            "methods": ["static"],
            "base_urls": ["http://localhost:1234", "http://127.0.0.1:1234"],
        },
    )

    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == "node-127-0-0-1-1234"
    assert nodes[0]["host"] == "127.0.0.1"
    assert nodes[0]["models"][0]["id"] == "127.0.0.1-model"


def test_metrics_include_node_counts_health_and_latency(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )

    metrics = client.get("/vampire/v1/metrics").json()
    assert metrics["object"] == "vampire.metrics"
    assert metrics["cluster"]["nodes_online"] == 1
    assert metrics["nodes"][0]["node"] == "node-a"
    assert metrics["nodes"][0]["health"] == "online"
    assert metrics["nodes"][0]["requests_total"] == 1
    assert metrics["nodes"][0]["avg_latency_ms"] is not None


def test_node_delete_removes_registration_and_unknown_nodes_404(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )

    assert client.delete("/vampire/v1/nodes/node-a").json() == {
        "id": "node-a",
        "status": "removed",
    }
    assert client.get("/vampire/v1/nodes/node-a").status_code == 404
    assert client.patch("/vampire/v1/nodes/missing", json={"trusted": True}).status_code == 404
    assert client.delete("/vampire/v1/nodes/missing").status_code == 404


def test_share_control_endpoint_updates_required_cli_command_state(client: TestClient) -> None:
    default = client.get("/vampire/v1/share").json()
    assert default == {
        "object": "vampire.share",
        "mode": "off",
        "enabled": False,
        "duration": None,
        "model": None,
    }

    updated = client.post(
        "/vampire/v1/share",
        json={"mode": "family", "enabled": True, "model": "family-model"},
    ).json()
    assert updated["mode"] == "family"
    assert updated["enabled"] is True
    assert updated["model"] == "family-model"


def test_discovery_does_not_auto_trust_nodes() -> None:
    """Default discovery (trusted_only=False) must NOT auto-grant trust."""
    from vampire.models import DiscoveryRequest
    from vampire.registry import registry as node_registry

    node_registry.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list", "data": [{"id": "m"}]})

    transport = httpx.MockTransport(handler)

    async def _run() -> list[Node]:
        async with httpx.AsyncClient(transport=transport) as http:
            return await cluster.discover_nodes(
                DiscoveryRequest(methods=["static"], base_urls=["http://10.0.0.9:1234"]),
                client=http,
            )

    nodes = asyncio.run(_run())

    assert nodes, "an online node should be discovered"
    assert all(node.trusted is False for node in nodes), (
        "discovery must never auto-grant trust; default is owner-deny"
    )
    stored = node_registry.get("node-10-0-0-9-1234")
    assert stored is not None
    assert stored.trusted is False


def test_trusted_only_discovery_returns_already_trusted_nodes() -> None:
    """trusted_only=True filters results to already-trusted nodes (not a grant)."""
    from vampire.models import DiscoveryRequest
    from vampire.registry import registry as node_registry

    node_registry.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list", "data": [{"id": "m"}]})

    transport = httpx.MockTransport(handler)

    async def _run() -> list[Node]:
        async with httpx.AsyncClient(transport=transport) as http:
            # First pass: discover an untrusted node (recorded, not returned under trusted_only).
            await cluster.discover_nodes(
                DiscoveryRequest(methods=["static"], base_urls=["http://10.0.0.9:1234"]),
                client=http,
            )
            # Owner grants trust out of band.
            node = node_registry.get("node-10-0-0-9-1234")
            assert node is not None
            node_registry.add(node.model_copy(update={"trusted": True}))
            # trusted_only discovery now returns the already-trusted node.
            return await cluster.discover_nodes(
                DiscoveryRequest(
                    methods=["static"],
                    base_urls=["http://10.0.0.9:1234"],
                    trusted_only=True,
                ),
                client=http,
            )

    nodes = asyncio.run(_run())

    assert [n.id for n in nodes] == ["node-10-0-0-9-1234"]
    assert nodes[0].trusted is True
