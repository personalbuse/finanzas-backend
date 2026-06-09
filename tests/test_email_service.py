from unittest.mock import AsyncMock, MagicMock, patch, ANY

import pytest
from pydantic import SecretStr


class TestEmailService:
    @pytest.fixture
    def service(self):
        from app.services.email_service import EmailService
        return EmailService()

    # ─── send_password_reset_email ───

    @pytest.mark.asyncio
    async def test_send_password_reset_success(self, service):
        service.resend_api_key = "test-key"
        with patch("resend.Emails.send", MagicMock(return_value={"id": "test-id"})):
            result = await service.send_password_reset_email("test@example.com", "reset-token-123")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_password_reset_no_api_key(self, service):
        service.resend_api_key = None
        result = await service.send_password_reset_email("test@example.com", "token")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_password_reset_exception(self, service):
        service.resend_api_key = "test-key"
        with patch("resend.Emails.send", MagicMock(side_effect=Exception("Resend error"))):
            result = await service.send_password_reset_email("test@example.com", "token")
            assert result is False

    # ─── send_verification_code (2fa) ───

    @pytest.mark.asyncio
    async def test_send_verification_code_2fa_success(self, service):
        service.resend_api_key = "test-key"
        with patch("resend.Emails.send", MagicMock(return_value={"id": "test-id"})):
            result = await service.send_verification_code("test@example.com", "123456")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_verification_code_no_api_key(self, service):
        service.resend_api_key = None
        result = await service.send_verification_code("test@example.com", "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_verification_code_exception(self, service):
        service.resend_api_key = "test-key"
        with patch("resend.Emails.send", MagicMock(side_effect=Exception("Resend error"))):
            result = await service.send_verification_code("test@example.com", "123456")
            assert result is False

    # ─── send_verification_code (registration) ───

    @pytest.mark.asyncio
    async def test_send_verification_code_registration_success(self, service):
        service.resend_api_key = "test-key"
        with patch("resend.Emails.send", MagicMock(return_value={"id": "test-id"})):
            result = await service.send_verification_code("test@example.com", "123456", code_type="registration")
            assert result is True

    # ─── singleton ───

    def test_email_service_singleton(self):
        from app.services.email_service import email_service
        from app.services.email_service import EmailService
        assert isinstance(email_service, EmailService)

    # ─── initialization with EMAIL_FROM default ───

    def test_email_from_default(self):
        from app.services.email_service import EmailService
        with patch("app.services.email_service.settings.RESEND_API_KEY", SecretStr("key")):
            with patch("app.services.email_service.settings.EMAIL_FROM", None):
                service = EmailService()
                assert service.email_from == "Simulador Inversiones <onboarding@resend.dev>"
