from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite does not store tz info)."""
    return datetime.now(UTC).replace(tzinfo=None)


def from_epoch(ts: int | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), UTC).replace(tzinfo=None)
