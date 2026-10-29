"""UTC normalization for timestamps at application boundaries."""

from datetime import datetime, timezone


def normalize_to_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        # Naive timestamps are treated as UTC.
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
