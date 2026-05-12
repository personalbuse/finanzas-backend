import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.rate_limiter import limiter, auth_rate_limit
from app.db.session import get_db
from app.schemas.user import UserCreate, UserResponse, validate_password_strength
from app.services.auth_service import authenticate_user, create_access_token, get_current_user, get_password_hash
from app.models.base import User, PasswordResetToken, VerificationCode
from app.services.email_service import email_service
from app.services.redis_2fa_service import redis_2fa_service

router = APIRouter()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


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
    except Exception as e:
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
    
    user = User(
        username=reg_data["username"],
        email=email,
        hashed_password=reg_data["hashed_password"],
        initial_balance=10000.00,
        current_balance=10000.00
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    await redis_2fa_service.clear_registration_data(email)
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "rol": user.rol},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "initial_balance": float(user.initial_balance),
            "current_balance": float(user.current_balance),
            "completed_courses": user.completed_courses or 0,
            "rol": user.rol,
            "created_at": str(user.created_at)
        }
    }


@router.post(
    "/resend-code",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def resend_code(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
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
    except Exception as e:
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
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id, "rol": user.rol},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "initial_balance": float(user.initial_balance),
            "current_balance": float(user.current_balance),
            "completed_courses": user.completed_courses or 0,
            "rol": user.rol,
            "created_at": str(user.created_at)
        }
    }


@router.get(
    "/profile",
    response_model=UserResponse,
    tags=["autenticación"]
)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        user = await get_current_user(db, token)
        return user
    except Exception as e:
        logger.exception("Error getting profile")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
        PasswordResetToken.used == False
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
    reset_token.used = True
    await db.commit()
    
    return {"message": "Contraseña actualizada exitosamente"}


@router.post(
    "/send-verification-code",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def send_verification_code(
    request: Request,
    email: str = Form(...),
    code_type: str = Form("2fa"),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    code = secrets.randbelow(900000) + 100000
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    stmt_del = select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.code_type == code_type,
        VerificationCode.used == False
    )
    result_del = await db.execute(stmt_del)
    old_codes = result_del.scalars().all()
    for old_code in old_codes:
        old_code.used = True
    
    verification = VerificationCode(
        user_id=user.id,
        code=str(code),
        code_type=code_type,
        expires_at=expires_at
    )
    db.add(verification)
    await db.commit()
    
    sent = await email_service.send_verification_code(user.email, str(code), code_type)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo enviar el código"
        )
    
    return {"message": "Código enviado al correo"}


@router.post(
    "/verify-code",
    tags=["autenticación"]
)
@limiter.limit(auth_rate_limit)
async def verify_code(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    code_type: str = Form("2fa"),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    stmt_code = select(VerificationCode).where(
        VerificationCode.user_id == user.id,
        VerificationCode.code == code,
        VerificationCode.code_type == code_type,
        VerificationCode.used == False
    )
    result_code = await db.execute(stmt_code)
    verification = result_code.scalar_one_or_none()
    
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido"
        )
    
    if verification.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código ha expirado"
        )
    
    verification.used = True
    await db.commit()
    
    return {"message": "Código verificado exitosamente", "verified": True}
