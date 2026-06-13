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

    @app.post("/v1/embeddings")
    async def embeddings(request: Request) -> JSONResponse:
        await request.body()
        return JSONResponse(
            {"object": "list", "data": [{"object": "embedding", "embedding": [0.1, 0.2]}]}
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
