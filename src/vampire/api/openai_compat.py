"""Layer 1 — LM Studio / OpenAI-compatible routes (DESIGN-API.md §3, §5-6).

These ``/v1/*`` routes are the drop-in compatibility surface. Phase 1 wires them
to the transparent proxy in :mod:`vampire.proxy`, which forwards every request to
the configured downstream LM Studio node while preserving streaming (§20) and the
OpenAI error format (§23). The named endpoints below document the Minimal MVP
surface (§24); a catch-all keeps any other ``/v1/*`` path transparent so existing
clients work unchanged by only swapping their base URL.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from vampire.cluster import aggregate_model_cards, refresh_registered_nodes
from vampire.models import ModelCard, ModelListResponse, RoutePolicy
from vampire.proxy import proxy_request, proxy_request_with_body
from vampire.registry import registry, route_registry
from vampire.router import Router

router = APIRouter(prefix="/v1", tags=["openai-compatible"])
_router = Router(registry)


@router.get("/models")
async def list_models(request: Request) -> Response:
    """Return registered-node model aggregation, falling back to Phase 1 passthrough."""
    if registry.list():
        nodes = await refresh_registered_nodes()
        physical = aggregate_model_cards(nodes).data
        virtual_ids = {"vampire:auto"}
        virtual_ids.update(route.virtual_model for route in route_registry.list())
        virtual = [
            ModelCard(id=virtual_id, owned_by="vampire") for virtual_id in sorted(virtual_ids)
        ]
        return JSONResponse(ModelListResponse(data=[*virtual, *physical]).model_dump())
    return await proxy_request(request)


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    """Proxy chat completions, including Server-Sent Event streaming bodies."""
    return await _route_or_proxy(request)


@router.post("/completions")
async def completions(request: Request) -> Response:
    """Proxy legacy text completions for clients that still use that endpoint."""
    return await _route_or_proxy(request)


@router.post("/responses")
async def responses(request: Request) -> Response:
    """Proxy the newer OpenAI-compatible Responses endpoint when LM Studio serves it."""
    return await _route_or_proxy(request)


@router.post("/embeddings")
async def embeddings(request: Request) -> Response:
    """Proxy embedding requests and preserve LM Studio's response envelope."""
    return await _route_or_proxy(request)


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


async def _route_or_proxy(request: Request) -> Response:
    """Route opt-in Vampire requests; otherwise preserve Phase 1 passthrough."""
    body = await request.body()
    payload = _json_payload(body)
    if payload is None:
        return await proxy_request_with_body(request, body=body)

    model = payload.get("model")
    if not isinstance(model, str) or not _is_routing_request(request, payload, model):
        return await proxy_request_with_body(request, body=body)

    strategy = _strategy_override(request, payload)
    policy = _route_policy(request, payload, model, strategy)
    target = _router.select(policy, requested_model=model)
    if target is None and policy.fallback:
        fallback = route_registry.get_by_virtual_model(policy.fallback) or _router.default_policy(
            policy.fallback,
            strategy=strategy or policy.strategy,
            requested_model=policy.fallback,
        )
        target = _router.select(fallback, requested_model=policy.fallback)
        policy = fallback

    if target is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": f"No online route target available for {model}.",
                    "type": "vampire_routing_error",
                    "code": "no_route_target",
                }
            },
        )

    routed_payload = dict(payload)
    routed_payload["model"] = target.model
    routed_payload.pop("vampire", None)
    return await proxy_request_with_body(
        request,
        downstream_base_url=registry.get(target.node).lmstudio_base_url,  # type: ignore[union-attr]
        body=json.dumps(routed_payload).encode("utf-8"),
        response_headers={
            "X-Vampire-Route": policy.id,
            "X-Vampire-Strategy": policy.strategy,
            "X-Vampire-Node": target.node,
            "X-Vampire-Model": target.model,
        },
    )


def _json_payload(body: bytes) -> dict[str, Any] | None:
    """Parse a JSON object request body or return ``None`` for passthrough."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _is_routing_request(request: Request, payload: dict[str, Any], model: str) -> bool:
    """Return whether the request opted in to Phase 3 routing."""
    vampire = _vampire_object(payload)
    mode = request.headers.get("X-Vampire-Mode") or vampire.get("mode")
    return (
        model.startswith("vampire:")
        or mode in {"route", "fallback"}
        or request.headers.get("X-Vampire-Route") is not None
    )


def _strategy_override(request: Request, payload: dict[str, Any]) -> str | None:
    """Extract routing strategy from headers or the opt-in ``vampire`` object."""
    vampire = _vampire_object(payload)
    raw_routing = vampire.get("routing")
    routing = raw_routing if isinstance(raw_routing, dict) else {}
    strategy = request.headers.get("X-Vampire-Strategy") or routing.get("strategy")
    return strategy if isinstance(strategy, str) else None


def _route_policy(
    request: Request,
    payload: dict[str, Any],
    model: str,
    strategy: str | None,
) -> RoutePolicy:
    """Resolve a configured route or synthesize the default Phase 3 policy."""
    vampire = _vampire_object(payload)
    route_id = request.headers.get("X-Vampire-Route") or vampire.get("route")
    route = route_registry.get(route_id) if isinstance(route_id, str) else None
    route = route or route_registry.get_by_virtual_model(model)
    if route is None:
        route = _router.default_policy(
            model, strategy=strategy or "round_robin", requested_model=model
        )
    elif strategy is not None:
        route = route.model_copy(update={"strategy": strategy})
    return route


def _vampire_object(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the request's opt-in Vampire control object when present."""
    raw = payload.get("vampire")
    return raw if isinstance(raw, dict) else {}
