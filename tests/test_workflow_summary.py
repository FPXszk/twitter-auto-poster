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


if __name__ == "__main__":
    main()
