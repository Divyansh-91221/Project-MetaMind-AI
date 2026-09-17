"""Local email/password authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.models.users import User
from app.schemas.auth import AuthResponse, AuthUser, LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _token_for(user: User) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be configured for authentication.")
    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "name": user.name,
        "email": user.email,
        "roles": [user.role],
        "iat": now,
        "exp": now + timedelta(hours=8),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    if not settings.jwt_issuer:
        claims.pop("iss")
    return jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def _response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=_token_for(user),
        user=AuthUser(name=user.name, email=user.email, role=user.role),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: DbSession) -> AuthResponse:
    email = _normalise_email(str(payload.email))
    existing = await session.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictError("An account with this email already exists.")
    user = User(
        name=payload.name.strip(), email=email, password_hash=_hash_password(payload.password)
    )
    session.add(user)
    await session.flush()
    return _response(user)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, session: DbSession) -> AuthResponse:
    email = _normalise_email(str(payload.email))
    user = await session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not user or not _verify_password(payload.password, user.password_hash):
        raise AuthenticationError("Invalid email or password.")
    return _response(user)
