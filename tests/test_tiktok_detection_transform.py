from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_detection_transform import transform_tracked_detections


class TikTokDetectionTransformTest(unittest.TestCase):
    def test_transform_applies_horizontal_flip_and_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "tracked_detections.json"
            source.write_text(
                json.dumps(
                    {
                        "video": {"duration_seconds": 10.0, "fps": 30.0, "total_frames": 300},
                        "frames": [
                            {
                                "frame_index": 0,
                                "timestamp_ms": 0,
                                "faces": [{"track_id": 1, "x": 0.2, "y": 0.1, "width": 0.3, "height": 0.4, "confidence": 0.9, "interpolated": False}],
                            },
                            {
                                "frame_index": 1,
                                "timestamp_ms": 33,
                                "faces": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            target = root / "transformed.json"
            payload = transform_tracked_detections(source, target, horizontal_flip=True, speed=0.8)
            transformed = json.loads(target.read_text(encoding="utf-8"))

            self.assertTrue(payload["ok"])
            self.assertAlmostEqual(transformed["frames"][0]["faces"][0]["x"], 0.5, places=6)
            self.assertEqual(len(transformed["frames"]), 2)
            self.assertEqual(transformed["frames"][1]["timestamp_ms"], 33)
            self.assertAlmostEqual(transformed["video"]["duration_seconds"], 0.066667, places=6)

    def test_transform_expands_frames_when_speed_is_slower(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "tracked_detections.json"
            source.write_text(
                json.dumps(
                    {
                        "video": {"duration_seconds": 2.0, "fps": 2.0, "total_frames": 4},
                        "frames": [
                            {"frame_index": 0, "timestamp_ms": 0, "faces": [{"track_id": 1, "x": 0.0, "y": 0.0, "width": 0.2, "height": 0.2, "confidence": 1.0, "interpolated": False}]},
                            {"frame_index": 1, "timestamp_ms": 500, "faces": []},
                            {"frame_index": 2, "timestamp_ms": 1000, "faces": []},
                            {"frame_index": 3, "timestamp_ms": 1500, "faces": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            target = root / "transformed.json"
            transformed = transform_tracked_detections(source, target, speed=0.8)
            payload = json.loads(target.read_text(encoding="utf-8"))

            self.assertTrue(transformed["ok"])
            self.assertEqual(len(payload["frames"]), 5)
            self.assertEqual(payload["video"]["total_frames"], 5)
            self.assertAlmostEqual(payload["video"]["duration_seconds"], 2.5, places=6)


if __name__ == "__main__":
    unittest.main()
