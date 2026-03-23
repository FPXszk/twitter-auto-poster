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

    def test_translate_to_japanese_returns_full_translated_text(self) -> None:
        translator = FakeTranslator(text=("あ" * 480) + "。" + ("い" * 100))

        result = post_summary.translate_to_japanese(
            "Apple stock rises 3% after strong earnings report",
            translator=translator,
        )

        self.assertEqual(result, ("あ" * 480) + "。" + ("い" * 100))

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
            "【👀 要約】\n\nアップル株が好決算で3%上昇",
        )

    def test_build_thread_posts_single_post_appends_source_url(self) -> None:
        posts = post_summary.build_thread_posts(
            "【👀 要約】\n\n短い要約です。",
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(
            posts[0],
            "【👀 要約】\n\n短い要約です。\n🔗 https://x.com/AppleNews/status/1234567890",
        )

    def test_build_summary_never_exceeds_max_length(self) -> None:
        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=80,
            screen_name="AppleNews",
            tweet_id="1234567890",
            translator=FakeTranslator(text="アップル株が好決算で3%上昇"),
        )

        self.assertLessEqual(post_summary.estimate_x_post_length(summary), 80)
        self.assertNotIn("https://x.com/AppleNews/status/1234567890", summary)

    def test_estimate_x_post_length_counts_urls_as_short_links(self) -> None:
        self.assertEqual(
            post_summary.estimate_x_post_length("https://x.com/AppleNews/status/1234567890"),
            post_summary.X_SHORT_URL_LENGTH,
        )

    def test_build_summary_respects_configured_max_length(self) -> None:
        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=2000,
            screen_name="AppleNews",
            tweet_id="1234567890",
            translator=FakeTranslator(text="あ" * 700),
        )

        self.assertLessEqual(post_summary.estimate_x_post_length(summary), 2000)
        self.assertIn("あ" * 700, summary)
        self.assertNotIn("https://x.com/AppleNews/status/1234567890", summary)

    def test_truncate_post_text_keeps_url_atomic(self) -> None:
        truncated = post_summary.truncate_post_text(
            "Test https://example.com more text",
            30,
        )

        self.assertLessEqual(post_summary.estimate_x_post_length(truncated), 30)
        self.assertNotIn("https://example.com mor", truncated)

    def test_build_summary_prefers_sentence_boundary_when_truncating(self) -> None:
        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=170,
            screen_name="AppleNews",
            tweet_id="1234567890",
            translator=FakeTranslator(text=("あ" * 40) + "。" + ("い" * 120)),
        )

        self.assertLessEqual(post_summary.estimate_x_post_length(summary), 170)
        self.assertTrue(summary.endswith("。"))

    def test_build_thread_posts_splits_naturally_and_appends_link_to_last_post(self) -> None:
        posts = post_summary.build_thread_posts(
            (
                "【👀 要約】\n\n"
                + ("a" * 120)
                + "。"
                + ("b" * 120)
                + "。"
                + ("c" * 80)
                + "。"
            ),
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertNotIn("🔗", posts[0])
        self.assertTrue(posts[1].endswith("https://x.com/AppleNews/status/1234567890"))
        for item in posts:
            self.assertLessEqual(post_summary.estimate_x_post_length(item), post_summary.MAX_X_POST_LENGTH)

    def test_build_thread_posts_raises_when_text_requires_more_than_max_posts(self) -> None:
        text = "【👀 要約】\n\n" + "".join((char * 260) + "。" for char in "abcdef")

        with self.assertRaises(ValueError):
            post_summary.build_thread_posts(
                text,
                source_url="https://x.com/AppleNews/status/1234567890",
            )

    def test_build_thread_posts_raises_when_last_segment_cannot_fit_source_url(self) -> None:
        with self.assertRaises(ValueError):
            post_summary.build_thread_posts(
                "【👀 要約】\n\n" + ("a" * 150) + "。" + ("b" * 260) + "。",
                source_url="https://x.com/AppleNews/status/1234567890",
            )

    def test_build_thread_posts_reserves_space_for_final_source_url(self) -> None:
        posts = post_summary.build_thread_posts(
            "【👀 要約】\n\n" + ("a" * 120) + "。" + ("b" * 120) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertTrue(posts[-1].endswith("https://x.com/AppleNews/status/1234567890"))

    def test_build_thread_posts_only_first_post_uses_continuation_suffix(self) -> None:
        posts = post_summary.build_thread_posts(
            "【👀 要約】\n\n" + ("a" * 150) + "、" + ("b" * 150) + "、" + ("c" * 150) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 3)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertFalse(posts[1].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertNotIn("🔗", posts[0])
        self.assertNotIn("🔗", posts[1])
        self.assertTrue(posts[2].endswith("https://x.com/AppleNews/status/1234567890"))


if __name__ == "__main__":
    main()
