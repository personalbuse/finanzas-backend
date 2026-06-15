import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import Redis2FAException
from app.core.rate_limiter import auth_rate_limit, limiter
from app.core.redis_client import RedisCache
from app.db.session import get_db
from app.models.base import BackupCode, PasswordResetToken, User, VerificationCode
from app.schemas.user import (
    TOTPBackupCodeRequest,
    TOTPDisableRequest,
    TOTPLoginVerifyRequest,
    TOTPSetupResponse,
    TOTPStatusResponse,
    TOTPVerifyRequest,
    TOTPVerifyResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
    validate_password_strength,
)
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_temp_token,
    decode_temp_token,
    decode_token,
    get_current_user,
    get_password_hash,
    get_refresh_token_from_request,
    get_token_from_request,
    verify_password,
)
from app.services.email_service import email_service
from app.services.redis_2fa_service import redis_2fa_service
from app.services.totp_service import totp_service

router = APIRouter()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login", auto_error=False)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    secure = settings.COOKIE_SECURE or settings.ENVIRONMENT == "production"
    domain = settings.COOKIE_DOMAIN or None
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=domain,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=domain,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/refresh-token",
    )


def _clear_auth_cookies(response: Response) -> None:
    for cookie in ("access_token", "refresh_token"):
        response.delete_cookie(key=cookie, path="/")


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post(
    "/register-init",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def register_init(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(
        (User.username == user_data.username) |
        (User.email == user_data.email)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        if existing.username == user_data.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de usuario ya está en uso"
            )
        if existing.email == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está en uso"
            )

    hashed_password = get_password_hash(user_data.password)

    saved = await redis_2fa_service.save_registration_data(
        user_data.email,
        user_data.username,
        hashed_password
    )

    if not saved:
        logger.error("redis_2fa_service.save_registration_data returned False")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al procesar el registro. Intenta de nuevo."
        )

    try:
        code = await redis_2fa_service.generate_and_save_code(user_data.email)
        sent = await email_service.send_verification_code(user_data.email, code)
        if not sent:
            raise RuntimeError("Verification email was not sent")
    except Exception:
        logger.exception("Error sending registration verification code")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al enviar el código. Intenta de nuevo."
        )

    return {
        "message": "Código de verificación enviado a tu correo",
        "email": user_data.email
    }


@router.post(
    "/register-verify",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def register_verify(
    request: Request,
    response: Response,
    email: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        await redis_2fa_service.verify_code(email, code)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    reg_data = await redis_2fa_service.get_registration_data(email)
    if not reg_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datos de registro expirados. Por favor regístrate de nuevo."
        )

    initial_balance = float(reg_data.get("initial_balance", 10000.00))
    user = User(
        username=reg_data["username"],
        email=email,
        hashed_password=reg_data["hashed_password"],
        initial_balance=initial_balance,
        current_balance=initial_balance,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await redis_2fa_service.clear_registration_data(email)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(user)

    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "initial_balance": float(user.initial_balance),
            "current_balance": float(user.current_balance),
            "completed_courses": user.completed_courses or 0,
            "rol": user.rol,
            "created_at": str(user.created_at),
        },
    }


@router.post(
    "/resend-code",
    tags=["autenticación"],
)
@limiter.limit(auth_rate_limit)
async def resend_code(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )

    reg_data = await redis_2fa_service.get_registration_data(email)
    if not reg_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay registro pendiente para este email. Por favor regístrate de nuevo."
        )

    try:
        code = await redis_2fa_service.generate_and_save_code(email)
        sent = await email_service.send_verification_code(email, code)
        if not sent:
            raise RuntimeError("Verification email was not sent")
    except Redis2FAException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception:
        logger.exception("Error resending verification code")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al reenviar el código. Intenta de nuevo."
        )

    return {"message": "Nuevo código enviado a tu correo"}


@router.post(
    "/login",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.rol == "admin" and not user.totp_enabled:
        access_token = create_access_token(
            data={"sub": user.username, "user_id": user.id},
        )
        refresh_token = create_refresh_token(user)
        _set_auth_cookies(response, access_token, refresh_token)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "requires_2fa_setup": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "initial_balance": float(user.initial_balance),
                "current_balance": float(user.current_balance),
                "completed_courses": user.completed_courses or 0,
                "rol": user.rol,
                "created_at": str(user.created_at),
            },
        }

    if user.totp_enabled:
        temp_token = create_temp_token(user)
        temp_jti = decode_temp_token(temp_token).get("jti")
        await RedisCache.set(f"temp_token:{temp_jti}", user.username, ttl_seconds=30)
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
        }

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(user)

    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "initial_balance": float(user.initial_balance),
            "current_balance": float(user.current_balance),
            "completed_courses": user.completed_courses or 0,
            "rol": user.rol,
            "created_at": str(user.created_at),
        },
    }


@router.post(
    "/refresh-token",
    tags=["autenticación"],
)
@limiter.limit("10/minute")
async def refresh_token_endpoint(
    request: Request,
    response: Response,
    refresh_token: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        try:
            refresh_token = get_refresh_token_from_request(request)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token provided",
            )
    try:
        decode_token(refresh_token, token_type="refresh")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from e

    user = await get_current_user(db, refresh_token, token_type="refresh")
    new_access = create_access_token(
        data={"sub": user.username, "user_id": user.id},
    )
    new_refresh = create_refresh_token(user)

    _set_auth_cookies(response, new_access, new_refresh)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.get(
    "/profile",
    response_model=UserResponse,
    tags=["autenticación"]
)
async def get_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    try:
        user = await get_current_user(db, token)
        return user
    except Exception:
        logger.exception("Error getting profile")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.patch(
    "/profile",
    response_model=UserResponse,
    tags=["autenticación"]
)
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    update_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    try:
        user = await get_current_user(db, token)
    except Exception:
        logger.exception("Error getting profile for update")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if update_data.username is not None and update_data.username != user.username:
        stmt = select(User).where(User.username == update_data.username)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de usuario ya está en uso"
            )
        user.username = update_data.username

    if update_data.email is not None and update_data.email != user.email:
        stmt = select(User).where(User.email == update_data.email)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está en uso"
            )
        user.email = update_data.email

    if update_data.new_password is not None:
        if not update_data.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere la contraseña actual para cambiarla"
            )
        if not verify_password(update_data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La contraseña actual es incorrecta"
            )
        user.hashed_password = get_password_hash(update_data.new_password)
        user.password_version = (user.password_version or 0) + 1

    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/forgot-password",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return {"message": "Si el correo existe, recibirás un enlace de recuperación"}

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token=hash_reset_token(token),
        expires_at=expires_at
    )
    db.add(reset_token)
    await db.commit()

    sent = await email_service.send_password_reset_email(user.email, token)
    if not sent:
        logger.error("Password reset email was not sent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo enviar el correo de recuperación"
        )

    return {"message": "Si el correo existe, recibirás un enlace de recuperación"}


@router.post(
    "/reset-password",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def reset_password(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        validate_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )

    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token == hash_reset_token(token),
        not PasswordResetToken.used
    )
    result = await db.execute(stmt)
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o ya utilizado"
        )

    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El token ha expirado"
        )

    stmt_user = select(User).where(User.id == reset_token.user_id)
    result_user = await db.execute(stmt_user)
    user = result_user.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    user.hashed_password = get_password_hash(new_password)
    user.password_version = (user.password_version or 0) + 1
    reset_token.used = True
    await db.commit()

    return {"message": "Contraseña actualizada exitosamente"}


@router.post(
    "/send-verification-code",
    tags=["autenticación"],
)
@limiter.limit("10/minute")
async def send_verification_code(
    request: Request,
    code_type: str = Form("2fa"),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    try:
        user = await get_current_user(db, token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    code = secrets.randbelow(900000) + 100000
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    stmt_del = select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.code_type == code_type,
        not VerificationCode.used,
    )
    result_del = await db.execute(stmt_del)
    old_codes = result_del.scalars().all()
    for old_code in old_codes:
        old_code.used = True

    verification = VerificationCode(
        user_id=user.id,
        code=str(code),
        code_type=code_type,
        expires_at=expires_at,
    )
    db.add(verification)
    await db.commit()

    sent = await email_service.send_verification_code(user.email, str(code), code_type)
    if not sent:
        logger.error("Verification code email was not sent")

    return {"message": "Código de verificación enviado a tu correo"}


@router.post(
    "/verify-code",
    tags=["autenticación"],
)
@limiter.limit("10/minute")
async def verify_code(
    request: Request,
    code: str = Form(...),
    code_type: str = Form("2fa"),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    try:
        user = await get_current_user(db, token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt_code = select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.code == code,
        VerificationCode.code_type == code_type,
        not VerificationCode.used,
    )
    result_code = await db.execute(stmt_code)
    verification = result_code.scalar_one_or_none()

    if not verification or verification.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado",
        )

    if verification.attempts >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Solicita un nuevo código.",
        )
    verification.attempts = (verification.attempts or 0) + 1
    verification.used = True
    await db.commit()

    return {"message": "Código verificado exitosamente", "verified": True}


@router.post(
    "/2fa/setup",
    tags=["2fa"],
)
@limiter.limit("10/minute")
async def twofa_setup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    user = await get_current_user(db, token)

    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA ya está activado")

    secret = totp_service.generate_secret()
    uri = totp_service.get_provisioning_uri(secret, user.username)
    qr = totp_service.generate_qr_base64(uri)

    user.totp_secret = secret
    await db.commit()

    return TOTPSetupResponse(secret=secret, qr_code=qr, provisioning_uri=uri)


@router.post(
    "/2fa/verify",
    tags=["2fa"],
)
@limiter.limit("10/minute")
async def twofa_verify(
    request: Request,
    body: TOTPVerifyRequest,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    user = await get_current_user(db, token)

    logger.info("=== DEBUG twofa_verify start ===")
    logger.info(f"user.id={user.id}, user.totp_secret={'SET' if user.totp_secret else 'NOT SET'}, user.totp_enabled={user.totp_enabled}")

    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Primero debes generar el setup")

    logger.info(f"Verifying TOTP code, code_len={len(body.code)}, secret_len={len(user.totp_secret) if user.totp_secret else 0}")
    if not totp_service.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=400, detail="Código inválido")

    try:
        backup_codes_raw = totp_service.generate_backup_codes(8)
        logger.info(f"backup_codes_raw count: {len(backup_codes_raw)}")
        for bc in backup_codes_raw:
            db.add(BackupCode(user_id=user.id, hashed_code=bc["hashed"]))
        user.totp_enabled = True
        user.totp_setup_at = datetime.utcnow()
        logger.info(f"About to commit. totp_setup_at value: {datetime.utcnow()}, type: {type(datetime.utcnow())}")
        await db.commit()
    except Exception as e:
        logger.exception(f"=== DEBUG twofa_verify COMMIT FAILED === {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno al configurar 2FA")

    return TOTPVerifyResponse(
        enabled=True,
        backup_codes=[bc["raw"] for bc in backup_codes_raw],
    )


@router.post(
    "/2fa/disable",
    tags=["2fa"],
)
@limiter.limit("5/minute")
async def twofa_disable(
    request: Request,
    body: TOTPDisableRequest,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    user = await get_current_user(db, token)

    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA no está activado")

    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Contraseña incorrecta")

    if not totp_service.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=400, detail="Código TOTP inválido")

    result = await db.execute(select(BackupCode).where(BackupCode.user_id == user.id))
    for bc in result.scalars().all():
        await db.delete(bc)

    user.totp_secret = None
    user.totp_enabled = False
    user.totp_setup_at = None
    await db.commit()

    return {"message": "2FA desactivado exitosamente"}


@router.get(
    "/2fa/status",
    response_model=TOTPStatusResponse,
    tags=["2fa"],
)
async def twofa_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        token = get_token_from_request(request)
    user = await get_current_user(db, token)

    return TOTPStatusResponse(enabled=user.totp_enabled, setup_at=user.totp_setup_at)


async def _complete_login(user: User, response: Response, db: AsyncSession) -> dict:
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(user)
    _set_auth_cookies(response, access_token, refresh_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "initial_balance": float(user.initial_balance),
            "current_balance": float(user.current_balance),
            "completed_courses": user.completed_courses or 0,
            "rol": user.rol,
            "created_at": str(user.created_at),
        },
    }


@router.post(
    "/2fa/login-verify",
    tags=["2fa"],
)
@limiter.limit("5/minute")
async def twofa_login_verify(
    request: Request,
    response: Response,
    body: TOTPLoginVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_temp_token(body.temp_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token temporal inválido o expirado")

    temp_jti = payload.get("jti")
    stored = await RedisCache.get(f"temp_token:{temp_jti}")
    if not stored:
        raise HTTPException(status_code=401, detail="Token temporal ya utilizado o expirado")

    username = payload.get("sub")
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=401, detail="Usuario no válido o 2FA no configurado")

    if not totp_service.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=400, detail="Código TOTP inválido")

    await RedisCache.delete(f"temp_token:{temp_jti}")
    return await _complete_login(user, response, db)


@router.post(
    "/2fa/login-backup",
    tags=["2fa"],
)
@limiter.limit("5/minute")
async def twofa_login_backup(
    request: Request,
    response: Response,
    body: TOTPBackupCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_temp_token(body.temp_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token temporal inválido o expirado")

    temp_jti = payload.get("jti")
    stored = await RedisCache.get(f"temp_token:{temp_jti}")
    if not stored:
        raise HTTPException(status_code=401, detail="Token temporal ya utilizado o expirado")

    username = payload.get("sub")
    stmt_user = select(User).where(User.username == username)
    result = await db.execute(stmt_user)
    user = result.scalar_one_or_none()

    if not user or not user.totp_enabled:
        raise HTTPException(status_code=401, detail="Usuario no válido o 2FA no configurado")

    hashed = totp_service.hash_backup_code(body.backup_code)
    stmt_bc = select(BackupCode).where(
        BackupCode.user_id == user.id,
        BackupCode.hashed_code == hashed,
        not BackupCode.used,
    )
    result_bc = await db.execute(stmt_bc)
    bc = result_bc.scalar_one_or_none()

    if not bc:
        raise HTTPException(status_code=400, detail="Código de respaldo inválido o ya utilizado")

    bc.used = True
    await db.commit()

    await RedisCache.delete(f"temp_token:{temp_jti}")
    return await _complete_login(user, response, db)


@router.post(
    "/logout",
    tags=["autenticación"],
)
async def logout(response: Response):
    _clear_auth_cookies(response)
    return {"message": "Sesión cerrada exitosamente"}
