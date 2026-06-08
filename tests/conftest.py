import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import create_application
from app.core.config import settings


@pytest.fixture(autouse=True)
def override_settings():
    settings.ENVIRONMENT = "test"
    settings.ENABLE_STARTUP_PRELOAD = False
    settings.TRUST_PROXY = False
    settings.ADMIN_API_KEY = "test-admin-key-12345"
    settings.SECRET_KEY = "test-secret-key-for-testing-only-1234567890"
    settings.REDIS_URL = None
    yield


class MockUser:
    def __init__(self, user_id=1, username="testuser", email="test@example.com",
                 rol="inversor", is_active=True, current_balance=10000.00,
                 initial_balance=10000.00, completed_courses=0, password_version=0):
        self.id = user_id
        self.username = username
        self.email = email
        self.rol = rol
        self.is_active = is_active
        self.current_balance = current_balance
        self.initial_balance = initial_balance
        self.completed_courses = completed_courses
        self.password_version = password_version
        self.hashed_password = "$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        self.created_at = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<MockUser(id={self.id}, username={self.username})>"


class MockAdminUser(MockUser):
    def __init__(self, user_id=2, username="adminuser", email="admin@example.com", rol="admin"):
        super().__init__(user_id=user_id, username=username, email=email, rol=rol)


class MockQueryResult:
    def __init__(self, scalar_result=None, scalars_list=None, all_list=None, scalar_one_result=None):
        self._scalar_result = scalar_result
        self._scalars_list = scalars_list or []
        self._all_list = all_list or []
        self._scalar_one_result = scalar_one_result

    def scalar(self):
        return self._scalar_result

    def scalar_one_or_none(self):
        return self._scalar_one_result

    def scalars(self):
        return self

    def all(self):
        return self._all_list

    def first(self):
        return self._scalar_one_result

    def one_or_none(self):
        return self._scalar_one_result

    def fetchall(self):
        return self._all_list

    def keys(self):
        return []

    def __iter__(self):
        return iter(self._all_list)

    def __len__(self):
        return len(self._all_list)

    @property
    def rowcount(self):
        return len(self._all_list)


class MockAsyncSession:
    def __init__(self):
        self.add = MagicMock()
        self.add_all = MagicMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.refresh = AsyncMock()
        self.close = AsyncMock()
        self.flush = AsyncMock()
        self.in_transaction = MagicMock(return_value=False)
        self.execute = AsyncMock(return_value=MockQueryResult())

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        return self


@pytest.fixture
def mock_db_session():
    return MockAsyncSession()


@pytest.fixture
def mock_user():
    return MockUser()


@pytest.fixture
def mock_admin_user():
    return MockAdminUser()


@pytest.fixture
def test_app(mock_db_session, mock_user, mock_admin_user):
    app = create_application()
    app.dependency_overrides = {}

    # Track current user for auth switching
    current_user_context = {"user": mock_user}

    # Override get_db
    from app.db.session import get_db

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    # Override require_admin in admin.py — zero params to avoid FastAPI treating them as query params
    async def mock_require_admin():
        if current_user_context["user"].rol != "admin":
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso solo para administradores",
            )
        return current_user_context["user"]

    from app.api.v1.admin import require_admin as real_require_admin
    app.dependency_overrides[real_require_admin] = mock_require_admin

    # Override require_admin_api_key — check request headers manually
    async def mock_admin_api_key():
        return None

    from app.core.security import require_admin_api_key as real_admin_api_key
    app.dependency_overrides[real_admin_api_key] = mock_admin_api_key

    # Patch get_current_user everywhere it's imported at module level
    # and also the wrapper dependencies get_authenticated_user
    mock_get_current_user = lambda db, token: current_user_context["user"]

    auth_patchers = [
        patch(module, side_effect=mock_get_current_user)
        for module in [
            "app.services.auth_service.get_current_user",
            "app.api.v1.authentication.get_current_user",
            "app.api.v1.portfolio.get_current_user",
            "app.api.v1.learning.get_current_user",
            "app.api.v1.leaderboard.get_current_user",
        ]
    ]
    for p in auth_patchers:
        p.start()

    # Override get_authenticated_user in portfolio and leaderboard
    # IMPORTANT: no parameters — FastAPI treats override params as query params
    async def mock_get_authenticated_user():
        return current_user_context["user"]

    from app.api.v1.portfolio import get_authenticated_user as portfolio_auth
    from app.api.v1.portfolio import get_current_username as portfolio_username
    from app.api.v1.leaderboard import get_authenticated_user as leaderboard_auth
    app.dependency_overrides[portfolio_auth] = mock_get_authenticated_user
    app.dependency_overrides[portfolio_username] = lambda: current_user_context["user"].username

    yield app, current_user_context, mock_db_session, mock_user, mock_admin_user

    for p in auth_patchers:
        p.stop()
    app.dependency_overrides = {}


@pytest_asyncio.fixture
async def client(test_app) -> AsyncGenerator:
    app, current_user_context, mock_db_session, mock_user, mock_admin_user = test_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client, test_app):
    app, current_user_context, mock_db_session, mock_user, mock_admin_user = test_app
    client.headers["Authorization"] = "Bearer test-access-token"
    client.headers["X-Admin-Token"] = settings.ADMIN_API_KEY
    return client


@pytest_asyncio.fixture
async def admin_client(auth_client, test_app):
    app, current_user_context, mock_db_session, mock_user, mock_admin_user = test_app
    current_user_context["user"] = mock_admin_user
    return auth_client


@pytest_asyncio.fixture
async def investor_client(auth_client, test_app):
    app, current_user_context, mock_db_session, mock_user, mock_admin_user = test_app
    current_user_context["user"] = mock_user
    return auth_client
