from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from post_feedback import extract_posted_tweet_id

logger = logging.getLogger(__name__)


def classify_candidate_result(payload: Mapping[str, Any]) -> str:
    """Classify the final result_mode, distinguishing genuine no-candidate from summary exhaustion."""
    current = str(payload.get("result_mode") or "unknown")
    if current != "candidate_ready":
        return current

    selected_candidates = payload.get("selected_candidates") or []
    post_candidates = payload.get("post_candidates") or []
    diagnostics = payload.get("diagnostics") or {}
    summary_attempts = diagnostics.get("summary_attempts") or []
    exhausted_by_generation = bool(summary_attempts) and all(
        (not a.get("ok")) and a.get("stage") != "evaluator"
        for a in summary_attempts
    )

    if len(selected_candidates) > 0 and len(post_candidates) == 0 and exhausted_by_generation:
        return "summary_exhausted"

    if payload.get("selected") is None:
        return "no_candidate"

    return current


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


def load_post_result_payload(
    post_result_file: str | None,
) -> dict[str, Any] | None:
    """Load and parse a post result JSON file.

    Returns the parsed dict on success, None on any error.
    """
    if not post_result_file:
        return None
    path = Path(post_result_file)
    if not path.is_file():
        logger.debug("post result file not found: %s", post_result_file)
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("failed to read post result file %s: %s", post_result_file, exc)
        return None
    if not isinstance(payload, Mapping):
        return None
    return dict(payload)


def _render_posted_tweet_info(post_result: Mapping[str, Any] | None) -> list[str]:
    """Render posted tweet ID and URL lines from a post result payload."""
    if post_result is None:
        return []
    tweet_id = extract_posted_tweet_id(post_result)
    if not tweet_id:
        return []
    data = post_result.get("data") or {}
    url = ""
    if isinstance(data, Mapping):
        url = str(data.get("url") or "")
    lines: list[str] = []
    if url:
        lines.append(f"- Posted tweet: [`{tweet_id}`]({url})")
    else:
        lines.append(f"- Posted tweet ID: `{tweet_id}`")
    return lines


def _render_hourly_guard(guard: Mapping[str, Any]) -> list[str]:
    """Render hourly post guard skip information."""
    lines = ["", "### Hourly guard", ""]
    reason = str(guard.get("reason") or "unknown")
    jst_hour = str(guard.get("jst_hour") or "")
    lines.append(f"- Guard result: `skipped`")
    lines.append(f"- Reason: `{reason}`")
    if jst_hour:
        lines.append(f"- JST hour slot: `{jst_hour}`")
    last_posted = str(guard.get("last_posted_at") or "")
    if last_posted:
        lines.append(f"- Last posted at: `{last_posted}`")
    error = str(guard.get("error") or "")
    if error:
        lines.append(f"- Error: `{error}`")
    return lines


def _render_reply_summary(reply_result: Mapping[str, Any] | None) -> list[str]:
    if reply_result is None:
        return []
    lines: list[str] = ["", "### Auto reply summary", ""]
    reply_status = str(reply_result.get("status") or "unknown")
    lines.append(f"- Reply status: `{reply_status}`")
    if reply_status == "disabled":
        lines.append("- Auto reply is disabled for this category.")
    elif reply_status == "no_history":
        lines.append("- No feedback history available for reply checks.")
    else:
        lines.extend(
            [
                f"- Tweets checked: `{reply_result.get('checked_tweets', 0)}`",
                f"- Replies found: `{reply_result.get('total_replies_found', 0)}`",
                f"- Replies sent: `{reply_result.get('replies_sent', 0)}`",
                f"- Already replied (skipped): `{reply_result.get('replies_skipped_already_replied', 0)}`",
            ]
        )
        reply_errors = reply_result.get("errors") or []
        if reply_errors:
            lines.append(f"- Reply errors: `{len(reply_errors)}`")
            for err in reply_errors[:5]:
                lines.append(f"  - `{err.get('stage', 'unknown')}`: {err.get('error', '')}")
        if reply_result.get("error"):
            lines.append(f"- Error: `{reply_result.get('error')}`")
    return lines


def render_run_summary(
    *,
    category: str,
    posting_window: str,
    posting_window_jst: str,
    payload: Mapping[str, Any] | None,
    candidate_error: str | None = None,
    reply_result: Mapping[str, Any] | None = None,
    hourly_guard: Mapping[str, Any] | None = None,
) -> list[str]:
    lines = [f"## {category} run summary", ""]
    lines.append(f"- Posting window allowed: `{posting_window}`")
    lines.append(f"- Current JST: `{posting_window_jst}`")

    if posting_window != "true":
        lines.extend(["", "- Skipped because current JST is outside the 07:00-01:00 hourly posting window."])
        lines.extend(_render_reply_summary(reply_result))
        return lines

    if hourly_guard and not hourly_guard.get("allowed", True):
        lines.extend(_render_hourly_guard(hourly_guard))
        lines.extend(_render_reply_summary(reply_result))
        return lines

    if candidate_error:
        lines.append(f"- Candidate payload error: `{candidate_error}`")
        lines.extend(_render_reply_summary(reply_result))
        return lines

    if payload is None:
        lines.append("candidate file was not created.")
        lines.extend(_render_reply_summary(reply_result))
        return lines

    result_mode = classify_candidate_result(payload)
    collection = payload.get("collection") or {}
    rotation = payload.get("rotation") or {}
    diagnostics = payload.get("diagnostics") or {}
    summary_attempts = diagnostics.get("summary_attempts") or []
    author_lookup = diagnostics.get("author_lookup") or {}
    feedback_refresh = diagnostics.get("feedback_refresh") or {}
    feedback_boosts = diagnostics.get("feedback_boosts") or {}
    summary_evaluator = diagnostics.get("summary_evaluator") or {}
    post_candidates = payload.get("post_candidates") or []
    alerts = payload.get("alerts") or []

    lines.extend(
        [
            f"- Requested mode: `{payload.get('requested_mode', 'unknown')}`",
            f"- Result mode: `{result_mode}`",
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
    if feedback_refresh:
        lines.extend(
            [
                f"- Feedback refresh: `{feedback_refresh.get('status', 'unknown')}`",
                f"- Feedback refreshed entries: `{feedback_refresh.get('refreshed_entries', 0)}`",
                f"- Feedback refresh failures: `{feedback_refresh.get('failed_entries', 0)}`",
                f"- Feedback-enabled sources: `{len(feedback_boosts)}`",
            ]
        )
    if summary_evaluator:
        lines.extend(
            [
                f"- Summary evaluator accepted: `{summary_evaluator.get('accepted', 0)}`",
                f"- Summary evaluator rejected: `{summary_evaluator.get('rejected', 0)}`",
            ]
        )

    selected = payload.get("selected")
    if not selected and result_mode != "summary_exhausted":
        lines.append("no eligible candidate was selected.")
    else:
        if selected:
            summary_generation = selected.get("summary_generation") or payload.get("summary_generation") or {}
            score_breakdown = selected.get("score_breakdown") or {}
            formatted_breakdown = ", ".join(f"{key}={value}" for key, value in score_breakdown.items()) or "n/a"
            author = selected.get("screen_name") or selected.get("author_name") or "unknown"
            lines.extend(
                [
                    f"- Selected source ID: `{selected.get('source_id', 'unknown')}`",
                    f"- Selected source type: `{selected.get('source_type', 'unknown')}`",
                    f"- Selected tweet ID: `{selected.get('id', '')}`",
                ]
            )
            source_url = str(selected.get("source_url") or "")
            if source_url:
                lines.append(f"- Source tweet: [{source_url}]({source_url})")
            lines.extend(
                [
                    f"- Author: `{author}`",
                    f"- Score: `{selected.get('score', 0)}`",
                    f"- Likes / Retweets / Replies / Views: `{selected.get('likes', 0)} / {selected.get('retweets', 0)} / {selected.get('replies', 0)} / {selected.get('views', 0)}`",
                    f"- Has image: `{selected.get('has_image', False)}`",
                    f"- Media classification: `{selected.get('media_classification_source', '')}`",
                    f"- Score breakdown: `{formatted_breakdown}`",
                    f"- Feedback boost: `{selected.get('feedback_boost', 0)}`",
                    f"- Summary provider: `{summary_generation.get('provider', '')}`",
                    f"- Summary model: `{summary_generation.get('model', '')}`",
                    f"- Summary: {payload.get('post_text', '')}",
                    "",
                    "### Source snippet",
                    "",
                    f"> {selected.get('text', '')}",
                ]
            )
            summary_validation = selected.get("summary_validation") or {}
            if summary_validation:
                lines.append(f"- Summary validation: `{'ok' if summary_validation.get('ok') else 'failed'}`")
                if summary_validation.get("reasons"):
                    lines.append(f"- Summary validation reasons: `{', '.join(summary_validation.get('reasons') or [])}`")
            usage_lines = summary_generation.get("usage_lines") or []
            if usage_lines:
                lines.extend(["", "### Copilot usage hints", ""])
                lines.extend(f"- `{item}`" for item in usage_lines)
            if summary_generation.get("stderr"):
                lines.extend(["", "### Copilot stderr", "", "```text", str(summary_generation.get("stderr")), "```"])

    if alerts:
        lines.extend(["", "### Alerts", ""])
        for item in alerts:
            if not isinstance(item, Mapping):
                continue
            level = str(item.get("level") or "info")
            code = str(item.get("code") or "unknown")
            message = str(item.get("message") or "")
            tweet_id = str(item.get("tweet_id") or "")
            suffix = f" ({tweet_id})" if tweet_id else ""
            lines.append(f"- `{level}` `{code}`{suffix}: {message}".rstrip())

    if summary_attempts:
        lines.extend(["", "### Summary attempts", ""])
        for item in summary_attempts:
            status = "ok" if item.get("ok") else "failed"
            detail = item.get("error") or item.get("provider") or ""
            lines.append(f"- `{item.get('tweet_id', '')}`: `{status}` {detail}".rstrip())
        has_refusal = any("llm_refusal" in str(a.get("error") or "") for a in summary_attempts)
        if has_refusal:
            lines.extend(["", "⚠️ LLM refusal detected — summary contained safety/refusal boilerplate and was rejected."])

    skipped = payload.get("skipped_candidates") or []
    if skipped:
        lines.extend(["", f"- Skipped candidates logged: `{len(skipped)}`"])
    if payload.get("post_error"):
        lines.append(f"- Error: `{payload.get('post_error')}`")
    if result_mode == "post_failed":
        lines.extend(
            [
                "",
                "### Post failure alert",
                "",
                f"- Post candidates exhausted: `{len(post_candidates)}`",
                f"- Last publish error: `{payload.get('post_error') or 'unknown'}`",
            ]
        )
    if result_mode == "summary_exhausted":
        failed_count = sum(
            1
            for a in summary_attempts
            if (not a.get("ok")) and a.get("stage") != "evaluator"
        )
        lines.extend(
            [
                "",
                "### Summary exhausted alert",
                "",
                "⚠️ All selected candidates failed during summary generation.",
                f"- Selected candidates: `{len(payload.get('selected_candidates') or [])}`",
                f"- Failed summary attempts: `{failed_count}`",
                f"- Post candidates produced: `{len(post_candidates)}`",
            ]
        )
        if payload.get("post_error"):
            lines.append(f"- Post error: `{payload.get('post_error')}`")
    if payload.get("post_result_file"):
        post_result = load_post_result_payload(str(payload["post_result_file"]))
        lines.extend(_render_posted_tweet_info(post_result))
        lines.extend(["", f"- Post result file: `{payload.get('post_result_file')}`"])

    lines.extend(_render_reply_summary(reply_result))

    return lines
