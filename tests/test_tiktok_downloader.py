from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_downloader import ALLOWED_TIKTOK_HOSTS, download_tiktok_video, validate_tiktok_url


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


class DownloadTikTokVideoTest(TestCase):
    @staticmethod
    def _fake_run_ok(command, capture_output, text, check=False):
        """Simulate yt-dlp writing a video.mp4 into the output template dir."""
        output_template = Path(command[5])
        output_template.parent.mkdir(parents=True, exist_ok=True)
        (output_template.parent / "video.mp4").write_bytes(b"\x00" * 100)

        class Result:
            returncode = 0
            stderr = ""
            stdout = ""

        return Result()

    @patch("tiktok_downloader.validate_video_path")
    @patch("tiktok_downloader.subprocess.run")
    def test_ytdlp_called_with_correct_args(
        self, mock_run: MagicMock, mock_validate: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_run.side_effect = self._fake_run_ok
            mock_validate.return_value = Path(tmpdir) / "validated.mp4"

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                download_tiktok_video(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                )

            cmd = mock_run.call_args[0][0]
            self.assertIn("yt-dlp", cmd[0])

    @patch("tiktok_downloader.validate_video_path")
    @patch("tiktok_downloader.subprocess.run")
    def test_valid_mp4_after_download_passes(
        self, mock_run: MagicMock, mock_validate: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            expected = Path(tmpdir) / "validated.mp4"
            mock_run.side_effect = self._fake_run_ok
            mock_validate.return_value = expected

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                result = download_tiktok_video(
                    "https://www.tiktok.com/@user/video/123",
                    tmpdir,
                )
            self.assertEqual(result, expected)

    @patch("tiktok_downloader.subprocess.run")
    def test_ytdlp_failure_raises(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:

            class FailResult:
                returncode = 1
                stderr = "error"
                stdout = ""

            mock_run.return_value = FailResult()

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                with self.assertRaises(RuntimeError) as ctx:
                    download_tiktok_video(
                        "https://www.tiktok.com/@user/video/123",
                        tmpdir,
                    )
            self.assertIn("yt-dlp", str(ctx.exception))

    @patch("tiktok_downloader.validate_video_path")
    @patch("tiktok_downloader.subprocess.run")
    def test_oversized_file_rejected_and_cleaned(
        self, mock_run: MagicMock, mock_validate: MagicMock
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_run.side_effect = self._fake_run_ok
            mock_validate.side_effect = ValueError("video file size exceeds limit")

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                with self.assertRaises(ValueError):
                    download_tiktok_video(
                        "https://www.tiktok.com/@user/video/123",
                        tmpdir,
                        max_size_bytes=50,
                    )

    @patch("tiktok_downloader.subprocess.run")
    def test_empty_output_dir_after_failed_download(self, mock_run: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:

            class FailResult:
                returncode = 1
                stderr = "boom"
                stdout = ""

            mock_run.return_value = FailResult()

            with patch("tiktok_downloader.shutil.which", return_value="/usr/bin/yt-dlp"):
                with self.assertRaises(RuntimeError):
                    download_tiktok_video(
                        "https://www.tiktok.com/@user/video/123",
                        tmpdir,
                    )
            remaining = list(Path(tmpdir).iterdir())
            self.assertEqual(remaining, [])


if __name__ == "__main__":
    main()
