from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from post_media import extract_candidate_media


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


if __name__ == "__main__":
    unittest.main()
