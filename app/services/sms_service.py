import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SmsService:
    def __init__(self):
        self.gateway_url = settings.SMS_GATEWAY_URL
        self.timeout = settings.SMS_TIMEOUT

    async def send_otp(self, phone_number: str, code: str) -> bool:
        url = f"{self.gateway_url}/send-sms"
        message = f"Código de verificación OTP: {code}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json={"number": phone_number, "message": message},
                )
                response.raise_for_status()
                logger.info(f"SMS OTP sent to {_mask_phone(phone_number)}")
                return True
        except httpx.TimeoutException:
            logger.error(f"SMS gateway timeout for {_mask_phone(phone_number)}")
            return False
        except httpx.HTTPStatusError as e:
            logger.error(f"SMS gateway error {e.response.status_code} for {_mask_phone(phone_number)}")
            return False
        except Exception:
            logger.exception(f"Failed to send SMS OTP to {_mask_phone(phone_number)}")
            return False


def _mask_phone(phone: str) -> str:
    if len(phone) >= 4:
        return f"******{phone[-4:]}"
    return "******"


sms_service = SmsService()
