"""Phase 3 virtual-model routing tests."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import vampire.proxy as proxy
from vampire.app import create_app
from vampire.models import ModelCard, Node, RoutePolicy, RouteTarget
from vampire.registry import registry
from vampire.router import Router


def _mock_cluster() -> FastAPI:
    """A multi-node LM Studio stand-in keyed by request host."""
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

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": "chatcmpl-routed",
                "object": "chat.completion",
                "model": payload["model"],
                "node": request.url.hostname,
                "saw_vampire_control": "vampire" in payload,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}],
            }
        )

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Gateway client whose node probes and routed calls go to a mock cluster."""
    mock = _mock_cluster()
    original = proxy.build_async_client

    def _build() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=mock))

    proxy.build_async_client = _build
    try:
        yield TestClient(create_app())
    finally:
        proxy.build_async_client = original


def _online_node(
    node_id: str,
    model: str,
    *,
    trusted: bool = False,
    queue_depth: int = 0,
    active_requests: int = 0,
    latency_ms: float | None = None,
) -> Node:
    return Node(
        id=node_id,
        lmstudio_base_url=f"http://{node_id}:1234",
        status="online",
        trusted=trusted,
        queue_depth=queue_depth,
        active_requests=active_requests,
        latency_ms=latency_ms,
        models=[ModelCard(id=model)],
    )


def _selected_node(target: RouteTarget | None) -> str:
    """Assert a route was selected and return its node id."""
    assert target is not None
    return target.node


def test_route_policy_crud(client: TestClient) -> None:
    route = {
        "id": "route-code",
        "virtual_model": "vampire:code",
        "targets": [{"node": "node-a", "model": "coder"}],
        "strategy": "round_robin",
        "fallback": "vampire:auto",
    }

    created = client.post("/vampire/v1/routes", json=route)
    assert created.status_code == 200
    assert created.json()["virtual_model"] == "vampire:code"

    listed = client.get("/vampire/v1/routes").json()
    assert listed["object"] == "list"
    assert listed["data"][0]["id"] == "route-code"

    fetched = client.get("/vampire/v1/routes/route-code")
    assert fetched.status_code == 200
    assert fetched.json()["targets"] == [{"node": "node-a", "model": "coder"}]

    deleted = client.delete("/vampire/v1/routes/route-code")
    assert deleted.status_code == 200
    assert client.get("/vampire/v1/routes/route-code").status_code == 404


def test_router_mvp_strategies() -> None:
    registry.add(_online_node("node-a", "shared", queue_depth=3, latency_ms=30))
    registry.add(_online_node("node-b", "shared", queue_depth=1, latency_ms=10))
    registry.add(_online_node("node-c", "other", trusted=True, queue_depth=2, latency_ms=20))
    router = Router(registry)
    targets = [
        RouteTarget(node="node-a", model="shared"),
        RouteTarget(node="node-b", model="shared"),
        RouteTarget(node="node-c", model="other"),
    ]

    assert (
        _selected_node(
            router.select(RoutePolicy(id="rr", virtual_model="vampire:auto", targets=targets))
        )
        == "node-a"
    )
    assert (
        _selected_node(
            router.select(RoutePolicy(id="rr", virtual_model="vampire:auto", targets=targets))
        )
        == "node-b"
    )
    assert (
        _selected_node(
            router.select(
                RoutePolicy(
                    id="busy", virtual_model="vampire:auto", targets=targets, strategy="least_busy"
                )
            )
        )
        == "node-b"
    )
    assert (
        _selected_node(
            router.select(
                RoutePolicy(
                    id="latency",
                    virtual_model="vampire:auto",
                    targets=targets,
                    strategy="least_latency",
                )
            )
        )
        == "node-b"
    )
    assert (
        _selected_node(
            router.select(
                RoutePolicy(
                    id="affinity",
                    virtual_model="vampire:auto",
                    targets=targets,
                    strategy="model_affinity",
                ),
                requested_model="other",
            )
        )
        == "node-c"
    )
    assert (
        _selected_node(
            router.select(
                RoutePolicy(
                    id="trusted",
                    virtual_model="vampire:auto",
                    targets=targets,
                    strategy="trusted_only",
                )
            )
        )
        == "node-c"
    )


def test_drained_node_stays_registered_but_is_not_route_candidate(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )

    drained = client.patch("/vampire/v1/nodes/node-a", json={"status": "draining"})

    assert drained.status_code == 200
    assert drained.json()["status"] == "draining"
    assert registry.get("node-a") is not None
    assert (
        Router(registry).select(
            RoutePolicy(
                id="route-drained",
                virtual_model="vampire:auto",
                targets=[RouteTarget(node="node-a", model="node-a-model")],
            )
        )
        is None
    )

    restored = client.patch("/vampire/v1/nodes/node-a", json={"status": "online"})

    assert restored.status_code == 200
    assert restored.json()["status"] == "online"


def test_virtual_model_request_routes_to_selected_node(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )
    client.post(
        "/vampire/v1/nodes", json={"id": "node-b", "lmstudio_base_url": "http://node-b:1234"}
    )
    client.post(
        "/vampire/v1/routes",
        json={
            "id": "route-auto",
            "virtual_model": "vampire:auto",
            "targets": [{"node": "node-b", "model": "node-b-model"}],
            "strategy": "round_robin",
        },
    )

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "vampire:auto",
            "messages": [{"role": "user", "content": "hello"}],
            "vampire": {"mode": "route"},
        },
    )

    assert resp.status_code == 200
    assert resp.json()["model"] == "node-b-model"
    assert resp.json()["node"] == "node-b"
    assert resp.json()["saw_vampire_control"] is False
    assert resp.headers["x-vampire-route"] == "route-auto"
    assert resp.headers["x-vampire-node"] == "node-b"
    assert resp.headers["x-vampire-model"] == "node-b-model"


def test_route_target_removed_before_dispatch_returns_structured_503(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )
    original_get = registry.get
    calls = 0

    def _get_then_missing(node_id: str) -> Node | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_get(node_id)
        return None

    monkeypatch.setattr(registry, "get", _get_then_missing)

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "node-a-model",
            "messages": [{"role": "user", "content": "hello"}],
            "vampire": {"mode": "route"},
        },
    )

    assert resp.status_code == 503
    assert resp.json()["error"] == {
        "message": "Route target node-a went offline before dispatch.",
        "type": "vampire_routing_error",
        "code": "route_target_unavailable",
    }


def test_x_vampire_headers_control_physical_model_routing(client: TestClient) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-a", "lmstudio_base_url": "http://node-a:1234"}
    )

    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Vampire-Mode": "route", "X-Vampire-Strategy": "model_affinity"},
        json={"model": "node-a-model", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert resp.status_code == 200
    assert resp.json()["model"] == "node-a-model"
    assert resp.headers["x-vampire-strategy"] == "model_affinity"


def test_route_fallback_uses_secondary_policy_when_primary_has_no_online_targets(
    client: TestClient,
) -> None:
    client.post(
        "/vampire/v1/nodes", json={"id": "node-b", "lmstudio_base_url": "http://node-b:1234"}
    )
    client.post(
        "/vampire/v1/routes",
        json={
            "id": "route-primary",
            "virtual_model": "vampire:auto",
            "targets": [{"node": "missing", "model": "missing-model"}],
            "strategy": "round_robin",
            "fallback": "vampire:backup",
        },
    )
    client.post(
        "/vampire/v1/routes",
        json={
            "id": "route-backup",
            "virtual_model": "vampire:backup",
            "targets": [{"node": "node-b", "model": "node-b-model"}],
            "strategy": "least_latency",
        },
    )

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "vampire:auto",
            "messages": [{"role": "user", "content": "hello"}],
            "vampire": {"mode": "fallback"},
        },
    )

    assert resp.status_code == 200
    assert resp.json()["node"] == "node-b"
    assert resp.headers["x-vampire-route"] == "route-backup"
