from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase, main
from zoneinfo import ZoneInfo

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from hourly_post_guard import check_hourly_guard, record_hourly_post

JST = ZoneInfo("Asia/Tokyo")


class HourlyPostGuardTest(TestCase):
    def test_allows_first_post_of_the_hour(self) -> None:
        """No state file -> live post should be allowed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            now = datetime(2026, 4, 1, 10, 15, 0, tzinfo=JST)

            result = check_hourly_guard(state_path, now)

        self.assertTrue(result["allowed"])

    def test_blocks_second_post_same_hour(self) -> None:
        """If already posted in this JST hour slot, second attempt is blocked."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            first_post = datetime(2026, 4, 1, 10, 5, 0, tzinfo=JST)
            record_hourly_post(state_path, first_post)

            now = datetime(2026, 4, 1, 10, 20, 0, tzinfo=JST)
            result = check_hourly_guard(state_path, now)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "already_posted_this_hour")

    def test_allows_post_in_next_hour(self) -> None:
        """After hour rolls over, live post should be allowed again."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            first_post = datetime(2026, 4, 1, 10, 5, 0, tzinfo=JST)
            record_hourly_post(state_path, first_post)

            now = datetime(2026, 4, 1, 11, 0, 0, tzinfo=JST)
            result = check_hourly_guard(state_path, now)

        self.assertTrue(result["allowed"])

    def test_dry_run_does_not_consume_state(self) -> None:
        """dry-run must not write hourly state (record_hourly_post not called)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"

            # Simulate: check passes, but we don't record (dry-run)
            now = datetime(2026, 4, 1, 10, 15, 0, tzinfo=JST)
            result = check_hourly_guard(state_path, now)
            self.assertTrue(result["allowed"])

            # State file should not exist
            self.assertFalse(state_path.exists())

            # Second check should still allow (no state was consumed)
            result2 = check_hourly_guard(state_path, now)
            self.assertTrue(result2["allowed"])

    def test_corrupt_state_file_fails_closed(self) -> None:
        """Unreadable state on live run must fail-closed (block post)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            state_path.write_text("{corrupt json!", encoding="utf-8")

            now = datetime(2026, 4, 1, 10, 15, 0, tzinfo=JST)
            result = check_hourly_guard(state_path, now)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "state_unreadable")
        self.assertIn("error", result)

    def test_record_creates_state_file(self) -> None:
        """record_hourly_post must create a valid JSON state file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            now = datetime(2026, 4, 1, 10, 30, 0, tzinfo=JST)

            record_hourly_post(state_path, now)

            self.assertTrue(state_path.exists())
            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(data["jst_hour"], "2026-04-01T10")

    def test_result_includes_jst_hour(self) -> None:
        """Result dict must always contain the jst_hour slot."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            now = datetime(2026, 4, 1, 14, 0, 0, tzinfo=JST)
            result = check_hourly_guard(state_path, now)

        self.assertEqual(result["jst_hour"], "2026-04-01T14")

    def test_blocked_result_includes_last_posted_at(self) -> None:
        """Blocked result should include last_posted_at timestamp."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "hourly-buz.json"
            first_post = datetime(2026, 4, 1, 10, 5, 0, tzinfo=JST)
            record_hourly_post(state_path, first_post)

            now = datetime(2026, 4, 1, 10, 20, 0, tzinfo=JST)
            result = check_hourly_guard(state_path, now)

        self.assertFalse(result["allowed"])
        self.assertIn("last_posted_at", result)


if __name__ == "__main__":
    main()
