from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_downloader import (
    ALLOWED_TIKTOK_HOSTS,
    TikTokDownloadJob,
    download_tiktok_video,
    download_tiktok_video_job,
    validate_tiktok_url,
)


class ValidateTikTokUrlTest(TestCase):
    def test_valid_tiktok_url_passes(self) -> None:
        url = "https://www.tiktok.com/@user/video/1234567890"
        result = validate_tiktok_url(url)
        self.assertEqual(result, url)

    def test_mobile_tiktok_url_passes(self) -> None:
        url = "https://m.tiktok.com/@user/video/1234567890"
        result = validate_tiktok_url(url)
        self.assertEqual(result, url)

    def test_vm_tiktok_url_passes(self) -> None:
        url = "https://vm.tiktok.com/abc123/"
        result = validate_tiktok_url(url)
        self.assertEqual(result, url)

    def test_vt_tiktok_url_passes(self) -> None:
        url = "https://vt.tiktok.com/abc123/"
        result = validate_tiktok_url(url)
        self.assertEqual(result, url)

    def test_non_tiktok_url_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_tiktok_url("https://evil.com/video/123")
        self.assertIn("TikTok", str(ctx.exception))

    def test_http_url_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_tiktok_url("http://www.tiktok.com/@user/video/123")

    def test_empty_url_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_tiktok_url("")

    def test_allowed_hosts_constant(self) -> None:
        self.assertIn("www.tiktok.com", ALLOWED_TIKTOK_HOSTS)
        self.assertIn("m.tiktok.com", ALLOWED_TIKTOK_HOSTS)
        self.assertIn("vm.tiktok.com", ALLOWED_TIKTOK_HOSTS)
        self.assertIn("vt.tiktok.com", ALLOWED_TIKTOK_HOSTS)


class DownloadTikTokVideoJobTest(TestCase):
    def _dispatch_subprocess(self, command, capture_output, text, check=False):
        if command[1] == "--version":
            return self._result(stdout="2026.01.01\n")
        if command[0].endswith("ffmpeg") and "-version" in command:
            return self._result(stdout="ffmpeg version 7.0\n")

        if "--dump-single-json" in command:
            return self._result(
                stdout=json.dumps(
                    {
                        "id": "video-123",
                        "webpage_url": "https://www.tiktok.com/@user/video/123",
                        "uploader": "user",
                        "title": "hello world",
                    }
                )
            )

        output_index = command.index("-o") + 1
        output_template = Path(command[output_index])
        output_template.parent.mkdir(parents=True, exist_ok=True)
        (output_template.parent / "source.mp4").write_bytes(b"\x00" * 128)
        (output_template.parent / "source.info.json").write_text("{}", encoding="utf-8")
        return self._result(stdout='{"id":"video-123"}')

    def _dispatch_subprocess_webm(self, command, capture_output, text, check=False):
        if command[1] == "--version":
            return self._result(stdout="2026.01.01\n")
        if command[0].endswith("ffmpeg") and "-version" in command:
            return self._result(stdout="ffmpeg version 7.0\n")

        if "--dump-single-json" in command:
            return self._result(
                stdout=json.dumps(
                    {
                        "id": "video-123",
                        "webpage_url": "https://www.tiktok.com/@user/video/123",
                        "uploader": "user",
                        "title": "hello world",
                    }
                )
            )

        if command[0].endswith("ffmpeg"):
            output_path = Path(command[-1])
            output_path.write_bytes(b"\x00" * 128)
            return self._result()

        output_index = command.index("-o") + 1
        output_template = Path(command[output_index])
        output_template.parent.mkdir(parents=True, exist_ok=True)
        (output_template.parent / "source.webm").write_bytes(b"\x00" * 128)
        (output_template.parent / "source.info.json").write_text("{}", encoding="utf-8")
        return self._result(stdout='{"id":"video-123"}')

    @staticmethod
    def _result(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    @patch("tiktok_downloader._ffprobe_details")
    @patch("tiktok_downloader.ensure_normalized_video")
    @patch("tiktok_downloader.validate_video_path")
    @patch("tiktok_downloader.subprocess.run")
    def test_job_writes_metadata_and_result(
        self,
        mock_run: MagicMock,
        mock_validate: MagicMock,
        mock_normalize: MagicMock,
        mock_ffprobe: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_run.side_effect = self._dispatch_subprocess
            expected = Path(tmpdir) / "video-123" / "normalized.mp4"
            mock_validate.side_effect = lambda path, max_size_bytes=0: Path(path)
            mock_ffprobe.return_value = {
                "container": "mp4",
                "video_codec": "h264",
                "audio_codec": "aac",
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "duration_seconds": 12.3,
                "size_bytes": 128,
            }
            mock_normalize.return_value = {
                "source_path": str(Path(tmpdir) / "video-123" / "source.mp4"),
                "normalized_path": str(expected),
                "source_ffprobe_json_path": str(Path(tmpdir) / "video-123" / "ffprobe.json"),
                "normalized_ffprobe_json_path": str(Path(tmpdir) / "video-123" / "normalized.ffprobe.json"),
                "normalize_log_path": str(Path(tmpdir) / "video-123" / "normalize.log"),
                "normalized_container": "mp4",
                "normalized_video_codec": "h264",
                "normalized_audio_codec": "aac",
                "normalized_width": 1080,
                "normalized_height": 1920,
                "normalized_fps": 30.0,
                "normalized_duration_seconds": 12.3,
                "normalized_size_bytes": 128,
            }

            with patch("tiktok_downloader.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
                result = download_tiktok_video_job(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                )

            self.assertTrue(result.ok)
            self.assertEqual(Path(result.output_path), expected)
            self.assertEqual(Path(result.source_path), Path(tmpdir) / "video-123" / "source.mp4")
            self.assertTrue((Path(tmpdir) / "video-123" / "metadata.json").exists())
            self.assertTrue((Path(tmpdir) / "video-123" / "result.json").exists())
            self.assertEqual(result.download_strategy, "strategy-1")

    @patch("tiktok_downloader.subprocess.run")
    def test_job_rejects_missing_ytdlp(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("tiktok_downloader.shutil.which", return_value=None), patch(
                "tiktok_downloader.importlib_util.find_spec", return_value=None
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    download_tiktok_video_job(
                        "https://www.tiktok.com/@user/video/123",
                        tmpdir,
                    )
        self.assertIn("yt-dlp", str(ctx.exception))
        mock_run.assert_not_called()

    @patch("tiktok_downloader.subprocess.run")
    def test_job_returns_metadata_only_for_dry_run(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_run.side_effect = [
                self._result(stdout="2026.01.01\n"),
                self._result(
                    stdout=json.dumps(
                        {
                            "id": "video-123",
                            "webpage_url": "https://www.tiktok.com/@user/video/123",
                            "uploader": "user",
                            "title": "hello world",
                        }
                    )
                ),
                self._result(stdout="ffmpeg version 7.0\n"),
            ]

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                result = download_tiktok_video_job(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                    dry_run=True,
                )

            self.assertTrue(result.ok)
            self.assertTrue(result.dry_run)
            self.assertEqual(result.output_path, "")
            self.assertEqual(result.download_strategy, "metadata-only")

    @patch("tiktok_downloader._ffprobe_details")
    @patch("tiktok_downloader.ensure_normalized_video")
    @patch("tiktok_downloader.validate_video_path")
    @patch("tiktok_downloader.subprocess.run")
    def test_job_normalizes_webm_to_mp4(
        self,
        mock_run: MagicMock,
        mock_validate: MagicMock,
        mock_normalize: MagicMock,
        mock_ffprobe: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_run.side_effect = self._dispatch_subprocess_webm
            mock_validate.side_effect = lambda path, max_size_bytes=0: Path(path)
            mock_ffprobe.return_value = {
                "container": "mp4",
                "video_codec": "h264",
                "audio_codec": "aac",
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "duration_seconds": 12.3,
                "size_bytes": 128,
            }
            mock_normalize.return_value = {
                "source_path": str(Path(tmpdir) / "video-123" / "source.mp4"),
                "normalized_path": str(Path(tmpdir) / "video-123" / "normalized.mp4"),
                "source_ffprobe_json_path": str(Path(tmpdir) / "video-123" / "ffprobe.json"),
                "normalized_ffprobe_json_path": str(Path(tmpdir) / "video-123" / "normalized.ffprobe.json"),
                "normalize_log_path": str(Path(tmpdir) / "video-123" / "normalize.log"),
                "normalized_container": "mp4",
                "normalized_video_codec": "h264",
                "normalized_audio_codec": "aac",
                "normalized_width": 1080,
                "normalized_height": 1920,
                "normalized_fps": 30.0,
                "normalized_duration_seconds": 12.3,
                "normalized_size_bytes": 128,
            }

            with patch("tiktok_downloader.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
                result = download_tiktok_video_job(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                )

            self.assertTrue(result.ok)
            self.assertEqual(Path(result.output_path).suffix.lower(), ".mp4")
            self.assertEqual(Path(result.output_path).name, "normalized.mp4")
            metadata = json.loads((Path(tmpdir) / "video-123" / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["normalized_from_ext"], ".webm")

    @patch("tiktok_downloader._ffprobe_details")
    @patch("tiktok_downloader.ensure_normalized_video")
    @patch("tiktok_downloader.validate_video_path")
    @patch("tiktok_downloader.subprocess.run")
    def test_job_reuses_existing_source_mp4(
        self,
        mock_run: MagicMock,
        mock_validate: MagicMock,
        mock_normalize: MagicMock,
        mock_ffprobe: MagicMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            job_dir = root / "video-123"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "source.mp4").write_bytes(b"ok")
            (job_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "video_id": "video-123",
                        "resolved_url": "https://www.tiktok.com/@user/video/123",
                        "uploader": "user",
                        "title": "hello world",
                    }
                ),
                encoding="utf-8",
            )

            mock_run.side_effect = [
                self._result(stdout="2026.01.01\n"),
                self._result(
                    stdout=json.dumps(
                        {
                            "id": "video-123",
                            "webpage_url": "https://www.tiktok.com/@user/video/123",
                            "uploader": "user",
                            "title": "hello world",
                        }
                    )
                ),
                self._result(stdout="ffmpeg version 7.0\n"),
            ]
            mock_validate.side_effect = lambda path, max_size_bytes=0: Path(path)
            mock_ffprobe.return_value = {
                "container": "mp4",
                "video_codec": "h264",
                "audio_codec": "aac",
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "duration_seconds": 12.3,
                "size_bytes": 2,
            }
            mock_normalize.return_value = {
                "source_path": str(job_dir / "source.mp4"),
                "normalized_path": str(job_dir / "normalized.mp4"),
                "source_ffprobe_json_path": str(job_dir / "ffprobe.json"),
                "normalized_ffprobe_json_path": str(job_dir / "normalized.ffprobe.json"),
                "normalize_log_path": str(job_dir / "normalize.log"),
                "normalized_container": "mp4",
                "normalized_video_codec": "h264",
                "normalized_audio_codec": "aac",
                "normalized_width": 1080,
                "normalized_height": 1920,
                "normalized_fps": 30.0,
                "normalized_duration_seconds": 12.3,
                "normalized_size_bytes": 2,
            }

            with patch("tiktok_downloader.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
                result = download_tiktok_video_job(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                )

            self.assertTrue(result.ok)
            self.assertTrue(result.reused_existing)
            self.assertEqual(result.download_strategy, "reuse")
            self.assertEqual(Path(result.output_path), job_dir / "normalized.mp4")

    @patch("tiktok_downloader.subprocess.run")
    def test_job_masks_cookie_file_in_log(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_run.side_effect = [
                self._result(stdout="2026.01.01\n"),
                self._result(
                    stdout=json.dumps(
                        {
                            "id": "video-123",
                            "webpage_url": "https://www.tiktok.com/@user/video/123",
                            "uploader": "user",
                            "title": "hello world",
                        }
                    )
                ),
                self._result(stdout="ffmpeg version 7.0\n"),
                self._result(returncode=1, stderr="login required"),
                self._result(returncode=1, stderr="login required"),
                self._result(returncode=1, stderr="login required"),
            ]

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                result = download_tiktok_video_job(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                    cookies_file="/secure/path/cookies.txt",
                )

            self.assertFalse(result.ok)
            log_path = Path(result.command_log_path)
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("--cookies ***", log_text)
            self.assertNotIn("/secure/path/cookies.txt", log_text)

    @patch("tiktok_downloader.download_tiktok_video_job")
    def test_legacy_download_function_returns_output_path(self, mock_job: MagicMock) -> None:
        mock_job.return_value = TikTokDownloadJob(
            ok=True,
            input_url="https://www.tiktok.com/@u/video/1",
            resolved_url="https://www.tiktok.com/@u/video/1",
            video_id="1",
            uploader="u",
            title="title",
            output_path="/tmp/source.mp4",
            container="mp4",
            video_codec="h264",
            audio_codec="aac",
            width=1080,
            height=1920,
            fps=30.0,
            duration_seconds=1.0,
            size_bytes=1,
            yt_dlp_version="2026.01.01",
            download_strategy="strategy-1",
            metadata_path="/tmp/metadata.json",
            command_log_path="/tmp/download.log",
            info_json_path="/tmp/source.info.json",
            ffprobe_json_path="/tmp/ffprobe.json",
            result_path="/tmp/result.json",
            dry_run=False,
            reused_existing=False,
        )

        result = download_tiktok_video("https://www.tiktok.com/@u/video/1", "/tmp")
        self.assertEqual(result, Path("/tmp/source.mp4"))


if __name__ == "__main__":
    main()
