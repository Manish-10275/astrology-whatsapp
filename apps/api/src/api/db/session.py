"""Database engine configuration, connection pooling, and session management."""

from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy import text

from api.config import get_settings

_async_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Creates or returns the global singleton AsyncEngine."""
    global _async_engine
    if _async_engine is None or database_url is not None:
        settings = get_settings()
        url = database_url or settings.DATABASE_URL

        # SQLite does not support pool_size and max_overflow
        is_sqlite = url.startswith("sqlite")
        engine_kwargs = {"echo": False}
        if not is_sqlite:
            engine_kwargs.update({
                "pool_size": settings.DATABASE_POOL_SIZE,
                "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
                "pool_pre_ping": True,
            })

        engine = create_async_engine(url, **engine_kwargs)
        if database_url is None:
            _async_engine = engine
        return engine
    return _async_engine


def get_async_sessionmaker(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    """Returns an async sessionmaker instance."""
    global _async_session_maker
    if _async_session_maker is None or engine is not None:
        target_engine = engine or get_async_engine()
        session_maker = async_sessionmaker(
            bind=target_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
        if engine is None:
            _async_session_maker = session_maker
        return session_maker
    return _async_session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    session_factory = get_async_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health(engine: Optional[AsyncEngine] = None) -> bool:
    """Executes a lightweight readiness check (SELECT 1) without exposing database credentials."""
    target_engine = engine or get_async_engine()
    try:
        async with target_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
