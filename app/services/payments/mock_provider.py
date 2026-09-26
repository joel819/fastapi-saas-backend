"""Mock payment provider used in demo mode (no Stripe key).

It signs and verifies webhooks with the same scheme Stripe uses
(`Stripe-Signature: t=<unix>,v1=<hex hmac_sha256(secret, "<t>.<payload>")>`),
so the verification path is exercised for real without any Stripe account.
"""
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.config import Settings
from app.models import User
from app.services.payments.base import CheckoutSession, SignatureError

DEFAULT_TOLERANCE_SECONDS = 300


def sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def verify_signature(
    payload: bytes, sig_header: str, secret: str, tolerance: int = DEFAULT_TOLERANCE_SECONDS
) -> None:
    try:
        parts = [p.split("=", 1) for p in sig_header.split(",")]
        ts = int(next(v for k, v in parts if k == "t"))
        candidates = [v for k, v in parts if k == "v1"]
    except (ValueError, StopIteration):
        raise SignatureError("Malformed signature header") from None
    if not candidates:
        raise SignatureError("No v1 signature found")
    if abs(time.time() - ts) > tolerance:
        raise SignatureError("Timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise SignatureError("Signature mismatch")


def build_event(event_type: str, obj: dict[str, Any], event_id: str | None = None) -> dict[str, Any]:
    return {
        "id": event_id or f"evt_mock_{uuid.uuid4().hex[:24]}",
        "object": "event",
        "type": event_type,
        "created": int(time.time()),
        "livemode": False,
        "data": {"object": obj},
    }


class MockProvider:
    name = "mock"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.secret = settings.effective_webhook_secret
        # session_id -> (user_id, plan). In-memory: fine for a single-process demo.
        self.pending: dict[str, tuple[int, str]] = {}

    def create_checkout_session(self, *, user: User, plan: str, idempotency_key: str | None) -> CheckoutSession:
        session_id = f"cs_mock_{uuid.uuid4().hex[:24]}"
        self.pending[session_id] = (user.id, plan)
        url = f"{self.settings.public_base_url}/billing/mock-checkout/{session_id}"
        return CheckoutSession(id=session_id, url=url)

    def complete_checkout(self, session_id: str) -> dict[str, Any] | None:
        """Simulate the customer paying: returns the checkout.session.completed event."""
        entry = self.pending.pop(session_id, None)
        if entry is None:
            return None
        user_id, plan = entry
        return build_event(
            "checkout.session.completed",
            {
                "id": session_id,
                "object": "checkout.session",
                "mode": "subscription",
                "client_reference_id": str(user_id),
                "customer": f"cus_mock_{user_id}",
                "subscription": f"sub_mock_{uuid.uuid4().hex[:16]}",
                "metadata": {"user_id": str(user_id), "plan": plan},
            },
        )

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        verify_signature(payload, sig_header, self.secret)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise SignatureError("Payload is not valid JSON") from None
