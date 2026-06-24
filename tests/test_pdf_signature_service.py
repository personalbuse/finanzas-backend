import base64
import tempfile
from pathlib import Path

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def temp_keys_dir():
    original = settings.PDF_KEYS_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        settings.PDF_KEYS_DIR = tmpdir
        yield
    settings.PDF_KEYS_DIR = original


def _get_service():
    from app.services.pdf_signature_service import PDFSignatureService
    PDFSignatureService._instance = None
    PDFSignatureService._initialized = False
    return PDFSignatureService()


def _generate_dummy_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Size 1 >>\n%%EOF\n"


class TestPDFSignatureService:
    def test_ensure_keys_generates_new_keys(self):
        service = _get_service()
        key_path = Path(settings.PDF_KEYS_DIR) / "ca-key.pem"
        cert_path = Path(settings.PDF_KEYS_DIR) / "ca-cert.pem"

        assert not key_path.exists()
        assert not cert_path.exists()

        service._ensure_keys()

        assert key_path.exists()
        assert cert_path.exists()
        assert key_path.stat().st_mode & 0o777 == 0o600

    def test_ensure_keys_loads_existing_keys(self):
        service = _get_service()
        service._ensure_keys()
        serial_1 = service._certificate.serial_number

        service2 = _get_service()
        service2._ensure_keys()
        serial_2 = service2._certificate.serial_number

        assert serial_1 == serial_2

    def test_sign_pdf_returns_signature_data(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        sig_data = service.sign_pdf(pdf_bytes)

        assert sig_data is not None
        assert "hash_hex" in sig_data
        assert "signature_b64" in sig_data
        assert "cert_serial" in sig_data
        assert "cert_subject" in sig_data
        assert "timestamp" in sig_data

        assert len(sig_data["hash_hex"]) == 64
        assert base64.b64decode(sig_data["signature_b64"])

    def test_sign_pdf_different_content_different_hash(self):
        service = _get_service()

        sig1 = service.sign_pdf(b"content A")
        sig2 = service.sign_pdf(b"content B")

        assert sig1["hash_hex"] != sig2["hash_hex"]
        assert sig1["signature_b64"] != sig2["signature_b64"]

    def test_verify_valid_signature(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        sig_data = service.sign_pdf(pdf_bytes)
        result = service.verify_pdf(pdf_bytes, sig_data["signature_b64"])

        assert result["valid"] is True
        assert result["hash_hex"] == sig_data["hash_hex"]
        assert result["cert_serial"] == sig_data["cert_serial"]

    def test_verify_tampered_pdf(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        sig_data = service.sign_pdf(pdf_bytes)

        tampered = pdf_bytes + b"\n% TAMPERED"
        result = service.verify_pdf(tampered, sig_data["signature_b64"])

        assert result["valid"] is False

    def test_verify_invalid_signature(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        fake_signature = base64.b64encode(b"fake_signature").decode("ascii")
        result = service.verify_pdf(pdf_bytes, fake_signature)

        assert result["valid"] is False

    def test_sign_pdf_returns_none_when_keys_missing(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.pdf_signature_service.PDFSignatureService._ensure_keys",
            lambda self: (_ for _ in ()).throw(FileNotFoundError()),
        )
        service = _get_service()
        result = service.sign_pdf(b"test")
        assert result is None

    def test_get_certificate_info(self):
        service = _get_service()
        service._ensure_keys()

        info = service.get_certificate_info()

        assert info["available"] is True
        assert "serial" in info
        assert "subject" in info
        assert "algorithm" in info
        assert "RSA" in info["algorithm"]

    def test_get_certificate_info_no_keys(self, monkeypatch):
        import types
        def _noop_ensure(self):
            return None
        monkeypatch.setattr(
            "app.services.pdf_signature_service.PDFSignatureService._ensure_keys",
            _noop_ensure,
        )
        from app.services.pdf_signature_service import PDFSignatureService
        PDFSignatureService._instance = None
        PDFSignatureService._initialized = False
        service = PDFSignatureService()
        service._certificate = None
        service._initialized = True
        info = service.get_certificate_info()
        assert info["available"] is False

    def test_extract_signature_from_valid_pdf(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        sig_data = service.sign_pdf(pdf_bytes)
        signed_pdf = pdf_bytes + (
            f"\n% X-Hash:{sig_data['hash_hex']}\n"
            f"% X-Signature-B64:{sig_data['signature_b64']}\n"
            f"% X-Timestamp:{sig_data['timestamp']}\n"
            f"% X-Cert-Serial:{sig_data['cert_serial']}\n"
            f"% X-Signature-End\n"
        ).encode("ascii")

        extracted = service.extract_signature_from_pdf(signed_pdf)

        assert extracted is not None
        assert extracted["signature_b64"] == sig_data["signature_b64"]
        assert extracted["hash_hex"] == sig_data["hash_hex"]
        assert extracted["timestamp"] == sig_data["timestamp"]
        assert extracted["cert_serial"] == sig_data["cert_serial"]

    def test_extract_signature_from_unsigned_pdf(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        extracted = service.extract_signature_from_pdf(pdf_bytes)
        assert extracted is None

    def test_extract_signature_from_empty_bytes(self):
        service = _get_service()
        extracted = service.extract_signature_from_pdf(b"")
        assert extracted is None

    def test_singleton_behavior(self):
        from app.services.pdf_signature_service import PDFSignatureService
        PDFSignatureService._instance = None
        PDFSignatureService._initialized = False
        service1 = PDFSignatureService()
        service2 = PDFSignatureService()
        assert service1 is service2


class TestPDFSignatureIntegration:
    def test_full_sign_and_verify_flow(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        sig_data = service.sign_pdf(pdf_bytes)
        assert sig_data is not None

        result = service.verify_pdf(pdf_bytes, sig_data["signature_b64"])
        assert result["valid"] is True

        for i in range(5):
            corrupted = bytearray(pdf_bytes)
            corrupted[i] = (corrupted[i] + 1) % 256
            result = service.verify_pdf(bytes(corrupted), sig_data["signature_b64"])
            assert result["valid"] is False

    def test_embedded_signature_verify(self):
        service = _get_service()
        pdf_bytes = _generate_dummy_pdf()

        sig_data = service.sign_pdf(pdf_bytes)
        signed_pdf = pdf_bytes + (
            f"\n% X-Hash:{sig_data['hash_hex']}\n"
            f"% X-Signature-B64:{sig_data['signature_b64']}\n"
            f"% X-Timestamp:{sig_data['timestamp']}\n"
            f"% X-Cert-Serial:{sig_data['cert_serial']}\n"
            f"% X-Signature-End\n"
        ).encode("ascii")

        extracted = service.extract_signature_from_pdf(signed_pdf)
        assert extracted is not None

        hash_marker = b"\n% X-Hash:"
        meta_start = signed_pdf.find(hash_marker)
        content_body = signed_pdf[:meta_start]
        result = service.verify_pdf(content_body, extracted["signature_b64"])
        assert result["valid"] is True

        tampered = signed_pdf + b"\n% extra data"
        extracted2 = service.extract_signature_from_pdf(tampered)
        assert extracted2 is not None
        meta_start2 = tampered.find(hash_marker)
        content_body2 = tampered[:meta_start2]
        result2 = service.verify_pdf(content_body2, extracted2["signature_b64"])
        assert result2["valid"] is True

        corrupted_pdf = signed_pdf.replace(b"1 0 obj", b"X 0 obj")
        extracted3 = service.extract_signature_from_pdf(corrupted_pdf)
        assert extracted3 is not None
        meta_start3 = corrupted_pdf.find(hash_marker)
        content_body3 = corrupted_pdf[:meta_start3]
        result3 = service.verify_pdf(content_body3, extracted3["signature_b64"])
        assert result3["valid"] is False
