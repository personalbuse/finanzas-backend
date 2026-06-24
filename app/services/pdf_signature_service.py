import base64
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from app.core.config import settings

logger = logging.getLogger(__name__)


class PDFSignatureService:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._keys_dir = Path(settings.PDF_KEYS_DIR)
        self._key_path = self._keys_dir / "ca-key.pem"
        self._cert_path = self._keys_dir / "ca-cert.pem"
        self._private_key = None
        self._certificate = None

    def _ensure_keys(self) -> None:
        if self._private_key is not None and self._certificate is not None:
            return

        if self._key_path.exists() and self._cert_path.exists():
            logger.info("Cargando llaves existentes desde %s", self._keys_dir)
            try:
                with self._key_path.open("rb") as f:
                    self._private_key = serialization.load_pem_private_key(
                        f.read(), password=None
                    )
                with self._cert_path.open("rb") as f:
                    self._certificate = x509.load_pem_x509_certificate(f.read())
                logger.info(
                    "Llaves cargadas: cert serial=%s",
                    self._certificate.serial_number,
                )
                return
            except Exception:
                logger.exception("Error cargando llaves existentes, regenerando")
                self._private_key = None
                self._certificate = None

        logger.info("Generando nuevo par de llaves RSA 2048 y certificado X.509")
        try:
            self._keys_dir.mkdir(parents=True, exist_ok=True)

            self._private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )

            public_key = self._private_key.public_key()
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CO"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Simulador de Inversiones FIUP"),
                x509.NameAttribute(NameOID.COMMON_NAME, "Simulador de Inversiones FIUP CA"),
            ])
            now = datetime.now(UTC)
            self._certificate = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(public_key)
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(self._private_key, hashes.SHA256())
            )

            self._key_path.write_bytes(
                self._private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            self._key_path.chmod(0o600)

            self._cert_path.write_bytes(
                self._certificate.public_bytes(serialization.Encoding.PEM)
            )

            logger.info(
                "Llaves generadas: key=%s cert=%s serial=%s",
                self._key_path, self._cert_path, self._certificate.serial_number,
            )
        except PermissionError:
            logger.exception("Permiso denegado al escribir llaves en %s", self._keys_dir)
            raise
        except Exception:
            logger.exception("Error generando llaves criptograficas")
            raise

    def sign_pdf(self, pdf_bytes: bytes) -> dict | None:
        try:
            self._ensure_keys()
            if self._private_key is None or self._certificate is None:
                logger.warning("No se pudieron cargar/generar llaves, PDF sin firma")
                return None

            pdf_hash = hashes.Hash(hashes.SHA256())
            pdf_hash.update(pdf_bytes)
            hash_bytes = pdf_hash.finalize()
            hash_hex = hash_bytes.hex()

            signature = self._private_key.sign(
                hash_bytes,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            signature_b64 = base64.b64encode(signature).decode("ascii")

            logger.info(
                "PDF firmado: hash=%s serial=%s",
                hash_hex[:16], self._certificate.serial_number,
            )

            return {
                "hash_hex": hash_hex,
                "signature_b64": signature_b64,
                "cert_serial": str(self._certificate.serial_number),
                "cert_subject": self._certificate.subject.rfc4514_string(),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        except FileNotFoundError:
            logger.warning("Llaves no encontradas al firmar, PDF sin firma")
            return None
        except PermissionError:
            logger.warning("Permiso denegado al acceder llaves, PDF sin firma")
            return None
        except Exception:
            logger.exception("Error firmando PDF, se entrega sin firma")
            return None

    def verify_pdf(self, pdf_bytes: bytes, signature_b64: str) -> dict:
        result = {
            "valid": False,
            "hash_hex": "",
            "message": "",
            "cert_serial": "",
            "cert_subject": "",
        }
        try:
            self._ensure_keys()
            if self._certificate is None:
                result["message"] = "No hay certificado configurado en el servidor"
                return result

            public_key = self._certificate.public_key()
            pdf_hash = hashes.Hash(hashes.SHA256())
            pdf_hash.update(pdf_bytes)
            hash_bytes = pdf_hash.finalize()
            hash_hex = hash_bytes.hex()

            signature = base64.b64decode(signature_b64)

            try:
                public_key.verify(
                    signature,
                    hash_bytes,
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                result["valid"] = True
                result["message"] = "Firma digital valida. El documento es autentico."
                logger.info("PDF verificado correctamente: hash=%s", hash_hex[:16])
            except Exception:
                result["valid"] = False
                result["message"] = "Firma digital invalida. El documento fue alterado."
                logger.warning("PDF con firma invalida: hash=%s", hash_hex[:16])

            result["hash_hex"] = hash_hex
            result["cert_serial"] = str(self._certificate.serial_number)
            result["cert_subject"] = self._certificate.subject.rfc4514_string()
            return result
        except FileNotFoundError:
            result["message"] = "No hay llaves configuradas en el servidor"
            return result
        except Exception:
            logger.exception("Error verificando firma PDF")
            result["message"] = "Error interno al verificar la firma"
            return result

    def get_certificate_info(self) -> dict:
        try:
            self._ensure_keys()
            if self._certificate is None:
                return {"available": False}
            return {
                "available": True,
                "serial": str(self._certificate.serial_number),
                "subject": self._certificate.subject.rfc4514_string(),
                "issuer": self._certificate.issuer.rfc4514_string(),
                "not_before": self._certificate.not_valid_before_utc.isoformat(),
                "not_after": self._certificate.not_valid_after_utc.isoformat(),
                "algorithm": "RSA 2048 + SHA-256",
            }
        except Exception:
            logger.exception("Error obteniendo info del certificado")
            return {"available": False}

    def extract_signature_from_pdf(self, pdf_bytes: bytes) -> dict | None:
        try:
            hash_marker = b"X-Hash:"
            sig_marker = b"X-Signature-B64:"
            ts_marker = b"X-Timestamp:"
            serial_marker = b"X-Cert-Serial:"
            end_marker = b"X-Signature-End"

            sig_start = pdf_bytes.find(sig_marker)
            if sig_start == -1:
                return None

            sig_end = pdf_bytes.find(end_marker, sig_start)
            if sig_end == -1:
                return None

            sig_line_end = pdf_bytes.find(b"\n", sig_start)
            if sig_line_end == -1:
                return None
            b64_str = pdf_bytes[sig_start + len(sig_marker):sig_line_end].strip().decode("ascii")
            if not b64_str:
                return None

            def _extract_value(marker: bytes) -> str:
                pos = pdf_bytes.find(marker)
                if pos == -1:
                    return ""
                line_end = pdf_bytes.find(b"\n", pos)
                if line_end == -1:
                    return ""
                return pdf_bytes[pos + len(marker):line_end].strip().decode("ascii")

            hash_hex = _extract_value(hash_marker)
            timestamp = _extract_value(ts_marker)
            serial = _extract_value(serial_marker)

            return {
                "signature_b64": b64_str,
                "hash_hex": hash_hex,
                "timestamp": timestamp,
                "cert_serial": serial,
            }
        except Exception:
            logger.exception("Error extrayendo firma del PDF")
            return None
