"""Runtime configuration for the Vampire gateway.

Defaults follow DESIGN-API.md: Vampire listens on port 7777 and proxies to a
downstream LM Studio node that commonly listens on port 1234. Settings can be
overridden with ``VAMPIRE_*`` environment variables.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Vampire runtime settings."""

    model_config = SettingsConfigDict(env_prefix="VAMPIRE_", env_file=".env")

    # Address the gateway listens on.
    host: str = "127.0.0.1"
    port: int = 7777

    # Default downstream LM Studio node used by the Phase 1 transparent proxy.
    lmstudio_base_url: str = "http://localhost:1234"

    # Local API key required on requests (Phase 6). Empty disables auth.
    auth_token: str = ""


def get_settings() -> Settings:
    """Return a fresh Settings instance loaded from the environment."""
    return Settings()
