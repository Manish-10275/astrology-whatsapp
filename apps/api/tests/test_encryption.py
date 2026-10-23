"""Tests for AES-256-GCM field-level encryption, tamper resistance, and phone pseudonymization."""

import base64
import pytest
from api.security.encryption import (
    encrypt_field,
    decrypt_field,
    compute_phone_hash,
    EncryptionError,
    DecryptionError,
    KeyRotationError,
)
from api.config import get_settings


def test_encryption_roundtrip():
    """Verify clean encryption and decryption of sensitive string data."""
    plaintext = "1990-05-15 14:30:00"
    encrypted = encrypt_field(plaintext)

    assert encrypted.startswith("v1:")
    assert encrypted != plaintext

    decrypted = decrypt_field(encrypted)
    assert decrypted == plaintext


def test_unique_nonce_per_operation():
    """Verify that encrypting identical data twice yields distinct ciphertexts (unique nonces)."""
    plaintext = "28.6139, 77.2090"  # New Delhi coordinates
    enc1 = encrypt_field(plaintext)
    enc2 = encrypt_field(plaintext)

    assert enc1 != enc2
    assert decrypt_field(enc1) == plaintext
    assert decrypt_field(enc2) == plaintext


def test_tamper_detection_ciphertext():
    """Verify that tampering with any ciphertext byte raises DecryptionError (authenticated tag failure)."""
    plaintext = "Confidential Birth Details"
    encrypted = encrypt_field(plaintext)

    version, b64_payload = encrypted.split(":", 1)
    raw_bytes = bytearray(base64.b64decode(b64_payload))

    # Tamper with a byte in the ciphertext payload (after the 12-byte nonce)
    raw_bytes[15] ^= 0xFF
    tampered_payload = base64.b64encode(bytes(raw_bytes)).decode("utf-8")
    tampered_encrypted = f"{version}:{tampered_payload}"

    with pytest.raises(DecryptionError):
        decrypt_field(tampered_encrypted)


def test_tamper_detection_auth_tag():
    """Verify that altering the authentication tag causes instant decryption rejection."""
    plaintext = "Sensitive Data"
    encrypted = encrypt_field(plaintext)

    version, b64_payload = encrypted.split(":", 1)
    raw_bytes = bytearray(base64.b64decode(b64_payload))

    # The last 16 bytes are the GCM authentication tag
    raw_bytes[-1] ^= 0x01
    tampered_payload = base64.b64encode(bytes(raw_bytes)).decode("utf-8")
    tampered_encrypted = f"{version}:{tampered_payload}"

    with pytest.raises(DecryptionError):
        decrypt_field(tampered_encrypted)


def test_tamper_detection_truncated_payload():
    """Verify that truncated or malformed payload raises DecryptionError."""
    with pytest.raises(DecryptionError):
        decrypt_field("v1:dG9vc2hvcnQ=")  # base64 for 'tooshort' (< 28 bytes)


def test_unknown_key_version():
    """Verify that an unknown key version raises KeyRotationError fail-closed."""
    plaintext = "Test Data"
    encrypted = encrypt_field(plaintext)
    _, payload = encrypted.split(":", 1)
    unknown_version_enc = f"v999:{payload}"

    with pytest.raises(KeyRotationError) as exc_info:
        decrypt_field(unknown_version_enc)
    assert "key version 'v999' not available" in str(exc_info.value)


def test_key_rotation_decryption():
    """Verify that data encrypted with a secondary key (v0) can be decrypted by keyring."""
    # Explicitly encrypt with v0 key version
    v0_encrypted = encrypt_field("Old Key Secret", key_version="v0")

    assert v0_encrypted.startswith("v0:")

    # Decrypt using default keyring (active is v1, but v0 is in secondary keys)
    decrypted = decrypt_field(v0_encrypted)
    assert decrypted == "Old Key Secret"


def test_phone_pseudonymization_deterministic():
    """Verify that phone hashing is deterministic, constant-length SHA-256, and pseudonymized."""
    phone = "+919876543210"
    hash1 = compute_phone_hash(phone)
    hash2 = compute_phone_hash(phone)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest
    assert all(c in "0123456789abcdef" for c in hash1)

    # Different number must produce completely different hash
    diff_hash = compute_phone_hash("+919876543211")
    assert diff_hash != hash1
