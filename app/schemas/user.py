from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.subscription import SubscriptionOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    created_at: datetime
    subscription: SubscriptionOut | None = None
