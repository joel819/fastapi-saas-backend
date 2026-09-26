"""Application settings, loaded from environment variables and an optional .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Used only when no Stripe key is configured (demo mode). Never use in production.
DEMO_WEBHOOK_SECRET = "whsec_demo_local_only_not_a_real_secret"
INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "fastapi-saas-backend"
    environment: str = "development"  # development | production
    database_url: str = "sqlite:///./data/app.db"
    seed_on_startup: bool = True

    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_basic: str = ""
    stripe_price_pro: str = ""
    public_base_url: str = "http://localhost:8000"

    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"
    rate_limit_auth: str = "5/minute"
    rate_limit_billing: str = "10/minute"

    @property
    def demo_mode(self) -> bool:
        """True when no Stripe key is set: payments go through the mock provider."""
        return not self.stripe_secret_key

    @property
    def effective_webhook_secret(self) -> str:
        if self.demo_mode:
            return self.stripe_webhook_secret or DEMO_WEBHOOK_SECRET
        return self.stripe_webhook_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
