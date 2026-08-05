"""Vampire command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from typing import Any

import httpx

from vampire import __version__
from vampire.config import configure_logging, get_settings
from vampire.models import DEFAULT_DISCOVERY_PORTS

DEFAULT_GATEWAY_URL = "http://127.0.0.1:7777"


def _serve(args: argparse.Namespace) -> int:
    """Run the gateway with CLI flags taking precedence over environment settings."""
    import uvicorn

    from vampire.app import create_app

    settings = get_settings()
    configure_logging(settings)
    host = args.host or settings.host
    port = args.port or settings.port
    uvicorn.run(create_app(), host=host, port=port)
    return 0


def build_sync_client() -> httpx.Client:
    """Return the HTTP client used by control-plane CLI commands."""
    return httpx.Client(timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0))


def _gateway_url(args: argparse.Namespace) -> str:
    """Return the configured Vampire gateway URL without a trailing slash."""
    return str(args.gateway).rstrip("/")


def _print_json(data: object) -> None:
    """Write a stable JSON representation for scripts and humans."""
    print(json.dumps(data, indent=2, sort_keys=True))


def _control_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> int:
    """Call a ``/vampire/v1/*`` control endpoint and print its response."""
    url = f"{_gateway_url(args)}{path}"
    try:
        with build_sync_client() as client:
            response = client.request(method, url, json=json_body)
    except httpx.RequestError as exc:
        print(f"Could not reach Vampire gateway at {_gateway_url(args)}: {exc}", file=sys.stderr)
        return 1

    try:
        payload: object = response.json()
    except ValueError:
        payload = {"status_code": response.status_code, "body": response.text}

    _print_json(payload)
    return 0 if response.is_success else 1


def _status(args: argparse.Namespace) -> int:
    """Show gateway and cluster status."""
    return _control_request(args, "GET", "/vampire/v1/status")


def _discover(args: argparse.Namespace) -> int:
    """Ask the gateway to discover reachable local LLM services."""
    body: dict[str, Any] = {
        "methods": args.methods or ["local"],
        "subnets": args.subnets,
        "ports": args.ports if args.ports is not None else list(DEFAULT_DISCOVERY_PORTS),
        "timeout_ms": args.timeout_ms,
        "trusted_only": args.trusted_only,
        "base_urls": args.base_urls,
    }
    return _control_request(args, "POST", "/vampire/v1/discover", json_body=body)


def _nodes_list(args: argparse.Namespace) -> int:
    """List registered nodes."""
    return _control_request(args, "GET", "/vampire/v1/nodes")


def _nodes_get(args: argparse.Namespace) -> int:
    """Show one registered node."""
    return _control_request(args, "GET", f"/vampire/v1/nodes/{args.node_id}")


def _nodes_add(args: argparse.Namespace) -> int:
    """Register an owner-approved local LLM service node."""
    body: dict[str, Any] = {
        "id": args.node_id,
        "base_url": args.base_url,
        "provider": args.provider,
        "trusted": args.trusted,
        "tags": args.tags,
    }
    if args.name is not None:
        body["name"] = args.name
    if args.host is not None:
        body["host"] = args.host
    if args.agent_base_url is not None:
        body["agent_base_url"] = args.agent_base_url
    return _control_request(args, "POST", "/vampire/v1/nodes", json_body=body)


def _nodes_update(args: argparse.Namespace) -> int:
    """Patch mutable node metadata."""
    body: dict[str, Any] = {}
    for key in (
        "name",
        "host",
        "base_url",
        "provider",
        "agent_base_url",
        "status",
        "trusted",
        "tags",
        "active_requests",
        "queue_depth",
        "tokens_per_second",
    ):
        value = getattr(args, key)
        if value is not None:
            body[key] = value
    return _control_request(args, "PATCH", f"/vampire/v1/nodes/{args.node_id}", json_body=body)


def _nodes_delete(args: argparse.Namespace) -> int:
    """Remove a registered node."""
    return _control_request(args, "DELETE", f"/vampire/v1/nodes/{args.node_id}")


def _nodes_drain(args: argparse.Namespace) -> int:
    """Mark a node unavailable for routing, or restore it to health-checked service."""
    status = "online" if args.state == "off" else "draining"
    return _control_request(
        args,
        "PATCH",
        f"/vampire/v1/nodes/{args.node_id}",
        json_body={"status": status},
    )


def _models(args: argparse.Namespace) -> int:
    """List the gateway's aggregated model inventory."""
    return _control_request(args, "GET", "/vampire/v1/models")


def _metrics(args: argparse.Namespace) -> int:
    """Show the dashboard metrics snapshot."""
    return _control_request(args, "GET", "/vampire/v1/metrics")


def _routes_list(args: argparse.Namespace) -> int:
    """List virtual-model route policies."""
    return _control_request(args, "GET", "/vampire/v1/routes")


def _routes_get(args: argparse.Namespace) -> int:
    """Show one route policy."""
    return _control_request(args, "GET", f"/vampire/v1/routes/{args.route_id}")


def _route_targets(raw_targets: list[str]) -> list[dict[str, str]]:
    """Parse ``node:model`` CLI targets into API route target objects."""
    targets: list[dict[str, str]] = []
    for raw in raw_targets:
        node, separator, model = raw.partition(":")
        if not separator or not node or not model:
            raise argparse.ArgumentTypeError("targets must use node:model")
        targets.append({"node": node, "model": model})
    return targets


def _routes_add(args: argparse.Namespace) -> int:
    """Create or replace a virtual-model route policy."""
    try:
        targets = _route_targets(args.targets)
    except argparse.ArgumentTypeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    body: dict[str, Any] = {
        "id": args.route_id,
        "virtual_model": args.virtual_model,
        "targets": targets,
        "strategy": args.strategy,
        "constraints": {},
    }
    if args.fallback is not None:
        body["fallback"] = args.fallback
    return _control_request(args, "POST", "/vampire/v1/routes", json_body=body)


def _routes_delete(args: argparse.Namespace) -> int:
    """Remove a virtual-model route policy."""
    return _control_request(args, "DELETE", f"/vampire/v1/routes/{args.route_id}")


def _share(args: argparse.Namespace) -> int:
    """Set the owner sharing mode required by the METHOD-A CLI shape."""
    if args.mode in {"off", "stop"} and args.state is not None:
        print("share off/stop do not accept an on/off state", file=sys.stderr)
        return 2

    mode = "off" if args.mode in {"off", "stop"} else args.mode
    if mode == "on":
        mode = "local"
    enabled = False if mode == "off" else args.state != "off"
    body: dict[str, Any] = {"mode": mode, "enabled": enabled}
    if args.duration is not None:
        body["duration"] = args.duration
    if args.model is not None:
        body["model"] = args.model
    return _control_request(args, "POST", "/vampire/v1/share", json_body=body)


def _dashboard(args: argparse.Namespace) -> int:
    """Print or open the Phase 4 browser dashboard URL."""
    url = _gateway_url(args)
    if args.open:
        webbrowser.open(url)
    print(url)
    return 0


def _todo(args: argparse.Namespace) -> int:
    """Explain that a future-phase command exists in the CLI shape only."""
    print(f"`vampire {args.command}` is not implemented yet (design-stage scaffold).")
    print("See IMPLEMENTATION-PLAN.md for the roadmap.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Create the ``vampire`` parser and bind subcommands to their handlers.

    Phase 0 exposes the console-script; Phases 2 and 3 wire the CLI to the
    control API for discovery, node registry, status, models, metrics, and
    route management. Phase 4 adds the dashboard launcher command.
    """
    parser = argparse.ArgumentParser(prog="vampire", description="LLM Vampire gateway.")
    parser.add_argument("--version", action="version", version=f"vampire {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    gateway_parent = argparse.ArgumentParser(add_help=False)
    gateway_parent.add_argument(
        "--gateway",
        default=DEFAULT_GATEWAY_URL,
        help=f"Vampire gateway base URL (default {DEFAULT_GATEWAY_URL}).",
    )

    serve = sub.add_parser("serve", help="Run the OpenAI-compatible gateway.")
    serve.add_argument("--host", default=None, help="Host to bind (default 127.0.0.1).")
    serve.add_argument("--port", type=int, default=None, help="Port to bind (default 7777).")
    serve.set_defaults(func=_serve)

    status = sub.add_parser("status", parents=[gateway_parent], help="Show cluster status.")
    status.set_defaults(func=_status)

    discover = sub.add_parser(
        "discover", parents=[gateway_parent], help="Discover local LLM services."
    )
    discover.add_argument(
        "--method",
        dest="methods",
        action="append",
        choices=["local", "static", "lan_scan"],
        default=None,
    )
    discover.add_argument("--subnet", dest="subnets", action="append", default=[])
    discover.add_argument("--port", dest="ports", type=int, action="append", default=None)
    discover.add_argument("--timeout-ms", type=int, default=1500)
    discover.add_argument("--trusted-only", action="store_true")
    discover.add_argument("--base-url", dest="base_urls", action="append", default=[])
    discover.set_defaults(func=_discover)

    nodes = sub.add_parser("nodes", parents=[gateway_parent], help="Manage the node registry.")
    node_sub = nodes.add_subparsers(dest="nodes_command")
    nodes.set_defaults(func=_nodes_list)

    node_list = node_sub.add_parser("list", help="List registered nodes.")
    node_list.set_defaults(func=_nodes_list)

    node_add = node_sub.add_parser("add", help="Register a local LLM service.")
    node_add.add_argument("node_id")
    node_add.add_argument("base_url")
    node_add.add_argument(
        "--provider",
        default="auto",
        help="Provider name or auto (default auto).",
    )
    node_add.add_argument("--name")
    node_add.add_argument("--host")
    node_add.add_argument("--agent-base-url")
    node_add.add_argument("--trusted", action="store_true")
    node_add.add_argument("--tag", dest="tags", action="append", default=[])
    node_add.set_defaults(func=_nodes_add)

    node_get = node_sub.add_parser("get", help="Show a registered node.")
    node_get.add_argument("node_id")
    node_get.set_defaults(func=_nodes_get)

    node_update = node_sub.add_parser("update", help="Patch a registered node.")
    node_update.add_argument("node_id")
    node_update.add_argument("--name")
    node_update.add_argument("--host")
    node_update.add_argument("--base-url", "--lmstudio-base-url", dest="base_url")
    node_update.add_argument("--provider")
    node_update.add_argument("--agent-base-url")
    node_update.add_argument("--status")
    node_update.add_argument("--trusted", action="store_true", default=None)
    node_update.add_argument("--tag", dest="tags", action="append")
    node_update.add_argument("--active-requests", type=int)
    node_update.add_argument("--queue-depth", type=int)
    node_update.add_argument("--tokens-per-second", type=float)
    node_update.set_defaults(func=_nodes_update)

    node_drain = node_sub.add_parser("drain", help="Drain or restore a node for routing.")
    node_drain.add_argument("node_id")
    node_drain.add_argument("state", nargs="?", choices=["on", "off"], default="on")
    node_drain.set_defaults(func=_nodes_drain)

    node_delete = node_sub.add_parser("delete", help="Remove a registered node.")
    node_delete.add_argument("node_id")
    node_delete.set_defaults(func=_nodes_delete)

    models = sub.add_parser("models", parents=[gateway_parent], help="List aggregated models.")
    models.set_defaults(func=_models)

    metrics = sub.add_parser("metrics", parents=[gateway_parent], help="Show cluster metrics.")
    metrics.set_defaults(func=_metrics)

    route = sub.add_parser("route", parents=[gateway_parent], help="Inspect or set routing rules.")
    route_sub = route.add_subparsers(dest="route_command")
    route.set_defaults(func=_routes_list)

    route_list = route_sub.add_parser("list", help="List route policies.")
    route_list.set_defaults(func=_routes_list)

    route_add = route_sub.add_parser("add", help="Create or replace a route policy.")
    route_add.add_argument("route_id")
    route_add.add_argument("virtual_model")
    route_add.add_argument("--target", dest="targets", action="append", required=True)
    route_add.add_argument(
        "--strategy",
        default="round_robin",
        choices=["round_robin", "least_busy", "least_latency", "model_affinity", "trusted_only"],
    )
    route_add.add_argument("--fallback")
    route_add.set_defaults(func=_routes_add)

    route_get = route_sub.add_parser("get", help="Show a route policy.")
    route_get.add_argument("route_id")
    route_get.set_defaults(func=_routes_get)

    route_delete = route_sub.add_parser("delete", help="Remove a route policy.")
    route_delete.add_argument("route_id")
    route_delete.set_defaults(func=_routes_delete)

    share = sub.add_parser("share", parents=[gateway_parent], help="Control owner sharing modes.")
    share.add_argument(
        "mode",
        choices=["on", "off", "local", "personal", "family", "business", "event", "stop"],
    )
    share.add_argument("state", nargs="?", choices=["on", "off"])
    share.add_argument("--duration")
    share.add_argument("--model")
    share.set_defaults(func=_share)

    dashboard = sub.add_parser(
        "dashboard",
        parents=[gateway_parent],
        aliases=["ui"],
        help="Print or open the browser dashboard URL.",
    )
    dashboard.add_argument("--open", action="store_true", help="Open the dashboard in a browser.")
    dashboard.set_defaults(func=_dashboard)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
