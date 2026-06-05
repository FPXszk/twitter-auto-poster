from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_video_normalizer import ensure_normalized_video, is_normalized_video


class VideoNormalizerTest(TestCase):
    @staticmethod
    def _result(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
        class Result:
            pass

        result = Result()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    def _dispatch_subprocess(self, command, capture_output, text, check=False):
        if command[0].endswith("ffprobe"):
            target = command[-1]
            if target.endswith("source.mp4"):
                payload = {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "hevc",
                            "pix_fmt": "yuv420p",
                            "width": 1080,
                            "height": 1920,
                            "avg_frame_rate": "30/1",
                        },
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                    "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "5.0", "size": "100"},
                }
                return self._result(stdout=json.dumps(payload))

            payload = {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 1080,
                        "height": 1920,
                        "avg_frame_rate": "30/1",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "5.0", "size": "120"},
            }
            return self._result(stdout=json.dumps(payload))

        if command[0].endswith("ffmpeg") and command[1] == "-y":
            Path(command[-1]).write_bytes(b"normalized")
            return self._result()

        if command[0].endswith("ffmpeg") and command[1] == "-v":
            return self._result()

        raise AssertionError(f"unexpected command: {command}")

    def test_is_normalized_video_accepts_h264_aac_yuv420p_mp4(self) -> None:
        self.assertTrue(
            is_normalized_video(
                {
                    "container": "mov,mp4,m4a,3gp,3g2,mj2",
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "pix_fmt": "yuv420p",
                }
            )
        )

    @patch("tiktok_video_normalizer.subprocess.run")
    def test_ensure_normalized_video_reencodes_hevc_source(self, mock_run) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.mp4"
            source.write_bytes(b"source")
            mock_run.side_effect = self._dispatch_subprocess

            with patch("tiktok_video_normalizer.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"):
                result = ensure_normalized_video(
                    source,
                    root / "normalized.mp4",
                    source_ffprobe_json_path=root / "ffprobe.json",
                    normalized_ffprobe_json_path=root / "normalized.ffprobe.json",
                    log_path=root / "normalize.log",
                )

            self.assertEqual(result["normalization_reason"], "re-encoded")
            self.assertTrue(result["normalization_applied"])
            self.assertEqual(result["normalized_video_codec"], "h264")
            self.assertTrue((root / "normalized.mp4").exists())
            self.assertTrue((root / "normalized.ffprobe.json").exists())
            self.assertTrue((root / "normalize.log").exists())


if __name__ == "__main__":
    main()
