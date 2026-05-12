import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_application


@pytest.fixture
async def client():
    app = create_application()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
