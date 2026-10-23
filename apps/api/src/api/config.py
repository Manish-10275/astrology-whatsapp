"""Application configuration and environment settings with fail-closed validation."""

import os
from typing import Dict, Optional
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for backend API and persistence layer."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Environment
    ENVIRONMENT: str = Field(default="development", description="development, test, staging, production")
    LOG_LEVEL: str = Field(default="INFO")

    # Database Settings
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres@localhost:5432/astrology_dev",
        description="Async PostgreSQL connection string (asyncpg driver)"
    )
    DATABASE_SYNC_URL: Optional[str] = Field(
        default="postgresql+psycopg://postgres@localhost:5432/astrology_dev",
        description="Synchronous PostgreSQL connection string for Alembic migrations"
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1, le=120)

    # Security: Field-Level Encryption (AES-256-GCM)
    ENCRYPTION_PRIMARY_KEY: SecretStr = Field(
        default=SecretStr("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
        description="Primary 256-bit AES encryption key encoded as a 64-char hex string"
    )
    ENCRYPTION_KEY_VERSION: str = Field(default="v1", description="Active key version identifier")
    # Secondary / rotated keys for decryption during key rotation transitions
    ENCRYPTION_SECONDARY_KEYS: Dict[str, SecretStr] = Field(
        default_factory=dict,
        description="Mapping of version -> key for previous keys still in circulation"
    )

    # Security: JWT & Session Management
    JWT_SECRET_KEY: SecretStr = Field(
        default=SecretStr("super-secret-jwt-key-with-minimum-32-characters-required-here"),
        description="HMAC secret for signing admin JWTs (minimum 32 characters)"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)

    # Security: Identity Pseudonymization
    PHONE_HASH_SALT: SecretStr = Field(
        default=SecretStr("default-phone-hash-salt-32-chars-long-minimum"),
        description="Secret salt used to compute HMAC-SHA256 phone hashes"
    )

    # Brute Force Protection
    AUTH_MAX_FAILED_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    AUTH_LOCKOUT_MINUTES: int = Field(default=15, ge=1, le=1440)

    # WhatsApp Cloud API Integration
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = Field(
        default=None,
        description="Meta WhatsApp Cloud API Phone Number ID"
    )
    WHATSAPP_ACCESS_TOKEN: Optional[SecretStr] = Field(
        default=None,
        description="Meta Graph API access token (System User permanent token)"
    )
    WHATSAPP_VERIFY_TOKEN: SecretStr = Field(
        default=SecretStr("astrology-whatsapp-verify-token-dev"),
        description="Meta webhook verification challenge token"
    )
    WHATSAPP_APP_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Meta App Secret for X-Hub-Signature-256 payload authentication"
    )
    WHATSAPP_API_VERSION: str = Field(default="v21.0")

    # AI / LLM Orchestration
    OPENAI_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="OpenAI API key for natural language interpretation"
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model for chat responses and interpretations"
    )

    # Ephemeral State & Redis (Optional / Graceful Fallback)
    REDIS_URL: Optional[str] = Field(
        default=None,
        description="Redis connection URL for temporary lock / deduplication cache"
    )

    @field_validator("ENCRYPTION_PRIMARY_KEY")
    def validate_encryption_key_length(cls, v: SecretStr) -> SecretStr:
        val = v.get_secret_value()
        try:
            raw_bytes = bytes.fromhex(val)
        except ValueError:
            raw_bytes = val.encode("utf-8")
        if len(raw_bytes) != 32:
            raise ValueError(
                f"ENCRYPTION_PRIMARY_KEY must resolve to exactly 32 bytes (256 bits). Found {len(raw_bytes)} bytes."
            )
        return v

    @field_validator("JWT_SECRET_KEY")
    def validate_jwt_secret_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long.")
        return v

    @field_validator("PHONE_HASH_SALT")
    def validate_phone_salt_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 16:
            raise ValueError("PHONE_HASH_SALT must be at least 16 characters long.")
        return v

    def get_encryption_key_bytes(self, key_version: str) -> bytes:
        """Returns the raw 32-byte key for the specified version."""
        if key_version == self.ENCRYPTION_KEY_VERSION:
            val = self.ENCRYPTION_PRIMARY_KEY.get_secret_value()
        elif key_version in self.ENCRYPTION_SECONDARY_KEYS:
            val = self.ENCRYPTION_SECONDARY_KEYS[key_version].get_secret_value()
        else:
            raise KeyError(f"Unknown encryption key version: '{key_version}'")

        try:
            raw = bytes.fromhex(val)
        except ValueError:
            raw = val.encode("utf-8")
        if len(raw) != 32:
            raise ValueError(f"Key '{key_version}' does not resolve to 32 bytes.")
        return raw


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
