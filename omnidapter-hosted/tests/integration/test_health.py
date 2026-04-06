"""Smoke tests for omnidapter-hosted API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Verify that the /health endpoint is available."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "omnidapter-hosted"}


@pytest.mark.asyncio
async def test_docs_page(client: AsyncClient):
    """Verify that the /docs documentation page is available."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text
