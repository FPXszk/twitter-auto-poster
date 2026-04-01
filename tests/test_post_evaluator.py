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

    # --- LLM refusal detection tests ---

    def test_evaluate_summary_rejects_exact_refusal_from_incident(self) -> None:
        """The exact text posted in run 23824500768 must be rejected."""
        result = evaluate_summary(
            "I'm sorry, but I cannot assist with that request.",
            source_text="元ツイート本文",
            max_length=280,
        )

        self.assertFalse(result["ok"])
        self.assertIn("llm_refusal", result["reasons"])

    def test_evaluate_summary_rejects_refusal_case_insensitive(self) -> None:
        result = evaluate_summary(
            "I'M SORRY, BUT I CANNOT ASSIST WITH THAT REQUEST.",
            source_text="元ツイート本文",
            max_length=280,
        )

        self.assertFalse(result["ok"])
        self.assertIn("llm_refusal", result["reasons"])

    def test_evaluate_summary_rejects_common_refusal_variants(self) -> None:
        refusals = [
            "I can't help with that request.",
            "I'm unable to assist with that.",
            "Sorry, I can't provide that information.",
            "I'm not able to help with that.",
            "As an AI language model, I cannot generate that content.",
            "I apologize, but I'm unable to fulfill this request.",
            "I cannot generate content that",
            "I'm sorry, I can't do that.",
        ]
        for text in refusals:
            with self.subTest(text=text):
                result = evaluate_summary(text, source_text="source", max_length=280)
                self.assertFalse(result["ok"], f"Expected refusal rejection for: {text}")
                self.assertIn("llm_refusal", result["reasons"], f"Expected llm_refusal reason for: {text}")

    def test_evaluate_summary_accepts_normal_japanese_summary(self) -> None:
        """Normal Japanese summaries must not be false-positive rejected as refusal."""
        result = evaluate_summary(
            "半導体関連株が買われて相場全体を押し上げた。",
            source_text="米国市場では半導体関連株が買われて相場全体を押し上げた。",
            max_length=280,
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("llm_refusal", result["reasons"])

    def test_evaluate_summary_accepts_text_containing_sorry_in_context(self) -> None:
        """Japanese text that coincidentally contains 'sorry' should not be rejected."""
        result = evaluate_summary(
            "申し訳ありませんが、今日の株価は下落しました。",
            source_text="source",
            max_length=280,
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("llm_refusal", result["reasons"])

    def test_evaluate_summary_accepts_english_with_sorry_not_refusal(self) -> None:
        """Normal English text with 'sorry' that isn't a refusal pattern."""
        result = evaluate_summary(
            "Sorry for the delay, here are today's market results.",
            source_text="source",
            max_length=280,
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("llm_refusal", result["reasons"])

    def test_evaluate_summary_rejects_refusal_with_smart_quotes(self) -> None:
        """Typographic/curly apostrophes must also be caught."""
        result = evaluate_summary(
            "I\u2019m sorry, but I cannot assist with that request.",
            source_text="source",
            max_length=280,
        )

        self.assertFalse(result["ok"])
        self.assertIn("llm_refusal", result["reasons"])


if __name__ == "__main__":
    main()
