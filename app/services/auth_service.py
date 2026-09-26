"""Registration, login and refresh-token rotation with reuse detection."""
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import RefreshToken, Subscription, User
from app.models._time import utcnow
from app.schemas.auth import TokenPair


class AuthError(Exception):
    """Invalid credentials or token. Message is safe to show to clients."""


class EmailTakenError(Exception):
    pass


def _normalise(email: str) -> str:
    return email.strip().lower()


def register(db: Session, email: str, password: str) -> User:
    user = User(email=_normalise(email), hashed_password=hash_password(password))
    user.subscription = Subscription(plan="free", status="active")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailTakenError(email) from None
    return user


def _issue_tokens(db: Session, user_id: int, family_id: str | None = None) -> tuple[TokenPair, str]:
    family_id = family_id or uuid.uuid4().hex
    refresh, jti, expires_at = create_refresh_token(user_id, family_id)
    db.add(RefreshToken(jti=jti, family_id=family_id, user_id=user_id, expires_at=expires_at))
    pair = TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=refresh,
        expires_in=get_settings().access_token_expire_minutes * 60,
    )
    return pair, jti


def login(db: Session, email: str, password: str) -> TokenPair:
    user = db.scalar(select(User).where(User.email == _normalise(email)))
    # verify_password runs even when user is None, to keep timing uniform.
    if not verify_password(password, user.hashed_password if user else None) or not user:
        raise AuthError("Invalid email or password")
    if not user.is_active:
        raise AuthError("Account disabled")
    pair, _ = _issue_tokens(db, user.id)
    db.commit()
    return pair


def _revoke_family(db: Session, family_id: str) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id).values(revoked=True))


def refresh(db: Session, token: str) -> TokenPair:
    try:
        payload = decode_token(token, "refresh")
    except TokenError:
        raise AuthError("Invalid refresh token") from None

    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if record is None:
        raise AuthError("Invalid refresh token")
    if record.revoked:
        # A rotated/revoked token was replayed: assume theft, kill the whole session family.
        _revoke_family(db, record.family_id)
        db.commit()
        raise AuthError("Refresh token reuse detected; session revoked")
    if record.expires_at <= utcnow():
        raise AuthError("Refresh token expired")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthError("Invalid refresh token")

    pair, new_jti = _issue_tokens(db, user.id, record.family_id)
    record.revoked = True
    record.replaced_by = new_jti
    db.commit()
    return pair


def logout(db: Session, token: str) -> None:
    """Revoke the session family the refresh token belongs to. Silent on bad tokens."""
    try:
        payload = decode_token(token, "refresh")
    except TokenError:
        return
    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if record:
        _revoke_family(db, record.family_id)
        db.commit()
