"""Shared pytest fixtures for the Astrology Platform API test suite."""

import os
import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Configure test environment variables BEFORE importing application modules
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres@localhost:5432/astrology_test"
os.environ["DATABASE_SYNC_URL"] = "postgresql+psycopg://postgres@localhost:5432/astrology_test"
os.environ["ENCRYPTION_PRIMARY_KEY"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
os.environ["ENCRYPTION_KEY_VERSION"] = "v1"
os.environ["ENCRYPTION_SECONDARY_KEYS"] = '{"v0": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"}'
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-minimum-32-chars-long-here"
os.environ["PHONE_HASH_SALT"] = "test-phone-hash-salt-32-chars-long-minimum"

from api.config import get_settings
from api.db.base import Base
import api.db.models  # noqa: F401
from api.db.session import get_db_session
from api.main import create_app
from api.security.hashing import hash_password
from api.security.token import create_access_token
from api.db.models.admin import AdminUser, AdminRole

from sqlalchemy.pool import NullPool
import api.db.session

test_settings = get_settings()
test_engine = create_async_engine(test_settings.DATABASE_URL, poolclass=NullPool, echo=False)
api.db.session._async_engine = test_engine
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    """Initializes schema once per test session and drops on teardown using sync engine."""
    sync_url = test_settings.DATABASE_SYNC_URL or test_settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    engine = create_engine(sync_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database():
    """Cleans all table rows between tests to ensure complete state isolation."""
    yield
    sync_url = test_settings.DATABASE_SYNC_URL or test_settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM audit_events; "
                "DELETE FROM birth_profiles; "
                "DELETE FROM consent_records; "
                "DELETE FROM deletion_requests; "
                "DELETE FROM user_preferences; "
                "DELETE FROM users; "
                "DELETE FROM admin_users;"
            )
        )
    engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields an isolated async session for database queries within a test."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def app_instance():
    """FastAPI application instance with overridden database session dependency."""
    app = create_app()

    async def _get_test_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _get_test_db
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app_instance) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client."""
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def create_test_admin(db_session: AsyncSession):
    """Factory fixture to create an admin user in the test database."""
    async def _create(
        username: str = "testadmin",
        email: str = "testadmin@example.com",
        password: str = "SecureAdminPass123!",
        role: AdminRole = AdminRole.SUPER_ADMIN,
    ) -> tuple[AdminUser, str]:
        admin = AdminUser(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

        token = create_access_token(
            admin_id=str(admin.id),
            username=admin.username,
            role=admin.role.value,
            permissions=admin.get_permissions(),
        )
        return admin, token

    return _create
