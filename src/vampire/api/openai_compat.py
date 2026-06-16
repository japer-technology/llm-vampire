"""Layer 1 — LM Studio / OpenAI-compatible routes (DESIGN-API.md §3, §5-6).
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.responses import Response, StreamingResponse

from vampire.cluster import aggregate_model_cards, refresh_registered_nodes
from vampire.models import ModelCard, ModelListResponse, RoutePolicy
from vampire.proxy import proxy_request, proxy_request_with_body
from vampire.registry import registry, route_registry
from vampire.router import MVP_STRATEGIES, Router

router = APIRouter(prefix="/v1", tags=["openai-compatible"])
_router = Router(registry)


class StrategyError(ValueError):
    """Raised when a request asks for an unsupported routing strategy."""


@router.get("/models")
async def list_models(request: Request) -> Response:
    """Return registered-node model aggregation, falling back to Phase 1 passthrough."""
    if registry.list():
        nodes = await refresh_registered_nodes(client=_request_http_client(request))
        physical = aggregate_model_cards(nodes).data
        virtual_ids = {"vampire:auto"}
        virtual_ids.update(route.virtual_model for route in route_registry.list())
        virtual = [
            ModelCard(id=virtual_id, owned_by="vampire") for virtual_id in sorted(virtual_ids)
        ]
        physical = [card for card in physical if card.id not in virtual_ids]
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

    try:
        strategy = _strategy_override(request, payload)
    except StrategyError:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "Unsupported routing strategy.",
                    "type": "vampire_routing_error",
                    "code": "unsupported_strategy",
                }
            },
        )
    policy = _route_policy(request, payload, model, strategy)
    selection = _router.select(policy, requested_model=model)
    if selection is None and policy.fallback:
        fallback = route_registry.get_by_virtual_model(policy.fallback) or _router.default_policy(
            policy.fallback,
            strategy=strategy or policy.strategy,
            requested_model=policy.fallback,
        )
        selection = _router.select(fallback, requested_model=policy.fallback)
        policy = fallback

    if selection is None:
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

    target = selection.target
    node = registry.get(target.node)
    if node is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": f"Selected route target node {target.node} is no longer registered.",
                    "type": "vampire_routing_error",
                    "code": "route_target_removed",
                }
            },
        )

    routed_payload = dict(payload)
    routed_payload["model"] = target.model
    routed_payload.pop("vampire", None)
    registry.mark_busy(target.node)
    try:
        response = await proxy_request_with_body(
            request,
            downstream_base_url=node.lmstudio_base_url,
            body=json.dumps(routed_payload).encode("utf-8"),
            response_headers={
                "X-Vampire-Route": policy.id,
                "X-Vampire-Strategy": selection.strategy,
                "X-Vampire-Node": target.node,
                "X-Vampire-Model": target.model,
            },
        )
    except BaseException:
        registry.mark_idle(target.node)
        raise

    if isinstance(response, StreamingResponse):
        original_iterator = response.body_iterator
        async def lifecycle_generator():
            try:
                async for chunk in original_iterator:
                    yield chunk
            finally:
                registry.mark_idle(target.node)
        response.body_iterator = lifecycle_generator()
    else:
        response.background = _release_on_finish(target.node, response.background)
    return response


def _release_on_finish(node_id: str, existing: BackgroundTask | None) -> BackgroundTask:
    release = BackgroundTask(registry.mark_idle, node_id)
    if existing is None:
        return release
    tasks = BackgroundTasks()
    tasks.add_task(existing)
    tasks.add_task(release)
    return tasks


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
    if not isinstance(strategy, str):
        return None
    if strategy not in MVP_STRATEGIES:
        raise StrategyError(f"unsupported routing strategy {strategy!r}")
    return strategy


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


def _request_http_client(request: Request) -> httpx.AsyncClient | None:
    client = getattr(request.app.state, "http_client", None)
    return client if isinstance(client, httpx.AsyncClient) else None
