"""Core data models (DESIGN-API.md §4).

These Pydantic models describe the orchestration objects Vampire manages. They
are intentionally minimal scaffolds; fields will grow as the phases in
IMPLEMENTATION-PLAN.md are implemented.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    constraints: dict = Field(default_factory=dict)
