"""Async database plumbing: declarative Base, lazy engine, session factory.

The engine is created lazily on first use so that importing this module (and the
ORM models that depend on it) does not require a live database or the asyncpg
driver to be importable. This keeps schema-only tests fast and decoupled.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in app/models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call."""
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict[str, Any] = {"echo": False, "future": True}
        # SQLite (offline dev/tests) gains nothing from pooling; NullPool also avoids
        # cross-event-loop connection finalizer noise at teardown. Postgres keeps the
        # default pool.
        if settings.database_url.startswith("sqlite"):
            from sqlalchemy import event
            from sqlalchemy.pool import NullPool

            kwargs["poolclass"] = NullPool
            _engine = create_async_engine(settings.database_url, **kwargs)

            # Enforce foreign keys on SQLite (off by default) so local/dev and the
            # test suite behave like the production PostgreSQL database.
            @event.listens_for(_engine.sync_engine, "connect")
            def _sqlite_fk_pragma(dbapi_connection, _record):  # pragma: no cover - trivial
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            return _engine
        _engine = create_async_engine(settings.database_url, **kwargs)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional async session."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine on shutdown (used by the app lifespan)."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def reset_engine_for_tests(**engine_kwargs: Any) -> None:
    """Force engine recreation; handy for test harnesses that swap DATABASE_URL."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
