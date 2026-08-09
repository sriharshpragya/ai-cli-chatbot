# ============================================
# Integration Tests for API (Async Version)
# Uses httpx AsyncClient - properly handles async
# ============================================
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from api import app


@pytest_asyncio.fixture
async def client():
    """Async test client that properly handles async lifecycle."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Health endpoint returns 200."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    """Metrics endpoint returns Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_providers_health_endpoint(client):
    """Providers health endpoint works."""
    response = await client.get("/health/providers")
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)


@pytest.mark.asyncio
async def test_budget_health_endpoint(client):
    """Budget health endpoint returns structure."""
    response = await client.get("/health/budget")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "daily" in data
    assert "monthly" in data


@pytest.mark.asyncio
async def test_chat_without_api_key_returns_401(client):
    """Chat endpoint requires authentication."""
    response = await client.post("/chat", json={
        "message": "hi",
        "mode": "general",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_with_invalid_api_key(client):
    """Invalid API key returns 403."""
    response = await client.post(
        "/chat",
        json={"message": "hi", "mode": "general"},
        headers={"X-API-Key": "invalid_key"}
    )
    assert response.status_code == 403