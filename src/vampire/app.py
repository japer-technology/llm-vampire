"""FastAPI application factory.

One process serves three things (METHOD-A.md): the OpenAI-compatible API
(``/v1/*``), the Vampire control API (``/vampire/v1/*``), and the static browser
UI (``/``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

import vampire.proxy as proxy
from vampire import __version__
from vampire.api import control, openai_compat
from vampire.auth import AuthError, auth_exception_handler, require_auth

# Repository ``web/`` directory holding the static single-page UI. Editable
# installs resolve this from the checked-out repository; packaged installs can
# omit it until the Phase 4 dashboard graduates from placeholder to product UI.
WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http_client = proxy.build_async_client()
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app() -> FastAPI:
    """Build the single-process Vampire application.

    METHOD-A calls for one artifact that exposes three surfaces: the
    OpenAI-compatible proxy at ``/v1/*``, the opt-in Vampire control API at
    ``/vampire/v1/*``, and the static browser UI at ``/``. The UI is mounted only
    when the repository ``web/`` directory is present so tests and minimal
    packaged environments can still create the API-only application.
    """
    app = FastAPI(
        title="lmstudio-vampire",
        version=__version__,
        description="OpenAI-compatible gateway + LAN orchestration for LM Studio.",
        lifespan=_lifespan,
    )

    app.add_exception_handler(AuthError, auth_exception_handler)
    app.include_router(openai_compat.router, dependencies=[Depends(require_auth)])
    app.include_router(control.router, dependencies=[Depends(require_auth)])

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

    return app
