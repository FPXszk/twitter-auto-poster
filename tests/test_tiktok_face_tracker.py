from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_face_tracker import track_faces_in_detections


class _FakeCapture:
    def __init__(self, frames):
        self._frames = list(frames)
        self._index = 0

    def isOpened(self):
        return True

    def read(self):
        if self._index >= len(self._frames):
            return False, None
        frame = self._frames[self._index]
        self._index += 1
        return True, frame.copy()

    def release(self):
        return None


class _FakeCv2:
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 0

    def __init__(self, frames):
        self._frames = frames

    def VideoCapture(self, _path):
        return _FakeCapture(self._frames)

    @staticmethod
    def rectangle(*_args, **_kwargs):
        return None

    @staticmethod
    def putText(*_args, **_kwargs):
        return None

    @staticmethod
    def imwrite(path, _frame):
        Path(path).write_bytes(b"preview")
        return True


def _write_detections(root: Path, *, frames: list[dict], video_path: Path) -> Path:
    detections_path = root / "faces" / "detections.json"
    detections_path.parent.mkdir(parents=True, exist_ok=True)
    detections_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "video_path": str(video_path),
                "video_sha256": "abc123",
                "video": {
                    "width": 320,
                    "height": 240,
                    "fps": 30.0,
                    "duration_seconds": round(len(frames) / 30.0, 6),
                    "total_frames": len(frames),
                },
                "frames": frames,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return detections_path


def _load_cli_module():
    entrypoint_path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok" / "track_faces.py"
    spec = importlib.util.spec_from_file_location("repo_tiktok_track_faces_cli_test", entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {entrypoint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FaceTrackerTest(TestCase):
    def test_track_faces_assigns_stable_ids_and_fills_short_gap(self) -> None:
        frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(3)]
        fake_cv2 = _FakeCv2(frames)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            video_path = root / "normalized.mp4"
            video_path.write_bytes(b"video")
            detections_path = _write_detections(
                root,
                video_path=video_path,
                frames=[
                    {
                        "frame_index": 0,
                        "timestamp_ms": 0,
                        "faces": [{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2, "confidence": 0.95}],
                    },
                    {"frame_index": 1, "timestamp_ms": 33, "faces": []},
                    {
                        "frame_index": 2,
                        "timestamp_ms": 67,
                        "faces": [{"x": 0.14, "y": 0.1, "width": 0.2, "height": 0.2, "confidence": 0.9}],
                    },
                ],
            )

            with patch("tiktok_face_tracker._lazy_import_cv2", return_value=fake_cv2):
                summary = track_faces_in_detections(
                    detections_path,
                    root / "tracked",
                    preview_interval=1,
                )

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["track_count"], 1)
            self.assertEqual(summary["interpolated_faces"], 1)
            self.assertEqual(summary["preview_images_written"], 3)

            tracked = json.loads((root / "tracked" / "tracked_detections.json").read_text(encoding="utf-8"))
            frame0 = tracked["frames"][0]["faces"][0]
            frame1 = tracked["frames"][1]["faces"][0]
            frame2 = tracked["frames"][2]["faces"][0]
            self.assertEqual(frame0["track_id"], 1)
            self.assertEqual(frame1["track_id"], 1)
            self.assertEqual(frame2["track_id"], 1)
            self.assertFalse(frame0["interpolated"])
            self.assertTrue(frame1["interpolated"])
            self.assertFalse(frame2["interpolated"])
            self.assertAlmostEqual(frame2["x"], 0.112, places=6)

    def test_track_faces_keeps_multiple_tracks_separate(self) -> None:
        frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(2)]
        fake_cv2 = _FakeCv2(frames)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            video_path = root / "normalized.mp4"
            video_path.write_bytes(b"video")
            detections_path = _write_detections(
                root,
                video_path=video_path,
                frames=[
                    {
                        "frame_index": 0,
                        "timestamp_ms": 0,
                        "faces": [
                            {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2, "confidence": 0.95},
                            {"x": 0.6, "y": 0.1, "width": 0.2, "height": 0.2, "confidence": 0.92},
                        ],
                    },
                    {
                        "frame_index": 1,
                        "timestamp_ms": 33,
                        "faces": [
                            {"x": 0.11, "y": 0.1, "width": 0.2, "height": 0.2, "confidence": 0.96},
                            {"x": 0.59, "y": 0.1, "width": 0.2, "height": 0.2, "confidence": 0.91},
                        ],
                    },
                ],
            )

            with patch("tiktok_face_tracker._lazy_import_cv2", return_value=fake_cv2):
                summary = track_faces_in_detections(detections_path, root / "tracked", preview_interval=1)

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["track_count"], 2)
            tracked = json.loads((root / "tracked" / "tracked_detections.json").read_text(encoding="utf-8"))
            first_ids = [face["track_id"] for face in tracked["frames"][0]["faces"]]
            second_ids = [face["track_id"] for face in tracked["frames"][1]["faces"]]
            self.assertEqual(first_ids, [1, 2])
            self.assertEqual(second_ids, [1, 2])


class FaceTrackerCliTest(TestCase):
    def test_main_emits_json_and_returns_zero_on_success(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(module, "track_faces_in_detections", return_value={"ok": True, "track_count": 1}):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = module.main(
                        ["--detections", str(Path(td) / "detections.json"), "--output-dir", td]
                    )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["track_count"], 1)

    def test_main_returns_one_on_exception(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(module, "track_faces_in_detections", side_effect=RuntimeError("boom")):
                exit_code = module.main(
                    ["--detections", str(Path(td) / "detections.json"), "--output-dir", td]
                )
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    main()
