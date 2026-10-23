"""Password hashing and verification using modern Argon2id (OWASP recommended standard)."""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

_hasher = PasswordHasher(
    time_cost=3,          # 3 iterations
    memory_cost=65536,    # 64 MiB
    parallelism=4,        # 4 threads
    hash_len=32,          # 32-byte digest
    salt_len=16           # 16-byte cryptographically random salt
)


def hash_password(password: str) -> str:
    """Hashes a password using Argon2id with a unique per-password salt."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")
    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies a candidate password against an Argon2id hash."""
    if not isinstance(password, str) or not isinstance(hashed_password, str):
        return False
    try:
        return _hasher.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Checks whether the password hash needs to be updated to match current Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except Exception:
        return True
