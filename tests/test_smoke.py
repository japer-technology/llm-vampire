"""Smoke tests: the scaffold imports, the app builds, and core routes respond."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vampire.app import create_app


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
