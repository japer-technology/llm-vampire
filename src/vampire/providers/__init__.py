"""Provider adapters for local LLM service discovery and interrogation."""

from vampire.providers.base import ProviderAdapter, ProviderProbe
from vampire.providers.registry import probe_endpoint

__all__ = ["ProviderAdapter", "ProviderProbe", "probe_endpoint"]
