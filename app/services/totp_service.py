import base64
import hashlib
import io
import logging
import secrets

import pyotp
import qrcode

logger = logging.getLogger(__name__)


class TOTPService:
    ISSUER = "Simulador FIUP"

    @staticmethod
    def generate_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(secret: str, username: str) -> str:
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name=TOTPService.ISSUER,
        )

    @staticmethod
    def generate_qr_base64(uri: str) -> str:
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    @staticmethod
    def generate_backup_codes(count: int = 8) -> list[dict]:
        codes = []
        for _ in range(count):
            raw = f"{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}"
            hashed = hashlib.sha256(raw.encode()).hexdigest()
            codes.append({"raw": raw, "hashed": hashed})
        return codes

    @staticmethod
    def hash_backup_code(raw_code: str) -> str:
        return hashlib.sha256(raw_code.encode()).hexdigest()


totp_service = TOTPService()
