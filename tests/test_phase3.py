"""Phase 3 virtual-model routing tests."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.responses import Response

import vampire.api.openai_compat as openai_compat
import vampire.proxy as proxy
from vampire.app import create_app
from vampire.models import ModelCard, Node, RoutePolicy, RouteTarget
from vampire.registry import registry, route_registry
from vampire.router import _MAX_CURSORS, Router, Selection


def _mock_cluster() -> FastAPI:
    """A multi-node local LLM stand-in keyed by request host."""
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
                        "created": 1781234567,
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
        base_url=f"http://{node_id}:1234",
        status="online",
        trusted=trusted,
        queue_depth=queue_depth,
        active_requests=active_requests,
        latency_ms=latency_ms,
        models=[ModelCard(id=model)],
    )


def _selected_node(selection: Selection | None) -> str:
    """Assert a route was selected and return its node id."""
    assert selection is not None
    return selection.target.node


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


def test_model_affinity_load_balances_across_replicas_of_same_model() -> None:
    registry.add(_online_node("node-a", "shared"))
    registry.add(_online_node("node-b", "shared"))
    registry.add(_online_node("node-c", "shared"))
    router = Router(registry)
    targets = [
        RouteTarget(node="node-a", model="shared"),
        RouteTarget(node="node-b", model="shared"),
        RouteTarget(node="node-c", model="shared"),
    ]
    policy = RoutePolicy(
        id="affinity-lb",
        virtual_model="vampire:auto",
        targets=targets,
        strategy="model_affinity",
    )

    picks = [_selected_node(router.select(policy, requested_model="shared")) for _ in range(9)]

    assert set(picks) == {"node-a", "node-b", "node-c"}
    assert picks.count("node-a") == 3
    assert picks.count("node-b") == 3
    assert picks.count("node-c") == 3
    selection = router.select(policy, requested_model="shared")
    assert selection is not None
    assert selection.strategy == "model_affinity"


def test_least_busy_reflects_inflight_registry_state() -> None:
    registry.add(_online_node("node-a", "shared"))
    registry.add(_online_node("node-b", "shared"))
    router = Router(registry)
    policy = RoutePolicy(
        id="busy",
        virtual_model="vampire:auto",
        targets=[
            RouteTarget(node="node-a", model="shared"),
            RouteTarget(node="node-b", model="shared"),
        ],
        strategy="least_busy",
    )

    registry.mark_busy("node-a")
    selection = router.select(policy)

    assert selection is not None
    assert selection.target.node == "node-b"
    registry.mark_idle("node-a")
    node = registry.get("node-a")
    assert node is not None
    assert node.active_requests == 0


def test_routed_request_marks_selected_node_busy_until_response_finishes(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})
    observed_active_requests: list[int] = []

    async def _fake_proxy_request_with_body(
        request: Request,
        *,
        downstream_base_url: str | None = None,
        body: bytes | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> Response:
        node = registry.get("node-a")
        assert node is not None
        observed_active_requests.append(node.active_requests)
        response = JSONResponse({"ok": True})
        if response_headers:
            response.headers.update(response_headers)
        return response

    monkeypatch.setattr(openai_compat, "proxy_request_with_body", _fake_proxy_request_with_body)

    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Vampire-Mode": "route", "X-Vampire-Strategy": "least_busy"},
        json={"model": "node-a-model", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert resp.status_code == 200
    assert observed_active_requests == [1]
    node = registry.get("node-a")
    assert node is not None
    assert node.active_requests == 0


def test_round_robin_cursor_map_is_bounded_under_distinct_virtual_models() -> None:
    registry.add(_online_node("node-a", "shared"))
    router = Router(registry)

    for index in range(_MAX_CURSORS + 1000):
        model = f"vampire:probe-{index}"
        policy = router.default_policy(model, requested_model=model)
        assert router.select(policy, requested_model=model) is not None

    assert len(router._cursors) <= _MAX_CURSORS


def test_hot_route_keeps_rotating_after_cursor_eviction() -> None:
    registry.add(_online_node("node-a", "shared"))
    registry.add(_online_node("node-b", "shared"))
    router = Router(registry)
    hot = router.default_policy("vampire:hot", requested_model="vampire:hot")
    assert _selected_node(router.select(hot, requested_model="vampire:hot")) == "node-a"

    for index in range(_MAX_CURSORS + 1000):
        model = f"vampire:cold-{index}"
        policy = router.default_policy(model, requested_model=model)
        assert router.select(policy, requested_model=model) is not None
        if index % 256 == 0:
            assert router.select(hot, requested_model="vampire:hot") is not None

    seen = {_selected_node(router.select(hot, requested_model="vampire:hot")) for _ in range(4)}
    assert seen == {"node-a", "node-b"}


def test_drained_node_stays_registered_but_is_not_route_candidate(client: TestClient) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})

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


def test_patch_unrelated_field_does_not_undrain_node(client: TestClient) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})

    drained = client.patch("/vampire/v1/nodes/node-a", json={"status": "draining"})
    updated = client.patch("/vampire/v1/nodes/node-a", json={"tags": ["gpu"]})

    assert drained.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["tags"] == ["gpu"]
    assert updated.json()["status"] == "draining"
    stored = registry.get("node-a")
    assert stored is not None
    assert stored.status == "draining"
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
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})
    client.post("/vampire/v1/nodes", json={"id": "node-b", "base_url": "http://node-b:1234"})
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
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})
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
        "message": "Selected route target node node-a is no longer registered.",
        "type": "vampire_routing_error",
        "code": "route_target_removed",
    }


def test_x_vampire_headers_control_physical_model_routing(client: TestClient) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})

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
    client.post("/vampire/v1/nodes", json={"id": "node-b", "base_url": "http://node-b:1234"})
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


def test_models_endpoint_survives_virtual_physical_id_collision(client: TestClient) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})
    resp = client.post(
        "/vampire/v1/routes",
        json={
            "id": "collide",
            "virtual_model": "node-a-model",
            "targets": [{"node": "node-a", "model": "node-a-model"}],
            "strategy": "round_robin",
        },
    )
    assert resp.status_code == 409

    registry_route = RoutePolicy(
        id="existing-collide",
        virtual_model="node-a-model",
        targets=[RouteTarget(node="node-a", model="node-a-model")],
    )
    route_registry.add(registry_route)

    models = client.get("/v1/models")

    assert models.status_code == 200
    ids = [card["id"] for card in models.json()["data"]]
    assert len(ids) == len(set(ids))
    card = next(card for card in models.json()["data"] if card["id"] == "node-a-model")
    assert card["owned_by"] == "vampire"


def test_models_listing_includes_created_for_every_card(client: TestClient) -> None:
    registry.add(
        Node(
            id="node-a",
            base_url="http://node-a:1234",
            status="online",
            trusted=True,
            models=[ModelCard(id="node-a-model")],
        )
    )

    response = client.get("/v1/models")

    assert response.status_code == 200
    cards = response.json()["data"]
    assert cards
    for card in cards:
        assert isinstance(card["created"], int)
        assert card["created"] > 0


def test_unknown_strategy_override_is_rejected_not_silently_downgraded(
    client: TestClient,
) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})

    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Vampire-Mode": "route", "X-Vampire-Strategy": "weighted_round_robin"},
        json={"model": "node-a-model", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_strategy"


def test_reported_strategy_is_the_effective_one(client: TestClient) -> None:
    client.post("/vampire/v1/nodes", json={"id": "node-a", "base_url": "http://node-a:1234"})

    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Vampire-Mode": "route", "X-Vampire-Strategy": "model_affinity"},
        json={
            "model": "vampire:auto",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["x-vampire-strategy"] == "round_robin"
