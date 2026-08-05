"""Provider-neutral discovery and model inventory coverage."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import pytest

from vampire import cluster
from vampire.models import DEFAULT_DISCOVERY_PORTS, DiscoveryRequest, Node
from vampire.registry import registry


def test_local_discovery_includes_popular_provider_ports() -> None:
    urls = cluster._candidate_urls(DiscoveryRequest(methods=["local"]))

    assert {urlparse(url).port for url in urls} == set(DEFAULT_DISCOVERY_PORTS)


@pytest.mark.asyncio
async def test_openai_compatible_probe_identifies_llamacpp() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            headers={"server": "llama.cpp"},
            json={"object": "list", "data": [{"id": "qwen", "owned_by": "local"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        refreshed = await cluster.refresh_node(
            Node(id="llama", base_url="http://127.0.0.1:8080"),
            client=client,
        )

    assert refreshed.status == "online"
    assert refreshed.provider == "llamacpp"
    assert refreshed.api_format == "openai-compatible"
    assert [model.id for model in refreshed.models] == ["qwen"]


@pytest.mark.asyncio
async def test_native_ollama_inventory_survives_registered_node_refresh() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "llama3.2:latest",
                            "size": 2_000_000,
                            "details": {"family": "llama"},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    node = Node(id="ollama", base_url="http://127.0.0.1:11434")
    registry.add(node)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await cluster.refresh_node(node, client=client)
        refreshed = await cluster.refresh_registered_nodes(client=client, force=True)

    assert first.provider == "ollama"
    assert first.api_format == "ollama"
    assert first.models[0].id == "llama3.2:latest"
    assert refreshed[0].status == "online"
    assert refreshed[0].models[0].owned_by == "ollama"
    assert paths.count("/api/tags") == 2


def test_provider_metadata_is_exposed_in_normalized_inventory() -> None:
    node = Node(
        id="localai",
        base_url="http://127.0.0.1:8080",
        provider="localai",
        status="online",
        models=[{"id": "codestral", "owned_by": "localai"}],
    )

    inventory = cluster.physical_model_inventory([node])

    assert inventory[0].provider == "localai"
    assert inventory[0].api_format == "openai-compatible"
    assert inventory[0].capabilities.chat is True
