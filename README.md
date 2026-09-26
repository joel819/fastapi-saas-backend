# fastapi-saas-backend

A FastAPI SaaS backend with JWT auth, subscriptions, verified and idempotent Stripe webhooks, and rate limiting. It runs locally for free.

## What it does

- **Auth:** register, login, refresh and logout. Access tokens last 15 minutes. Refresh tokens rotate on every use, and replaying an old one revokes that login's whole session.
- **Users and subscriptions:** stored in SQLite through SQLAlchemy 2. Every user gets a `free` plan, and `/users/me/premium` shows how to gate an endpoint behind a paid plan.
- **Billing:** checkout sessions through Stripe (test mode) or a built-in mock provider. `Idempotency-Key` headers make checkout retries safe.
- **Webhooks:** `POST /webhooks/stripe` checks the signature against the raw request body, rejects stale timestamps, and processes each event id once. A replayed event returns `200 duplicate` and changes nothing.
- **Rate limiting:** limits apply per user for authenticated requests and per IP for anonymous ones. Auth routes are capped at 5 per minute by default.
- **Tests:** 41 pytest tests that need no API keys and no network access.

## Quickstart

With Docker:

```bash
git clone https://github.com/joel819/fastapi-saas-backend.git && cd fastapi-saas-backend
docker compose up
```

Without Docker (Python 3.11+):

```bash
git clone https://github.com/joel819/fastapi-saas-backend.git && cd fastapi-saas-backend
pip install -r requirements.txt
uvicorn main:app
```

Open http://localhost:8000/docs. Sample users are seeded on startup, and all of them use the password `demo-password-123`:

| Email | Plan | Status |
|---|---|---|
| demo@example.com | pro | active |
| alice@example.com | basic | trialing |
| bob@example.com | pro | past_due |
| carol@example.com | basic | active (cancels at period end) |
| dave@example.com | free | canceled |
| erin@example.com | free | active |

Run the tests with `pytest`.

## Try the full payment flow (demo mode)

```bash
# 1. Log in as a free user
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"erin@example.com","password":"demo-password-123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Premium is blocked (402)
curl localhost:8000/users/me/premium -H "Authorization: Bearer $TOKEN"

# 3. Start a checkout, then open the returned checkout_url to "pay"
curl -X POST localhost:8000/billing/checkout -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -H 'Idempotency-Key: my-key-1' -d '{"plan":"pro"}'

# 4. Premium now works
curl localhost:8000/users/me/premium -H "Authorization: Bearer $TOKEN"

# 5. Send a signed webhook twice: the first is processed, the replay is ignored
python -m scripts.send_test_webhook --replay
```

## Architecture

```
main.py                    uvicorn entrypoint
app/
  config.py                pydantic-settings; demo_mode = no STRIPE_SECRET_KEY
  db.py                    engine, session, get_db dependency
  factory.py               app assembly, middleware, startup (create tables + seed)
  models/                  User, Subscription, RefreshToken, WebhookEvent, IdempotencyKey
  schemas/                 request/response models
  core/
    security.py            bcrypt, JWT encode/decode (access vs refresh type check)
    deps.py                get_current_user, require_active_subscription
    rate_limit.py          slowapi limiter, per-user/per-IP key
  services/
    auth_service.py        register, login, refresh rotation + reuse detection, logout
    subscription_service.py  event -> subscription state, idempotent processing
    payments/              PaymentProvider protocol
      stripe_provider.py   real Stripe (test keys)
      mock_provider.py     demo provider, same signature scheme as Stripe
  routers/                 health, auth, users, billing, webhooks
scripts/
  seed.py                  sample data (idempotent)
  send_test_webhook.py     sign and send a webhook to a running server
tests/                     pytest suite, isolated temp SQLite per run
```

**How the pieces fit:**

- Routers stay thin. The business logic lives in `services/`, and routers only translate service errors into HTTP responses.
- The payment provider is chosen once, by `get_payment_provider()`. Everything else talks to the `PaymentProvider` protocol, so swapping mock for Stripe changes no other code.
- Webhook idempotency works because `webhook_events.id` is the Stripe event id and serves as the primary key. The state change and the event record commit in one transaction. If the transaction fails, nothing is recorded and Stripe retries. If two deliveries race, the database's unique constraint picks one winner.
- Checkout idempotency stores the first response under `(user, endpoint, key)`. The same key with a different request body returns `409`. With real Stripe, the key is also passed through to Stripe.
- Every refresh token has a row in the database, grouped by login "family". Rotating a token marks the old one revoked. Presenting a revoked token revokes the whole family.
- Tables are created with `create_all()` on startup. For a production schema, add Alembic migrations.
- Rate-limit counters live in memory, so they reset on restart and aren't shared between workers. For more than one worker, point `storage_uri` in `core/rate_limit.py` at Redis.

## Demo mode

**It runs free, with no API keys.** When `STRIPE_SECRET_KEY` is unset, the app uses the mock payment provider:

- Checkout returns a local URL, and opening it simulates a successful payment.
- Webhooks are signed and verified with the same `t=…,v1=HMAC-SHA256` scheme Stripe uses, against a built-in demo secret, so the verification code runs for real.
- `GET /health` reports `"demo_mode": true`.

To use real Stripe test mode, set `STRIPE_SECRET_KEY=sk_test_...`, `STRIPE_WEBHOOK_SECRET` and the two `STRIPE_PRICE_*` ids in `.env`, then forward events with the free Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Only use test-mode keys. For production, set `ENVIRONMENT=production` and a strong `JWT_SECRET`. The app refuses to start with the default secret.

## Configuration

Every variable is listed with its default in [`.env.example`](.env.example). Copy it to `.env` to override the defaults.
