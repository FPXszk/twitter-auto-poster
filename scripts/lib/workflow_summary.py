from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def load_latest_candidate_payload(
    candidate_files: Sequence[Path],
) -> tuple[dict[str, Any] | None, str | None]:
    if not candidate_files:
        return None, None

    candidate_path = candidate_files[-1]
    raw = candidate_path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, f"{candidate_path.name}: candidate file is empty"

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{candidate_path.name}: candidate file contains invalid JSON ({exc})"

    if not isinstance(payload, Mapping):
        return None, f"{candidate_path.name}: candidate file did not contain a JSON object"

    return dict(payload), None


def render_run_summary(
    *,
    category: str,
    posting_window: str,
    posting_window_jst: str,
    payload: Mapping[str, Any] | None,
    candidate_error: str | None = None,
) -> list[str]:
    lines = [f"## {category} run summary", ""]
    lines.append(f"- Posting window allowed: `{posting_window}`")
    lines.append(f"- Current JST: `{posting_window_jst}`")

    if posting_window != "true":
        lines.extend(["", "- Skipped because current JST is outside the 08:00-24:00 posting window."])
        return lines

    if candidate_error:
        lines.append(f"- Candidate payload error: `{candidate_error}`")
        return lines

    if payload is None:
        lines.append("candidate file was not created.")
        return lines

    collection = payload.get("collection") or {}
    rotation = payload.get("rotation") or {}
    diagnostics = payload.get("diagnostics") or {}
    summary_attempts = diagnostics.get("summary_attempts") or []
    author_lookup = diagnostics.get("author_lookup") or {}
    post_candidates = payload.get("post_candidates") or []

    lines.extend(
        [
            f"- Requested mode: `{payload.get('requested_mode', 'unknown')}`",
            f"- Result mode: `{payload.get('result_mode', 'unknown')}`",
            f"- Selection mode: `{payload.get('selection_mode', 'score')}`",
            f"- Payload files: `{payload.get('payload_count', 0)}`",
            f"- User fetch status: `{collection.get('user', {})}`",
            f"- Search fetch status: `{collection.get('search', {})}`",
            f"- Post candidates ready: `{len(post_candidates)}`",
            f"- Summary attempts: `{len(summary_attempts)}`",
        ]
    )
    if rotation:
        lines.extend(
            [
                f"- Previous source: `{rotation.get('previous_source', '')}`",
                f"- Selected source: `{rotation.get('selected_source', '')}`",
                f"- Next source: `{rotation.get('next_source', '')}`",
                f"- Target media mode: `{rotation.get('target_media_mode', payload.get('target_media_mode', ''))}`",
                f"- Selected media mode: `{rotation.get('selected_media_mode', '')}`",
                f"- Media preference satisfied: `{rotation.get('media_preference_satisfied', False)}`",
            ]
        )
    if author_lookup:
        lines.extend(
            [
                f"- Author payload metrics: `{author_lookup.get('payload_metrics', 0)}`",
                f"- Author cache hits: `{author_lookup.get('cache_hits', 0)}`",
                f"- Author lookup success: `{author_lookup.get('lookup_success', 0)}`",
                f"- Author lookup failed: `{author_lookup.get('lookup_failed', 0)}`",
            ]
        )

    selected = payload.get("selected")
    if not selected:
        lines.append("no eligible candidate was selected.")
    else:
        summary_generation = selected.get("summary_generation") or payload.get("summary_generation") or {}
        score_breakdown = selected.get("score_breakdown") or {}
        formatted_breakdown = ", ".join(f"{key}={value}" for key, value in score_breakdown.items()) or "n/a"
        author = selected.get("screen_name") or selected.get("author_name") or "unknown"
        lines.extend(
            [
                f"- Selected source ID: `{selected.get('source_id', 'unknown')}`",
                f"- Selected source type: `{selected.get('source_type', 'unknown')}`",
                f"- Selected tweet ID: `{selected.get('id', '')}`",
                f"- Author: `{author}`",
                f"- Score: `{selected.get('score', 0)}`",
                f"- Likes / Retweets / Replies / Views: `{selected.get('likes', 0)} / {selected.get('retweets', 0)} / {selected.get('replies', 0)} / {selected.get('views', 0)}`",
                f"- Has image: `{selected.get('has_image', False)}`",
                f"- Media classification: `{selected.get('media_classification_source', '')}`",
                f"- Score breakdown: `{formatted_breakdown}`",
                f"- Summary provider: `{summary_generation.get('provider', '')}`",
                f"- Summary model: `{summary_generation.get('model', '')}`",
                f"- Summary: {payload.get('post_text', '')}",
                "",
                "### Source snippet",
                "",
                f"> {selected.get('text', '')}",
            ]
        )
        usage_lines = summary_generation.get("usage_lines") or []
        if usage_lines:
            lines.extend(["", "### Copilot usage hints", ""])
            lines.extend(f"- `{item}`" for item in usage_lines)
        if summary_generation.get("stderr"):
            lines.extend(["", "### Copilot stderr", "", "```text", str(summary_generation.get("stderr")), "```"])

    if summary_attempts:
        lines.extend(["", "### Summary attempts", ""])
        for item in summary_attempts:
            status = "ok" if item.get("ok") else "failed"
            detail = item.get("error") or item.get("provider") or ""
            lines.append(f"- `{item.get('tweet_id', '')}`: `{status}` {detail}".rstrip())

    skipped = payload.get("skipped_candidates") or []
    if skipped:
        lines.extend(["", f"- Skipped candidates logged: `{len(skipped)}`"])
    if payload.get("post_error"):
        lines.append(f"- Error: `{payload.get('post_error')}`")
    if payload.get("post_result_file"):
        lines.extend(["", f"- Post result file: `{payload.get('post_result_file')}`"])
    return lines
