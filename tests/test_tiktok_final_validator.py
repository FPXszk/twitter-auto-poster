from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_final_validator import validate_final_video


def _load_cli_module():
    entrypoint_path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok" / "validate_final_video.py"
    spec = importlib.util.spec_from_file_location("repo_tiktok_final_validator_cli_test", entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {entrypoint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TikTokFinalValidatorTest(unittest.TestCase):
    @staticmethod
    def _result(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_validate_final_video_writes_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference = root / "reference.mp4"
            candidate = root / "candidate.mp4"
            preview = root / "preview.png"
            reference.write_bytes(b"video")
            candidate.write_bytes(b"video")
            preview.write_bytes(b"png")
            coverage = root / "face-coverage-report.json"
            overlay = root / "overlay-summary.json"
            coverage.write_text(json.dumps({"ok": True, "coverage_ratio": 1.0}), encoding="utf-8")
            overlay.write_text(json.dumps({"interpolated_faces": 1}), encoding="utf-8")

            def fake_probe(path, *, ffprobe_json_path):
                Path(ffprobe_json_path).write_text("{}", encoding="utf-8")
                return {
                    "container": "mov,mp4,m4a,3gp,3g2,mj2",
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "pix_fmt": "yuv420p",
                    "width": 1080,
                    "height": 1920,
                    "fps": 30.0,
                    "duration_seconds": 13.75,
                    "size_bytes": 1000,
                }

            def dispatch(command, capture_output, text, check=False):
                if command[1] == "-v":
                    return self._result()
                raise AssertionError(f"unexpected command: {command}")

            with patch("tiktok_final_validator.probe_video", side_effect=fake_probe), patch(
                "tiktok_final_validator.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch("tiktok_final_validator.subprocess.run", side_effect=dispatch):
                payload = validate_final_video(
                    reference,
                    candidate,
                    coverage_report_path=coverage,
                    overlay_summary_path=overlay,
                    preview_image_path=preview,
                    output_dir=root / "validation",
                )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["coverage_ratio"], 1.0)
            self.assertTrue((root / "validation" / "validation_result.json").exists())
            self.assertEqual(payload["warnings"], ["interpolated faces present in overlay summary"])

    def test_cli_main_emits_json(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with patch.object(
                module,
                "validate_final_video",
                return_value={"ok": True, "candidate_video_path": f"{tmpdir}/candidate.mp4"},
            ):
                with redirect_stdout(stdout):
                    exit_code = module.main(
                        [
                            "--reference-video",
                            f"{tmpdir}/reference.mp4",
                            "--candidate-video",
                            f"{tmpdir}/candidate.mp4",
                        ]
                    )
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
