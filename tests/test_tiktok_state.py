from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from tiktok_state import is_posted, load_posted_ids, mark_posted


class LoadPostedIdsTest(unittest.TestCase):
    def test_nonexistent_file_returns_empty_set(self) -> None:
        result = load_posted_ids("/nonexistent/path/posted.txt")
        self.assertEqual(result, set())

    def test_file_with_ids_returns_correct_set(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("vid001\nvid002\nvid003\n")
            path = f.name
        try:
            result = load_posted_ids(path)
            self.assertEqual(result, {"vid001", "vid002", "vid003"})
        finally:
            os.unlink(path)

    def test_duplicates_stripped_on_load(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("vid001\nvid001\nvid002\n")
            path = f.name
        try:
            result = load_posted_ids(path)
            self.assertEqual(result, {"vid001", "vid002"})
        finally:
            os.unlink(path)

    def test_blank_lines_ignored(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("vid001\n\n  \nvid002\n")
            path = f.name
        try:
            result = load_posted_ids(path)
            self.assertEqual(result, {"vid001", "vid002"})
        finally:
            os.unlink(path)


class IsPostedTest(unittest.TestCase):
    def test_returns_true_when_present(self) -> None:
        self.assertTrue(is_posted("vid001", {"vid001", "vid002"}))

    def test_returns_false_when_absent(self) -> None:
        self.assertFalse(is_posted("vid999", {"vid001", "vid002"}))


class MarkPostedTest(unittest.TestCase):
    def test_appends_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("vid001\n")
            path = f.name
        try:
            result = mark_posted("vid002", path)
            self.assertTrue(result)
            contents = Path(path).read_text()
            self.assertIn("vid002", contents)
            self.assertIn("vid001", contents)
        finally:
            os.unlink(path)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("vid001\n")
            path = f.name
        try:
            result = mark_posted("vid002", path, dry_run=True)
            self.assertFalse(result)
            contents = Path(path).read_text()
            self.assertNotIn("vid002", contents)
        finally:
            os.unlink(path)

    def test_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "posted.txt"
            result = mark_posted("vid001", path)
            self.assertTrue(result)
            self.assertTrue(path.exists())
            self.assertIn("vid001", path.read_text())

    def test_does_not_duplicate_existing_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "posted.txt"
            mark_posted("vid001", path)
            mark_posted("vid001", path)
            lines = [l for l in path.read_text().splitlines() if l.strip()]
            self.assertEqual(lines.count("vid001"), 1)


if __name__ == "__main__":
    unittest.main()
