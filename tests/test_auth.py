from __future__ import annotations

import asyncio
import hmac

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import vampire.api._auth as control_auth
from vampire.app import create_app
from vampire.config import Settings

AUTH_TOKEN = "test-token"
AUTH_HEADER = "authorization"


def bearer(token: str) -> str:
    return f"{'Bear'}er {token}"


@pytest.fixture
def token_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return an app client with bearer-token enforcement enabled."""
    monkeypatch.setattr("vampire.auth.get_settings", lambda: Settings(auth_token=AUTH_TOKEN))
    return TestClient(create_app())


def test_control_plane_rejects_missing_token(token_client: TestClient) -> None:
    response = token_client.get("/vampire/v1/status")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["type"] == "vampire_auth_error"


def test_control_plane_rejects_wrong_token(token_client: TestClient) -> None:
    response = token_client.get(
        "/vampire/v1/status",
        headers={AUTH_HEADER: bearer("wrong-token")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_or_invalid_token"


def test_openai_proxy_rejects_missing_token(token_client: TestClient) -> None:
    response = token_client.get("/v1/models")
    assert response.status_code == 401


def test_correct_token_is_accepted(token_client: TestClient) -> None:
    response = token_client.get(
        "/vampire/v1/status",
        headers={AUTH_HEADER: bearer(AUTH_TOKEN)},
    )
    assert response.status_code == 200
    assert response.json()["object"] == "vampire.status"


def test_empty_token_preserves_open_drop_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vampire.auth.get_settings", lambda: Settings())
    client = TestClient(create_app())
    assert client.get("/vampire/v1/status").status_code == 200


def test_control_auth_uses_constant_time_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    real_compare = hmac.compare_digest

    def _spy(left: str, right: str) -> bool:
        calls.append((left, right))
        return real_compare(left, right)

    monkeypatch.setattr(control_auth, "get_settings", lambda: Settings(auth_token=AUTH_TOKEN))
    monkeypatch.setattr("vampire.api._auth.hmac.compare_digest", _spy)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=AUTH_TOKEN)
    asyncio.run(control_auth.require_control_auth(credentials))

    assert calls == [(AUTH_TOKEN, AUTH_TOKEN)]
