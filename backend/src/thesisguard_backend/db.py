"""Async SQLAlchemy engine/session setup."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from thesisguard_backend.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


if engine.url.get_backend_name() == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def initialize_local_database() -> None:
    """Create tables automatically for the zero-setup local SQLite database."""

    if engine.url.get_backend_name() != "sqlite":
        return

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
