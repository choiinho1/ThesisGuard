"""POST /api/auth/signup, /login · GET /api/auth/me"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.deps import CurrentUser, DbSession
from thesisguard_backend.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from thesisguard_backend.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = await db.scalar(select(orm.User).where(orm.User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다.")
    return TokenResponse(access_token=create_access_token(subject=str(user.id)))


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> orm.User:
    return current_user
