from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import post_author


def make_executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class PostAuthorTest(TestCase):
    def test_resolve_twitter_bin_prefers_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            twitter_path = make_executable(Path(temp_dir) / "twitter")

            resolved = post_author.resolve_twitter_bin(
                env={"TWITTER_BIN": str(twitter_path)},
                default_bin=Path("/does/not/exist"),
            )

        self.assertEqual(resolved, str(twitter_path))

    def test_resolve_twitter_bin_uses_repo_default_before_path_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            default_path = make_executable(Path(temp_dir) / "twitter")

            resolved = post_author.resolve_twitter_bin(
                env={},
                default_bin=default_path,
                which=lambda _: "/usr/bin/twitter",
            )

        self.assertEqual(resolved, str(default_path))

    def test_resolve_twitter_bin_falls_back_to_path_command(self) -> None:
        resolved = post_author.resolve_twitter_bin(
            env={"TWITTER_BIN": "twitter-custom"},
            default_bin=Path("/does/not/exist"),
            which=lambda command: f"/usr/local/bin/{command}",
        )

        self.assertEqual(resolved, "/usr/local/bin/twitter-custom")

    def test_resolve_twitter_bin_raises_when_binary_is_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "twitter-cli not found"):
            post_author.resolve_twitter_bin(
                env={},
                default_bin=Path("/does/not/exist"),
                which=lambda _: None,
            )

    def test_fetch_author_metrics_uses_resolved_command(self) -> None:
        captured: dict[str, object] = {}

        def fake_runner(command: list[str], **_: object) -> SimpleNamespace:
            captured["command"] = command
            return SimpleNamespace(
                returncode=0,
                stdout='{"data":{"screenName":"tester","followersCount":42,"friendsCount":7,"verified":true}}',
                stderr="",
            )

        with patch.object(post_author, "resolve_twitter_bin", return_value="/tmp/twitter-bin"):
            payload = post_author.fetch_author_metrics("tester", command_runner=fake_runner)

        self.assertEqual(captured["command"], ["/tmp/twitter-bin", "user", "tester", "--json"])
        self.assertEqual(payload["screen_name"], "tester")
        self.assertEqual(payload["followers"], 42)
        self.assertEqual(payload["following"], 7)
        self.assertTrue(payload["verified"])

    def test_fetch_author_metrics_wraps_lookup_errors(self) -> None:
        def fake_runner(command: list[str], **_: object) -> SimpleNamespace:
            return SimpleNamespace(returncode=1, stdout="", stderr="lookup failed")

        with patch.object(post_author, "resolve_twitter_bin", return_value="/tmp/twitter-bin"):
            with self.assertRaisesRegex(RuntimeError, "lookup failed"):
                post_author.fetch_author_metrics("tester", command_runner=fake_runner)

    def test_enrich_author_metrics_updates_diagnostics_for_payload_cache_and_lookup(self) -> None:
        diagnostics: dict[str, object] = {}
        cache: dict[str, dict[str, object]] = {}

        payload_metrics, warning = post_author.enrich_author_metrics(
            {"author": {"screenName": "tester", "followersCount": 10}},
            cache=cache,
            diagnostics=diagnostics,
        )
        self.assertIsNone(warning)
        self.assertEqual(payload_metrics["followers"], 10)
        self.assertEqual(diagnostics["payload_metrics"], 1)

        cached_metrics, warning = post_author.enrich_author_metrics(
            {"author": {"screenName": "tester"}},
            cache=cache,
            diagnostics=diagnostics,
        )
        self.assertIsNone(warning)
        self.assertEqual(cached_metrics["followers"], 10)
        self.assertEqual(diagnostics["cache_hits"], 1)

        with patch.object(post_author, "fetch_author_metrics", return_value={"screen_name": "lookup", "followers": 20, "following": 3, "verified": True}):
            fetched_metrics, warning = post_author.enrich_author_metrics(
                {"author": {"screenName": "lookup"}},
                cache={},
                diagnostics=diagnostics,
            )
        self.assertIsNone(warning)
        self.assertEqual(fetched_metrics["followers"], 20)
        self.assertEqual(diagnostics["lookup_success"], 1)

        with patch.object(post_author, "fetch_author_metrics", side_effect=RuntimeError("boom")):
            _, warning = post_author.enrich_author_metrics(
                {"author": {"screenName": "broken"}},
                cache={},
                diagnostics=diagnostics,
            )
        self.assertEqual(warning, "boom")
        self.assertEqual(diagnostics["lookup_failed"], 1)


if __name__ == "__main__":
    main()
