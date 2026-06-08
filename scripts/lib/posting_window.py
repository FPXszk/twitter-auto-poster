"""Posting window helpers for JST-based workflow schedules."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Iterable

JST = ZoneInfo("Asia/Tokyo")


def should_run_in_posting_window(
    now: datetime,
    *,
    allowed_times: Iterable[tuple[int, int]] | None = None,
) -> bool:
    """Return True if *now* falls inside the configured JST posting window.

    Raises ValueError if *now* is a naive datetime.
    """
    if now.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")

    jst_now = now.astimezone(JST)
    if allowed_times is not None:
        for hour, minute in allowed_times:
            if jst_now.hour == hour and jst_now.minute >= minute:
                return True
        return False

    jst_hour = jst_now.hour
    return jst_hour >= 7 or jst_hour <= 1
