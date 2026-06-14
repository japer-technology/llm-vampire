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

import json
import logging
from collections.abc import AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import Response

from vampire.config import get_settings

logger = logging.getLogger(__name__)

# Headers that must not be copied verbatim between connections. ``host`` and
# ``content-length`` are recomputed by httpx for the upstream request; the
# remaining entries are hop-by-hop headers (RFC 9110 §7.6.1) that describe a
# single transport connection. Forwarding them would let client/gateway transfer
# details leak into the gateway/node connection and can corrupt streaming.
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
_DROP_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {
    "host",
    "content-length",
    "authorization",
    "cookie",
}

# No read/write timeout: model generations can stream for a long time. A short
# connect timeout still surfaces unreachable nodes quickly as an upstream error.
_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=None, pool=None)
_LIMITS = httpx.Limits(max_connections=200, max_keepalive_connections=50)


def build_async_client() -> httpx.AsyncClient:
    """Return the HTTP client used to reach downstream LM Studio nodes.

    Exposed as a seam so tests can inject a mock transport (a stand-in LM Studio
    server) without opening real network sockets.
    """
    return httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS)


def _request_client(request: Request) -> tuple[httpx.AsyncClient, bool]:
    client = getattr(request.app.state, "http_client", None)
    if isinstance(client, httpx.AsyncClient):
        return client, False
    return build_async_client(), True


def _filter_request_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    """Return end-to-end request headers safe to forward upstream.

    Custom client headers, including future ``X-Vampire-*`` controls, are
    preserved. Transport-specific headers that httpx must recompute are
    removed, along with client credentials that the gateway terminates itself.
    """
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in _DROP_REQUEST_HEADERS]


def _filter_response_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    """Return end-to-end response headers safe to send back to the client.

    Unlike request headers, ``content-length`` is retained when the upstream sent
    one, but connection-specific hop-by-hop headers are stripped because Uvicorn
    owns the client-side transport.
    """
    return [(k, v) for k, v in headers.multi_items() if k.lower() not in _HOP_BY_HOP_HEADERS]


def _upstream_error(message: str) -> JSONResponse:
    """Build an OpenAI-compatible error envelope for an unreachable node (§23).

    Network failures are the gateway's error, not LM Studio's response, so the
    custom ``vampire_upstream_error`` type lets operators distinguish routing
    connectivity from model-serving failures while keeping the familiar
    ``{"error": ...}`` envelope expected by OpenAI-compatible clients.
    """
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": message,
                "type": "vampire_upstream_error",
                "code": "upstream_unavailable",
            }
        },
    )


async def proxy_request(request: Request, *, downstream_base_url: str | None = None) -> Response:
    """Forward ``request`` to the downstream LM Studio node and stream the reply.

    The method, path, query string, headers and body are passed through
    unchanged so an existing OpenAI / LM Studio client works against the gateway
    by only swapping its base URL. The upstream response is consumed as an async
    byte iterator and returned as a ``StreamingResponse`` so regular JSON,
    chunked transfer, and Server-Sent Events all avoid full-body buffering.
    """
    return await proxy_request_with_body(request, downstream_base_url=downstream_base_url)


async def proxy_request_with_body(
    request: Request,
    *,
    downstream_base_url: str | None = None,
    body: bytes | None = None,
    response_headers: dict[str, str] | None = None,
) -> Response:
    """Forward ``request`` with an optional pre-serialized body and response metadata."""
    settings = get_settings()
    base_url = (downstream_base_url or settings.lmstudio_base_url).rstrip("/")
    url = f"{base_url}{request.url.path}"

    body = body if body is not None else await request.body()
    headers = _filter_request_headers(httpx.Headers(request.headers.raw))

    client, should_close_client = _request_client(request)
    upstream_request = client.build_request(
        request.method,
        url,
        params=request.query_params.multi_items(),
        headers=headers,
        content=body,
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        if should_close_client:
            await client.aclose()
        # Log the underlying cause server-side; do not leak internals to clients.
        logger.warning("Downstream LM Studio node %s unreachable: %r", base_url, exc)
        response = _upstream_error(f"Could not reach downstream LM Studio node at {base_url}.")
        if response_headers:
            response.headers.update(response_headers)
        return response

    is_event_stream = (
        (upstream.headers.get("content-type") or "").lower().startswith("text/event-stream")
    )

    async def body_stream() -> AsyncIterator[bytes]:
        """Relay upstream bytes and close both sides of the upstream connection."""
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        except httpx.HTTPError as exc:
            logger.warning("Downstream LM Studio node %s failed mid-stream: %r", base_url, exc)
            if not is_event_stream:
                raise
            error_frame = json.dumps(
                {
                    "error": {
                        "message": (f"Downstream LM Studio node at {base_url} failed mid-stream."),
                        "type": "vampire_upstream_error",
                        "code": "upstream_stream_interrupted",
                    }
                }
            )
            yield f"data: {error_frame}\n\n".encode()
            yield b"data: [DONE]\n\n"
        finally:
            await upstream.aclose()
            if should_close_client:
                await client.aclose()

    filtered_headers = dict(_filter_response_headers(upstream.headers))
    if response_headers:
        filtered_headers.update(response_headers)
    return StreamingResponse(
        body_stream(),
        status_code=upstream.status_code,
        headers=filtered_headers,
        media_type=upstream.headers.get("content-type"),
    )
