"""Layer 1 — LM Studio / OpenAI-compatible routes (DESIGN-API.md §3, §5-6).

These ``/v1/*`` routes are the drop-in compatibility surface. Phase 1 wires them
to the transparent proxy in :mod:`vampire.proxy`; for now they return a clear
"not implemented" payload so the app starts and the contract is visible.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


def _not_implemented(route: str) -> JSONResponse:
    """OpenAI-style error envelope (DESIGN-API.md §23)."""
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "message": f"{route} is not implemented yet (design-stage scaffold).",
                "type": "vampire_not_implemented",
                "code": "not_implemented",
            }
        },
    )


@router.get("/models")
async def list_models() -> JSONResponse:
    return _not_implemented("GET /v1/models")


@router.post("/chat/completions")
async def chat_completions() -> JSONResponse:
    return _not_implemented("POST /v1/chat/completions")


@router.post("/completions")
async def completions() -> JSONResponse:
    return _not_implemented("POST /v1/completions")


@router.post("/responses")
async def responses() -> JSONResponse:
    return _not_implemented("POST /v1/responses")


@router.post("/embeddings")
async def embeddings() -> JSONResponse:
    return _not_implemented("POST /v1/embeddings")
