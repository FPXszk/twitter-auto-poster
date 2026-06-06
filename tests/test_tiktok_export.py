from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_export import export_validated_video


class TikTokExportTest(unittest.TestCase):
    def _write_validation(self, root: Path) -> Path:
        path = root / "validation" / "validation_result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "ok": True,
                    "candidate": {
                        "duration_seconds": 12.3,
                        "video_codec": "h264",
                        "audio_codec": "aac",
                    },
                    "coverage_ratio": 1.0,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_export_copies_validated_video_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.mp4"
            candidate.write_bytes(b"fake-video")
            validation = self._write_validation(root)
            export_root = root / "iCloudDrive" / "TikTokReady"
            export_root.mkdir(parents=True, exist_ok=True)

            payload = export_validated_video(
                candidate_video_path=candidate,
                validation_result_path=validation,
                export_root=export_root,
                video_id="7621519315451448596",
                source_url="https://www.tiktok.com/@u/video/7621519315451448596",
            )

            result_path = Path(payload["result_path"])
            self.assertTrue(result_path.exists())
            self.assertTrue(Path(payload["ready_to_post_path"]).exists())
            self.assertEqual(Path(payload["ready_to_post_path"]).read_bytes(), b"fake-video")
            self.assertTrue(Path(payload["source_url_path"]).exists())
            self.assertIn("manual", Path(payload["readme_path"]).read_text(encoding="utf-8").lower())

    def test_export_refuses_existing_destination_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.mp4"
            candidate.write_bytes(b"fake-video")
            validation = self._write_validation(root)
            export_root = root / "iCloudDrive" / "TikTokReady"
            export_root.mkdir(parents=True, exist_ok=True)

            export_validated_video(
                candidate_video_path=candidate,
                validation_result_path=validation,
                export_root=export_root,
                video_id="7621519315451448596",
                source_url="https://www.tiktok.com/@u/video/7621519315451448596",
            )

            with self.assertRaises(FileExistsError):
                export_validated_video(
                    candidate_video_path=candidate,
                    validation_result_path=validation,
                    export_root=export_root,
                    video_id="7621519315451448596",
                    source_url="https://www.tiktok.com/@u/video/7621519315451448596",
                )

    def test_export_force_creates_new_attempt_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.mp4"
            candidate.write_bytes(b"fake-video")
            validation = self._write_validation(root)
            export_root = root / "iCloudDrive" / "TikTokReady"
            export_root.mkdir(parents=True, exist_ok=True)

            first = export_validated_video(
                candidate_video_path=candidate,
                validation_result_path=validation,
                export_root=export_root,
                video_id="7621519315451448596",
                source_url="https://www.tiktok.com/@u/video/7621519315451448596",
            )
            second = export_validated_video(
                candidate_video_path=candidate,
                validation_result_path=validation,
                export_root=export_root,
                video_id="7621519315451448596",
                source_url="https://www.tiktok.com/@u/video/7621519315451448596",
                force=True,
            )

            self.assertNotEqual(first["export_dir"], second["export_dir"])
            self.assertIn("attempt-", Path(second["export_dir"]).name)


if __name__ == "__main__":
    unittest.main()
