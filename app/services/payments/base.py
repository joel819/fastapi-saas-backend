from dataclasses import dataclass
from typing import Any, Protocol

from app.models import User


class SignatureError(Exception):
    """Webhook signature missing, malformed, wrong or too old."""


class PaymentConfigError(Exception):
    """Provider is not configured for the requested operation."""


@dataclass
class CheckoutSession:
    id: str
    url: str


class PaymentProvider(Protocol):
    name: str

    def create_checkout_session(
        self, *, user: User, plan: str, idempotency_key: str | None
    ) -> CheckoutSession: ...

    def construct_event(self, payload: bytes, sig_header: str) -> dict[str, Any]:
        """Verify the signature and return the parsed event. Raises SignatureError."""
        ...
