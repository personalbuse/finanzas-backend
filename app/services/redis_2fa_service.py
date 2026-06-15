import json
import logging
import secrets

from app.core.exceptions import (
    InvalidCodeException,
    MaxAttemptsException,
    RedisUnavailableException,
)
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
TTL_SECONDS = 600  # 10 minutos


class Redis2FAService:
    async def save_registration_data(self, email: str, username: str, hashed_password: str) -> bool:
        client = await get_redis_client()
        if not client:
            return False

        try:
            key = f"register:data:{email}"
            value = json.dumps({
                "username": username,
                "hashed_password": hashed_password,
                "attempts": 0
            })
            await client.setex(key, TTL_SECONDS, value)
            return True
        except Exception:
            logger.exception("Error saving registration data")
            return False

    async def generate_and_save_code(self, email: str) -> str:
        client = await get_redis_client()
        if not client:
            raise RedisUnavailableException("Redis no disponible")

        code_key = f"register:code:{email}"
        attempts_key = f"register:attempts:{email}"

        attempts = await client.get(attempts_key)
        if attempts and int(attempts) >= MAX_ATTEMPTS:
            raise MaxAttemptsException("Demasiados intentos. Solicita un nuevo código.")

        code = f"{secrets.randbelow(900000) + 100000}"

        await client.setex(code_key, TTL_SECONDS, code)
        await client.setex(attempts_key, TTL_SECONDS, "0")

        return code

    async def verify_code(self, email: str, code: str) -> bool:
        client = await get_redis_client()
        if not client:
            raise RedisUnavailableException("Redis no disponible")

        code_key = f"register:code:{email}"
        attempts_key = f"register:attempts:{email}"

        stored_code_raw = await client.get(code_key)

        if not stored_code_raw:
            raise InvalidCodeException("El código ha expirado. Solicita uno nuevo.")

        stored_code = stored_code_raw.decode("utf-8")

        if stored_code != code:
            attempts = await client.get(attempts_key) or "0"
            new_attempts = int(attempts) + 1
            await client.setex(attempts_key, TTL_SECONDS, str(new_attempts))

            if new_attempts >= MAX_ATTEMPTS:
                await client.delete(code_key)
                await client.delete(attempts_key)
                raise MaxAttemptsException("Demasiados intentos fallidos. Solicita un nuevo código.")

            remaining = MAX_ATTEMPTS - new_attempts
            raise InvalidCodeException(f"Código incorrecto. Intentos restantes: {remaining}")

        await client.delete(code_key)
        await client.delete(attempts_key)
        return True

    async def get_registration_data(self, email: str) -> dict | None:
        client = await get_redis_client()
        if not client:
            return None

        key = f"register:data:{email}"
        data = await client.get(key)
        if data:
            return json.loads(data)
        return None

    async def clear_registration_data(self, email: str) -> bool:
        client = await get_redis_client()
        if not client:
            return False

        try:
            await client.delete(f"register:data:{email}")
            await client.delete(f"register:code:{email}")
            await client.delete(f"register:attempts:{email}")
            return True
        except Exception:
            logger.exception("Error clearing registration data")
            return False

    async def check_pending_registration(self, email: str) -> bool:
        data = await self.get_registration_data(email)
        return data is not None


redis_2fa_service = Redis2FAService()
