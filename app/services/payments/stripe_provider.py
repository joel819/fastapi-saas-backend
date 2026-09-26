"""Stripe provider (use test-mode keys: sk_test_..., whsec_...)."""
import json
from typing import Any

import stripe

from app.config import Settings
from app.models import User
from app.services.payments.base import CheckoutSession, PaymentConfigError, SignatureError


class StripeProvider:
    name = "stripe"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = stripe.StripeClient(settings.stripe_secret_key)
        self.prices = {"basic": settings.stripe_price_basic, "pro": settings.stripe_price_pro}

    def create_checkout_session(self, *, user: User, plan: str, idempotency_key: str | None) -> CheckoutSession:
        price = self.prices.get(plan)
        if not price:
            raise PaymentConfigError(f"No Stripe price configured for plan '{plan}'")
        metadata = {"user_id": str(user.id), "plan": plan}
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price, "quantity": 1}],
            "success_url": f"{self.settings.public_base_url}/billing/subscription?checkout=success",
            "cancel_url": f"{self.settings.public_base_url}/billing/subscription?checkout=cancel",
            "client_reference_id": str(user.id),
            "metadata": metadata,
            "subscription_data": {"metadata": metadata},
        }
        if user.stripe_customer_id:
            params["customer"] = user.stripe_customer_id
        else:
            params["customer_email"] = user.email
        options = {"idempotency_key": idempotency_key} if idempotency_key else None
        session = self.client.v1.checkout.sessions.create(params=params, options=options)
        return CheckoutSession(id=session.id, url=session.url)

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        secret = self.settings.effective_webhook_secret
        if not secret:
            raise SignatureError("STRIPE_WEBHOOK_SECRET is not configured")
        try:
            stripe.WebhookSignature.verify_header(payload.decode("utf-8"), sig_header, secret)
        except (stripe.SignatureVerificationError, UnicodeDecodeError) as exc:
            raise SignatureError(str(exc)) from None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            raise SignatureError("Payload is not valid JSON") from None
