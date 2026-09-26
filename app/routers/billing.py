import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.db import get_db
from app.models import IdempotencyKey, User
from app.schemas.subscription import CheckoutIn, CheckoutOut, SubscriptionOut
from app.services.payments import PaymentConfigError, PaymentProvider, get_payment_provider
from app.services.subscription_service import process_verified_event

router = APIRouter(prefix="/billing", tags=["billing"])
ENDPOINT = "POST /billing/checkout"


@router.post("/checkout", response_model=CheckoutOut)
@limiter.limit(get_settings().rate_limit_billing)
def create_checkout(
    request: Request,
    body: CheckoutIn,
    idempotency_key: str | None = Header(default=None, max_length=255),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
):
    """Start a checkout. Send an `Idempotency-Key` header to make retries safe."""
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()

    if idempotency_key:
        stored = db.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user.id,
                IdempotencyKey.endpoint == ENDPOINT,
                IdempotencyKey.key == idempotency_key,
            )
        )
        if stored:
            if stored.request_fingerprint != fingerprint:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "Idempotency-Key was already used with a different request"
                )
            return CheckoutOut(**json.loads(stored.response_body))

    try:
        session = provider.create_checkout_session(user=user, plan=body.plan, idempotency_key=idempotency_key)
    except PaymentConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None

    result = CheckoutOut(session_id=session.id, checkout_url=session.url, provider=provider.name)

    if idempotency_key:
        db.add(
            IdempotencyKey(
                user_id=user.id,
                endpoint=ENDPOINT,
                key=idempotency_key,
                request_fingerprint=fingerprint,
                response_body=result.model_dump_json(),
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # concurrent retry stored it first; our result is equivalent
    return result


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(user: User = Depends(get_current_user)):
    if user.subscription is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No subscription")
    return user.subscription


@router.get("/mock-checkout/{session_id}")
def complete_mock_checkout(
    session_id: str,
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
) -> dict:
    """Demo mode only: simulates the customer completing payment for a mock session."""
    if provider.name != "mock":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    event = provider.complete_checkout(session_id)  # type: ignore[attr-defined]
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or already completed session")
    result, outcome = process_verified_event(db, event)
    return {"status": result, "outcome": outcome, "event_id": event["id"]}
