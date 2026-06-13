"""Layer 1 — LM Studio / OpenAI-compatible routes (DESIGN-API.md §3, §5-6).

These ``/v1/*`` routes are the drop-in compatibility surface. Phase 1 wires them
to the transparent proxy in :mod:`vampire.proxy`, which forwards every request to
the configured downstream LM Studio node while preserving streaming (§20) and the
OpenAI error format (§23). The named endpoints below document the Minimal MVP
surface (§24); a catch-all keeps any other ``/v1/*`` path transparent so existing
clients work unchanged by only swapping their base URL.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import Response

from vampire.proxy import proxy_request

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


@router.get("/models")
async def list_models(request: Request) -> Response:
    return await proxy_request(request)


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    return await proxy_request(request)


@router.post("/completions")
async def completions(request: Request) -> Response:
    return await proxy_request(request)


@router.post("/responses")
async def responses(request: Request) -> Response:
    return await proxy_request(request)


@router.post("/embeddings")
async def embeddings(request: Request) -> Response:
    return await proxy_request(request)


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def passthrough(path: str, request: Request) -> Response:
    """Transparently forward any other ``/v1/*`` path to the downstream node."""
    return await proxy_request(request)
