"""Password hashing and JWT session tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AppError

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt operates on the first 72 bytes; truncate explicitly and safely.
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, organization_id: str | None, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "org": organization_id,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "agentic-bi",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM], issuer="agentic-bi")
    except jwt.ExpiredSignatureError as exc:
        raise AppError("SESSION_EXPIRED", "Your session has expired. Please sign in again.", 401) from exc
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_SESSION", "Invalid session token.", 401) from exc
