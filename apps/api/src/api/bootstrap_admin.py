"""CLI utility to bootstrap the initial super administrator without hardcoded passwords."""

import asyncio
import sys
import argparse
import getpass
from datetime import datetime, timezone
from sqlalchemy import select

from api.db.session import get_async_sessionmaker, get_async_engine
from api.db.models.admin import AdminUser, AdminRole
from api.db.models.audit import AuditEvent
from api.security.hashing import hash_password


async def bootstrap_admin(username: str, email: str, role: AdminRole, password: str) -> None:
    """Creates a new administrative user with Argon2id password hashing and audit trail."""
    session_maker = get_async_sessionmaker()
    async with session_maker() as session:
        # Check if user already exists
        result = await session.execute(
            select(AdminUser).where((AdminUser.username == username) | (AdminUser.email == email))
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Error: Admin user with username '{username}' or email '{email}' already exists.")
            sys.exit(1)

        hashed = hash_password(password)
        admin = AdminUser(
            username=username,
            email=email,
            password_hash=hashed,
            role=role,
            is_active=True
        )
        session.add(admin)
        await session.flush()

        audit = AuditEvent(
            actor_id="CLI_BOOTSTRAP",
            actor_role="system",
            action="ADMIN_BOOTSTRAP",
            target_entity="admin_user",
            target_id=str(admin.id),
            details={"username": username, "email": email, "role": role.value}
        )
        session.add(audit)
        await session.commit()
        print(f"Success: Initial administrator '{username}' ({role.value}) created successfully with ID {admin.id}.")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap initial administrator account.")
    parser.add_argument("--username", required=True, help="Administrator username")
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument(
        "--role",
        default="super_admin",
        choices=[r.value for r in AdminRole],
        help="Administrator role (default: super_admin)"
    )
    parser.add_argument("--password", required=False, help="Administrator password (prompted if omitted)")

    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("Enter administrator password: ")
        confirm_password = getpass.getpass("Confirm administrator password: ")
        if password != confirm_password:
            print("Error: Passwords do not match.")
            sys.exit(1)

    if len(password) < 12:
        print("Error: Password must be at least 12 characters long.")
        sys.exit(1)

    role_enum = AdminRole(args.role)
    asyncio.run(bootstrap_admin(args.username, args.email, role_enum, password))


if __name__ == "__main__":
    main()
