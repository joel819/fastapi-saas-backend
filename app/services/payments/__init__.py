from functools import lru_cache

from app.config import get_settings
from app.services.payments.base import (
    CheckoutSession,
    PaymentConfigError,
    PaymentProvider,
    SignatureError,
)


@lru_cache
def get_payment_provider() -> PaymentProvider:
    """Stripe when STRIPE_SECRET_KEY is set, otherwise the mock provider (demo mode)."""
    settings = get_settings()
    if settings.demo_mode:
        from app.services.payments.mock_provider import MockProvider

        return MockProvider(settings)
    from app.services.payments.stripe_provider import StripeProvider

    return StripeProvider(settings)


__all__ = [
    "CheckoutSession",
    "PaymentConfigError",
    "PaymentProvider",
    "SignatureError",
    "get_payment_provider",
]
