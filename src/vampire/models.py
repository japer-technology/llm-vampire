"""Core data models (DESIGN-API.md §4).

These Pydantic models describe the orchestration objects Vampire manages. They
are intentionally minimal scaffolds; fields will grow as the phases in
IMPLEMENTATION-PLAN.md are implemented.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


OpenAIRole = Literal["system", "user", "assistant", "tool", "developer"]
ModelKind = Literal["physical", "virtual"]


class NodeCapabilities(BaseModel):
    chat: bool = True
    responses: bool = False
    completions: bool = True
    embeddings: bool = False
    vision: bool = False
    tools: bool = False
    streaming: bool = True


class Node(BaseModel):
    """A machine running LM Studio (DESIGN-API.md §4.1)."""

    id: str
    name: str | None = None
    host: str | None = None
    lmstudio_base_url: str
    agent_base_url: str | None = None
    status: str = "unknown"
    trusted: bool = False
    capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)
    tags: list[str] = Field(default_factory=list)


class VirtualModel(BaseModel):
    """A model alias exposed by Vampire (DESIGN-API.md §4.2)."""

    id: str
    type: ModelKind = "virtual"
    description: str | None = None
    targets: list[str] = Field(default_factory=list)
    policy_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteTarget(BaseModel):
    node: str
    model: str


class RoutePolicy(BaseModel):
    """A virtual-model routing rule (DESIGN-API.md §4.3 / §16)."""

    id: str
    virtual_model: str
    targets: list[RouteTarget] = Field(default_factory=list)
    strategy: str = "round_robin"
    fallback: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class OpenAIMessage(BaseModel):
    """OpenAI-compatible chat message shape."""

    role: OpenAIRole
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    model_config = ConfigDict(extra="allow")


class OpenAIRequestBase(BaseModel):
    """Shared OpenAI-compatible request fields accepted by LM Studio."""

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


class ModelCard(BaseModel):
    """OpenAI-compatible model listing item."""

    id: str
    object: Literal["model"] = "model"
    owned_by: str = "lmstudio-vampire"

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
