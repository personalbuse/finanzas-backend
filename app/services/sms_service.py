import asyncio
import logging

from twilio.rest import Client

from app.core.config import settings

logger = logging.getLogger(__name__)


class SMSService:
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN.get_secret_value() if settings.TWILIO_AUTH_TOKEN else ""
        self.service_sid = settings.TWILIO_VERIFY_SERVICE_SID
        self.client = Client(self.account_sid, auth_token) if self.account_sid and auth_token else None

    async def send_code(self, to: str) -> bool:
        if not self.client:
            logger.warning("Twilio not configured, skipping SMS")
            return False

        try:
            loop = asyncio.get_event_loop()
            verification = await loop.run_in_executor(
                None,
                lambda: self.client.verify.v2.services(self.service_sid).verifications.create(
                    to=to, channel="sms"
                ),
            )
            logger.info("SMS verification code sent to %s (status=%s)", to, verification.status)
            return verification.status == "pending"
        except Exception:
            logger.exception("Failed to send SMS verification code to %s", to)
            return False

    async def verify_code(self, to: str, code: str) -> bool:
        if not self.client:
            logger.warning("Twilio not configured, skipping verification")
            return False

        try:
            loop = asyncio.get_event_loop()
            check = await loop.run_in_executor(
                None,
                lambda: self.client.verify.v2.services(self.service_sid).verification_checks.create(
                    to=to, code=code
                ),
            )
            logger.info("SMS verification check for %s (status=%s)", to, check.status)
            return check.status == "approved"
        except Exception:
            logger.exception("Failed to verify SMS code for %s", to)
            return False


sms_service = SMSService()
