"""Tests for Argon2id password hashing and verification."""

import pytest
from api.security.hashing import hash_password, verify_password, needs_rehash


def test_password_hashing():
    """Verify that password hashing uses Argon2id with unique salts."""
    pwd = "ComplexPassword99!"
    hash1 = hash_password(pwd)
    hash2 = hash_password(pwd)

    assert hash1.startswith("$argon2id$")
    assert hash2.startswith("$argon2id$")
    assert hash1 != hash2  # Salt ensures uniqueness


def test_password_verification():
    """Verify correct password verification and rejection of incorrect passwords."""
    pwd = "CorrectPassword123"
    hashed = hash_password(pwd)

    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_verify_malformed_hash():
    """Verify that malformed hash strings fail verification cleanly without raising exceptions."""
    assert verify_password("password", "invalid$hash$format") is False
    assert verify_password("password", "") is False


def test_needs_rehash():
    """Verify that freshly hashed passwords with default parameters do not need rehashing."""
    hashed = hash_password("FreshPassword123")
    assert needs_rehash(hashed) is False
