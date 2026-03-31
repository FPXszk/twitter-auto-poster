"""Posting window check for the hourly JST 7:00–1:00 run window."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def should_run_in_posting_window(now: datetime) -> bool:
    """Return True if *now* falls inside the JST 7:00–1:00 hourly run window.

    Raises ValueError if *now* is a naive datetime.
    """
    if now.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    jst_hour = now.astimezone(JST).hour
    return jst_hour >= 7 or jst_hour <= 1
