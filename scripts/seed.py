"""Load sample users and subscriptions. Safe to run repeatedly (skips existing users).

Usage: python -m scripts.seed
"""
from datetime import timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal, init_db
from app.models import Subscription, User
from app.models._time import utcnow

DEMO_PASSWORD = "demo-password-123"

# email, plan, status, days until period end, cancel_at_period_end
SAMPLE_USERS = [
    ("demo@example.com", "pro", "active", 30, False),
    ("alice@example.com", "basic", "trialing", 14, False),
    ("bob@example.com", "pro", "past_due", 3, False),
    ("carol@example.com", "basic", "active", 20, True),
    ("dave@example.com", "free", "canceled", None, False),
    ("erin@example.com", "free", "active", None, False),
]


def seed(verbose: bool = True) -> int:
    init_db()
    created = 0
    pw_hash = hash_password(DEMO_PASSWORD)  # hash once; all demo users share it
    with SessionLocal() as db:
        for i, (email, plan, status, days, cancel) in enumerate(SAMPLE_USERS, start=1):
            if db.scalar(select(User).where(User.email == email)):
                continue
            paid = plan != "free"
            user = User(
                email=email,
                hashed_password=pw_hash,
                stripe_customer_id=f"cus_seed_{i:04d}" if paid else None,
            )
            user.subscription = Subscription(
                plan=plan,
                status=status,
                stripe_subscription_id=f"sub_seed_{i:04d}" if paid else None,
                current_period_end=utcnow() + timedelta(days=days) if days else None,
                cancel_at_period_end=cancel,
            )
            db.add(user)
            created += 1
        db.commit()
    if verbose:
        print(f"Seeded {created} new user(s). All demo users use password: {DEMO_PASSWORD}")
        for email, plan, status, *_ in SAMPLE_USERS:
            print(f"  {email:<20} {plan:<6} {status}")
    return created


if __name__ == "__main__":
    seed()
