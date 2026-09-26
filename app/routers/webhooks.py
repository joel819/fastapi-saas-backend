from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db import get_db
from app.services.payments import PaymentProvider, SignatureError, get_payment_provider
from app.services.subscription_service import process_verified_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
@limiter.exempt
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
) -> dict:
    """Receives Stripe events. Verifies the signature on the raw body, then processes
    each event id at most once (replays return 200 with status=duplicate)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing Stripe-Signature header")
    try:
        event = provider.construct_event(payload, sig_header)
    except SignatureError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid signature: {exc}") from None
    if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed event")

    result, outcome = process_verified_event(db, event)
    return {"status": result, "outcome": outcome}
