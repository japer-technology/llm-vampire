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
    """Proxy ``GET /v1/models`` to the configured LM Studio node unchanged."""
    return await proxy_request(request)


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    """Proxy chat completions, including Server-Sent Event streaming bodies."""
    return await proxy_request(request)


@router.post("/completions")
async def completions(request: Request) -> Response:
    """Proxy legacy text completions for clients that still use that endpoint."""
    return await proxy_request(request)


@router.post("/responses")
async def responses(request: Request) -> Response:
    """Proxy the newer OpenAI-compatible Responses endpoint when LM Studio serves it."""
    return await proxy_request(request)


@router.post("/embeddings")
async def embeddings(request: Request) -> Response:
    """Proxy embedding requests and preserve LM Studio's response envelope."""
    return await proxy_request(request)


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def passthrough(path: str, request: Request) -> Response:
    """Forward any other ``/v1/*`` path so compatibility is not artificially capped.

    LM Studio's OpenAI-compatible surface can grow faster than Vampire's named
    route list. The catch-all keeps clients working by passing unknown compatible
    paths, query strings, headers, and bodies through the same transparent proxy.
    """
    return await proxy_request(request)
