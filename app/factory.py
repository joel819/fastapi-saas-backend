import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import INSECURE_DEFAULT_JWT_SECRET, get_settings
from app.core.rate_limit import limiter
from app.db import init_db
from app.routers import auth, billing, health, users, webhooks

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    if settings.seed_on_startup:
        from scripts.seed import seed

        seed(verbose=False)
    if settings.demo_mode:
        log.warning("DEMO MODE: no STRIPE_SECRET_KEY set, using the mock payment provider.")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.environment == "production" and settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
        raise RuntimeError("Set JWT_SECRET before running in production.")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="SaaS backend: JWT auth, subscriptions, Stripe webhooks, rate limiting.",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    for r in (health.router, auth.router, users.router, billing.router, webhooks.router):
        app.include_router(r)
    return app
