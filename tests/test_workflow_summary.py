from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import workflow_summary


class WorkflowSummaryTest(TestCase):
    def test_load_latest_candidate_payload_returns_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate-buz.123.json"
            candidate_path.write_text('{"selected":{"id":"123"}}', encoding="utf-8")

            payload, error = workflow_summary.load_latest_candidate_payload([candidate_path])

        self.assertEqual(payload, {"selected": {"id": "123"}})
        self.assertIsNone(error)

    def test_load_latest_candidate_payload_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate-buz.123.json"
            candidate_path.write_text("", encoding="utf-8")

            payload, error = workflow_summary.load_latest_candidate_payload([candidate_path])

        self.assertIsNone(payload)
        self.assertIn("empty", error or "")

    def test_load_latest_candidate_payload_reports_json_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate_path = Path(temp_dir) / "candidate-buz.123.json"
            candidate_path.write_text("{", encoding="utf-8")

            payload, error = workflow_summary.load_latest_candidate_payload([candidate_path])

        self.assertIsNone(payload)
        self.assertIn("invalid JSON", error or "")


if __name__ == "__main__":
    main()
