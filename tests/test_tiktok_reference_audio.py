from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_reference_audio import extract_reference_audio_from_tiktok


def _load_cli_module():
    entrypoint_path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok" / "extract_reference_audio.py"
    spec = importlib.util.spec_from_file_location("repo_tiktok_reference_audio_cli_test", entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {entrypoint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TikTokReferenceAudioTest(unittest.TestCase):
    @staticmethod
    def _result(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_extract_reference_audio_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "abc123"
            source_dir.mkdir(parents=True, exist_ok=True)
            source = source_dir / "normalized.mp4"
            source.write_bytes(b"video")

            download_job = SimpleNamespace(
                ok=True,
                input_url="https://www.tiktok.com/@u/video/1",
                resolved_url="https://www.tiktok.com/@u/video/1",
                video_id="abc123",
                output_path=str(source),
                result_path=str(source_dir / "result.json"),
                message="ok",
            )

            def fake_probe(path, *, ffprobe_json_path):
                target = Path(path)
                Path(ffprobe_json_path).write_text("{}", encoding="utf-8")
                if target.name == "normalized.mp4":
                    return {"audio_codec": "aac", "duration_seconds": 15.0, "size_bytes": 1000}
                return {"audio_codec": "aac", "duration_seconds": 15.0, "size_bytes": 555}

            def dispatch(command, capture_output, text, check=False):
                if command[1] == "-y":
                    Path(command[-1]).write_bytes(b"audio")
                    return self._result()
                if command[1] == "-v":
                    return self._result()
                raise AssertionError(f"unexpected command: {command}")

            with patch("tiktok_reference_audio.download_tiktok_video_job", return_value=download_job), patch(
                "tiktok_reference_audio.probe_video", side_effect=fake_probe
            ), patch("tiktok_reference_audio.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), patch(
                "tiktok_reference_audio.subprocess.run", side_effect=dispatch
            ):
                payload = extract_reference_audio_from_tiktok(
                    "https://www.tiktok.com/@u/video/1",
                    root,
                )

            self.assertTrue(payload.ok)
            self.assertTrue((source_dir / "reference_audio.m4a").exists())
            self.assertTrue((source_dir / "reference_audio.json").exists())
            self.assertEqual(payload.audio_codec, "aac")

    def test_cli_main_emits_json(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_job = module.helper_module.TikTokReferenceAudioJob(
                ok=True,
                input_url="https://www.tiktok.com/@u/video/1",
                resolved_url="https://www.tiktok.com/@u/video/1",
                video_id="abc123",
                output_dir=tmpdir,
                source_video_path=f"{tmpdir}/normalized.mp4",
                audio_path=f"{tmpdir}/reference_audio.m4a",
                audio_ffprobe_json_path=f"{tmpdir}/reference_audio.ffprobe.json",
                processing_log_path=f"{tmpdir}/reference_audio.log",
                summary_path=f"{tmpdir}/reference_audio.json",
                audio_codec="aac",
                duration_seconds=15.0,
                size_bytes=1234,
                download_result_path=f"{tmpdir}/result.json",
                message="ok",
            )
            stdout = io.StringIO()
            with patch.object(module, "extract_reference_audio_from_tiktok", return_value=fake_job):
                with redirect_stdout(stdout):
                    exit_code = module.main(
                        [
                            "--url",
                            "https://www.tiktok.com/@u/video/1",
                            "--output-dir",
                            tmpdir,
                        ]
                    )
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["video_id"], "abc123")


if __name__ == "__main__":
    unittest.main()
