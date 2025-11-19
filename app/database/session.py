from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import get_settings

_engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine() -> AsyncEngine:
    """Return a singleton async engine instance."""
    global _engine, async_session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, echo=False, future=True)
        async_session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, autoflush=False, autocommit=False
        )
    return _engine


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide an async database session context."""
    global async_session_factory
    if async_session_factory is None:
        get_async_engine()
    assert async_session_factory is not None  # for mypy
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


__all__ = ["get_async_engine", "async_session_factory", "get_session"]

