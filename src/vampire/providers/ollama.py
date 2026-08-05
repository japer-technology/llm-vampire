"""Adapter for Ollama's native model inventory API."""

from __future__ import annotations

from typing import Any

import httpx

from vampire.models import ModelCard, NodeCapabilities
from vampire.providers.base import ProviderProbe


class OllamaAdapter:
    """Normalize Ollama's ``/api/tags`` response into OpenAI model cards."""

    name = "ollama"

    async def probe(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        *,
        timeout: httpx.Timeout,
        provider_hint: str,
    ) -> ProviderProbe | None:
        del provider_hint
        response = await client.get(f"{base_url}/api/tags", timeout=timeout)
        if response.status_code in {404, 405}:
            return None
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            return None

        cards: list[ModelCard] = []
        for raw in payload["models"]:
            if not isinstance(raw, dict):
                continue
            model_id = raw.get("name") or raw.get("model")
            if not isinstance(model_id, str) or model_id.startswith("vampire:"):
                continue
            cards.append(
                ModelCard.model_validate(
                    {
                        "id": model_id,
                        "owned_by": "ollama",
                        "modified_at": raw.get("modified_at"),
                        "size": raw.get("size"),
                        "digest": raw.get("digest"),
                        "details": raw.get("details"),
                    }
                )
            )

        return ProviderProbe(
            provider="ollama",
            api_format="ollama",
            models=cards,
            capabilities=NodeCapabilities(embeddings=True),
        )

