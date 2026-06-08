from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRedis2FAService:
    @pytest.fixture
    def service(self):
        from app.services.redis_2fa_service import Redis2FAService
        return Redis2FAService()

    @pytest.fixture
    def mock_redis(self):
        mock = AsyncMock()
        mock.get = AsyncMock()
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock(return_value=[])
        return mock

    # ─── save_registration_data ───

    @pytest.mark.asyncio
    async def test_save_registration_data_success(self, service, mock_redis):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.save_registration_data("test@example.com", "testuser", "hashed_pwd")
            assert result is True
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_registration_data_no_redis(self, service):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=None)):
            result = await service.save_registration_data("test@example.com", "testuser", "hashed_pwd")
            assert result is False

    @pytest.mark.asyncio
    async def test_save_registration_data_exception(self, service, mock_redis):
        mock_redis.setex.side_effect = Exception("Redis error")
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.save_registration_data("test@example.com", "testuser", "hashed_pwd")
            assert result is False

    # ─── generate_and_save_code ───

    @pytest.mark.asyncio
    async def test_generate_and_save_code_success(self, service, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            code = await service.generate_and_save_code("test@example.com")
            assert len(code) == 6
            assert code.isdigit()
            mock_redis.setex.assert_called()

    @pytest.mark.asyncio
    async def test_generate_and_save_code_no_redis(self, service):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=None)):
            with pytest.raises(Exception, match="Redis no disponible"):
                await service.generate_and_save_code("test@example.com")

    @pytest.mark.asyncio
    async def test_generate_and_save_code_max_attempts(self, service, mock_redis):
        mock_redis.get = AsyncMock(return_value="3")
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(Exception, match="Demasiados intentos"):
                await service.generate_and_save_code("test@example.com")

    # ─── verify_code ───

    @pytest.mark.asyncio
    async def test_verify_code_success(self, service, mock_redis):
        mock_redis.get = AsyncMock(side_effect=["123456", "0"])
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.verify_code("test@example.com", "123456")
            assert result is True
            assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_verify_code_no_redis(self, service):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=None)):
            with pytest.raises(Exception, match="Redis no disponible"):
                await service.verify_code("test@example.com", "123456")

    @pytest.mark.asyncio
    async def test_verify_code_expired(self, service, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(Exception, match="ha expirado"):
                await service.verify_code("test@example.com", "123456")

    @pytest.mark.asyncio
    async def test_verify_code_wrong(self, service, mock_redis):
        mock_redis.get = AsyncMock(side_effect=["654321", "1"])
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(Exception, match="Código incorrecto"):
                await service.verify_code("test@example.com", "123456")

    @pytest.mark.asyncio
    async def test_verify_code_max_attempts_reached(self, service, mock_redis):
        mock_redis.get = AsyncMock(side_effect=["654321", "2"])
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            with pytest.raises(Exception, match="Demasiados intentos fallidos"):
                await service.verify_code("test@example.com", "123456")

    # ─── get_registration_data ───

    @pytest.mark.asyncio
    async def test_get_registration_data_found(self, service, mock_redis):
        import json
        expected = {"username": "testuser", "hashed_password": "pwd", "attempts": 0}
        mock_redis.get = AsyncMock(return_value=json.dumps(expected))
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.get_registration_data("test@example.com")
            assert result == expected

    @pytest.mark.asyncio
    async def test_get_registration_data_not_found(self, service, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.get_registration_data("test@example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_registration_data_no_redis(self, service):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=None)):
            result = await service.get_registration_data("test@example.com")
            assert result is None

    # ─── clear_registration_data ───

    @pytest.mark.asyncio
    async def test_clear_registration_data_success(self, service, mock_redis):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.clear_registration_data("test@example.com")
            assert result is True
            assert mock_redis.delete.call_count == 3

    @pytest.mark.asyncio
    async def test_clear_registration_data_no_redis(self, service):
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=None)):
            result = await service.clear_registration_data("test@example.com")
            assert result is False

    @pytest.mark.asyncio
    async def test_clear_registration_data_exception(self, service, mock_redis):
        mock_redis.delete.side_effect = Exception("Redis error")
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.clear_registration_data("test@example.com")
            assert result is False

    # ─── check_pending_registration ───

    @pytest.mark.asyncio
    async def test_check_pending_registration_exists(self, service, mock_redis):
        import json
        mock_redis.get = AsyncMock(return_value=json.dumps({"username": "test"}))
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.check_pending_registration("test@example.com")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_pending_registration_not_exists(self, service, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        with patch("app.services.redis_2fa_service.get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await service.check_pending_registration("test@example.com")
            assert result is False

    # ─── module-level singleton ───

    def test_module_singleton_exists(self):
        from app.services.redis_2fa_service import redis_2fa_service
        from app.services.redis_2fa_service import Redis2FAService
        assert isinstance(redis_2fa_service, Redis2FAService)
