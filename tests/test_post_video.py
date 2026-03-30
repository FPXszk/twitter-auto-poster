from __future__ import annotations

import asyncio
import builtins
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_video import (
    _XClientTransactionAdapter,
    build_post_video_success_payload,
    build_twikit_cookies,
    configure_client_transaction_backend,
    post_video_tweet,
    validate_video_path,
    write_post_video_result,
)

SAMPLE_VIDEO_MP4 = (
    b"\x00\x00\x00\x18ftypmp42"
    b"\x00\x00\x00\x10moov"
    b"\x00\x00\x00\x10trak"
    b"\x00\x00\x00\x10vide"
    b"\x00\x00\x00\x10mdat"
)


class PostVideoTest(unittest.TestCase):
    def test_build_twikit_cookies_uses_existing_secret_names(self) -> None:
        cookies = build_twikit_cookies(
            {
                "TWITTER_AUTH_TOKEN": "auth-token-value",
                "TWITTER_CT0": "ct0-token-value",
            }
        )

        self.assertEqual(
            cookies,
            {
                "auth_token": "auth-token-value",
                "ct0": "ct0-token-value",
            },
        )

    def test_build_twikit_cookies_requires_both_tokens(self) -> None:
        with self.assertRaisesRegex(ValueError, "TWITTER_AUTH_TOKEN"):
            build_twikit_cookies({"TWITTER_CT0": "ct0-only"})

    def test_validate_video_path_accepts_existing_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                resolved = validate_video_path(video_path)

            self.assertEqual(resolved, video_path.resolve())

    def test_validate_video_path_rejects_non_mp4_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mov"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with self.assertRaisesRegex(ValueError, "MP4"):
                validate_video_path(video_path)

    def test_validate_video_path_rejects_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with self.assertRaisesRegex(ValueError, "exceeds limit"):
                validate_video_path(video_path, max_size_bytes=4)

    def test_validate_video_path_rejects_invalid_mp4_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_text("<html>not a video</html>", encoding="utf-8")

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                with self.assertRaisesRegex(ValueError, "valid MP4"):
                    validate_video_path(video_path)

    def test_validate_video_path_rejects_quicktime_brand(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(b"\x00\x00\x00\x18ftypqt  ")

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                with self.assertRaisesRegex(ValueError, "valid MP4"):
                    validate_video_path(video_path)

    def test_validate_video_path_rejects_audio_only_brand(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(b"\x00\x00\x00\x18ftypM4A ")

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                with self.assertRaisesRegex(ValueError, "valid MP4"):
                    validate_video_path(video_path)

    def test_validate_video_path_rejects_truncated_stub(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                with self.assertRaisesRegex(ValueError, "valid MP4 video"):
                    validate_video_path(video_path)

    def test_validate_video_path_rejects_when_ffprobe_reports_no_video_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with patch("post_video._ffprobe_has_video_stream", return_value=False):
                with self.assertRaisesRegex(ValueError, "video stream"):
                    validate_video_path(video_path)

    def test_post_video_tweet_rejects_weighted_length_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                with self.assertRaisesRegex(ValueError, "weighted chars"):
                    post_video_tweet(
                        tweet_text="漢" * 141,
                        video_path=video_path,
                        dry_run=True,
                    )

    def test_post_video_tweet_returns_dry_run_payload_without_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                payload = post_video_tweet(
                    tweet_text="dry run caption",
                    video_path=video_path,
                    dry_run=True,
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["action"], "dry_run_video")
        self.assertEqual(payload["data"]["tweet_count"], 0)
        self.assertEqual(payload["data"]["video_path"], str(video_path.resolve()))

    def test_post_video_tweet_uses_client_factory_for_live_post(self) -> None:
        class FakeHttpClient:
            def __init__(self) -> None:
                self.closed = False

            async def aclose(self) -> None:
                self.closed = True

        class FakeTweet:
            id = "tweet-123"

        class FakeClient:
            def __init__(self) -> None:
                self.http = FakeHttpClient()
                self.cookies: dict[str, str] = {}
                self.clear_cookies = False
                self.uploaded_path = ""
                self.wait_for_completion = False
                self.media_ids: list[str] = []
                self.text = ""

            def set_cookies(self, cookies: dict[str, str], clear_cookies: bool = False) -> None:
                self.cookies = dict(cookies)
                self.clear_cookies = clear_cookies

            async def upload_media(self, source: str, wait_for_completion: bool = False) -> str:
                self.uploaded_path = source
                self.wait_for_completion = wait_for_completion
                return "media-123"

            async def create_tweet(self, text: str, media_ids: list[str]) -> FakeTweet:
                self.text = text
                self.media_ids = list(media_ids)
                return FakeTweet()

        client = FakeClient()

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(SAMPLE_VIDEO_MP4)

            with patch("post_video._ffprobe_has_video_stream", return_value=None):
                payload = post_video_tweet(
                    tweet_text="live caption",
                    video_path=video_path,
                    dry_run=False,
                    env={
                        "TWITTER_AUTH_TOKEN": "auth-token-value",
                        "TWITTER_CT0": "ct0-token-value",
                    },
                    client_factory=lambda: client,
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["action"], "post_video")
        self.assertEqual(payload["data"]["id"], "tweet-123")
        self.assertEqual(client.cookies["auth_token"], "auth-token-value")
        self.assertEqual(client.cookies["ct0"], "ct0-token-value")
        self.assertTrue(client.clear_cookies)
        self.assertTrue(client.wait_for_completion)
        self.assertEqual(client.uploaded_path, str(video_path.resolve()))
        self.assertEqual(client.media_ids, ["media-123"])
        self.assertEqual(client.text, "live caption")
        self.assertTrue(client.http.closed)

    def test_configure_client_transaction_backend_uses_adapter_when_helpers_are_provided(self) -> None:
        class FakeExternalTransaction:
            def __init__(self, *, home_page_response, ondemand_file_response) -> None:
                self.home_page_response = home_page_response
                self.ondemand_file_response = ondemand_file_response

            def generate_transaction_id(
                self,
                *,
                method: str,
                path: str,
                home_page_response=None,
                key=None,
                animation_key=None,
                time_now=None,
            ) -> str:
                return f"{method}:{path}:{home_page_response}:{self.ondemand_file_response}"

        class FakeResponse:
            text = "ondemand-js-body"

        class FakeSession:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, dict[str, str]]] = []

            async def request(self, method: str, url: str, headers: dict[str, str]):
                self.calls.append((method, url, dict(headers)))
                return FakeResponse()

        async def fake_load_home_page(session, headers):
            self.assertEqual(headers["User-Agent"], "ua")
            return "home-page-soup"

        def fake_get_ondemand_file_url(home_page_response) -> str:
            self.assertEqual(home_page_response, "home-page-soup")
            return "https://abs.twimg.com/responsive-web/client-web/ondemand.s.newhasha.js"

        class FakeClient:
            def __init__(self) -> None:
                self.client_transaction = object()

        client = FakeClient()
        backend = configure_client_transaction_backend(
            client,
            transaction_cls=FakeExternalTransaction,
            get_ondemand_file_url=fake_get_ondemand_file_url,
            load_home_page=fake_load_home_page,
        )

        self.assertEqual(backend, "x_client_transaction")

        session = FakeSession()
        asyncio.run(client.client_transaction.init(session, {"User-Agent": "ua"}))

        self.assertEqual(
            session.calls,
            [
                (
                    "GET",
                    "https://abs.twimg.com/responsive-web/client-web/ondemand.s.newhasha.js",
                    {"User-Agent": "ua"},
                )
            ],
        )
        self.assertEqual(client.client_transaction.home_page_response, "home-page-soup")
        self.assertEqual(
            client.client_transaction.generate_transaction_id(method="POST", path="/i/api/graphql/demo"),
            "POST:/i/api/graphql/demo:home-page-soup:ondemand-js-body",
        )

    def test_configure_client_transaction_backend_falls_back_to_twikit_patch(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.client_transaction = object()

        client = FakeClient()
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "x_client_transaction" or name.startswith("x_client_transaction."):
                raise ImportError("x_client_transaction unavailable in test")
            return original_import(name, globals, locals, fromlist, level)

        with patch("post_video.patch_twikit_transaction") as patch_twikit:
            with patch("builtins.__import__", side_effect=fake_import):
                backend = configure_client_transaction_backend(client)

        self.assertEqual(backend, "twikit_compat")
        patch_twikit.assert_called_once_with()

    def test_configure_client_transaction_backend_uses_installed_dependency(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.client_transaction = object()

        client = FakeClient()
        backend = configure_client_transaction_backend(client)

        self.assertEqual(backend, "x_client_transaction")
        self.assertIsInstance(client.client_transaction, _XClientTransactionAdapter)

    def test_build_post_video_success_payload_matches_publish_shape(self) -> None:
        payload = build_post_video_success_payload(
            tweet_id="12345",
            tweet_text="video caption",
            video_path=Path("/tmp/video.mp4"),
            dry_run=False,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["action"], "post_video")
        self.assertEqual(payload["data"]["id"], "12345")
        self.assertEqual(payload["data"]["url"], "https://x.com/i/status/12345")
        self.assertEqual(payload["data"]["tweet_ids"], ["12345"])
        self.assertEqual(payload["data"]["tweet_count"], 1)
        self.assertEqual(payload["data"]["video_path"], "/tmp/video.mp4")
        self.assertFalse(payload["data"]["dry_run"])

    def test_write_post_video_result_writes_utf8_json(self) -> None:
        payload = build_post_video_success_payload(
            tweet_id="12345",
            tweet_text="動画キャプション",
            video_path=Path("/tmp/video.mp4"),
            dry_run=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "post-video-result.json"
            write_post_video_result(output_path, payload)

            loaded = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["data"]["video_path"], "/tmp/video.mp4")
        self.assertTrue(loaded["data"]["dry_run"])
        self.assertEqual(loaded["message"], "dry-run validated video post")


    def test_configure_backend_falls_back_on_non_import_error(self) -> None:
        """Non-ImportError during x_client_transaction import triggers twikit fallback."""

        class FakeClient:
            def __init__(self) -> None:
                self.client_transaction = object()

        client = FakeClient()
        original_ct = client.client_transaction
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "x_client_transaction" or name.startswith("x_client_transaction."):
                raise RuntimeError("x_client_transaction helpers broken at import")
            return original_import(name, globals, locals, fromlist, level)

        with patch("post_video.patch_twikit_transaction") as patch_twikit:
            with patch("builtins.__import__", side_effect=fake_import):
                backend = configure_client_transaction_backend(client)

        self.assertEqual(backend, "twikit_compat")
        patch_twikit.assert_called_once_with()
        self.assertIs(client.client_transaction, original_ct)

    def test_adapter_init_failure_restores_original_ct_and_completes_init(self) -> None:
        """Adapter init failure should restore and initialize the original CT in-place."""

        class FakeClient:
            def __init__(self) -> None:
                self.client_transaction = FakeOriginalTransaction()

        class FakeOriginalTransaction:
            def __init__(self) -> None:
                self.home_page_response = None
                self.init_calls: list[tuple[object, dict[str, str]]] = []

            async def init(self, session, headers) -> None:
                self.init_calls.append((session, dict(headers)))
                self.home_page_response = "restored-home-page"

            def generate_transaction_id(self, *, method: str, path: str, **kwargs) -> str:
                return f"restored:{method}:{path}"

        client = FakeClient()
        original_ct = client.client_transaction

        async def failing_load_home_page(session, headers):
            raise RuntimeError("ondemand regex parse failure in XClientTransaction")

        def fake_get_url(response) -> str:
            return "https://example.com/ondemand.js"

        class FakeTransaction:
            def __init__(self, *, home_page_response, ondemand_file_response):
                pass

        backend = configure_client_transaction_backend(
            client,
            transaction_cls=FakeTransaction,
            get_ondemand_file_url=fake_get_url,
            load_home_page=failing_load_home_page,
        )
        self.assertEqual(backend, "x_client_transaction")
        self.assertIsInstance(client.client_transaction, _XClientTransactionAdapter)

        class FakeSession:
            async def request(self, **kwargs):
                return type("R", (), {"text": ""})()

        with patch("post_video.patch_twikit_transaction") as patch_twikit:
            session = FakeSession()
            asyncio.run(client.client_transaction.init(session, {"User-Agent": "ua"}))
            patch_twikit.assert_called_once_with()

        self.assertIs(client.client_transaction, original_ct)
        self.assertEqual(
            original_ct.init_calls,
            [
                (
                    session,
                    {"User-Agent": "ua"},
                )
            ],
        )
        self.assertEqual(original_ct.home_page_response, "restored-home-page")
        self.assertEqual(
            client.client_transaction.generate_transaction_id(method="POST", path="/i/api/graphql/demo"),
            "restored:POST:/i/api/graphql/demo",
        )


if __name__ == "__main__":
    unittest.main()
