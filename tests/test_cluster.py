import pytest
import asyncio
from vampire.registry import registry
from vampire.cluster import discover_nodes, _node_id_for_url
from vampire.models import DiscoveryRequest, Node
import httpx
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_discover_nodes_prevents_resurrection(monkeypatch):
    # Setup
    base_url = "http://localhost:1234"
    node_id = _node_id_for_url(base_url)
    node = Node(id=node_id, lmstudio_base_url=base_url, status="online")
    registry.add(node)

    # We want to simulate a node being removed during the refresh_node call
    async def slow_refresh(n, timeout_ms=None, client=None):
        await asyncio.sleep(0.1)
        return n.model_copy(update={"status": "online"})

    # Mocking functions in vampire.cluster
    monkeypatch.setattr("vampire.cluster.refresh_node", AsyncMock(side_effect=slow_refresh))
    monkeypatch.setattr("vampire.cluster._candidate_urls", lambda req: [base_url])

    # 1. Start discovery
    request = DiscoveryRequest(subnets=["127.0.0.1"], ports=[1234])
    discovery_task = asyncio.create_task(discover_nodes(request))
    
    # 2. Wait for the probe to be "in flight" (in the sleep)
    await asyncio.sleep(0.05)
    
    # 3. Remove the node from the registry while probe is sleeping
    registry.remove(node_id)
    assert registry.get(node_id) is None
    
    # 4. Wait for discovery to complete
    results = await discovery_task
    
    # 5. Assert the node was NOT resurrected
    assert len(results) == 0, f"Node was resurrected! Results: {results}"
    assert registry.get(node_id) is None, "Node should not be in registry!"

@pytest.mark.asyncio
async def test_discover_nodes_successful_registration(monkeypatch):
    # Setup
    base_url = "http://localhost:1234"
    node_id = _node_id_for_url(base_url)
    node = Node(id=node_id, lmstudio_base_url=base_url, status="online")
    registry.clear()

    async def fast_refresh(n, timeout_ms=None, client=None):
        return n.model_copy(update={"status": "online"})

    monkeypatch.setattr("vampire.cluster.refresh_node", AsyncMock(side_effect=fast_refresh))
    monkeypatch.setattr("vampire.cluster._candidate_urls", lambda req: [base_url])

    request = DiscoveryRequest(subnets=["127.0.0.1"], ports=[1234])
    results = await discover_nodes(request)
    
    assert len(results) == 1
    assert results[0].id == node_id
    assert registry.get(node_id) is not None
