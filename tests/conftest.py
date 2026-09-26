"""Test setup: isolated SQLite file, demo-mode payments, no external services or keys.

Env vars are set before the app is imported, and take precedence over any local .env.
"""
import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="saas-tests-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmpdir}/test.db",
    SEED_ON_STARTUP="false",
    JWT_SECRET="test-secret-not-for-production-use-000",
    STRIPE_SECRET_KEY="",
    STRIPE_WEBHOOK_SECRET="",
    RATE_LIMIT_ENABLED="true",
    RATE_LIMIT_AUTH="5/minute",
    ENVIRONMENT="test",
)

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.db import Base, engine, init_db  # noqa: E402
from app.services.payments import get_payment_provider  # noqa: E402
from app.services.payments.mock_provider import build_event, sign_payload  # noqa: E402
from main import app  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _fresh_state():
    init_db()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    limiter.reset()
    get_payment_provider().pending.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def register(client):
    def _register(email: str = "user@example.com", password: str = PASSWORD):
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        return r.json()

    return _register


@pytest.fixture
def tokens(client, register):
    register()
    r = client.post("/auth/login", json={"email": "user@example.com", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def auth_headers(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def send_webhook(client):
    """Post a correctly signed event. Returns (response, event)."""

    def _send(event_type: str, obj: dict, event_id: str | None = None, *, secret=None, timestamp=None):
        event = build_event(event_type, obj, event_id)
        payload = json.dumps(event).encode()
        sig = sign_payload(payload, secret or get_settings().effective_webhook_secret, timestamp)
        r = client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": sig})
        return r, event

    return _send
