"""FastAPI application factory.

One process serves three things (METHOD-A.md): the OpenAI-compatible API
(``/v1/*``), the Vampire control API (``/vampire/v1/*``), and the static browser
UI (``/``).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vampire import __version__
from vampire.api import control, openai_compat

# Repository ``web/`` directory holding the static single-page UI. Editable
# installs resolve this from the checked-out repository; packaged installs can
# omit it until the Phase 4 dashboard graduates from placeholder to product UI.
WEB_DIR = Path(__file__).resolve().parents[2] / "web"


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
    )

    app.include_router(openai_compat.router)
    app.include_router(control.router)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

    return app
