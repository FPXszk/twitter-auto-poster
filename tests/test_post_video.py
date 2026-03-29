from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_video import (
    build_post_video_success_payload,
    build_twikit_cookies,
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


if __name__ == "__main__":
    unittest.main()
