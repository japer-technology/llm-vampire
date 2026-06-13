"""Phase 2 node registry, discovery, inventory, and metrics tests."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import vampire.proxy as proxy
from vampire.app import create_app


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
