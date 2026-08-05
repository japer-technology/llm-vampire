"""Core data models (DESIGN-API.md §4).

These Pydantic models describe the orchestration objects Vampire manages. They
are intentionally minimal scaffolds; fields will grow as the phases in
IMPLEMENTATION-PLAN.md are implemented.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

DEFAULT_DISCOVERY_PORTS = (1234, 11434, 8080, 8000, 5000, 5001, 4891, 1337)
"""Common ports used by local LLM servers supported by automatic discovery."""

OpenAIRole = Literal["system", "user", "assistant", "tool", "developer"]
"""Roles accepted by the OpenAI-compatible chat message format."""

ModelKind = Literal["physical", "virtual"]
"""Model catalogue categories: node-hosted models or Vampire virtual aliases."""

ShareMode = Literal["off", "local", "personal", "family", "business", "event"]
"""Owner sharing modes exposed by the required ``vampire share`` command."""

_SYNTHETIC_CREATED = int(time.time())


class ModelCard(BaseModel):
    """OpenAI-compatible model listing item."""

    id: str
    object: Literal["model"] = "model"
    created: int = _SYNTHETIC_CREATED
    owned_by: str = "llm-vampire"

    model_config = ConfigDict(extra="allow")


class ModelListResponse(BaseModel):
    """OpenAI-compatible model list response."""

    object: Literal["list"] = "list"
    data: list[ModelCard] = Field(default_factory=list)

    @field_validator("data")
    @classmethod
    def keep_model_ids_unique(cls, data: list[ModelCard]) -> list[ModelCard]:
        ids = [model.id for model in data]
        if len(ids) != len(set(ids)):
            raise ValueError("model ids must be unique")
        return data


class NodeCapabilities(BaseModel):
    """Capabilities Vampire records for an owner-approved LLM service.

    Phase 0 supplies the shape. Phase 2 will populate it by interrogating each
    node, and Phase 3 routing can use it to avoid sending embeddings, tools, or
    vision requests to nodes that cannot serve them.
    """

    chat: bool = True
    responses: bool = False
    completions: bool = True
    embeddings: bool = False
    vision: bool = False
    tools: bool = False
    streaming: bool = True


class Node(BaseModel):
    """A machine running an owner-approved local LLM API endpoint (§4.1).

    ``base_url`` is the provider endpoint Vampire proxies to. The deprecated
    ``lmstudio_base_url`` input and output remain available for existing clients.
    ``agent_base_url`` is reserved for the optional node agent deferred beyond
    MVP. ``trusted`` and ``tags`` are carried from day one because later routing
    and policy phases use them without changing the public node shape.
    """

    id: str
    name: str | None = None
    host: str | None = None
    base_url: str
    provider: str = "auto"
    api_format: str = "openai-compatible"
    agent_base_url: str | None = None
    status: str = "unknown"
    trusted: bool = False
    capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)
    tags: list[str] = Field(default_factory=list)
    models: list[ModelCard] = Field(default_factory=list)
    request_count: int = 0
    error_count: int = 0
    active_requests: int = 0
    queue_depth: int = 0
    latency_ms: float | None = None
    tokens_per_second: float | None = None
    last_checked_at: str | None = None
    last_error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_base_url(cls, data: Any) -> Any:
        """Accept the pre-rebrand ``lmstudio_base_url`` request field."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        base_url = values.get("base_url")
        legacy_url = values.get("lmstudio_base_url")
        if base_url is None and legacy_url is not None:
            values["base_url"] = legacy_url
        elif base_url is not None and legacy_url is not None and base_url != legacy_url:
            raise ValueError("base_url and lmstudio_base_url must match")
        return values

    @computed_field(return_type=str)
    @property
    def lmstudio_base_url(self) -> str:
        """Return the deprecated provider URL field for API compatibility."""
        return self.base_url


class NodeUpdate(BaseModel):
    """Partial update for a registered LLM service node (§14)."""

    name: str | None = None
    host: str | None = None
    base_url: str | None = None
    provider: str | None = None
    api_format: str | None = None
    agent_base_url: str | None = None
    status: str | None = None
    trusted: bool | None = None
    capabilities: NodeCapabilities | None = None
    tags: list[str] | None = None
    active_requests: int | None = None
    queue_depth: int | None = None
    tokens_per_second: float | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_base_url(cls, data: Any) -> Any:
        """Accept the pre-rebrand ``lmstudio_base_url`` patch field."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        base_url = values.get("base_url")
        legacy_url = values.get("lmstudio_base_url")
        if base_url is None and legacy_url is not None:
            values["base_url"] = legacy_url
        elif base_url is not None and legacy_url is not None and base_url != legacy_url:
            raise ValueError("base_url and lmstudio_base_url must match")
        return values


class DiscoveryRequest(BaseModel):
    """Discovery request body (DESIGN-API.md §12)."""

    methods: list[str] = Field(default_factory=lambda: ["static"])
    subnets: list[str] = Field(default_factory=list)
    ports: list[int] = Field(default_factory=lambda: list(DEFAULT_DISCOVERY_PORTS))
    timeout_ms: int = 1500
    trusted_only: bool = False
    base_urls: list[str] = Field(default_factory=list)


class PhysicalModel(BaseModel):
    """Detailed model inventory item exposed by ``/vampire/v1/models`` (§15)."""

    node: str
    model: str
    provider: str = "openai-compatible"
    api_format: str = "openai-compatible"
    loaded: bool = True
    owned_by: str = "llm-vampire"
    capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)
    context_window: int | None = None
    tokens_per_second: float | None = None

    model_config = ConfigDict(extra="allow")


class VirtualModel(BaseModel):
    """A model alias exposed by Vampire instead of a single physical model (§4.2).

    ``targets`` names candidate node/model pairs for the alias, ``policy_id``
    links to future policy controls, and ``metadata`` gives later phases a safe
    extension point without breaking clients that already understand the base
    object.
    """

    id: str
    type: ModelKind = "virtual"
    description: str | None = None
    targets: list[str] = Field(default_factory=list)
    policy_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteTarget(BaseModel):
    """A concrete node/model pair that can satisfy a route policy."""

    node: str
    model: str


class RoutePolicy(BaseModel):
    """A virtual-model routing rule (DESIGN-API.md §4.3 / §16).

    Phase 0 defines the durable API shape. Phase 3 implements strategy
    execution, while Phase 6 expands ``constraints`` with trust, realm, token,
    and owner-policy requirements.
    """

    id: str
    virtual_model: str
    targets: list[RouteTarget] = Field(default_factory=list)
    strategy: str = "round_robin"
    fallback: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class ShareStatus(BaseModel):
    """Current owner sharing mode for the early CLI/control-plane seam."""

    object: Literal["vampire.share"] = "vampire.share"
    mode: ShareMode = "off"
    enabled: bool = False
    duration: str | None = None
    model: str | None = None


class ShareUpdate(BaseModel):
    """Update payload for the owner sharing command surface."""

    mode: ShareMode
    enabled: bool
    duration: str | None = None
    model: str | None = None


class OpenAIMessage(BaseModel):
    """OpenAI-compatible chat message shape.

    Extra fields are preserved so provider extensions pass through unchanged.
    Tool-call fields are included even before Phase 6 policy because modern
    OpenAI-compatible clients may send or receive them on the transparent
    passthrough surface.
    """

    role: OpenAIRole
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    model_config = ConfigDict(extra="allow")


class OpenAIRequestBase(BaseModel):
    """Shared OpenAI-compatible request fields accepted by local LLM providers.

    The optional ``vampire`` object is ignored by the Phase 1 transparent proxy
    and becomes an opt-in routing/policy control in later phases.
    """

    model: str
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    vampire: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionRequest(OpenAIRequestBase):
    """Request body for ``POST /v1/chat/completions``."""

    messages: list[OpenAIMessage]


class CompletionRequest(OpenAIRequestBase):
    """Request body for ``POST /v1/completions``."""

    prompt: str | list[str]


class EmbeddingsRequest(BaseModel):
    """Request body for ``POST /v1/embeddings``."""

    model: str
    input: str | list[str] | list[int] | list[list[int]]
    vampire: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class ResponsesRequest(OpenAIRequestBase):
    """Request body for ``POST /v1/responses``."""

    input: str | list[dict[str, Any]]


class OpenAIError(BaseModel):
    """OpenAI-compatible error payload (DESIGN-API.md §23)."""

    message: str
    type: str
    code: str | None = None
    param: str | None = None


class OpenAIErrorResponse(BaseModel):
    """OpenAI-compatible error response envelope."""

    error: OpenAIError
