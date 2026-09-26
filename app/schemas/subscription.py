from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    is_entitled: bool


class CheckoutIn(BaseModel):
    plan: Literal["basic", "pro"]


class CheckoutOut(BaseModel):
    session_id: str
    checkout_url: str
    provider: str
