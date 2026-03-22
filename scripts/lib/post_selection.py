from __future__ import annotations

from typing import Any, Mapping, Sequence


def candidate_sort_key(item: Mapping[str, Any]) -> tuple[float, int, int, int, str]:
    return (
        float(item.get("score", 0)),
        int(item.get("views", 0)),
        int(item.get("retweets", 0)),
        int(item.get("likes", 0)),
        str(item.get("created_at", "")),
    )


def sort_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in sorted(candidates, key=candidate_sort_key, reverse=True)]


def normalize_rotation_index(raw_value: str | int | None, total_sources: int) -> int:
    if total_sources <= 0:
        return 0
    try:
        return int(raw_value or 0) % total_sources
    except (TypeError, ValueError):
        return 0


def select_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    source_order: Sequence[str],
    max_candidates: int,
    selection_mode: str,
    rotation_index: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered_candidates = sort_candidates(candidates)
    limit = max(max_candidates, 1)

    if selection_mode != "round_robin" or not source_order:
        return ordered_candidates[:limit], {
            "selection_mode": "score",
            "source_order": list(source_order),
            "start_index": 0,
            "selected_source_index": None,
            "next_index": 0,
        }

    normalized_source_order = [item for item in source_order if item]
    start_index = normalize_rotation_index(rotation_index, len(normalized_source_order))
    candidates_by_source: dict[str, list[dict[str, Any]]] = {}
    for candidate in ordered_candidates:
        source_id = str(candidate.get("source_id") or "")
        if not source_id:
            continue
        candidates_by_source.setdefault(source_id, []).append(candidate)

    for offset in range(len(normalized_source_order)):
        source_index = (start_index + offset) % len(normalized_source_order)
        source_id = normalized_source_order[source_index]
        source_candidates = candidates_by_source.get(source_id) or []
        if source_candidates:
            return source_candidates[:limit], {
                "selection_mode": "round_robin",
                "source_order": normalized_source_order,
                "start_index": start_index,
                "selected_source_index": source_index,
                "next_index": (source_index + 1) % len(normalized_source_order),
            }

    return [], {
        "selection_mode": "round_robin",
        "source_order": normalized_source_order,
        "start_index": start_index,
        "selected_source_index": None,
        "next_index": start_index,
    }
