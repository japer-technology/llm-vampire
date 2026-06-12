"""Vampire command-line interface.

Implements the ``vampire`` console-script. ``serve`` runs the gateway; the other
subcommands (``discover``, ``share``, ``nodes``, ``status``, ``route``) match the
CLI shape in ASPIRATION.md and are stubbed pending the phases in
IMPLEMENTATION-PLAN.md.
"""

from __future__ import annotations

import argparse

from vampire import __version__
from vampire.config import get_settings


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    host = args.host or settings.host
    port = args.port or settings.port
    uvicorn.run("vampire.app:create_app", host=host, port=port, factory=True)
    return 0


def _todo(args: argparse.Namespace) -> int:
    print(f"`vampire {args.command}` is not implemented yet (design-stage scaffold).")
    print("See IMPLEMENTATION-PLAN.md for the roadmap.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vampire", description="LM Studio Vampire gateway.")
    parser.add_argument("--version", action="version", version=f"vampire {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the OpenAI-compatible gateway.")
    serve.add_argument("--host", default=None, help="Host to bind (default 127.0.0.1).")
    serve.add_argument("--port", type=int, default=None, help="Port to bind (default 7777).")
    serve.set_defaults(func=_serve)

    for name, help_text in (
        ("discover", "Discover LM Studio nodes on the LAN."),
        ("share", "Control owner sharing modes."),
        ("nodes", "Manage the node registry."),
        ("status", "Show cluster status."),
        ("route", "Inspect or set routing rules."),
    ):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=_todo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
