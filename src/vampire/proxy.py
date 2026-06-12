"""Transparent OpenAI-compatible proxy to a downstream LM Studio node.

Phase 1 scaffold (IMPLEMENTATION-PLAN.md): forward ``/v1/*`` requests to a single
configured LM Studio node, preserving streaming and the OpenAI error format. The
full streaming/fan-out implementation is added in later phases.
"""

from __future__ import annotations

import httpx

from vampire.config import get_settings


async def forward(method: str, path: str, body: bytes | None = None) -> httpx.Response:
    """Forward a request to the configured downstream LM Studio node.

    This is a placeholder seam: it shows where ``httpx.AsyncClient`` fan-out will
    live. It is not yet wired into the routes.
    """
    settings = get_settings()
    url = f"{settings.lmstudio_base_url.rstrip('/')}{path}"
    async with httpx.AsyncClient() as client:
        return await client.request(method, url, content=body)
