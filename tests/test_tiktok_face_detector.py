from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_face_detector import detect_faces_in_video


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

    def get(self, prop_id):
        return {
            3: 320,
            4: 240,
            5: 30.0,
            7: len(self._frames),
        }.get(prop_id, 0)

    def release(self):
        return None


class _FakeCv2:
    COLOR_BGR2RGB = 1
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    CAP_PROP_FRAME_COUNT = 7
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 0

    def __init__(self, frames):
        self._frames = frames

    def VideoCapture(self, _path):
        return _FakeCapture(self._frames)

    @staticmethod
    def cvtColor(frame, _code):
        return frame

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


def _fake_detection(x, y, width, height, score):
    return SimpleNamespace(
        score=[score],
        location_data=SimpleNamespace(
            relative_bounding_box=SimpleNamespace(
                xmin=x,
                ymin=y,
                width=width,
                height=height,
            )
        ),
    )


class _FakeDetector:
    def __init__(self, frame_detections):
        self._frame_detections = list(frame_detections)
        self._index = 0

    def process(self, _frame):
        detections = self._frame_detections[self._index]
        self._index += 1
        return SimpleNamespace(detections=detections)

    def close(self):
        return None


class _FakeYuNetDetector:
    def __init__(self, frame_detections):
        self._frame_detections = list(frame_detections)
        self._index = 0

    def process(self, _frame):
        detections = self._frame_detections[self._index]
        self._index += 1
        return detections

    def close(self):
        return None


class FaceDetectorTest(TestCase):
    def test_detect_faces_writes_outputs_and_sorts_faces(self) -> None:
        frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(2)]
        fake_cv2 = _FakeCv2(frames)
        fake_mp = SimpleNamespace(__version__="0.test")

        detector = _FakeDetector(
            [
                [
                    _fake_detection(0.6, 0.1, 0.2, 0.2, 0.9),
                    _fake_detection(0.1, 0.2, 0.3, 0.3, 0.8),
                ],
                [],
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "normalized.mp4"
            video_path.write_bytes(b"video")

            with patch("tiktok_face_detector._lazy_import_cv2", return_value=fake_cv2), patch(
                "tiktok_face_detector._lazy_import_mediapipe", return_value=fake_mp
            ):
                summary = detect_faces_in_video(
                    video_path,
                    Path(tmpdir) / "faces",
                    preview_interval=1,
                    detector_factory=lambda _min_confidence: detector,
                )

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["processed_frames"], 2)
            self.assertEqual(summary["frames_with_faces"], 1)
            self.assertEqual(summary["preview_images_written"], 2)

            detections = json.loads((Path(tmpdir) / "faces" / "detections.json").read_text(encoding="utf-8"))
            self.assertEqual(len(detections["frames"]), 2)
            first_frame_faces = detections["frames"][0]["faces"]
            self.assertEqual(len(first_frame_faces), 2)
            self.assertLess(first_frame_faces[0]["x"], first_frame_faces[1]["x"])
            self.assertTrue((Path(tmpdir) / "faces" / "preview" / "frame_000000.jpg").exists())

    def test_detect_faces_allows_zero_face_video(self) -> None:
        frames = [np.zeros((240, 320, 3), dtype=np.uint8)]
        fake_cv2 = _FakeCv2(frames)
        fake_mp = SimpleNamespace(__version__="0.test")
        detector = _FakeDetector([[]])

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "normalized.mp4"
            video_path.write_bytes(b"video")

            with patch("tiktok_face_detector._lazy_import_cv2", return_value=fake_cv2), patch(
                "tiktok_face_detector._lazy_import_mediapipe", return_value=fake_mp
            ):
                summary = detect_faces_in_video(
                    video_path,
                    Path(tmpdir) / "faces",
                    preview_interval=1,
                    detector_factory=lambda _min_confidence: detector,
                )

            self.assertTrue(summary["ok"])
            self.assertEqual(summary["total_detections"], 0)
            self.assertEqual(summary["frames_without_faces"], 1)

    def test_detect_faces_supports_direct_detector_face_dicts(self) -> None:
        frames = [np.zeros((240, 320, 3), dtype=np.uint8)]
        fake_cv2 = _FakeCv2(frames)
        fake_mp = SimpleNamespace(__version__="0.test")
        detector = _FakeYuNetDetector(
            [
                [
                    {
                        "x": 0.5,
                        "y": 0.1,
                        "width": 0.2,
                        "height": 0.3,
                        "confidence": 0.93,
                    }
                ]
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "normalized.mp4"
            video_path.write_bytes(b"video")

            with patch("tiktok_face_detector._lazy_import_cv2", return_value=fake_cv2), patch(
                "tiktok_face_detector._lazy_import_mediapipe", return_value=fake_mp
            ):
                summary = detect_faces_in_video(
                    video_path,
                    Path(tmpdir) / "faces",
                    preview_interval=1,
                    detector_factory=lambda _min_confidence: detector,
                )

            self.assertTrue(summary["ok"])
            detections = json.loads((Path(tmpdir) / "faces" / "detections.json").read_text(encoding="utf-8"))
            face = detections["frames"][0]["faces"][0]
            self.assertAlmostEqual(face["x"], 0.5, places=6)
            self.assertAlmostEqual(face["height"], 0.3, places=6)
            self.assertAlmostEqual(face["confidence"], 0.93, places=6)


if __name__ == "__main__":
    main()
