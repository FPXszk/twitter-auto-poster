from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_anonymization_pipeline import run_tiktok_anonymization_pipeline


class TikTokAnonymizationPipelineTest(unittest.TestCase):
    @patch("tiktok_anonymization_pipeline.export_validated_video")
    @patch("tiktok_anonymization_pipeline.validate_final_video")
    @patch("tiktok_anonymization_pipeline.overlay_faces_on_video")
    @patch("tiktok_anonymization_pipeline.track_faces_in_detections")
    @patch("tiktok_anonymization_pipeline.detect_faces_in_video")
    @patch("tiktok_anonymization_pipeline.download_tiktok_video_job")
    def test_pipeline_runs_end_to_end_and_writes_result(
        self,
        mock_download,
        mock_detect,
        mock_track,
        mock_overlay,
        mock_validate,
        mock_export,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            normalized = root / "downloads" / "7621519315451448596" / "normalized.mp4"
            normalized.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_bytes(b"normalized")
            source = normalized.parent / "source.mp4"
            source.write_bytes(b"source")
            export_root = root / "iCloudDrive" / "TikTokReady"
            export_root.mkdir(parents=True, exist_ok=True)

            mock_download.return_value.to_dict.return_value = {
                "ok": True,
                "video_id": "7621519315451448596",
                "resolved_url": "https://www.tiktok.com/@u/video/7621519315451448596",
                "source_path": str(source),
                "normalized_path": str(normalized),
                "result_path": str(normalized.parent / "result.json"),
                "output_path": str(source),
            }
            mock_detect.return_value = {"ok": True, "total_detections": 12}

            def _track_side_effect(detections_path, output_dir, **_kwargs):
                tracked = Path(output_dir) / "tracked_detections.json"
                tracked.parent.mkdir(parents=True, exist_ok=True)
                tracked.write_text('{"frames":[{"frame_index":0,"timestamp_ms":0,"faces":[]}]}', encoding="utf-8")
                (Path(output_dir) / "tracking_summary.json").write_text('{"ok": true, "track_count": 1}', encoding="utf-8")
                return {"ok": True, "track_count": 1}

            def _overlay_side_effect(_input, _detections, _stamp, output_path, **_kwargs):
                target = Path(output_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"edited")
                (target.parent / "overlay-summary.json").write_text('{"ok": true}', encoding="utf-8")
                (target.parent / "face-coverage-report.json").write_text('{"ok": true, "coverage_ratio": 1.0}', encoding="utf-8")
                return {"ok": True}

            def _validate_side_effect(_ref, _candidate, **kwargs):
                out_dir = Path(kwargs["output_dir"])
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "validation_result.json").write_text('{"ok": true}', encoding="utf-8")
                return {"ok": True}

            mock_track.side_effect = _track_side_effect
            mock_overlay.side_effect = _overlay_side_effect
            mock_validate.side_effect = _validate_side_effect
            mock_export.return_value = {
                "ok": True,
                "export_dir": str(export_root / "2026-06-06_7621519315451448596"),
                "result_path": str(export_root / "2026-06-06_7621519315451448596" / "result.json"),
                "ready_to_post_path": str(export_root / "2026-06-06_7621519315451448596" / "ready_to_post.mp4"),
            }

            result = run_tiktok_anonymization_pipeline(
                tiktok_url="https://www.tiktok.com/@u/video/7621519315451448596",
                output_root=root / "pipeline",
                export_dir=export_root,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["current_state"], "EXPORTED")
            self.assertEqual(result["track_count"], 1)
            self.assertTrue(Path(result["result_path"]).exists())

    @patch("tiktok_anonymization_pipeline.download_tiktok_video_job")
    def test_pipeline_requires_known_export_dir(self, mock_download) -> None:
        with tempfile.TemporaryDirectory() as td:
            normalized = Path(td) / "normalized.mp4"
            normalized.write_bytes(b"normalized")
            mock_download.return_value.to_dict.return_value = {
                "ok": True,
                "video_id": "7621519315451448596",
                "resolved_url": "https://www.tiktok.com/@u/video/7621519315451448596",
                "source_path": str(normalized),
                "normalized_path": str(normalized),
                "result_path": str(Path(td) / "result.json"),
                "output_path": str(normalized),
            }
            with self.assertRaises(RuntimeError):
                run_tiktok_anonymization_pipeline(
                    tiktok_url="https://www.tiktok.com/@u/video/7621519315451448596",
                    output_root=Path(td) / "pipeline",
                    export_dir="",
                )


if __name__ == "__main__":
    unittest.main()
