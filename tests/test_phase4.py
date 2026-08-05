"""Phase 4 browser-UI tests (IMPLEMENTATION-PLAN.md §"Phase 4").

Phase 4 ships a static single-page dashboard served from ``/`` by the same
FastAPI process, plus a ``vampire dashboard`` / ``vampire ui`` launcher. The SPA
is plain HTML+JS, so these tests assert two things: the served document wires to
every control/compat surface the plan calls for, and those backend surfaces the
dashboard depends on actually respond end-to-end through the served app.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import get_args

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pytest import CaptureFixture, MonkeyPatch

import vampire.cli as cli
import vampire.proxy as proxy
from vampire.app import create_app
from vampire.models import ShareMode
from vampire.router import MVP_STRATEGIES


def _mock_cluster() -> FastAPI:
    """A small local LLM stand-in so dashboard-driven calls reach a node."""
    app = FastAPI()

    @app.get("/v1/models")
    async def models(request: Request) -> JSONResponse:
        host = request.url.hostname or "unknown"
        return JSONResponse(
            {"object": "list", "data": [{"id": f"{host}-model", "object": "model"}]}
        )

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": "chatcmpl-ui",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}],
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


# --- The served dashboard document -------------------------------------------


def test_dashboard_is_served_from_root_as_html(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Phase 4 dashboard + playground" in resp.text
    assert "llm-vampire" in resp.text


def test_dashboard_wires_to_every_control_surface(client: TestClient) -> None:
    page = client.get("/").text
    for endpoint in (
        "/vampire/v1/status",
        "/vampire/v1/nodes",
        "/vampire/v1/models",
        "/vampire/v1/routes",
        "/vampire/v1/metrics",
        "/vampire/v1/share",
        "/vampire/v1/discover",
    ):
        assert endpoint in page


def test_dashboard_playground_posts_to_openai_chat_completions(client: TestClient) -> None:
    assert "/v1/chat/completions" in client.get("/").text


def test_dashboard_discovery_form_exposes_plan_options(client: TestClient) -> None:
    """Discovery form must offer subnet/port/timeout/trusted-only controls."""
    page = client.get("/").text
    for field in ('name="subnets"', 'name="ports"', 'name="timeout_ms"', 'name="trusted_only"'):
        assert field in page


def test_dashboard_route_form_offers_all_mvp_strategies(client: TestClient) -> None:
    page = client.get("/").text
    for strategy in MVP_STRATEGIES:
        assert strategy in page


def test_dashboard_share_form_offers_owner_share_modes(client: TestClient) -> None:
    page = client.get("/").text
    # Every selectable owner share mode (CLI-only "on"/"stop" aliases excluded).
    for mode in get_args(ShareMode):
        if mode in {"on", "stop"}:
            continue
        assert f">{mode}<" in page


# --- The backend surfaces the dashboard depends on (end-to-end) --------------


def test_dashboard_initial_load_surfaces_all_respond(client: TestClient) -> None:
    """Mirror the SPA's initial fan-out load; each surface must respond 200."""
    for endpoint in (
        "/vampire/v1/status",
        "/vampire/v1/nodes",
        "/vampire/v1/models",
        "/vampire/v1/routes",
        "/vampire/v1/metrics",
        "/vampire/v1/share",
    ):
        assert client.get(endpoint).status_code == 200


def test_dashboard_node_then_playground_round_trip(client: TestClient) -> None:
    """Register a node like the UI, then drive the playground prompt path."""
    registered = client.post(
        "/vampire/v1/nodes",
        json={"id": "home-gpu", "base_url": "http://home-gpu:1234"},
    )
    assert registered.status_code == 200

    # The dashboard summary cards read aggregated models from the control API.
    models = client.get("/vampire/v1/models").json()
    assert any(item["node"] == "home-gpu" for item in models["data"])

    # The prompt playground posts straight to the OpenAI-compatible surface.
    reply = client.post(
        "/v1/chat/completions",
        json={"model": "home-gpu-model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert reply.status_code == 200
    assert reply.json()["choices"][0]["message"]["content"] == "hi"


def test_dashboard_discovery_button_runs_static_discovery(client: TestClient) -> None:
    resp = client.post(
        "/vampire/v1/discover",
        json={"methods": ["static"], "base_urls": ["http://node-c:1234"]},
    )
    assert resp.status_code == 200
    assert resp.json()["object"] == "vampire.discovery_result"


# --- The dashboard launcher command ------------------------------------------


def test_cli_dashboard_prints_gateway_url(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    opened: list[str] = []
    monkeypatch.setattr("vampire.cli.webbrowser.open", opened.append)

    assert cli.main(["dashboard", "--gateway", "http://gateway:7777"]) == 0
    assert "http://gateway:7777" in capsys.readouterr().out
    assert opened == []


def test_cli_ui_alias_opens_browser_when_requested(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    opened: list[str] = []
    monkeypatch.setattr("vampire.cli.webbrowser.open", opened.append)

    assert cli.main(["ui", "--gateway", "http://gateway:7777", "--open"]) == 0
    assert opened == ["http://gateway:7777"]
    assert "http://gateway:7777" in capsys.readouterr().out
