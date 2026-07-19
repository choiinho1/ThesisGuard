"""POST /api/auth/signup, /login, /google · GET /api/auth/me"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.config import get_settings
from thesisguard_backend.deps import CurrentUser, DbSession
from thesisguard_backend.schemas import (
    GoogleLoginRequest,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from thesisguard_backend.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _default_portfolio(user_id: uuid.UUID) -> orm.Portfolio:
    return orm.Portfolio(
        user_id=user_id,
        name="MY THESIS",
        investment_purpose="장기 자산 성장",
        investment_horizon="장기",
        cash_ratio=0,
    )


async def _ensure_default_portfolio(db: DbSession, user: orm.User) -> None:
    portfolio_id = await db.scalar(
        select(orm.Portfolio.id).where(orm.Portfolio.user_id == user.id).limit(1)
    )
    if portfolio_id is not None:
        return

    db.add(_default_portfolio(user.id))
    await db.commit()


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: DbSession) -> orm.User:
    existing = await db.scalar(select(orm.User).where(orm.User.email == payload.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입된 이메일입니다.")

    user = orm.User(
        email=payload.email, password_hash=hash_password(payload.password), name=payload.name
    )
    db.add(user)
    await db.flush()
    db.add(orm.AlertSettings(user_id=user.id))
    db.add(_default_portfolio(user.id))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = await db.scalar(select(orm.User).where(orm.User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다."
        )
    return TokenResponse(access_token=create_access_token(subject=str(user.id)))


@router.post("/google", response_model=TokenResponse)
async def login_with_google(payload: GoogleLoginRequest, db: DbSession) -> TokenResponse:
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "서버에 GOOGLE_CLIENT_ID가 설정되어 있지 않습니다.",
        )

    try:
        claims = google_id_token.verify_oauth2_token(
            payload.id_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "유효하지 않은 Google 인증 정보입니다."
        ) from exc

    email = claims.get("email")
    if not email:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Google 계정에서 이메일을 확인할 수 없습니다."
        )

    user = await db.scalar(select(orm.User).where(orm.User.email == email))
    if user is None:
        # Google-authenticated accounts never log in with a password, so the
        # hash only needs to be a value nobody can guess.
        user = orm.User(
            email=email,
            password_hash=hash_password(uuid.uuid4().hex),
            name=claims.get("name"),
        )
        db.add(user)
        await db.flush()
        db.add(orm.AlertSettings(user_id=user.id))
        db.add(_default_portfolio(user.id))
        await db.commit()
        await db.refresh(user)

    return TokenResponse(access_token=create_access_token(subject=str(user.id)))


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser, db: DbSession) -> orm.User:
    await _ensure_default_portfolio(db, current_user)
    return current_user
