from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from session_summary import (
    build_session_log_filename,
    build_summary_prompt,
    render_fallback_summary,
)


class SessionSummaryTest(TestCase):
    def test_build_session_log_filename_uses_timestamp(self) -> None:
        timestamp = datetime(2026, 3, 28, 2, 15, 30, tzinfo=timezone.utc)

        result = build_session_log_filename(timestamp)

        self.assertEqual(result, "session-20260328_021530.md")

    def test_build_summary_prompt_mentions_required_sections(self) -> None:
        prompt = build_summary_prompt(project_name="twitter-auto-poster", exit_reason="normal_exit")

        self.assertIn("twitter-auto-poster", prompt)
        self.assertIn("目的", prompt)
        self.assertIn("変更ファイル", prompt)
        self.assertIn("未完了事項", prompt)
        self.assertIn("次回の着手点", prompt)

    def test_render_fallback_summary_includes_changed_files(self) -> None:
        timestamp = datetime(2026, 3, 28, 2, 20, 0, tzinfo=timezone.utc)

        result = render_fallback_summary(
            project_name="twitter-auto-poster",
            exit_reason="normal_exit",
            timestamp=timestamp,
            changed_files=["docs/RUNBOOK.md", "devinit.sh"],
            git_status_lines=[" M docs/RUNBOOK.md", " M devinit.sh"],
        )

        self.assertIn("# Session Summary", result)
        self.assertIn("docs/RUNBOOK.md", result)
        self.assertIn("devinit.sh", result)
        self.assertIn("normal_exit", result)


if __name__ == "__main__":
    main()
