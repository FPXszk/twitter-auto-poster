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

from tiktok_similarity_variant import generate_similarity_variant


def _load_cli_module():
    entrypoint_path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok" / "generate_similarity_variant.py"
    spec = importlib.util.spec_from_file_location("repo_tiktok_similarity_variant_cli_test", entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {entrypoint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TikTokSimilarityVariantTest(unittest.TestCase):
    @staticmethod
    def _result(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def test_generate_variant_with_external_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "normalized.mp4"
            source.write_bytes(b"video")
            audio = root / "reference_audio.m4a"
            audio.write_bytes(b"audio")
            output = root / "variant" / "variant.mp4"

            def fake_probe(path, *, ffprobe_json_path):
                target = Path(path)
                Path(ffprobe_json_path).parent.mkdir(parents=True, exist_ok=True)
                Path(ffprobe_json_path).write_text("{}", encoding="utf-8")
                if target == source:
                    return {
                        "container": "mov,mp4,m4a,3gp,3g2,mj2",
                        "video_codec": "h264",
                        "audio_codec": "aac",
                        "pix_fmt": "yuv420p",
                        "width": 1080,
                        "height": 1920,
                        "fps": 30.0,
                        "duration_seconds": 15.0,
                        "size_bytes": 1000,
                    }
                if target == audio:
                    return {
                        "container": "mov,mp4,m4a,3gp,3g2,mj2",
                        "video_codec": "",
                        "audio_codec": "aac",
                        "pix_fmt": "",
                        "width": 0,
                        "height": 0,
                        "fps": 0.0,
                        "duration_seconds": 15.0,
                        "size_bytes": 500,
                    }
                return {
                    "container": "mov,mp4,m4a,3gp,3g2,mj2",
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "pix_fmt": "yuv420p",
                    "width": 1080,
                    "height": 1920,
                    "fps": 30.0,
                    "duration_seconds": 18.75,
                    "size_bytes": 2000,
                }

            def dispatch(command, capture_output, text, check=False):
                if command[1] == "-y":
                    Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                    Path(command[-1]).write_bytes(b"variant")
                    return self._result()
                if command[1] == "-v":
                    return self._result()
                raise AssertionError(f"unexpected command: {command}")

            with patch("tiktok_similarity_variant.probe_video", side_effect=fake_probe), patch(
                "tiktok_similarity_variant.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"
            ), patch("tiktok_similarity_variant.subprocess.run", side_effect=dispatch) as mock_run:
                payload = generate_similarity_variant(
                    source,
                    output,
                    audio_input=audio,
                )

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["used_external_audio"])
            ffmpeg_call = mock_run.call_args_list[0].args[0]
            self.assertIn("-filter:a", ffmpeg_call)
            self.assertIn("atempo=0.800000", ffmpeg_call)
            self.assertTrue(output.exists())
            self.assertTrue((output.parent / "variant-summary.json").exists())

    def test_generate_variant_rejects_invalid_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "normalized.mp4"
            source.write_bytes(b"video")
            with self.assertRaises(ValueError):
                generate_similarity_variant(source, Path(tmpdir) / "out.mp4", speed=0.0)

    def test_cli_main_uses_config_defaults(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "variant.json"
            config_path.write_text(json.dumps({"speed": 0.9, "mosaic_block_size": 12}), encoding="utf-8")
            stdout = io.StringIO()
            with patch.object(
                module,
                "generate_similarity_variant",
                return_value={"ok": True, "output_video_path": str(root / "out.mp4")},
            ) as mock_generate:
                with redirect_stdout(stdout):
                    exit_code = module.main(
                        [
                            "--input",
                            str(root / "in.mp4"),
                            "--output",
                            str(root / "out.mp4"),
                            "--config",
                            str(config_path),
                        ]
                    )
        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_generate.call_args.kwargs["speed"], 0.9)
        self.assertEqual(mock_generate.call_args.kwargs["mosaic_block_size"], 12)


if __name__ == "__main__":
    unittest.main()
