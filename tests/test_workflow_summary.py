from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import workflow_summary


class WorkflowSummaryTest(TestCase):
    def test_load_latest_candidate_payload_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate-buz.123.json"
            candidate_path.write_text('{"selected":{"id":"123"}}', encoding="utf-8")

            payload, error = workflow_summary.load_latest_candidate_payload([candidate_path])

        self.assertEqual(payload, {"selected": {"id": "123"}})
        self.assertIsNone(error)

    def test_load_latest_candidate_payload_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate-buz.123.json"
            candidate_path.write_text("", encoding="utf-8")

            payload, error = workflow_summary.load_latest_candidate_payload([candidate_path])

        self.assertIsNone(payload)
        self.assertIn("empty", error or "")

    def test_load_latest_candidate_payload_reports_json_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate-buz.123.json"
            candidate_path.write_text("{", encoding="utf-8")

            payload, error = workflow_summary.load_latest_candidate_payload([candidate_path])

        self.assertIsNone(payload)
        self.assertIn("invalid JSON", error or "")

    def test_render_run_summary_includes_diagnostics_and_attempts(self) -> None:
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "post",
                "result_mode": "candidate_ready",
                "selection_mode": "round_robin_account",
                "payload_count": 2,
                "collection": {"user": {}, "search": {}},
                "rotation": {"selected_source": "alpha", "next_source": "beta"},
                "selected": {
                    "id": "123",
                    "source_id": "alpha-big",
                    "source_type": "search",
                    "screen_name": "alpha",
                    "score": 10,
                    "likes": 1,
                    "retweets": 2,
                    "replies": 3,
                    "views": 4,
                    "has_image": True,
                    "media_classification_source": "payload",
                    "text": "snippet",
                },
                "post_text": "summary body",
                "post_candidates": [{"id": "123"}],
                "diagnostics": {
                    "author_lookup": {"payload_metrics": 1, "cache_hits": 2, "lookup_success": 3, "lookup_failed": 4},
                    "feedback_refresh": {"status": "ok", "refreshed_entries": 2, "failed_entries": 0},
                    "feedback_boosts": {"alpha-big": {"feedback_boost": 2.5, "history_count": 2}},
                    "summary_attempts": [{"tweet_id": "123", "ok": False, "error": "boom"}, {"tweet_id": "456", "ok": True, "provider": "copilot"}],
                    "summary_evaluator": {"accepted": 1, "rejected": 1},
                    "selected_min_age_hours": 72,
                    "eligible_min_age_hours": [72, 96, 168],
                },
                "alerts": [
                    {"level": "warning", "code": "summary_validation_failed", "message": "contains_url", "tweet_id": "789"}
                ],
            },
        )

        rendered = "\n".join(lines)
        self.assertIn("Post candidates ready", rendered)
        self.assertIn("Author cache hits", rendered)
        self.assertIn("Summary attempts", rendered)
        self.assertIn("Feedback refresh", rendered)
        self.assertIn("Feedback-enabled sources", rendered)
        self.assertIn("summary_validation_failed", rendered)
        self.assertIn("Selected min age hours", rendered)
        self.assertIn("Eligible min age hours", rendered)
        self.assertIn("123", rendered)

    def test_render_run_summary_highlights_post_failure(self) -> None:
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "post_failed",
                "selection_mode": "score",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [{"id": "123"}, {"id": "456"}],
                "post_error": "twitter post failed",
                "alerts": [],
            },
        )

        rendered = "\n".join(lines)
        self.assertIn("Post failure alert", rendered)
        self.assertIn("twitter post failed", rendered)

    def test_render_run_summary_highlights_summary_exhausted(self) -> None:
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "summary_exhausted",
                "selection_mode": "round_robin_account",
                "payload_count": 3,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [],
                "selected_candidates": [{"id": "100"}, {"id": "200"}],
                "alerts": [
                    {
                        "level": "warning",
                        "code": "summary_generation_failed",
                        "message": "copilot CLI failed: Error: Classic Personal Access Tokens (ghp_) are not supported by Copilot.",
                        "tweet_id": "100",
                    },
                    {
                        "level": "warning",
                        "code": "summary_generation_failed",
                        "message": "copilot CLI failed: Error: Classic Personal Access Tokens (ghp_) are not supported by Copilot.",
                        "tweet_id": "200",
                    },
                ],
                "diagnostics": {
                    "summary_attempts": [
                        {"tweet_id": "100", "ok": False, "error": "copilot CLI failed", "stage": "generation"},
                        {"tweet_id": "200", "ok": False, "error": "copilot CLI failed", "stage": "generation"},
                    ],
                },
                "post_error": None,
            },
        )

        rendered = "\n".join(lines)
        self.assertIn("summary_exhausted", rendered)
        self.assertIn("Summary exhausted", rendered)
        self.assertIn("summary_generation_failed", rendered)
        self.assertNotIn("no eligible candidate was selected.", rendered)

    def test_render_run_summary_no_candidate_does_not_show_exhausted_alert(self) -> None:
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "no_candidate",
                "selection_mode": "score",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [],
                "alerts": [],
                "diagnostics": {},
            },
        )

        rendered = "\n".join(lines)
        self.assertIn("no_candidate", rendered)
        self.assertNotIn("Summary exhausted", rendered)

    def test_classify_candidate_result_genuine_no_candidate(self) -> None:
        payload = {
            "result_mode": "candidate_ready",
            "selected_candidates": [],
            "post_candidates": [],
            "diagnostics": {"summary_attempts": []},
        }
        result = workflow_summary.classify_candidate_result(payload)
        self.assertEqual(result, "no_candidate")

    def test_classify_candidate_result_summary_exhausted(self) -> None:
        payload = {
            "result_mode": "candidate_ready",
            "selected_candidates": [{"id": "100"}, {"id": "200"}],
            "post_candidates": [],
            "diagnostics": {
                "summary_attempts": [
                    {"tweet_id": "100", "ok": False, "error": "copilot CLI failed", "stage": "generation"},
                    {"tweet_id": "200", "ok": False, "error": "copilot CLI failed", "stage": "generation"},
                ],
            },
        }
        result = workflow_summary.classify_candidate_result(payload)
        self.assertEqual(result, "summary_exhausted")

    def test_classify_candidate_result_candidate_ready(self) -> None:
        payload = {
            "result_mode": "candidate_ready",
            "selected": {"id": "100"},
            "selected_candidates": [{"id": "100"}],
            "post_candidates": [{"id": "100"}],
            "diagnostics": {
                "summary_attempts": [{"tweet_id": "100", "ok": True}],
            },
        }
        result = workflow_summary.classify_candidate_result(payload)
        self.assertEqual(result, "candidate_ready")

    def test_classify_candidate_result_preserves_non_candidate_ready(self) -> None:
        payload = {
            "result_mode": "posted",
            "selected_candidates": [{"id": "100"}],
            "post_candidates": [{"id": "100"}],
            "diagnostics": {"summary_attempts": []},
        }
        result = workflow_summary.classify_candidate_result(payload)
        self.assertEqual(result, "posted")

    def test_classify_candidate_result_ignores_evaluator_only_failures(self) -> None:
        payload = {
            "result_mode": "candidate_ready",
            "selected_candidates": [{"id": "100"}],
            "post_candidates": [],
            "diagnostics": {
                "summary_attempts": [
                    {"tweet_id": "100", "ok": False, "error": "contains_url", "stage": "evaluator"},
                ],
            },
        }
        result = workflow_summary.classify_candidate_result(payload)
        self.assertEqual(result, "no_candidate")

    def test_classify_candidate_result_ignores_mixed_generation_and_evaluator_failures(self) -> None:
        payload = {
            "result_mode": "candidate_ready",
            "selected_candidates": [{"id": "100"}, {"id": "200"}],
            "post_candidates": [],
            "diagnostics": {
                "summary_attempts": [
                    {"tweet_id": "100", "ok": False, "error": "copilot CLI failed", "stage": "generation"},
                    {"tweet_id": "200", "ok": False, "error": "contains_url", "stage": "evaluator"},
                ],
            },
        }
        result = workflow_summary.classify_candidate_result(payload)
        self.assertEqual(result, "no_candidate")


    def test_render_run_summary_includes_reply_result(self) -> None:
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "posted",
                "selection_mode": "round_robin_account",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [{"id": "123"}],
                "selected": {
                    "id": "123",
                    "source_id": "alpha-big",
                    "source_type": "search",
                    "screen_name": "alpha",
                    "score": 10,
                    "likes": 1,
                    "retweets": 2,
                    "replies": 3,
                    "views": 4,
                    "has_image": False,
                    "media_classification_source": "default",
                    "text": "snippet",
                },
                "post_text": "summary body",
                "alerts": [],
                "diagnostics": {},
            },
            reply_result={
                "status": "ok",
                "checked_tweets": 3,
                "total_replies_found": 5,
                "replies_sent": 2,
                "replies_skipped_already_replied": 1,
                "errors": [],
            },
        )

        rendered = "\n".join(lines)
        self.assertIn("Auto reply summary", rendered)
        self.assertIn("Tweets checked: `3`", rendered)
        self.assertIn("Replies sent: `2`", rendered)

    def test_render_run_summary_reply_disabled(self) -> None:
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload=None,
            reply_result={"status": "disabled"},
        )
        rendered = "\n".join(lines)
        self.assertIn("disabled", rendered)

    def test_render_run_summary_shows_posted_tweet_id_and_url(self) -> None:
        """Successful post must surface the posted tweet ID and URL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            post_result_path = Path(temp_dir) / "post-buz.json"
            post_result_path.write_text(
                '{"ok":true,"data":{"id":"2038439962035556640",'
                '"url":"https://x.com/i/status/2038439962035556640",'
                '"success":true}}',
                encoding="utf-8",
            )
            lines = workflow_summary.render_run_summary(
                category="buz",
                posting_window="true",
                posting_window_jst="2026-03-28T10:00:00+09:00",
                payload={
                    "requested_mode": "live",
                    "result_mode": "posted",
                    "selection_mode": "round_robin_account",
                    "payload_count": 1,
                    "collection": {"user": {}, "search": {}},
                    "post_candidates": [{"id": "123"}],
                    "selected": {
                        "id": "123",
                        "source_id": "alpha-big",
                        "source_type": "search",
                        "screen_name": "alpha",
                        "score": 10,
                        "likes": 1, "retweets": 2, "replies": 3, "views": 4,
                        "has_image": False,
                        "media_classification_source": "default",
                        "text": "snippet",
                    },
                    "post_text": "summary body",
                    "post_result_file": str(post_result_path),
                    "alerts": [],
                    "diagnostics": {},
                },
            )

        rendered = "\n".join(lines)
        self.assertIn("2038439962035556640", rendered)
        self.assertIn("https://x.com/i/status/2038439962035556640", rendered)
        self.assertIn("Posted tweet", rendered)

    def test_render_run_summary_missing_post_result_file_no_crash(self) -> None:
        """Missing post result file must not crash the summary."""
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "posted",
                "selection_mode": "score",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [{"id": "123"}],
                "selected": {
                    "id": "123",
                    "source_id": "alpha-big",
                    "source_type": "search",
                    "screen_name": "alpha",
                    "score": 10,
                    "likes": 1, "retweets": 2, "replies": 3, "views": 4,
                    "has_image": False,
                    "media_classification_source": "default",
                    "text": "snippet",
                },
                "post_text": "summary body",
                "post_result_file": "/nonexistent/path/post-buz.json",
                "alerts": [],
                "diagnostics": {},
            },
        )
        rendered = "\n".join(lines)
        # Must not crash, and should still show the post_result_file debug line
        self.assertIn("Post result file", rendered)
        # Must not contain "Posted tweet" since we couldn't read the file
        self.assertNotIn("Posted tweet", rendered)

    def test_render_run_summary_invalid_post_result_json_no_crash(self) -> None:
        """Corrupt post result file must not crash the summary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            post_result_path = Path(temp_dir) / "post-buz.json"
            post_result_path.write_text("{broken", encoding="utf-8")
            lines = workflow_summary.render_run_summary(
                category="buz",
                posting_window="true",
                posting_window_jst="2026-03-28T10:00:00+09:00",
                payload={
                    "requested_mode": "live",
                    "result_mode": "posted",
                    "selection_mode": "score",
                    "payload_count": 1,
                    "collection": {"user": {}, "search": {}},
                    "post_candidates": [{"id": "123"}],
                    "selected": {
                        "id": "123",
                        "source_id": "alpha-big",
                        "source_type": "search",
                        "screen_name": "alpha",
                        "score": 10,
                        "likes": 1, "retweets": 2, "replies": 3, "views": 4,
                        "has_image": False,
                        "media_classification_source": "default",
                        "text": "snippet",
                    },
                    "post_text": "summary body",
                    "post_result_file": str(post_result_path),
                    "alerts": [],
                    "diagnostics": {},
                },
            )

        rendered = "\n".join(lines)
        self.assertNotIn("Posted tweet", rendered)

    def test_render_run_summary_no_post_result_file_key(self) -> None:
        """Payload without post_result_file (e.g. skip/no-candidate) must not show posted tweet."""
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-03-28T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "no_candidate",
                "selection_mode": "score",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [],
                "alerts": [],
                "diagnostics": {},
            },
        )
        rendered = "\n".join(lines)
        self.assertNotIn("Posted tweet", rendered)

    def test_load_post_result_payload_valid(self) -> None:
        """Valid post result file returns parsed payload."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            path.write_text('{"ok":true,"data":{"id":"999","url":"https://x.com/i/status/999"}}', encoding="utf-8")
            result = workflow_summary.load_post_result_payload(str(path))
        self.assertIsNotNone(result)
        self.assertEqual(result["data"]["id"], "999")

    def test_load_post_result_payload_missing_file(self) -> None:
        """Missing file returns None."""
        result = workflow_summary.load_post_result_payload("/nonexistent/file.json")
        self.assertIsNone(result)

    def test_load_post_result_payload_invalid_json(self) -> None:
        """Invalid JSON returns None."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "result.json"
            path.write_text("{broken", encoding="utf-8")
            result = workflow_summary.load_post_result_payload(str(path))
        self.assertIsNone(result)

    def test_load_post_result_payload_none_path(self) -> None:
        """None path returns None."""
        result = workflow_summary.load_post_result_payload(None)
        self.assertIsNone(result)

    def test_render_run_summary_shows_refusal_detection_warning(self) -> None:
        """When summary_validation contains llm_refusal, summary must show a refusal warning."""
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-04-01T10:00:00+09:00",
            payload={
                "requested_mode": "live",
                "result_mode": "candidate_ready",
                "selection_mode": "round_robin_account",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "post_candidates": [],
                "selected_candidates": [{"id": "2038253848922574941"}],
                "alerts": [
                    {
                        "level": "warning",
                        "code": "summary_validation_failed",
                        "message": "llm_refusal",
                        "tweet_id": "2038253848922574941",
                        "source_id": "pam99ham",
                    },
                ],
                "diagnostics": {
                    "summary_attempts": [
                        {
                            "tweet_id": "2038253848922574941",
                            "ok": False,
                            "error": "summary validation failed: llm_refusal",
                            "stage": "evaluator",
                        },
                    ],
                },
            },
        )
        rendered = "\n".join(lines)
        self.assertIn("llm_refusal", rendered)
        self.assertIn("⚠️ LLM refusal", rendered)

    def test_render_run_summary_shows_source_tweet_and_provider(self) -> None:
        """Summary must surface source tweet URL, provider, and model."""
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-04-01T10:00:00+09:00",
            payload={
                "requested_mode": "post",
                "result_mode": "candidate_ready",
                "selection_mode": "round_robin_account",
                "payload_count": 1,
                "collection": {"user": {}, "search": {}},
                "selected": {
                    "id": "2038253848922574941",
                    "source_id": "pam99ham",
                    "source_type": "search",
                    "screen_name": "pam99ham",
                    "score": 15,
                    "likes": 10,
                    "retweets": 5,
                    "replies": 2,
                    "views": 1000,
                    "has_image": False,
                    "media_classification_source": "default",
                    "text": "元ツイート本文",
                    "source_url": "https://x.com/pam99ham/status/2038253848922574941",
                    "summary_generation": {
                        "provider": "copilot_cli",
                        "model": "gpt-5-mini",
                    },
                },
                "post_text": "要約テキスト",
                "source_url": "https://x.com/pam99ham/status/2038253848922574941",
                "post_candidates": [{"id": "2038253848922574941"}],
                "alerts": [],
                "diagnostics": {},
            },
        )
        rendered = "\n".join(lines)
        self.assertIn("Source tweet:", rendered)
        self.assertIn("https://x.com/pam99ham/status/2038253848922574941", rendered)
        self.assertIn("copilot_cli", rendered)
        self.assertIn("gpt-5-mini", rendered)

    def test_render_run_summary_shows_hourly_guard_skip(self) -> None:
        """When hourly_guard data is present, summary must show the skip reason."""
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="true",
            posting_window_jst="2026-04-01T10:00:00+09:00",
            payload=None,
            hourly_guard={
                "allowed": False,
                "reason": "already_posted_this_hour",
                "jst_hour": "2026-04-01T10",
                "last_posted_at": "2026-04-01T10:05:00+09:00",
            },
        )
        rendered = "\n".join(lines)
        self.assertIn("Hourly guard", rendered)
        self.assertIn("already_posted_this_hour", rendered)

    def test_render_run_summary_skipped_outside_window_shows_new_window(self) -> None:
        """投稿時間帯外スキップ文言が 07:00-01:00 になること。"""
        lines = workflow_summary.render_run_summary(
            category="buz",
            posting_window="false",
            posting_window_jst="2026-03-31T03:00:00+09:00",
            payload=None,
        )
        joined = "\n".join(lines)
        self.assertIn("07:00-01:00", joined)
        self.assertNotIn("08:00-24:00", joined)


if __name__ == "__main__":
    main()
