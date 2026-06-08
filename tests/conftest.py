import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_application
from app.core.config import settings


@pytest.fixture(autouse=True)
def override_settings():
    """Ensure test environment variables are set."""
    settings.ENVIRONMENT = "test"
    settings.ENABLE_STARTUP_PRELOAD = False
    settings.TRUST_PROXY = False
    yield


@pytest.fixture
async def client():
    app = create_application()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
