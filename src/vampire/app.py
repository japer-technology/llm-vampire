"""FastAPI application factory.

One process serves three things (METHOD-A.md): the OpenAI-compatible API
(``/v1/*``), the Vampire control API (``/vampire/v1/*``), and the static Phase 4
browser dashboard (``/``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse

import vampire.proxy as proxy
from vampire import __version__
from vampire.api import control, openai_compat
from vampire.auth import AuthError, auth_exception_handler, require_auth

# Repository ``html/`` single-file Phase 4 dashboard served at ``/``. Editable
# installs resolve this from the checked-out repository; packaged installs can
# omit it and still build the API-only application.
DASHBOARD_FILE = Path(__file__).resolve().parents[2] / "html" / "vampire-dashboard.html"


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
    ``/vampire/v1/*``, and the static browser UI at ``/``. The Phase 4
    dashboard is served only when the repository ``html/vampire-dashboard.html``
    file is present so tests and minimal packaged environments can still create
    the API-only application.
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

    if DASHBOARD_FILE.is_file():

        @app.get("/", include_in_schema=False)
        async def dashboard() -> FileResponse:
            """Serve the single-file Phase 4 browser dashboard."""
            return FileResponse(DASHBOARD_FILE, media_type="text/html")

    return app
