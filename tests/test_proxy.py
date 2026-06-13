"""Phase 1 transparent-proxy tests (IMPLEMENTATION-PLAN.md).

A mock LM Studio server stands in for a real node so the ``/v1/*`` passthrough,
OpenAI-compatible streaming (DESIGN-API.md §20), and error format (§23) can be
exercised without GPUs or real network sockets.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.responses import Response

import vampire.proxy as proxy
from vampire.app import create_app


def _mock_lmstudio() -> FastAPI:
    """A tiny stand-in for LM Studio's OpenAI-compatible API."""
    app = FastAPI()

    @app.get("/v1/models")
    async def models() -> JSONResponse:
        return JSONResponse({"object": "list", "data": [{"id": "local-model", "object": "model"}]})

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Response:
        payload = await request.json()
        if not payload.get("stream"):
            return JSONResponse(
                {
                    "id": "chatcmpl-1",
                    "object": "chat.completion",
                    "model": payload["model"],
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}],
                }
            )

        async def events() -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/v1/completions")
    async def completions(request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": "cmpl-1",
                "object": "text_completion",
                "model": payload["model"],
                "choices": [{"index": 0, "text": "hello"}],
            }
        )

    @app.post("/v1/responses")
    async def responses(request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": "resp-1",
                "object": "response",
                "model": payload["model"],
                "output_text": "hi",
            }
        )

    @app.post("/v1/embeddings")
    async def embeddings(request: Request) -> JSONResponse:
        await request.body()
        return JSONResponse(
            {"object": "list", "data": [{"object": "embedding", "embedding": [0.1, 0.2]}]}
        )

    @app.api_route("/v1/echo/{path:path}", methods=["GET", "POST", "PATCH"])
    async def echo(path: str, request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "path": path,
                "query": dict(request.query_params),
                "x_client_marker": request.headers.get("x-client-marker"),
                "x_vampire_route": request.headers.get("x-vampire-route"),
            }
        )

    @app.get("/v1/rate-limited")
    async def rate_limited() -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "message": "too many requests",
                    "type": "rate_limit_error",
                    "code": "rate_limit",
                }
            },
        )

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Gateway client whose downstream node is the in-process mock server."""
    mock = _mock_lmstudio()
    original = proxy.build_async_client

    def _build() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=mock))

    proxy.build_async_client = _build
    try:
        yield TestClient(create_app())
    finally:
        proxy.build_async_client = original


def test_models_passthrough(client: TestClient) -> None:
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == "local-model"


def test_chat_completion_passthrough(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "local-model", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "hi"


def test_chat_completion_streaming_passthrough(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "local-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "data: [DONE]" in resp.text


def test_embeddings_passthrough(client: TestClient) -> None:
    resp = client.post("/v1/embeddings", json={"model": "local-model", "input": "hello"})
    assert resp.status_code == 200
    assert resp.json()["data"][0]["embedding"] == [0.1, 0.2]


def test_completions_passthrough(client: TestClient) -> None:
    resp = client.post("/v1/completions", json={"model": "local-model", "prompt": "hello"})
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["text"] == "hello"


def test_responses_passthrough(client: TestClient) -> None:
    resp = client.post("/v1/responses", json={"model": "local-model", "input": "hello"})
    assert resp.status_code == 200
    assert resp.json()["object"] == "response"


def test_catch_all_preserves_query_and_end_to_end_headers(client: TestClient) -> None:
    resp = client.patch(
        "/v1/echo/custom/path?alpha=one&beta=two",
        headers={"X-Client-Marker": "kept", "X-Vampire-Route": "future-control"},
        json={"ignored": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "custom/path"
    assert body["query"] == {"alpha": "one", "beta": "two"}
    assert body["x_client_marker"] == "kept"
    assert body["x_vampire_route"] == "future-control"


def test_upstream_openai_error_status_and_body_passthrough(client: TestClient) -> None:
    resp = client.get("/v1/rate-limited")

    assert resp.status_code == 429
    assert resp.json()["error"]["type"] == "rate_limit_error"
