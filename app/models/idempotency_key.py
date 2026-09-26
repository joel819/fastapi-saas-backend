from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._time import utcnow


class IdempotencyKey(Base):
    """Stores the response for a client-supplied Idempotency-Key so retries are safe."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "endpoint", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(255))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    response_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
