from fastapi import HTTPException, status


class CustomException(HTTPException):
    def __init__(self, status_code: int = 400, detail: str = None):
        if detail is None:
            detail = "Error en la solicitud"
        super().__init__(status_code=status_code, detail=detail)


class NotFoundException(CustomException):
    def __init__(self, detail: str = "Recurso no encontrado"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class UnauthorizedException(CustomException):
    def __init__(self, detail: str = "No autorizado"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenException(CustomException):
    def __init__(self, detail: str = "No tienes permisos suficientes"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ValidationException(CustomException):
    def __init__(self, detail: str = "Error de validación"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


class RateLimitException(CustomException):
    def __init__(self, detail: str = "Límite de requests alcanzado"):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


class Redis2FAException(Exception):
    """Base exception for 2FA Redis operations"""
    pass


class RedisUnavailableException(Redis2FAException):
    """Raised when Redis client is not available"""
    pass


class InvalidCodeException(Redis2FAException):
    """Raised when verification code is invalid or expired"""
    pass


class MaxAttemptsException(Redis2FAException):
    """Raised when max verification attempts exceeded"""
    pass
