from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from post_scoring import calculate_score as _base_calculate_score
from post_scoring import normalize_score_weights as _base_normalize_score_weights

logger = logging.getLogger(__name__)

DEFAULT_TIKTOK_SCORE_WEIGHTS: dict[str, float] = {
    "likes": 1.0,
    "retweets": 1.0,
    "replies": 1.0,
    "views": 1.0,
    "velocity": 0.0,
    "freshness": 0.0,
    "image_bonus": 0.0,
    "author_virality": 0.0,
}


def normalize_tiktok_score_weights(
    raw_weights: Mapping[str, Any] | None,
) -> dict[str, float]:
    """Fill in TikTok score weight defaults, delegating to post_scoring."""
    return _base_normalize_score_weights(raw_weights)


def extract_candidate_metrics(item: Mapping[str, Any]) -> dict[str, int]:
    """Extract scoring metrics from a TikTok video item."""
    metrics = item.get("metrics") or {}
    return {
        "likes": int(metrics.get("likes") or item.get("likes") or 0),
        "retweets": int(metrics.get("retweets") or item.get("retweets") or 0),
        "replies": int(metrics.get("replies") or item.get("replies") or 0),
        "views": int(metrics.get("views") or item.get("views") or 0),
    }


def calculate_tiktok_score(
    metrics: Mapping[str, int],
    raw_weights: Mapping[str, Any] | None = None,
    *,
    created_at: str = "",
    max_age_hours: float | None = None,
    source_boost: float = 0.0,
    now: datetime | None = None,
) -> tuple[float, dict[str, float]]:
    """Calculate a TikTok video score, reusing post_scoring.calculate_score internally."""
    return _base_calculate_score(
        metrics,
        raw_weights,
        created_at=created_at,
        max_age_hours=max_age_hours,
        source_boost=source_boost,
        now=now,
    )


# Backward-compatible alias for tiktok_pipeline.py
calculate_score = calculate_tiktok_score
normalize_score_weights = normalize_tiktok_score_weights
