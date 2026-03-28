from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_media import build_image_download_request, download_image_attachments, extract_candidate_media


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PostMediaTest(unittest.TestCase):
    def test_extract_candidate_media_detects_photo_from_payload(self) -> None:
        payload = {"media": [{"type": "photo", "url": "https://pbs.twimg.com/media/example-1.jpg"}]}

        media = extract_candidate_media(payload)

        self.assertEqual(media["media_mode"], "image")
        self.assertTrue(media["has_image"])
        self.assertEqual(media["classification_source"], "payload")
        self.assertEqual(media["image_urls"], ["https://pbs.twimg.com/media/example-1.jpg"])

    def test_extract_candidate_media_uses_query_hint_when_payload_is_missing(self) -> None:
        media = extract_candidate_media({}, fallback_mode="image")

        self.assertEqual(media["media_mode"], "image")
        self.assertTrue(media["has_image"])
        self.assertEqual(media["classification_source"], "query_hint")

    def test_extract_candidate_media_defaults_to_text_without_media(self) -> None:
        media = extract_candidate_media({})

        self.assertEqual(media["media_mode"], "text")
        self.assertFalse(media["has_image"])
        self.assertEqual(media["classification_source"], "default")
        self.assertEqual(media["image_urls"], [])

    def test_build_image_download_request_uses_browser_headers(self) -> None:
        request = build_image_download_request("https://pbs.twimg.com/media/example-1.jpg")

        self.assertEqual(request.headers["User-agent"], "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")
        self.assertEqual(request.headers["Referer"], "https://x.com/")
        self.assertIn("image/", request.headers["Accept"])

    def test_download_image_attachments_writes_files_from_requests(self) -> None:
        captured: list[tuple[str, int]] = []

        def fake_urlopen(request, timeout: int = 0) -> FakeResponse:
            captured.append((request.full_url, timeout))
            return FakeResponse(b"binary-image")

        with tempfile.TemporaryDirectory() as temp_dir:
            saved_paths = download_image_attachments(
                ["https://pbs.twimg.com/media/example-1.jpg?name=small"],
                temp_dir,
                urlopen=fake_urlopen,
            )

            self.assertEqual(len(saved_paths), 1)
            self.assertEqual(Path(saved_paths[0]).read_bytes(), b"binary-image")

        self.assertEqual(captured, [("https://pbs.twimg.com/media/example-1.jpg?name=small", 30)])


if __name__ == "__main__":
    unittest.main()
