"""Rate limiting with slowapi (in-memory storage; swap storage_uri for Redis in production).

Authenticated requests are limited per user; anonymous requests per client IP.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings
from app.core.security import TokenError, decode_token


def rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            return f"user:{decode_token(auth[7:], 'access')['sub']}"
        except TokenError:
            pass
    return f"ip:{get_remote_address(request)}"


_settings = get_settings()

limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[_settings.rate_limit_default],
    enabled=_settings.rate_limit_enabled,
    storage_uri="memory://",
    headers_enabled=False,
)
