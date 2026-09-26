from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._time import utcnow

PAID_PLANS = {"basic", "pro"}
ENTITLED_STATUSES = {"active", "trialing"}


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")  # free | basic | pro
    # active | trialing | past_due | canceled | incomplete | unpaid
    status: Mapped[str] = mapped_column(String(32), default="active")
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="subscription")  # noqa: F821

    @property
    def is_entitled(self) -> bool:
        return self.plan in PAID_PLANS and self.status in ENTITLED_STATUSES
