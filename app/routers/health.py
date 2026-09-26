from fastapi import APIRouter, Request

from app.config import get_settings
from app.core.rate_limit import limiter
from app.services.payments import get_payment_provider

router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.exempt
def health(request: Request) -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "demo_mode": s.demo_mode,
        "payments_provider": get_payment_provider().name,
    }
