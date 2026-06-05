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
from PIL import Image

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_face_overlay import overlay_faces_on_video


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
    def __init__(self, frames):
        self._frames = frames
        self.saved_frames: dict[str, np.ndarray] = {}

    def VideoCapture(self, _path):
        return _FakeCapture(self._frames)

    def imwrite(self, path, frame):
        self.saved_frames[str(path)] = frame.copy()
        Path(path).write_bytes(b"frame")
        return True


def _write_tracked_detections(root: Path, *, video_path: Path, frames: list[dict]) -> Path:
    tracked_path = root / "tracks" / "tracked_detections.json"
    tracked_path.parent.mkdir(parents=True, exist_ok=True)
    tracked_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "video_path": str(video_path),
                "video_sha256": "abc123",
                "video": {
                    "width": 64,
                    "height": 64,
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
    return tracked_path


def _load_cli_module():
    entrypoint_path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok" / "overlay_faces.py"
    spec = importlib.util.spec_from_file_location("repo_tiktok_overlay_faces_cli_test", entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {entrypoint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FaceOverlayTest(TestCase):
    @staticmethod
    def _result(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_overlay_faces_writes_summary_and_coverage(self) -> None:
        frames = [np.zeros((64, 64, 3), dtype=np.uint8) for _ in range(2)]
        fake_cv2 = _FakeCv2(frames)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "normalized.mp4"
            source.write_bytes(b"video")
            stamp = root / "stamp.png"
            Image.new("RGBA", (12, 12), (255, 0, 0, 200)).save(stamp)
            tracked = _write_tracked_detections(
                root,
                video_path=source,
                frames=[
                    {
                        "frame_index": 0,
                        "timestamp_ms": 0,
                        "faces": [{"track_id": 1, "x": 0.2, "y": 0.2, "width": 0.2, "height": 0.2, "confidence": 0.9, "interpolated": False}],
                    },
                    {
                        "frame_index": 1,
                        "timestamp_ms": 33,
                        "faces": [{"track_id": 1, "x": 0.22, "y": 0.2, "width": 0.2, "height": 0.2, "confidence": 0.9, "interpolated": True}],
                    },
                ],
            )

            def dispatch(command, capture_output, text, check=False):
                if command[0].endswith("ffprobe"):
                    target = command[-1]
                    payload = {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "pix_fmt": "yuv420p",
                                "width": 64,
                                "height": 64,
                                "avg_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "0.066667", "size": "1234"},
                    }
                    return self._result(stdout=json.dumps(payload))
                if command[0].endswith("ffmpeg") and command[1] == "-y":
                    Path(command[-1]).write_bytes(b"edited")
                    return self._result()
                if command[0].endswith("ffmpeg") and command[1] == "-v":
                    return self._result()
                raise AssertionError(f"unexpected command: {command}")

            with patch("tiktok_face_overlay._lazy_import_cv2", return_value=fake_cv2), patch(
                "tiktok_face_overlay.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch("tiktok_face_overlay.subprocess.run", side_effect=dispatch):
                summary = overlay_faces_on_video(source, tracked, stamp, root / "edited" / "edited.mp4")

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["frames_written"], 2)
            self.assertEqual(summary["faces_expected"], 2)
            self.assertEqual(summary["faces_covered"], 2)
            self.assertEqual(summary["interpolated_faces"], 1)
            self.assertTrue((root / "edited" / "overlay-summary.json").exists())
            self.assertTrue((root / "edited" / "face-coverage-report.json").exists())
            self.assertTrue((root / "edited" / "edited.mp4").exists())

    def test_overlay_changes_frame_pixels(self) -> None:
        frames = [np.zeros((64, 64, 3), dtype=np.uint8)]
        fake_cv2 = _FakeCv2(frames)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "normalized.mp4"
            source.write_bytes(b"video")
            stamp = root / "stamp.png"
            Image.new("RGBA", (8, 8), (0, 255, 0, 255)).save(stamp)
            tracked = _write_tracked_detections(
                root,
                video_path=source,
                frames=[
                    {
                        "frame_index": 0,
                        "timestamp_ms": 0,
                        "faces": [{"track_id": 1, "x": 0.25, "y": 0.25, "width": 0.25, "height": 0.25, "confidence": 0.9, "interpolated": False}],
                    }
                ],
            )

            def dispatch(command, capture_output, text, check=False):
                if command[0].endswith("ffprobe"):
                    payload = {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "pix_fmt": "yuv420p",
                                "width": 64,
                                "height": 64,
                                "avg_frame_rate": "30/1",
                            }
                        ],
                        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "0.033333", "size": "1234"},
                    }
                    return self._result(stdout=json.dumps(payload))
                if command[0].endswith("ffmpeg") and command[1] == "-y":
                    Path(command[-1]).write_bytes(b"edited")
                    return self._result()
                if command[0].endswith("ffmpeg") and command[1] == "-v":
                    return self._result()
                raise AssertionError(f"unexpected command: {command}")

            with patch("tiktok_face_overlay._lazy_import_cv2", return_value=fake_cv2), patch(
                "tiktok_face_overlay.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch("tiktok_face_overlay.subprocess.run", side_effect=dispatch):
                overlay_faces_on_video(source, tracked, stamp, root / "edited" / "edited.mp4")

            saved_frame = next(iter(fake_cv2.saved_frames.values()))
            self.assertGreater(int(saved_frame[:, :, 1].sum()), 0)


class FaceOverlayCliTest(TestCase):
    def test_main_emits_json_and_returns_zero_on_success(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(module, "overlay_faces_on_video", return_value={"ok": True, "coverage_ratio": 1.0}):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = module.main(
                        [
                            "--input",
                            str(Path(td) / "normalized.mp4"),
                            "--detections",
                            str(Path(td) / "tracked_detections.json"),
                            "--stamp",
                            str(Path(td) / "stamp.png"),
                            "--output",
                            str(Path(td) / "edited.mp4"),
                        ]
                    )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["coverage_ratio"], 1.0)

    def test_main_returns_one_on_exception(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(module, "overlay_faces_on_video", side_effect=RuntimeError("boom")):
                exit_code = module.main(
                    [
                        "--input",
                        str(Path(td) / "normalized.mp4"),
                        "--detections",
                        str(Path(td) / "tracked_detections.json"),
                        "--stamp",
                        str(Path(td) / "stamp.png"),
                        "--output",
                        str(Path(td) / "edited.mp4"),
                    ]
                )
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    main()
