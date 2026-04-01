from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")


def _jst_hour_slot(dt: datetime) -> str:
    """Return the JST hour slot string for *dt* (e.g. '2026-04-01T10')."""
    jst_dt = dt.astimezone(JST)
    return jst_dt.strftime("%Y-%m-%dT%H")


def check_hourly_guard(
    state_path: Path,
    now: datetime,
) -> dict[str, Any]:
    """Check whether a live post is allowed in the current JST hour slot.

    Returns a dict with at least ``allowed`` (bool), ``jst_hour`` (str),
    and ``reason`` (str) when blocked.
    """
    current_slot = _jst_hour_slot(now)
    base: dict[str, Any] = {"jst_hour": current_slot}

    if not state_path.exists():
        return {**base, "allowed": True}

    try:
        raw = state_path.read_text(encoding="utf-8")
        state = json.loads(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("hourly guard state unreadable: %s", exc)
        return {
            **base,
            "allowed": False,
            "reason": "state_unreadable",
            "error": str(exc),
        }

    if not isinstance(state, dict):
        return {
            **base,
            "allowed": False,
            "reason": "state_unreadable",
            "error": "state is not a JSON object",
        }

    last_slot = str(state.get("jst_hour") or "")
    if last_slot == current_slot:
        return {
            **base,
            "allowed": False,
            "reason": "already_posted_this_hour",
            "last_posted_at": str(state.get("posted_at") or ""),
        }

    return {**base, "allowed": True}


def record_hourly_post(state_path: Path, now: datetime) -> None:
    """Record that a live post was made in the current JST hour slot.

    Only call this for actual live posts (not dry-run).
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "jst_hour": _jst_hour_slot(now),
        "posted_at": now.astimezone(JST).isoformat(),
    }
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
