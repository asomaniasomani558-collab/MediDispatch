"""Shared helpers for models."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp.

    Stored naive so SQLite (dev/test) and PostgreSQL behave identically; every
    timestamp in the system is UTC (Ghana is UTC+0 year-round anyway).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
