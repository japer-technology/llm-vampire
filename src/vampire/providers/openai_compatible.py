"""Adapter for OpenAI-compatible local LLM servers."""

from __future__ import annotations

from typing import Any

import httpx

from vampire.models import ModelCard, NodeCapabilities
from vampire.providers.base import ProviderProbe

_PROVIDER_MARKERS = (
    ("lm studio", "lmstudio"),
    ("lmstudio", "lmstudio"),
    ("llama.cpp", "llamacpp"),
    ("llamacpp", "llamacpp"),
    ("ollama", "ollama"),
    ("localai", "localai"),
    ("vllm", "vllm"),
    ("text-generation-webui", "text-generation-webui"),
    ("oobabooga", "text-generation-webui"),
    ("kobold", "koboldcpp"),
    ("gpt4all", "gpt4all"),
    ("jan", "jan"),
)


def coerce_model_cards(payload: object) -> list[ModelCard]:
    """Extract model cards from an OpenAI-compatible ``/v1/models`` response."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    cards: list[ModelCard] = []
    for raw in data:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            if raw["id"].startswith("vampire:"):
                continue
            cards.append(ModelCard.model_validate(raw))
    return cards


def _provider_name(response: httpx.Response, cards: list[ModelCard], provider_hint: str) -> str:
    if provider_hint != "auto":
        return provider_hint
    evidence = " ".join(
        [
            response.headers.get("server", ""),
            response.headers.get("x-powered-by", ""),
            *(card.owned_by for card in cards),
        ]
    ).lower()
    for marker, provider in _PROVIDER_MARKERS:
        if marker in evidence:
            return provider
    return "openai-compatible"


class OpenAICompatibleAdapter:
    """Interrogate the standard model inventory exposed by local LLM servers."""

    name = "openai-compatible"

    async def probe(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        *,
        timeout: httpx.Timeout,
        provider_hint: str,
    ) -> ProviderProbe | None:
        response = await client.get(f"{base_url}/v1/models", timeout=timeout)
        if response.status_code in {404, 405}:
            return None
        response.raise_for_status()
        payload: Any = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return None
        cards = coerce_model_cards(payload)
        return ProviderProbe(
            provider=_provider_name(response, cards, provider_hint),
            api_format="openai-compatible",
            models=cards,
            capabilities=NodeCapabilities(),
        )
