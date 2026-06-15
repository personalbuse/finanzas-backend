from app.core.exceptions import (
    CustomException,
    ForbiddenException,
    NotFoundException,
    RateLimitException,
    UnauthorizedException,
    ValidationException,
)


class TestExceptions:
    def test_custom_exception_default(self):
        exc = CustomException()
        assert exc.detail == "Error en la solicitud"
        assert exc.status_code == 400

    def test_not_found_exception_default(self):
        exc = NotFoundException()
        assert exc.detail == "Recurso no encontrado"
        assert exc.status_code == 404

    def test_unauthorized_exception_default(self):
        exc = UnauthorizedException()
        assert exc.detail == "No autorizado"
        assert exc.status_code == 401

    def test_forbidden_exception_default(self):
        exc = ForbiddenException()
        assert exc.detail == "No tienes permisos suficientes"
        assert exc.status_code == 403

    def test_validation_exception_default(self):
        exc = ValidationException()
        assert exc.detail == "Error de validación"
        assert exc.status_code == 422

    def test_rate_limit_exception_default(self):
        exc = RateLimitException()
        assert exc.detail == "Límite de requests alcanzado"
        assert exc.status_code == 429

    def test_custom_exception_custom_detail(self):
        exc = CustomException(status_code=418, detail="Custom error")
        assert exc.detail == "Custom error"
        assert exc.status_code == 418
