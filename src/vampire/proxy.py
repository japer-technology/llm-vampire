"""Transparent OpenAI-compatible proxy to a downstream LM Studio node.

Phase 1 (IMPLEMENTATION-PLAN.md): forward ``/v1/*`` requests to a single
configured LM Studio node, preserving OpenAI-compatible streaming
(DESIGN-API.md §20) and the OpenAI error format (DESIGN-API.md §23).

The response is always streamed back to the caller, so both regular JSON
responses and Server-Sent Event streams pass through transparently and the body
never needs to be buffered in full. Multi-node fan-out and routing are layered on
top of this seam in later phases.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from vampire.config import get_settings

# Headers that must not be copied verbatim between connections. ``host`` and
# ``content-length`` are recomputed by httpx for the upstream request; the
# remaining entries are hop-by-hop headers (RFC 9110 §7.6.1) that describe a
# single transport connection rather than the end-to-end message.
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_DROP_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {"host", "content-length"}

# No read/write timeout: model generations can stream for a long time. A short
# connect timeout still surfaces unreachable nodes quickly as an upstream error.
_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=None, pool=None)


def build_async_client() -> httpx.AsyncClient:
    """Return the HTTP client used to reach downstream LM Studio nodes.

    Exposed as a seam so tests can inject a mock transport (a stand-in LM Studio
    server) without opening real network sockets.
    """
    return httpx.AsyncClient(timeout=_TIMEOUT)


def _filter_request_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in _DROP_REQUEST_HEADERS]


def _filter_response_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in _HOP_BY_HOP_HEADERS]


def _upstream_error(message: str, detail: str) -> JSONResponse:
    """OpenAI-compatible error envelope for an unreachable node (§23)."""
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": message,
                "type": "vampire_upstream_error",
                "code": "upstream_unavailable",
                "vampire": {"detail": detail},
            }
        },
    )


async def proxy_request(request: Request, *, downstream_base_url: str | None = None) -> Response:
    """Forward ``request`` to the downstream LM Studio node and stream the reply.

    The method, path, query string, headers and body are passed through
    unchanged so an existing OpenAI / LM Studio client works against the gateway
    by only swapping its base URL.
    """
    settings = get_settings()
    base_url = (downstream_base_url or settings.lmstudio_base_url).rstrip("/")
    url = f"{base_url}{request.url.path}"

    body = await request.body()
    headers = _filter_request_headers(httpx.Headers(request.headers.raw))

    client = build_async_client()
    upstream_request = client.build_request(
        request.method,
        url,
        params=dict(request.query_params),
        headers=headers,
        content=body,
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        return _upstream_error(
            f"Could not reach downstream LM Studio node at {base_url}.",
            f"{type(exc).__name__}: {exc}",
        )

    async def body_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body_stream(),
        status_code=upstream.status_code,
        headers=dict(_filter_response_headers(upstream.headers)),
        media_type=upstream.headers.get("content-type"),
    )
