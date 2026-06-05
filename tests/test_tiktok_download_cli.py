from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


def _load_cli_module():
    entrypoint_path = Path(__file__).resolve().parents[1] / "scripts" / "tiktok" / "download_video.py"
    spec = importlib.util.spec_from_file_location("repo_tiktok_download_cli_test", entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {entrypoint_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TikTokDownloadCliTest(unittest.TestCase):
    def test_main_emits_json_and_returns_zero_on_success(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(
                module,
                "download_tiktok_video_job",
                return_value=module.helper_module.TikTokDownloadJob(
                    ok=True,
                    input_url="https://www.tiktok.com/@u/video/1",
                    resolved_url="https://www.tiktok.com/@u/video/1",
                    video_id="1",
                    uploader="u",
                    title="title",
                    output_path=str(Path(td) / "1" / "source.mp4"),
                    container="mp4",
                    video_codec="h264",
                    audio_codec="aac",
                    width=1080,
                    height=1920,
                    fps=30.0,
                    duration_seconds=15.0,
                    size_bytes=1234,
                    yt_dlp_version="2026.01.01",
                    download_strategy="strategy-1",
                    metadata_path=str(Path(td) / "1" / "metadata.json"),
                    command_log_path=str(Path(td) / "1" / "download.log"),
                    info_json_path=str(Path(td) / "1" / "source.info.json"),
                    ffprobe_json_path=str(Path(td) / "1" / "ffprobe.json"),
                    result_path=str(Path(td) / "1" / "result.json"),
                    dry_run=False,
                    reused_existing=False,
                    message="ok",
                ),
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = module.main(
                        ["--url", "https://www.tiktok.com/@u/video/1", "--output-dir", td]
                    )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["video_id"], "1")

    def test_main_returns_one_on_exception(self) -> None:
        module = _load_cli_module()
        with tempfile.TemporaryDirectory() as td:
            with patch.object(module, "download_tiktok_video_job", side_effect=RuntimeError("boom")):
                exit_code = module.main(
                    ["--url", "https://www.tiktok.com/@u/video/1", "--output-dir", td]
                )
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
