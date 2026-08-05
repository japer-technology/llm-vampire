"""llm-vampire: provider-neutral local LLM aggregation and orchestration.

Vampire sits in front of one or more owner-approved local LLM services as a
transparent OpenAI-compatible proxy and adds opt-in orchestration (discovery,
routing, fusion, policy). See IMPLEMENTATION-PLAN.md for the build roadmap.

The provider adapter layer normalizes model inventory from OpenAI-compatible
servers and Ollama while preserving transparent ``/v1/*`` passthrough.
"""

__version__ = "0.0.1"
