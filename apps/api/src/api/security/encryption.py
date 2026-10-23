"""Field-level authenticated encryption using AES-256-GCM with versioned key management."""

import os
import base64
import hmac
import hashlib
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from api.config import get_settings


class EncryptionError(Exception):
    """Base exception for cryptographic operations."""
    pass


class DecryptionError(EncryptionError):
    """Raised when ciphertext is corrupted, tampered with, or cannot be decrypted."""
    pass


class KeyRotationError(EncryptionError):
    """Raised when a key version is not found in the active key ring."""
    pass


def encrypt_field(plaintext: str, key_version: Optional[str] = None) -> str:
    """Encrypts plaintext using AES-256-GCM.
    
    Format:
        {key_version}:{base64_encoded(nonce + ciphertext_with_auth_tag)}
        
    - Nonce: 12 cryptographically random bytes (os.urandom(12)).
    - Auth Tag: 16-byte Poly1305 / GCM tag appended automatically by AESGCM.
    - Fail-closed: Never returns partial or unauthenticated data.
    """
    if not isinstance(plaintext, str):
        raise TypeError(f"Plaintext must be a string, got {type(plaintext)}")

    settings = get_settings()
    version = key_version or settings.ENCRYPTION_KEY_VERSION

    try:
        key_bytes = settings.get_encryption_key_bytes(version)
    except KeyError as e:
        raise KeyRotationError(f"Encryption failed: key version '{version}' not found.") from e

    # 12-byte cryptographically secure random nonce
    nonce = os.urandom(12)
    aesgcm = AESGCM(key_bytes)
    plaintext_bytes = plaintext.encode("utf-8")

    # AESGCM.encrypt returns ciphertext + 16-byte auth tag
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    # Combine nonce + ciphertext
    payload = nonce + ciphertext
    b64_payload = base64.b64encode(payload).decode("utf-8")

    return f"{version}:{b64_payload}"


def decrypt_field(encrypted_token: str) -> str:
    """Decrypts an AES-256-GCM token and verifies authentication tag integrity.
    
    Fail-closed: Tampering, truncation, or incorrect keys raise DecryptionError.
    """
    if not isinstance(encrypted_token, str):
        raise TypeError(f"Encrypted token must be a string, got {type(encrypted_token)}")

    if ":" not in encrypted_token:
        raise DecryptionError("Malformed encrypted token: missing version separator.")

    version, b64_payload = encrypted_token.split(":", 1)
    settings = get_settings()

    try:
        key_bytes = settings.get_encryption_key_bytes(version)
    except KeyError as e:
        raise KeyRotationError(f"Decryption failed: key version '{version}' not available.") from e

    try:
        payload = base64.b64decode(b64_payload)
    except Exception as e:
        raise DecryptionError(f"Invalid base64 payload: {e}") from e

    # Minimum length: 12 bytes nonce + 16 bytes auth tag = 28 bytes
    if len(payload) < 28:
        raise DecryptionError("Ciphertext payload is truncated.")

    nonce = payload[:12]
    ciphertext = payload[12:]

    aesgcm = AESGCM(key_bytes)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as e:
        raise DecryptionError("Decryption failed: authentication tag verification failed (tampered data).") from e
    except Exception as e:
        raise DecryptionError(f"Decryption failed: {e}") from e

    return plaintext_bytes.decode("utf-8")


def compute_phone_hash(phone_e164: str, salt: Optional[str] = None) -> str:
    """Computes a deterministic, salted HMAC-SHA256 hash of a phone number for indexable lookups.
    
    Raw phone numbers are never stored in indexable plain text.
    """
    settings = get_settings()
    effective_salt = salt or settings.PHONE_HASH_SALT.get_secret_value()
    cleaned_phone = phone_e164.strip()

    h = hmac.new(
        effective_salt.encode("utf-8"),
        cleaned_phone.encode("utf-8"),
        hashlib.sha256
    )
    return h.hexdigest()
