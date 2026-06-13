"""Shared test isolation for process-local Vampire state."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from vampire.registry import registry, route_registry, share_registry


@pytest.fixture(autouse=True)
def clear_registry() -> Iterator[None]:
    """Keep the in-memory node registry isolated between tests."""
    registry.clear()
    route_registry.clear()
    share_registry.clear()
    yield
    registry.clear()
    route_registry.clear()
    share_registry.clear()
