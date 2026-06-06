from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_actions_summary import render_actions_summary


class TikTokActionsSummaryTest(unittest.TestCase):
    def test_render_actions_summary_includes_required_fields(self) -> None:
        lines = render_actions_summary(
            {
                "ok": True,
                "video_id": "7621519315451448596",
                "current_state": "EXPORTED",
                "detected_face_count": 12,
                "track_count": 1,
                "validation_ok": True,
                "export_dir_name": "2026-06-06_7621519315451448596",
                "output_filename": "ready_to_post.mp4",
                "processing_seconds": 3.14,
                "result_path": "tmp/tiktok-pipeline/latest-result.json",
            }
        )
        rendered = "\n".join(lines)
        self.assertIn("Video ID", rendered)
        self.assertIn("EXPORTED", rendered)
        self.assertIn("ready_to_post.mp4", rendered)


if __name__ == "__main__":
    unittest.main()
