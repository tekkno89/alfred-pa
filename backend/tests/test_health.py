import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    """Test the health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_api_root(client: AsyncClient) -> None:
    """Test the API root endpoint."""
    response = await client.get("/api/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Alfred AI Assistant API"
    assert data["version"] == "0.1.0"
