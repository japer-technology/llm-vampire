"""Runtime configuration for the Vampire gateway.

Defaults follow DESIGN-API.md: Vampire listens on port 7777 and proxies to a
downstream LM Studio node that commonly listens on port 1234. Settings can be
overridden with ``VAMPIRE_*`` environment variables. They are cached on first
access for the process lifetime; restart the gateway after changing runtime
configuration.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Vampire runtime settings loaded from defaults, ``.env``, and env vars.

    Pydantic settings applies the ``VAMPIRE_`` prefix, so
    ``VAMPIRE_LMSTUDIO_BASE_URL=http://host:1234`` overrides the default
    downstream node without changing code.
    """

    model_config = SettingsConfigDict(env_prefix="VAMPIRE_", env_file=".env")

    # Address the gateway listens on when ``vampire serve`` starts Uvicorn.
    host: str = "127.0.0.1"
    port: int = 7777

    # Default downstream LM Studio node used by the Phase 1 transparent proxy.
    lmstudio_base_url: str = "http://localhost:1234"

    # Logging verbosity for this gateway process; downstream LM Studio logging is
    # controlled by the node owner, not by Vampire.
    log_level: str = "INFO"

    # Local API key required on API requests. Empty keeps Phase 1 drop-in OpenAI
    # compatibility unauthenticated by default.
    auth_token: str = ""


def configure_logging(settings: Settings | None = None) -> None:
    """Configure process logging from runtime settings."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process settings snapshot."""
    return Settings()
