from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC clock (matches the SQLite `DateTime` columns) without the
    deprecated `datetime.utcnow()` call."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
