"""Apply verified Stripe (or mock) events to local subscription state, idempotently."""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Subscription, User, WebhookEvent
from app.models._time import from_epoch

log = logging.getLogger(__name__)


def _get_or_create_subscription(db: Session, user: User) -> Subscription:
    if user.subscription is None:
        user.subscription = Subscription(plan="free", status="active")
    return user.subscription


def _find_subscription(db: Session, stripe_sub_id: str | None, metadata: dict) -> Subscription | None:
    if stripe_sub_id:
        sub = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id))
        if sub:
            return sub
    user_id = (metadata or {}).get("user_id")
    if user_id and str(user_id).isdigit():
        user = db.get(User, int(user_id))
        if user:
            return _get_or_create_subscription(db, user)
    return None


def _period_end(obj: dict) -> Any:
    # Newer Stripe API versions moved current_period_end onto subscription items.
    ts = obj.get("current_period_end")
    if ts is None:
        items = (obj.get("items") or {}).get("data") or []
        ts = items[0].get("current_period_end") if items else None
    return from_epoch(ts)


def _on_checkout_completed(db: Session, obj: dict) -> str:
    metadata = obj.get("metadata") or {}
    raw_user_id = metadata.get("user_id") or obj.get("client_reference_id")
    if not raw_user_id or not str(raw_user_id).isdigit():
        return "ignored:no_user_reference"
    user = db.get(User, int(raw_user_id))
    if user is None:
        return "ignored:unknown_user"
    if obj.get("customer"):
        user.stripe_customer_id = obj["customer"]
    sub = _get_or_create_subscription(db, user)
    sub.plan = metadata.get("plan", sub.plan)
    sub.status = "active"
    sub.cancel_at_period_end = False
    if obj.get("subscription"):
        sub.stripe_subscription_id = obj["subscription"]
    return "subscription_activated"


def _on_subscription_changed(db: Session, obj: dict) -> str:
    sub = _find_subscription(db, obj.get("id"), obj.get("metadata"))
    if sub is None:
        return "ignored:unknown_subscription"
    sub.stripe_subscription_id = obj.get("id") or sub.stripe_subscription_id
    sub.status = obj.get("status", sub.status)
    sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end", False))
    sub.current_period_end = _period_end(obj) or sub.current_period_end
    plan = (obj.get("metadata") or {}).get("plan")
    if plan:
        sub.plan = plan
    return "subscription_updated"


def _on_subscription_deleted(db: Session, obj: dict) -> str:
    sub = _find_subscription(db, obj.get("id"), obj.get("metadata"))
    if sub is None:
        return "ignored:unknown_subscription"
    sub.status = "canceled"
    sub.plan = "free"
    sub.cancel_at_period_end = False
    return "subscription_canceled"


def _on_invoice_payment_failed(db: Session, obj: dict) -> str:
    stripe_sub_id = obj.get("subscription") or (
        ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
    )
    sub = _find_subscription(db, stripe_sub_id, {})
    if sub is None:
        return "ignored:unknown_subscription"
    sub.status = "past_due"
    return "subscription_past_due"


HANDLERS = {
    "checkout.session.completed": _on_checkout_completed,
    "customer.subscription.created": _on_subscription_changed,
    "customer.subscription.updated": _on_subscription_changed,
    "customer.subscription.deleted": _on_subscription_deleted,
    "invoice.payment_failed": _on_invoice_payment_failed,
}


def apply_event(db: Session, event: dict[str, Any]) -> str:
    """Mutates state for one event without committing. Returns a short outcome label."""
    handler = HANDLERS.get(event.get("type", ""))
    if handler is None:
        return "ignored:unhandled_type"
    obj = (event.get("data") or {}).get("object") or {}
    return handler(db, obj)


def process_verified_event(db: Session, event: dict[str, Any]) -> tuple[str, str]:
    """Idempotent processing. Returns (status, outcome) where status is processed|duplicate.

    The event row and the state change are committed in one transaction, so an event
    is either fully applied and recorded, or neither (and Stripe will retry).
    """
    event_id = event["id"]
    existing = db.get(WebhookEvent, event_id)
    if existing is not None:
        return "duplicate", existing.outcome

    outcome = apply_event(db, event)
    db.add(WebhookEvent(id=event_id, type=event.get("type", ""), outcome=outcome))
    try:
        db.commit()
    except IntegrityError:
        # A concurrent delivery of the same event won the race.
        db.rollback()
        return "duplicate", "concurrent_delivery"
    log.info("webhook %s %s -> %s", event_id, event.get("type"), outcome)
    return "processed", outcome
