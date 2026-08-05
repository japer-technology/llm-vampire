"""Provider adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from vampire.models import ModelCard, NodeCapabilities


@dataclass(frozen=True)
class ProviderProbe:
    """Normalized result returned after interrogating a provider endpoint."""

    provider: str
    api_format: str
    models: list[ModelCard]
    capabilities: NodeCapabilities


class ProviderAdapter(Protocol):
    """Contract implemented by provider-specific model inventory probes."""

    name: str

    async def probe(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        *,
        timeout: httpx.Timeout,
        provider_hint: str,
    ) -> ProviderProbe | None:
        """Return normalized provider data, or ``None`` when the API is absent."""

