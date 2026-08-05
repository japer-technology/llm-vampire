"""Smoke tests: the scaffold imports, the app builds, and core routes respond."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import CaptureFixture

from vampire import __version__
from vampire.app import create_app
from vampire.cli import main
from vampire.config import Settings
from vampire.desktop.launcher import build_parser as build_desktop_parser
from vampire.models import (
    ChatCompletionRequest,
    ModelCard,
    ModelListResponse,
    OpenAIMessage,
    VirtualModel,
)


def test_app_builds() -> None:
    app = create_app()
    assert app.title == "llm-vampire"


def test_status_route() -> None:
    client = TestClient(create_app())
    resp = client.get("/vampire/v1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "vampire.status"


def test_phase4_dashboard_is_served_from_root() -> None:
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Phase 4 dashboard + playground" in resp.text
    assert "/vampire/v1/models" in resp.text
    assert "/v1/chat/completions" in resp.text


def test_node_registration_roundtrip() -> None:
    client = TestClient(create_app())
    node = {"id": "node-test", "base_url": "http://localhost:1234"}
    assert client.post("/vampire/v1/nodes", json=node).status_code == 200

    listed = client.get("/vampire/v1/nodes").json()
    assert any(n["id"] == "node-test" for n in listed["data"])


def test_openai_route_proxies_upstream_error_when_node_unreachable() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1/models")
    # With no reachable downstream LLM service the proxy returns an
    # OpenAI-compatible error envelope (DESIGN-API.md §23) rather than crashing.
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_unavailable"


def test_default_settings_match_phase_zero_ports() -> None:
    settings = Settings()
    assert settings.port == 7777
    assert settings.default_base_url == "http://localhost:1234"
    assert settings.log_level == "INFO"


def test_cli_version_uses_phase_zero_console_entrypoint(capsys: CaptureFixture[str]) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    assert f"vampire {__version__}" in capsys.readouterr().out


def test_desktop_launcher_parser_accepts_no_open() -> None:
    args = build_desktop_parser().parse_args(["--host", "127.0.0.1", "--port", "7777", "--no-open"])
    assert args.host == "127.0.0.1"
    assert args.port == 7777
    assert args.no_open is True


def test_virtual_model_shape() -> None:
    model = VirtualModel(id="vampire:auto", targets=["node-a:llama"])
    assert model.type == "virtual"
    assert model.targets == ["node-a:llama"]


def test_openai_request_and_response_shapes() -> None:
    request = ChatCompletionRequest(
        model="local-model",
        messages=[OpenAIMessage(role="user", content="hello")],
        stream=True,
    )
    response = ModelListResponse(data=[ModelCard(id=request.model)])

    assert request.messages[0].role == "user"
    assert request.stream is True
    assert response.data[0].id == "local-model"
