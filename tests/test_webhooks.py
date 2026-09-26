import json
import time

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.services.payments.base import SignatureError
from app.services.payments.mock_provider import sign_payload
from app.services.payments.stripe_provider import StripeProvider


def _activate(client, auth_headers, plan="pro") -> dict:
    url = client.post("/billing/checkout", json={"plan": plan}, headers=auth_headers).json()["checkout_url"]
    client.get(url.replace("http://localhost:8000", ""))
    return client.get("/users/me", headers=auth_headers).json()["subscription"]


def _stripe_sub_id(client, auth_headers):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        return user.subscription.stripe_subscription_id


def test_missing_signature_rejected(client):
    r = client.post("/webhooks/stripe", content=b"{}")
    assert r.status_code == 400


def test_wrong_secret_rejected(client, send_webhook):
    r, _ = send_webhook("customer.subscription.deleted", {"id": "sub_x"}, secret="whsec_wrong")
    assert r.status_code == 400


def test_tampered_payload_rejected(client):
    payload = json.dumps({"id": "evt_1", "type": "x", "data": {"object": {}}}).encode()
    sig = sign_payload(payload, get_settings().effective_webhook_secret)
    r = client.post("/webhooks/stripe", content=payload + b" ", headers={"Stripe-Signature": sig})
    assert r.status_code == 400


def test_stale_timestamp_rejected(client, send_webhook):
    r, _ = send_webhook("customer.subscription.deleted", {"id": "sub_x"}, timestamp=int(time.time()) - 3600)
    assert r.status_code == 400


def test_malformed_signature_header_rejected(client):
    r = client.post("/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "garbage"})
    assert r.status_code == 400


def test_unhandled_event_type_acknowledged(client, send_webhook):
    r, _ = send_webhook("customer.created", {"id": "cus_1"})
    assert r.status_code == 200
    assert r.json()["outcome"] == "ignored:unhandled_type"


def test_subscription_deleted_downgrades_user(client, auth_headers, send_webhook):
    _activate(client, auth_headers)
    sub_id = _stripe_sub_id(client, auth_headers)
    r, _ = send_webhook("customer.subscription.deleted", {"id": sub_id, "status": "canceled"})
    assert r.json() == {"status": "processed", "outcome": "subscription_canceled"}
    sub = client.get("/billing/subscription", headers=auth_headers).json()
    assert sub["plan"] == "free" and sub["status"] == "canceled"


def test_subscription_updated_sets_period_end(client, auth_headers, send_webhook):
    _activate(client, auth_headers)
    sub_id = _stripe_sub_id(client, auth_headers)
    end = int(time.time()) + 30 * 86400
    # Newer API shape: current_period_end lives on the subscription item.
    obj = {"id": sub_id, "status": "active", "cancel_at_period_end": True,
           "items": {"data": [{"current_period_end": end}]}}
    r, _ = send_webhook("customer.subscription.updated", obj)
    assert r.json()["outcome"] == "subscription_updated"
    sub = client.get("/billing/subscription", headers=auth_headers).json()
    assert sub["cancel_at_period_end"] is True
    assert sub["current_period_end"] is not None


def test_payment_failed_marks_past_due(client, auth_headers, send_webhook):
    _activate(client, auth_headers)
    sub_id = _stripe_sub_id(client, auth_headers)
    r, _ = send_webhook("invoice.payment_failed", {"object": "invoice", "subscription": sub_id})
    assert r.json()["outcome"] == "subscription_past_due"
    assert client.get("/users/me/premium", headers=auth_headers).status_code == 402


def test_replayed_event_is_not_applied_twice(client, auth_headers, send_webhook):
    _activate(client, auth_headers)
    sub_id = _stripe_sub_id(client, auth_headers)

    r1, _ = send_webhook("invoice.payment_failed", {"subscription": sub_id}, event_id="evt_same")
    assert r1.json()["status"] == "processed"

    # User pays; the subscription recovers via a different event.
    r2, _ = send_webhook("customer.subscription.updated", {"id": sub_id, "status": "active"})
    assert r2.json()["status"] == "processed"

    # Stripe re-delivers the old failure event. It must not flip the user back to past_due.
    r3, _ = send_webhook("invoice.payment_failed", {"subscription": sub_id}, event_id="evt_same")
    assert r3.status_code == 200
    assert r3.json()["status"] == "duplicate"
    assert client.get("/billing/subscription", headers=auth_headers).json()["status"] == "active"


def test_unknown_subscription_is_recorded_not_errored(client, send_webhook):
    r, _ = send_webhook("customer.subscription.deleted", {"id": "sub_does_not_exist"})
    assert r.status_code == 200
    assert r.json()["outcome"] == "ignored:unknown_subscription"


def test_stripe_provider_verifies_real_stripe_signature_format():
    """The real Stripe SDK accepts signatures from our signer (same scheme), with no network."""
    settings = get_settings().model_copy(
        update={"stripe_secret_key": "sk_test_dummy", "stripe_webhook_secret": "whsec_test_abc"}
    )
    provider = StripeProvider(settings)
    payload = json.dumps({"id": "evt_1", "object": "event", "type": "ping", "data": {"object": {}}}).encode()

    event = provider.construct_event(payload, sign_payload(payload, "whsec_test_abc"))
    assert event["id"] == "evt_1"

    with pytest.raises(SignatureError):
        provider.construct_event(payload, sign_payload(payload, "whsec_other"))
