"""Password hashing (bcrypt) and JWT creation/verification."""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import get_settings

# Hash used when the user does not exist, so login timing doesn't reveal valid emails.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt()).decode()


class TokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), (hashed or _DUMMY_HASH).encode())
    except ValueError:
        return False


def _encode(claims: dict[str, Any], ttl: timedelta) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(UTC)
    expires = now + ttl
    payload = {**claims, "iat": now, "exp": expires, "jti": uuid.uuid4().hex}
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, expires


def create_access_token(user_id: int) -> str:
    ttl = timedelta(minutes=get_settings().access_token_expire_minutes)
    token, _ = _encode({"sub": str(user_id), "type": "access"}, ttl)
    return token


def create_refresh_token(user_id: int, family_id: str) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at as naive UTC)."""
    ttl = timedelta(days=get_settings().refresh_token_expire_days)
    token, expires = _encode({"sub": str(user_id), "type": "refresh", "fam": family_id}, ttl)
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    return token, jti, expires.replace(tzinfo=None)


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"expected {expected_type} token")
    return payload
