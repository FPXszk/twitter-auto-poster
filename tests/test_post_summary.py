from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import post_summary


class FakeTranslationResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeTranslator:
    def __init__(self, text: str = "日本語訳", *, should_fail: bool = False) -> None:
        self.text = text
        self.should_fail = should_fail
        self.calls: list[tuple[str, str]] = []

    def translate(self, text: str, dest: str) -> FakeTranslationResponse:
        self.calls.append((text, dest))
        if self.should_fail:
            raise RuntimeError("translation failed")
        return FakeTranslationResponse(self.text)


class PostSummaryTest(TestCase):
    def test_translate_to_japanese_uses_googletrans_result(self) -> None:
        translator = FakeTranslator(text="アップル株が決算で上昇")

        result = post_summary.translate_to_japanese(
            "Apple stock rises 3% after strong earnings report",
            translator=translator,
        )

        self.assertEqual(result, "アップル株が決算で上昇")
        self.assertEqual(
            translator.calls,
            [("Apple stock rises 3% after strong earnings report", "ja")],
        )

    def test_translate_to_japanese_falls_back_to_english_on_failure(self) -> None:
        translator = FakeTranslator(should_fail=True)

        result = post_summary.translate_to_japanese(
            "Apple stock rises 3% after strong earnings report",
            translator=translator,
        )

        self.assertEqual(result, "Apple stock rises 3% after strong earnings report")

    def test_build_source_tweet_url_prefers_screen_name(self) -> None:
        url = post_summary.build_source_tweet_url(
            "AppleNews",
            "1234567890",
            source_username="fallback_user",
        )

        self.assertEqual(url, "https://x.com/AppleNews/status/1234567890")

    def test_build_source_tweet_url_falls_back_to_source_username(self) -> None:
        url = post_summary.build_source_tweet_url(
            "",
            "1234567890",
            source_username="@fallback_user",
        )

        self.assertEqual(url, "https://x.com/fallback_user/status/1234567890")

    def test_build_summary_formats_translated_quote_post(self) -> None:
        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=280,
            screen_name="AppleNews",
            tweet_id="1234567890",
            source_username="fallback_user",
            translator=FakeTranslator(text="アップル株が好決算で3%上昇"),
        )

        self.assertEqual(
            summary,
            "【🌐 日本語訳】\n\nアップル株が好決算で3%上昇\n\n---\nhttps://x.com/AppleNews/status/1234567890",
        )

    def test_build_summary_preserves_url_when_truncating(self) -> None:
        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=80,
            screen_name="AppleNews",
            tweet_id="1234567890",
            translator=FakeTranslator(text="あ" * 100),
        )

        self.assertLessEqual(len(summary), 80)
        self.assertTrue(summary.endswith("https://x.com/AppleNews/status/1234567890"))

    def test_build_summary_never_exceeds_max_length(self) -> None:
        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=30,
            screen_name="AppleNews",
            tweet_id="1234567890",
            translator=FakeTranslator(text="アップル株が好決算で3%上昇"),
        )

        self.assertLessEqual(len(summary), 30)


if __name__ == "__main__":
    main()
