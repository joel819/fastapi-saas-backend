from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._time import utcnow


class WebhookEvent(Base):
    """Processed Stripe events. The primary key on the event id makes processing idempotent."""

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(128))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
