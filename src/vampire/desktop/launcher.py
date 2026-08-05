"""Double-click friendly desktop launcher for packaged Vampire builds."""

from __future__ import annotations

import argparse
import threading
import webbrowser

from vampire.app import create_app
from vampire.config import configure_logging, get_settings


def build_parser() -> argparse.ArgumentParser:
    """Create the desktop launcher parser."""
    parser = argparse.ArgumentParser(
        prog="vampire-desktop",
        description="Start LLM Vampire and open the browser dashboard.",
    )
    parser.add_argument("--host", default=None, help="Host to bind (default from settings).")
    parser.add_argument(
        "--port", type=int, default=None, help="Port to bind (default from settings)."
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the gateway without opening the dashboard in a browser.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the gateway, open the dashboard, and block until the server exits."""
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)
    host = args.host or settings.host
    port = args.port or settings.port
    url = f"http://{host}:{port}"

    if not args.no_open:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()

    import uvicorn

    uvicorn.run(create_app(), host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
