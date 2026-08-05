"""Built-in provider adapter registry."""

from __future__ import annotations

import httpx

from vampire.providers.base import ProviderAdapter, ProviderProbe
from vampire.providers.ollama import OllamaAdapter
from vampire.providers.openai_compatible import OpenAICompatibleAdapter

_OPENAI = OpenAICompatibleAdapter()
_OLLAMA = OllamaAdapter()


def _adapters(provider_hint: str) -> tuple[ProviderAdapter, ...]:
    if provider_hint == "ollama":
        return (_OLLAMA, _OPENAI)
    return (_OPENAI, _OLLAMA)


async def probe_endpoint(
    client: httpx.AsyncClient,
    base_url: str,
    *,
    timeout: httpx.Timeout,
    provider_hint: str = "auto",
) -> ProviderProbe:
    """Probe a local endpoint using the applicable built-in provider adapters."""
    failures: list[Exception] = []
    for adapter in _adapters(provider_hint):
        try:
            result = await adapter.probe(
                client,
                base_url,
                timeout=timeout,
                provider_hint=provider_hint,
            )
        except (httpx.RequestError, httpx.InvalidURL):
            raise
        except (httpx.HTTPStatusError, ValueError) as exc:
            failures.append(exc)
            continue
        if result is not None:
            return result

    if failures:
        raise failures[-1]
    raise ValueError("endpoint does not expose a supported local LLM model API")
