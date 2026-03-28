from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_evaluator import evaluate_summary


class PostEvaluatorTest(TestCase):
    def test_evaluate_summary_accepts_valid_summary(self) -> None:
        result = evaluate_summary(
            "半導体関連株が買われて相場全体を押し上げた。",
            source_text="米国市場では半導体関連株が買われて相場全体を押し上げた。",
            max_length=280,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["reasons"], [])
        self.assertGreater(result["estimated_length"], 0)

    def test_evaluate_summary_rejects_empty_text(self) -> None:
        result = evaluate_summary("", source_text="source", max_length=280)

        self.assertFalse(result["ok"])
        self.assertIn("empty_summary", result["reasons"])

    def test_evaluate_summary_rejects_embedded_urls(self) -> None:
        result = evaluate_summary(
            "詳しくはこちら https://example.com",
            source_text="source",
            max_length=280,
        )

        self.assertFalse(result["ok"])
        self.assertIn("contains_url", result["reasons"])

    def test_evaluate_summary_rejects_text_over_length_limit(self) -> None:
        result = evaluate_summary("a" * 281, source_text="source", max_length=280)

        self.assertFalse(result["ok"])
        self.assertIn("summary_too_long", result["reasons"])


if __name__ == "__main__":
    main()
