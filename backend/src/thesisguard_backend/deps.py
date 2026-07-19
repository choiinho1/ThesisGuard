"""Shared FastAPI dependencies: DB session and current-user auth."""

from __future__ import annotations

import uuid
from typing import Annotated

from agents.graph import ThesisGuardAgent
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from thesisguard_backend import models as orm
from thesisguard_backend.db import get_db
from thesisguard_backend.security import decode_access_token

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)],
    db: DbSession,
) -> orm.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if user_id is None:
        raise unauthorized
    user = await db.get(orm.User, uuid.UUID(user_id))
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[orm.User, Depends(get_current_user)]


async def get_current_admin_user(current_user: CurrentUser) -> orm.User:
    if current_user.role != orm.UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자 권한이 필요합니다.")
    return current_user


AdminUser = Annotated[orm.User, Depends(get_current_admin_user)]


def get_agent(request: Request) -> ThesisGuardAgent:
    """C exposes no module-level ``structure_thesis``, only instance methods.

    B builds one ``ThesisGuardAgent`` at startup (see main.py's lifespan) and
    keeps the reference on ``app.state`` so routes can call instance methods
    like ``astructure_thesis`` / ``aanswer_portfolio_query`` directly, instead
    of only having the module-level ``arun_analysis_workflow`` C exports.
    """

    return request.app.state.agent


Agent = Annotated[ThesisGuardAgent, Depends(get_agent)]


async def get_owned_portfolio(
    portfolio_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> orm.Portfolio:
    portfolio = await db.get(orm.Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "포트폴리오를 찾을 수 없습니다.")
    return portfolio
