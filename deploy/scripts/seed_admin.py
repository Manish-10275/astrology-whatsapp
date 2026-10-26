"""Secure interactive initial administrator account provisioning."""

import sys
import getpass
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from api.config import get_settings
from api.db.models.admin import AdminUser, AdminRole
from api.security.hashing import hash_password


async def create_initial_admin():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    print("==================================================")
    print("ASTROLOGY PLATFORM — ADMIN PROVISIONING UTILITY")
    print("==================================================")

    # Allow passing via environment variables for non-interactive automation, or prompt
    import os
    username = os.environ.get("INITIAL_ADMIN_USERNAME")
    email = os.environ.get("INITIAL_ADMIN_EMAIL")
    password = os.environ.get("INITIAL_ADMIN_PASSWORD")

    if not username:
        username = input("Enter admin username: ").strip()
    if not email:
        email = input("Enter admin email: ").strip()
    if not password:
        password = getpass.getpass("Enter admin password (min 12 characters): ")
        confirm_password = getpass.getpass("Confirm admin password: ")
        if password != confirm_password:
            print("Error: Passwords do not match.")
            sys.exit(1)

    if len(password) < 12:
        print("Error: Password must be at least 12 characters long.")
        sys.exit(1)

    async with session_factory() as session:
        result = await session.execute(select(AdminUser).where(AdminUser.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Error: Admin user '{username}' already exists in the database.")
            sys.exit(1)

        admin = AdminUser(
            id=uuid.uuid4(),
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=AdminRole.SUPER_ADMIN,
            is_active=True,
            failed_login_attempts=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        session.add(admin)
        await session.commit()
        print(f"Success: Administrator '{username}' provisioned with SUPER_ADMIN role.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_initial_admin())
