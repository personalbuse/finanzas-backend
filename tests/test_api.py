import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_register_init_missing_data(client: AsyncClient):
    response = await client.post("/api/v1/register-init", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stocks_batch_invalid_body(client: AsyncClient):
    response = await client.post("/api/v1/stocks/batch", json={"symbols": []})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stocks_batch_missing_body(client: AsyncClient):
    response = await client.post("/api/v1/stocks/batch", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_kpis_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/kpis")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_profile_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/profile")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_convert_currency_invalid_amount(client: AsyncClient):
    response = await client.get("/api/v1/exchange-rate/convert", params={"amount": -1, "from_currency": "USD", "to_currency": "COP"})
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_buy_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/portfolio/buy",
        json={"symbol": "AAPL", "quantity": 10},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sell_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/portfolio/sell",
        json={"symbol": "AAPL", "quantity": 1},
    )
    assert response.status_code == 401
