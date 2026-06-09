from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from post_scoring import extract_candidate_metrics

DEFAULT_HISTORY_LIMIT = 200
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_MAX_FEEDBACK_BOOST = 6.0


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_feedback_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            entries.append(dict(payload))
    return entries


def write_feedback_history(
    path: Path,
    entries: Sequence[Mapping[str, Any]],
    *,
    max_entries: int = DEFAULT_HISTORY_LIMIT,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = [dict(entry) for entry in entries][-max(max_entries, 1) :]
    lines = [json.dumps(entry, ensure_ascii=False) for entry in trimmed]
    path.write_text(("".join(f"{line}\n" for line in lines)), encoding="utf-8")


def append_feedback_history(
    path: Path,
    entry: Mapping[str, Any],
    *,
    max_entries: int = DEFAULT_HISTORY_LIMIT,
) -> int:
    entries = load_feedback_history(path)
    entries.append(dict(entry))
    write_feedback_history(path, entries, max_entries=max_entries)
    return min(len(entries), max(max_entries, 1))


def extract_posted_tweet_id(post_result_payload: Mapping[str, Any] | None) -> str:
    if not isinstance(post_result_payload, Mapping):
        return ""
    data = post_result_payload.get("data")
    if isinstance(data, Mapping):
        return str(data.get("id") or "").strip()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping):
                tweet_id = str(item.get("id") or "").strip()
                if tweet_id:
                    return tweet_id
    return ""


def build_feedback_entry(
    selected_candidate: Mapping[str, Any],
    posted_tweet_id: str,
    *,
    posted_at: str,
) -> dict[str, Any]:
    return {
        "posted_tweet_id": str(posted_tweet_id).strip(),
        "posted_at": str(posted_at).strip(),
        "source_tweet_id": str(selected_candidate.get("id") or "").strip(),
        "source_id": str(selected_candidate.get("source_id") or "").strip(),
        "source_key": str(selected_candidate.get("source_key") or "").strip(),
        "source_username": str(selected_candidate.get("source_username") or "").strip(),
        "source_type": str(selected_candidate.get("source_type") or "").strip(),
        "source_score": float(selected_candidate.get("score") or 0.0),
        "posted_text": str(selected_candidate.get("summary_text") or "").strip(),
        "normalized_post_text": " ".join(str(selected_candidate.get("summary_text") or "").split()),
        "post_metrics": dict(selected_candidate.get("post_metrics") or {}),
        "last_refreshed_at": None,
    }


def refresh_feedback_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    fetch_tweet_payload: Callable[[str], Mapping[str, Any]],
    now: datetime | None = None,
    max_refresh: int = 10,
    min_refresh_interval_hours: float = 6,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    updated_entries = [dict(entry) for entry in entries]
    summary = {
        "status": "ok",
        "history_entries": len(updated_entries),
        "refreshed_entries": 0,
        "skipped_entries": 0,
        "failed_entries": 0,
    }

    indexed_entries = sorted(
        enumerate(updated_entries),
        key=lambda item: _parse_datetime(item[1].get("posted_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    refreshed = 0
    lookback_delta = timedelta(days=max(lookback_days, 1))
    min_refresh_delta = timedelta(hours=max(min_refresh_interval_hours, 0))

    for index, entry in indexed_entries:
        posted_at = _parse_datetime(entry.get("posted_at"))
        if posted_at is None or current - posted_at > lookback_delta:
            continue
        if refreshed >= max(max_refresh, 1):
            summary["skipped_entries"] += 1
            continue

        last_refreshed_at = _parse_datetime(entry.get("last_refreshed_at"))
        if last_refreshed_at is not None and current - last_refreshed_at < min_refresh_delta:
            summary["skipped_entries"] += 1
            continue

        posted_tweet_id = str(entry.get("posted_tweet_id") or "").strip()
        if not posted_tweet_id:
            summary["failed_entries"] += 1
            continue

        try:
            payload = fetch_tweet_payload(posted_tweet_id)
        except Exception:
            summary["failed_entries"] += 1
            continue

        metrics = extract_candidate_metrics(payload)
        refreshed += 1
        summary["refreshed_entries"] += 1
        updated_entries[index]["post_metrics"] = metrics
        updated_entries[index]["last_refreshed_at"] = current.isoformat()

    return updated_entries, summary


def _calculate_quality_score(metrics: Mapping[str, Any]) -> float:
    extracted = extract_candidate_metrics(metrics)
    return (
        float(extracted.get("likes", 0))
        + (float(extracted.get("retweets", 0)) * 3.0)
        + (float(extracted.get("replies", 0)) * 4.0)
        + (float(extracted.get("views", 0)) * 0.02)
    )


def build_feedback_boost_map(
    entries: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_feedback_boost: float = DEFAULT_MAX_FEEDBACK_BOOST,
) -> dict[str, dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    grouped: dict[str, dict[str, Any]] = {}
    lookback_delta = timedelta(days=max(lookback_days, 1))

    for entry in entries:
        source_id = str(entry.get("source_id") or "").strip()
        posted_at = _parse_datetime(entry.get("posted_at"))
        metrics = entry.get("post_metrics")
        if not source_id or posted_at is None or not isinstance(metrics, Mapping):
            continue
        if current - posted_at > lookback_delta:
            continue

        age_days = max((current - posted_at).total_seconds() / 86400.0, 0.0)
        recency_weight = max(0.25, 1.0 - (age_days / max(lookback_days, 1)) * 0.75)
        quality_score = _calculate_quality_score(metrics) * recency_weight
        bucket = grouped.setdefault(
            source_id,
            {
                "quality_sum": 0.0,
                "history_count": 0,
                "last_posted_at": posted_at.isoformat(),
            },
        )
        bucket["quality_sum"] += quality_score
        bucket["history_count"] += 1
        if posted_at.isoformat() > str(bucket.get("last_posted_at") or ""):
            bucket["last_posted_at"] = posted_at.isoformat()

    feedback_boosts: dict[str, dict[str, Any]] = {}
    for source_id, bucket in grouped.items():
        history_count = int(bucket["history_count"] or 0)
        if history_count <= 0:
            continue
        average_quality = float(bucket["quality_sum"] or 0.0) / history_count
        feedback_boost = min(max_feedback_boost, round(average_quality / 250.0, 2))
        if feedback_boost <= 0:
            continue
        feedback_boosts[source_id] = {
            "feedback_boost": feedback_boost,
            "history_count": history_count,
            "average_quality": round(average_quality, 2),
            "last_posted_at": bucket.get("last_posted_at"),
        }
    return feedback_boosts


def _extract_tweet_payload(cli_payload: Mapping[str, Any], tweet_id: str) -> dict[str, Any]:
    data = cli_payload.get("data")
    items: list[Mapping[str, Any]] = []
    if isinstance(data, Mapping):
        items = [data]
    elif isinstance(data, list):
        items = [item for item in data if isinstance(item, Mapping)]
    for item in items:
        if str(item.get("id") or "").strip() == tweet_id:
            return dict(item)
    return {}


def fetch_tweet_payload(twitter_bin: str, tweet_id: str) -> dict[str, Any]:
    result = subprocess.run(
        [twitter_bin, "tweet", tweet_id, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "twitter tweet failed")
    payload = json.loads(result.stdout)
    if payload.get("ok") is not True:
        raise RuntimeError("twitter tweet response was not ok")
    extracted = _extract_tweet_payload(payload, tweet_id)
    if not extracted:
        raise RuntimeError("tweet payload did not include requested tweet id")
    return extracted


def refresh_feedback_history_file(
    history_path: Path,
    twitter_bin: str,
    *,
    max_entries: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    entries = load_feedback_history(history_path)
    updated_entries, summary = refresh_feedback_entries(
        entries,
        fetch_tweet_payload=lambda tweet_id: fetch_tweet_payload(twitter_bin, tweet_id),
    )
    write_feedback_history(history_path, updated_entries, max_entries=max_entries)
    summary["active_sources"] = len(build_feedback_boost_map(updated_entries))
    return summary
