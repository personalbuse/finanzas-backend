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
    assert data["status"] == "ok"


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


# ── Admin endpoints (auth required) ──

@pytest.mark.asyncio
async def test_admin_users_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_user_detail_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/users/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_change_role_requires_auth(client: AsyncClient):
    response = await client.patch("/api/v1/admin/users/1/role", json={"new_role": "admin"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_ban_requires_auth(client: AsyncClient):
    response = await client.patch("/api/v1/admin/users/1/ban")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_balance_requires_auth(client: AsyncClient):
    response = await client.patch("/api/v1/admin/users/1/balance", json={"new_balance": 5000})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_kpis_evolution_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/kpis/evolution")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_top_stocks_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/kpis/top-stocks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_kpis_distribution_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/kpis/distribution")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_logs_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/logs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_transactions_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/transactions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_suspicious_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/suspicious-transactions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_config_list_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/config")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_config_update_requires_auth(client: AsyncClient):
    response = await client.put("/api/v1/admin/config/maintenance_mode", json={"value": "true"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_maintenance_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/admin/maintenance")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_refresh_stocks_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/admin/refresh/stocks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_refresh_rates_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/admin/refresh/rates")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_refresh_indices_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/admin/refresh/indices")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_clear_cache_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/admin/cache/clear")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_table_stats_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/admin/stats/tables")
    assert response.status_code == 401
