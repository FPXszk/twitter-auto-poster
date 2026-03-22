from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import post_summary


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeRateLimitError(Exception):
    status_code = 429


class PostSummaryTest(TestCase):
    def test_build_gemini_prompt_truncates_cleaned_text_to_500_chars(self) -> None:
        source_text = ("A" * 520) + " https://example.com\n@user"

        prompt = post_summary.build_gemini_prompt(source_text)

        self.assertIn("ツイート：", prompt)
        snippet = prompt.split("ツイート：", maxsplit=1)[1]
        self.assertEqual(len(snippet), 500)
        self.assertNotIn("https://example.com", prompt)
        self.assertNotIn("@user", prompt)

    def test_call_gemini_summary_retries_once_after_429(self) -> None:
        sleep_calls: list[float] = []

        class FakeModel:
            def __init__(self) -> None:
                self.calls = 0

            def generate_content(self, prompt: str) -> FakeResponse:
                self.calls += 1
                if self.calls == 1:
                    raise FakeRateLimitError("429 quota exceeded")
                self.prompt = prompt
                return FakeResponse("🌟決算好感\n背景\n👉要点")

        model = FakeModel()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            with patch.object(post_summary, "load_gemini_model", return_value=model):
                result = post_summary.call_gemini_summary(
                    "Apple stock rises 3% after strong earnings report",
                    sleep_func=sleep_calls.append,
                )

        self.assertEqual(result, "🌟決算好感\n背景\n👉要点")
        self.assertEqual(sleep_calls, [4, 4, 10, 4, 4])
        self.assertIn("Apple stock rises 3% after strong earnings report", model.prompt)

    def test_build_summary_uses_rule_based_japanese_when_key_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            summary = post_summary.build_summary(
                "Apple stock rises 3% after strong earnings report",
                prefix="Xで反応上位: ",
                language="ja",
                max_length=140,
            )

        self.assertTrue(summary.startswith("Xで反応上位: "))
        self.assertIn("Apple stock 上昇 3% after 強い 決算 report", summary)

    def test_build_summary_falls_back_to_english_after_gemini_failure(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            with patch.object(post_summary, "call_gemini_summary", side_effect=RuntimeError("429 quota exceeded")):
                summary = post_summary.build_summary(
                    "Apple stock rises 3% after strong earnings report",
                    prefix="Xで反応上位: ",
                    language="ja",
                    max_length=200,
                )

        self.assertEqual(
            summary,
            "Xで反応上位: Apple stock rises 3% after strong earnings report",
        )

    def test_build_summary_uses_gemini_output_without_prefix(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
            with patch.object(post_summary, "call_gemini_summary", return_value="🌟決算速報\n背景\n👉要点"):
                summary = post_summary.build_summary(
                    "Apple stock rises 3% after strong earnings report",
                    prefix="Xで反応上位: ",
                    language="ja",
                    max_length=200,
                )

        self.assertEqual(summary, "🌟決算速報\n背景\n👉要点")


if __name__ == "__main__":
    main()
