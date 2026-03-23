from __future__ import annotations

import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "python").resolve()))

from python.summary_common import post_summary


class SummaryCommonTests(unittest.TestCase):
    @patch("python.summary_common.subprocess.run")
    def test_post_summary_reports_whoami_failure_details(self, mock_run: object) -> None:
        mock_run.side_effect = [
            CompletedProcess(
                args=["twitter", "whoami", "--json"],
                returncode=1,
                stdout="",
                stderr="🔐 Getting Twitter cookies...\n401 Unauthorized",
            )
        ]

        with TemporaryDirectory() as temp_dir:
            twitter_bin = Path(temp_dir) / "twitter"
            twitter_bin.write_text("", encoding="utf-8")

            with self.assertRaises(RuntimeError) as context:
                post_summary("hello", twitter_bin)

        message = str(context.exception)
        self.assertIn("twitter whoami failed with exit code 1.", message)
        self.assertIn("401 Unauthorized", message)

    @patch("python.summary_common.subprocess.run")
    def test_post_summary_reports_post_failure_details(self, mock_run: object) -> None:
        mock_run.side_effect = [
            CompletedProcess(
                args=["twitter", "whoami", "--json"],
                returncode=0,
                stdout='{"ok":true}',
                stderr="",
            ),
            CompletedProcess(
                args=["twitter", "post", "hello", "--json"],
                returncode=1,
                stdout='{"ok":false,"error":"duplicate"}',
                stderr="🔐 Getting Twitter cookies...",
            ),
        ]

        with TemporaryDirectory() as temp_dir:
            twitter_bin = Path(temp_dir) / "twitter"
            twitter_bin.write_text("", encoding="utf-8")

            with self.assertRaises(RuntimeError) as context:
                post_summary("hello", twitter_bin)

        message = str(context.exception)
        self.assertIn("twitter post failed with exit code 1.", message)
        self.assertIn("stderr: 🔐 Getting Twitter cookies...", message)
        self.assertIn('stdout: {"ok":false,"error":"duplicate"}', message)


if __name__ == "__main__":
    unittest.main()
