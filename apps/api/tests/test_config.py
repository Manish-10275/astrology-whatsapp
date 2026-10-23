"""Unit tests for configuration validation and fail-closed security guarantees."""

import pytest
from pydantic import ValidationError
from api.config import Settings


def test_valid_settings():
    """Verify that valid configuration loads cleanly and yields 32-byte key."""
    settings = Settings(
        ENCRYPTION_PRIMARY_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ENCRYPTION_KEY_VERSION="v1",
        JWT_SECRET_KEY="super-secret-jwt-key-with-minimum-32-characters-required-here",
        PHONE_HASH_SALT="default-phone-hash-salt-32-chars-long-minimum",
    )
    key_bytes = settings.get_encryption_key_bytes("v1")
    assert isinstance(key_bytes, bytes)
    assert len(key_bytes) == 32


def test_invalid_encryption_key_too_short():
    """Verify fail-closed error when encryption key is shorter than 256 bits (32 bytes)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENCRYPTION_PRIMARY_KEY="abcdef1234",
            JWT_SECRET_KEY="super-secret-jwt-key-with-minimum-32-characters-required-here",
            PHONE_HASH_SALT="default-phone-hash-salt-32-chars-long-minimum",
        )
    assert "must resolve to exactly 32 bytes" in str(exc_info.value)


def test_invalid_encryption_key_non_hex():
    """Verify fail-closed error when encryption key does not resolve to 32 bytes."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENCRYPTION_PRIMARY_KEY="g" * 64,
            JWT_SECRET_KEY="super-secret-jwt-key-with-minimum-32-characters-required-here",
            PHONE_HASH_SALT="default-phone-hash-salt-32-chars-long-minimum",
        )
    assert "must resolve to exactly 32 bytes" in str(exc_info.value)


def test_invalid_jwt_secret_too_short():
    """Verify fail-closed error when JWT secret is less than 32 characters."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENCRYPTION_PRIMARY_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            JWT_SECRET_KEY="short-secret",
            PHONE_HASH_SALT="default-phone-hash-salt-32-chars-long-minimum",
        )
    assert "JWT_SECRET_KEY must be at least 32 characters" in str(exc_info.value)


def test_invalid_phone_hash_salt_too_short():
    """Verify fail-closed error when phone salt is less than 16 characters."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENCRYPTION_PRIMARY_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            JWT_SECRET_KEY="super-secret-jwt-key-with-minimum-32-characters-required-here",
            PHONE_HASH_SALT="short",
        )
    assert "PHONE_HASH_SALT must be at least 16 characters" in str(exc_info.value)


def test_secondary_encryption_keys():
    """Verify keyring loading for rotated secondary keys."""
    settings = Settings(
        ENCRYPTION_PRIMARY_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ENCRYPTION_KEY_VERSION="v2",
        ENCRYPTION_SECONDARY_KEYS={
            "v1": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        },
        JWT_SECRET_KEY="super-secret-jwt-key-with-minimum-32-characters-required-here",
        PHONE_HASH_SALT="default-phone-hash-salt-32-chars-long-minimum",
    )
    key_v2 = settings.get_encryption_key_bytes("v2")
    key_v1 = settings.get_encryption_key_bytes("v1")
    assert len(key_v2) == 32
    assert len(key_v1) == 32
    with pytest.raises(KeyError):
        settings.get_encryption_key_bytes("v999")
