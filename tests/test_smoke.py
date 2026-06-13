"""Smoke tests: the scaffold imports, the app builds, and core routes respond."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vampire.app import create_app
from vampire.config import Settings
from vampire.models import ChatCompletionRequest, ModelCard, ModelListResponse, VirtualModel


def test_app_builds() -> None:
    app = create_app()
    assert app.title == "lmstudio-vampire"


def test_status_route() -> None:
    client = TestClient(create_app())
    resp = client.get("/vampire/v1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "vampire.status"


def test_node_registration_roundtrip() -> None:
    client = TestClient(create_app())
    node = {"id": "node-test", "lmstudio_base_url": "http://localhost:1234"}
    assert client.post("/vampire/v1/nodes", json=node).status_code == 200

    listed = client.get("/vampire/v1/nodes").json()
    assert any(n["id"] == "node-test" for n in listed["data"])


def test_openai_route_present_but_stubbed() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1/models")
    assert resp.status_code == 501
    assert resp.json()["error"]["code"] == "not_implemented"


def test_default_settings_match_phase_zero_ports() -> None:
    settings = Settings()
    assert settings.port == 7777
    assert settings.lmstudio_base_url == "http://localhost:1234"
    assert settings.log_level == "INFO"


def test_virtual_model_shape() -> None:
    model = VirtualModel(id="vampire:auto", targets=["node-a:llama"])
    assert model.type == "virtual"
    assert model.targets == ["node-a:llama"]


def test_openai_request_and_response_shapes() -> None:
    request = ChatCompletionRequest(
        model="local-model",
        messages=[{"role": "user", "content": "hello"}],
        stream=True,
    )
    response = ModelListResponse(data=[ModelCard(id=request.model)])

    assert request.messages[0].role == "user"
    assert request.stream is True
    assert response.data[0].id == "local-model"
