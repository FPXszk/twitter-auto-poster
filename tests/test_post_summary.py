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

    def test_resolve_summary_provider_supports_legacy_aliases(self) -> None:
        self.assertEqual(post_summary.resolve_summary_provider("googletrans"), "legacy_google_translate")
        self.assertEqual(post_summary.resolve_summary_provider("legacy_google_translate"), "legacy_google_translate")

    def test_resolve_summary_provider_supports_copilot_aliases(self) -> None:
        self.assertEqual(post_summary.resolve_summary_provider("copilot"), "copilot_cli")
        self.assertEqual(post_summary.resolve_summary_provider("copilot_cli"), "copilot_cli")

    def test_resolve_summary_provider_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValueError):
            post_summary.resolve_summary_provider("unknown")

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
            "アップル株が好決算で3%上昇",
        )

    def test_build_thread_posts_single_post_appends_source_url(self) -> None:
        posts = post_summary.build_thread_posts(
            "短い要約です。",
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(
            posts[0],
            "短い要約です。\n🔗 https://x.com/AppleNews/status/1234567890",
        )

    def test_build_thread_posts_caps_single_post_limit_at_280(self) -> None:
        posts = post_summary.build_thread_posts(
            ("a" * 180) + "。" + ("b" * 140) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
            single_post_max_length=4000,
        )

        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertTrue(posts[-1].endswith("https://x.com/AppleNews/status/1234567890"))
        for item in posts:
            self.assertLessEqual(post_summary.estimate_x_post_length(item), post_summary.MAX_X_POST_LENGTH)

    def test_build_thread_posts_single_post_skips_source_url_in_none_mode(self) -> None:
        posts = post_summary.build_thread_posts(
            "短い要約です。",
            source_url="https://x.com/AppleNews/status/1234567890",
            source_reference_mode="none",
        )

        self.assertEqual(posts, ["短い要約です。"])

    def test_build_thread_posts_thread_skips_source_url_in_none_mode(self) -> None:
        posts = post_summary.build_thread_posts(
            ("a" * 120) + "。" + ("b" * 120) + "。" + ("c" * 80) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
            source_reference_mode="none",
        )

        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertNotIn("https://x.com/AppleNews/status/1234567890", posts[0])
        self.assertNotIn("https://x.com/AppleNews/status/1234567890", posts[1])

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

    def test_clean_post_source_text_preserves_paragraph_breaks(self) -> None:
        cleaned = post_summary.clean_post_source_text(
            "I keep getting asked:\n\nWhat's the PT of $SIVE?\n\n@user https://example.com #stocks"
        )

        self.assertEqual(
            cleaned,
            "I keep getting asked:\n\nWhat's the PT of $SIVE?\n\nstocks",
        )

    def test_build_summary_raw_preserves_body_without_ai_rewrite(self) -> None:
        summary = post_summary.build_summary(
            "1行目\n\n2行目🙂 https://example.com @user #topic",
            prefix="",
            language="raw",
            max_length=280,
        )

        self.assertEqual(summary, "1行目\n\n2行目🙂 topic")

    # --- has_candidate_content ---

    def test_has_candidate_content_rejects_url_only_text_without_image(self) -> None:
        self.assertFalse(post_summary.has_candidate_content("https://t.co/example", has_image=False))

    def test_has_candidate_content_accepts_url_only_text_with_image(self) -> None:
        self.assertTrue(post_summary.has_candidate_content("https://t.co/example", has_image=True))

    def test_has_candidate_content_accepts_normal_text_without_image(self) -> None:
        self.assertTrue(post_summary.has_candidate_content("Apple stock rises 3%", has_image=False))

    def test_has_candidate_content_accepts_normal_text_with_image(self) -> None:
        self.assertTrue(post_summary.has_candidate_content("Apple stock rises 3%", has_image=True))

    def test_has_candidate_content_rejects_empty_text_without_image(self) -> None:
        self.assertFalse(post_summary.has_candidate_content("", has_image=False))

    def test_has_candidate_content_accepts_empty_text_with_image(self) -> None:
        self.assertTrue(post_summary.has_candidate_content("", has_image=True))

    # --- build_candidate_dedup_key ---

    def test_build_candidate_dedup_key_uses_raw_text_for_image_only_posts(self) -> None:
        self.assertEqual(
            post_summary.build_candidate_dedup_key("https://t.co/example", has_image=True),
            "https://t.co/example",
        )

    def test_build_candidate_dedup_key_preserves_url_case_for_image_posts(self) -> None:
        key_a = post_summary.build_candidate_dedup_key("https://t.co/AbC123", has_image=True)
        key_b = post_summary.build_candidate_dedup_key("https://t.co/aBc123", has_image=True)
        self.assertNotEqual(key_a, key_b)

    def test_build_candidate_dedup_key_normalizes_text_posts(self) -> None:
        self.assertEqual(
            post_summary.build_candidate_dedup_key("  Apple  Stock  RISES  ", has_image=False),
            "apple stock rises",
        )

    def test_build_candidate_dedup_key_different_image_urls_produce_different_keys(self) -> None:
        key_a = post_summary.build_candidate_dedup_key("https://t.co/abc123", has_image=True)
        key_b = post_summary.build_candidate_dedup_key("https://t.co/xyz789", has_image=True)
        self.assertNotEqual(key_a, key_b)

    def test_build_candidate_dedup_key_returns_empty_for_empty_text_no_image(self) -> None:
        self.assertEqual(post_summary.build_candidate_dedup_key("", has_image=False), "")

    def test_build_candidate_dedup_key_empty_text_image_uses_tweet_id(self) -> None:
        key = post_summary.build_candidate_dedup_key("", has_image=True, tweet_id="12345")
        self.assertEqual(key, "__media_only:12345")

    def test_build_candidate_dedup_key_empty_text_image_different_ids_differ(self) -> None:
        key_a = post_summary.build_candidate_dedup_key("", has_image=True, tweet_id="111")
        key_b = post_summary.build_candidate_dedup_key("", has_image=True, tweet_id="222")
        self.assertNotEqual(key_a, key_b)

    def test_build_candidate_dedup_key_prefers_cleaned_text_over_raw_for_mixed_posts(self) -> None:
        key = post_summary.build_candidate_dedup_key(
            "Apple rises 3% https://t.co/example",
            has_image=True,
        )
        self.assertEqual(key, "apple rises 3%")
        self.assertNotIn("t.co", key)

    # --- summary fallback for image-only posts ---

    def test_build_summary_uses_neutral_fallback_for_empty_source(self) -> None:
        summary = post_summary.build_summary(
            "https://t.co/example",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=280,
            screen_name="AppleNews",
            tweet_id="1234567890",
        )

        self.assertEqual(summary, "話題の投稿を紹介します")

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

    def test_build_thread_summary_preserves_full_translated_text(self) -> None:
        summary = post_summary.build_thread_summary(
            "Apple stock rises 3% after strong earnings report",
            language="ja",
            translator=FakeTranslator(text=("あ" * 320) + "。" + ("い" * 120)),
        )

        self.assertIn(("あ" * 320) + "。" + ("い" * 120), summary)
        self.assertGreater(post_summary.estimate_x_post_length(summary), post_summary.MAX_X_POST_LENGTH)

    def test_build_thread_summary_preserves_inline_bullets(self) -> None:
        summary = post_summary.build_thread_summary(
            "ignored",
            language="ja",
            translator=FakeTranslator(text="項目A • 項目B • 項目C"),
        )

        self.assertIn("項目A • 項目B • 項目C", summary)
        self.assertNotIn("\n• 項目B", summary)

    def test_build_thread_summary_preserves_blank_lines_from_source(self) -> None:
        translator = FakeTranslator(text="ignored")

        summary = post_summary.build_thread_summary(
            "Line one\n\nLine two",
            language="ja",
            translator=translator,
        )

        self.assertEqual(summary, "ignored")
        self.assertEqual(translator.calls, [("Line one\n\nLine two", "ja")])

    def test_build_thread_summary_can_use_copilot_provider(self) -> None:
        class FakeCompletedProcess:
            def __init__(self, stdout: str, stderr: str = "") -> None:
                self.stdout = stdout
                self.stderr = stderr

        def fake_command_runner(command: list[str], *, working_directory: object | None = None) -> FakeCompletedProcess:
            self.assertEqual(command[:4], ["copilot", "--model", "gpt-5-mini", "-p"])
            self.assertEqual(working_directory, Path("/tmp/work"))
            return FakeCompletedProcess("🚨速報\n要約本文")

        summary = post_summary.build_thread_summary(
            "Apple stock rises 3% after strong earnings report",
            language="ja",
            provider="copilot_cli",
            copilot_model="gpt-5-mini",
            command_runner=fake_command_runner,
            working_directory=Path("/tmp/work"),
        )

        self.assertEqual(summary, "🚨速報\n要約本文")

    def test_build_thread_summary_can_capture_copilot_usage_diagnostics(self) -> None:
        diagnostics: dict[str, object] = {}

        class FakeCompletedProcess:
            def __init__(self, stdout: str, stderr: str) -> None:
                self.stdout = stdout
                self.stderr = stderr

        summary = post_summary.build_thread_summary(
            "Apple stock rises 3% after strong earnings report",
            language="ja",
            provider="copilot_cli",
            copilot_model="gpt-5-mini",
            command_runner=lambda command, *, working_directory=None: FakeCompletedProcess(
                "🚨速報\n要約本文",
                "Used 1 premium request\nRemaining quota: 99",
            ),
            diagnostics_sink=diagnostics,
        )

        self.assertEqual(summary, "🚨速報\n要約本文")
        self.assertEqual(diagnostics["provider"], "copilot_cli")
        self.assertEqual(diagnostics["model"], "gpt-5-mini")
        self.assertEqual(diagnostics["usage_lines"], ["Used 1 premium request", "Remaining quota: 99"])

    def test_build_summary_compacts_copilot_output_for_single_post(self) -> None:
        class FakeCompletedProcess:
            def __init__(self, stdout: str, stderr: str = "") -> None:
                self.stdout = stdout
                self.stderr = stderr

        summary = post_summary.build_summary(
            "Apple stock rises 3% after strong earnings report",
            prefix="Xで反応上位: ",
            language="ja",
            max_length=120,
            provider="copilot_cli",
            copilot_model="gpt-5-mini",
            command_runner=lambda command, *, working_directory=None: FakeCompletedProcess(
                "🚨速報\n\n- 米株は続落。\n- VIXは上昇。\n- 出来高も増加。\n\n投資家心理はまだ慎重で、底打ち確認には時間が必要です。"
            ),
        )

        self.assertLessEqual(post_summary.estimate_x_post_length(summary), 120)
        self.assertNotIn("\n", summary)
        self.assertNotIn("🚨", summary)
        self.assertNotIn("- ", summary)
        self.assertIn("米株は続落。", summary)
        self.assertIn("VIXは上昇。", summary)
        self.assertTrue(summary.endswith(("。", "…")))

    def test_build_thread_posts_splits_naturally_and_appends_link_to_last_post(self) -> None:
        posts = post_summary.build_thread_posts(
            (
                ("a" * 120)
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

    def test_build_thread_posts_keeps_thread_segment_limit_when_single_post_limit_is_custom(self) -> None:
        posts = post_summary.build_thread_posts(
            ("a" * 150) + "。" + ("b" * 150) + "。" + ("c" * 150) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
            single_post_max_length=320,
        )

        self.assertEqual(len(posts), 3)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertTrue(posts[-1].endswith("https://x.com/AppleNews/status/1234567890"))
        for item in posts:
            self.assertLessEqual(post_summary.estimate_x_post_length(item), post_summary.MAX_X_POST_LENGTH)

    def test_build_thread_posts_raises_when_text_requires_more_than_max_posts(self) -> None:
        text = "".join((char * 260) + "。" for char in "abcdef")

        with self.assertRaises(ValueError):
            post_summary.build_thread_posts(
                text,
                source_url="https://x.com/AppleNews/status/1234567890",
            )

    def test_build_thread_posts_raises_when_last_segment_cannot_fit_source_url(self) -> None:
        with self.assertRaises(ValueError):
            post_summary.build_thread_posts(
                ("a" * 150) + "。" + ("b" * 260) + "。",
                source_url="https://x.com/AppleNews/status/1234567890",
            )

    def test_build_thread_posts_reserves_space_for_final_source_url(self) -> None:
        posts = post_summary.build_thread_posts(
            ("a" * 120) + "。" + ("b" * 120) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertTrue(posts[-1].endswith("https://x.com/AppleNews/status/1234567890"))

    def test_build_thread_posts_only_first_post_uses_continuation_suffix(self) -> None:
        posts = post_summary.build_thread_posts(
            ("a" * 150) + "、" + ("b" * 150) + "、" + ("c" * 150) + "。",
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 3)
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertFalse(posts[1].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertNotIn("🔗", posts[0])
        self.assertNotIn("🔗", posts[1])
        self.assertTrue(posts[2].endswith("https://x.com/AppleNews/status/1234567890"))

    def test_build_thread_posts_does_not_split_numeric_comma_group(self) -> None:
        summary = post_summary.build_thread_summary(
            "ignored",
            language="ja",
            translator=FakeTranslator(
                text=(
                    "$ONDS 第 4 四半期の収益 • 収益: 予想と比較して 3,000 万ドル2,800 万ドル "
                    "• EBITDA: (1,000 万ドル) 対予想(900 万ドル) "
                    "• 予想と比較して粗利益率 42%37% "
                    "• バックログ: ~6,800 万ドル "
                    "• キャッシュポジション: ~15 億ドル 2026 年度ガイダンス "
                    "• 収益: 3 億 7,500 万ドル (Mistral、BIRD、INDO Earth、Rotron を除く) "
                    "Ondas は、2028 年第 1 四半期までに全社で黒字に達すると予想しています。"
                )
            ),
        )

        posts = post_summary.build_thread_posts(
            summary,
            source_url="https://x.com/AppleNews/status/1234567890",
        )

        self.assertEqual(len(posts), 2)
        self.assertIn("3 億 7,500 万ドル", posts[0])
        self.assertNotIn("500 万ドル", posts[1])
        self.assertTrue(posts[0].endswith(post_summary.THREAD_CONTINUATION_SUFFIX))
        self.assertTrue(posts[1].endswith("https://x.com/AppleNews/status/1234567890"))


if __name__ == "__main__":
    main()
