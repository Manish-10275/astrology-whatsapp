"""JWT generation, decoding, and session token verification."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from api.config import get_settings


class TokenError(Exception):
    """Base exception for authentication token errors."""
    pass


class TokenExpiredError(TokenError):
    """Raised when an authentication token has expired."""
    pass


class InvalidTokenSignatureError(TokenError):
    """Raised when token signature or payload is invalid."""
    pass


def create_access_token(
    admin_id: str,
    username: str,
    role: str,
    permissions: List[str],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Creates a signed JWT access token for an authenticated administrator."""
    settings = get_settings()
    now_utc = datetime.now(timezone.utc)
    expire = now_utc + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: Dict[str, Any] = {
        "sub": str(admin_id),
        "username": username,
        "role": role,
        "permissions": permissions,
        "exp": expire,
        "iat": now_utc,
        "jti": str(uuid.uuid4())
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM
    )
    return token


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and cryptographically validates a JWT access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except ExpiredSignatureError as e:
        raise TokenExpiredError("Access token has expired.") from e
    except InvalidTokenError as e:
        raise InvalidTokenSignatureError(f"Invalid access token: {e}") from e
