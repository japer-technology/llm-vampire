"""Runtime configuration for the LLM Vampire gateway.

Vampire listens on port 7777 and proxies to a provider-neutral local LLM
endpoint. Settings can be overridden with ``VAMPIRE_*`` environment variables.
They are cached on first access for the process lifetime; restart the gateway
after changing runtime configuration.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Vampire runtime settings loaded from defaults, ``.env``, and env vars.

    ``VAMPIRE_DEFAULT_BASE_URL`` selects the fallback downstream service. The
    pre-rebrand ``VAMPIRE_LMSTUDIO_BASE_URL`` name remains supported.
    """

    model_config = SettingsConfigDict(env_prefix="VAMPIRE_", env_file=".env", populate_by_name=True)

    # Address the gateway listens on when ``vampire serve`` starts Uvicorn.
    host: str = "127.0.0.1"
    port: int = 7777

    # Default downstream service used when no registered node is selected.
    default_base_url: str = Field(
        default="http://localhost:1234",
        validation_alias=AliasChoices(
            "default_base_url",
            "lmstudio_base_url",
            "VAMPIRE_DEFAULT_BASE_URL",
            "VAMPIRE_LMSTUDIO_BASE_URL",
        ),
    )

    # Logging verbosity for this gateway process; downstream provider logging is
    # controlled by the node owner, not by Vampire.
    log_level: str = "INFO"

    # Local API key required on API requests. Empty keeps Phase 1 drop-in OpenAI
    # compatibility unauthenticated by default.
    auth_token: str = ""

    @property
    def lmstudio_base_url(self) -> str:
        """Return the deprecated fallback URL attribute for compatibility."""
        return self.default_base_url


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
