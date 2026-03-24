from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import copilot_summary


class CopilotSummaryTest(TestCase):
    def test_build_prompt_injects_source_text_placeholder(self) -> None:
        prompt = copilot_summary.build_prompt(
            "Original tweet body",
            prompt_template="要約してください\n{source_text}",
        )

        self.assertEqual(prompt, "要約してください\nOriginal tweet body")

    def test_build_prompt_appends_source_text_when_placeholder_missing(self) -> None:
        prompt = copilot_summary.build_prompt(
            "Original tweet body",
            prompt_template="要約してください",
        )

        self.assertTrue(prompt.endswith("元ツイート:\nOriginal tweet body"))

    def test_load_prompt_template_uses_working_directory_for_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompt_path = Path(temp_dir) / "config" / "prompt.txt"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text("要約\n{source_text}", encoding="utf-8")

            loaded = copilot_summary.load_prompt_template(
                "config/prompt.txt",
                working_directory=temp_dir,
            )

        self.assertEqual(loaded, "要約\n{source_text}")

    def test_summarize_to_japanese_builds_expected_command(self) -> None:
        captured: dict[str, object] = {}

        def fake_runner(command: list[str], *, working_directory: object | None = None) -> SimpleNamespace:
            captured["command"] = command
            captured["working_directory"] = working_directory
            return SimpleNamespace(stdout="要約結果", stderr="")

        summary = copilot_summary.summarize_to_japanese(
            "Original tweet body",
            model="gpt-5-mini",
            command_runner=fake_runner,
            working_directory=Path("/tmp/copilot"),
        )

        self.assertEqual(summary, "要約結果")
        self.assertEqual(captured["working_directory"], Path("/tmp/copilot"))
        self.assertEqual(captured["command"][:4], ["copilot", "--model", "gpt-5-mini", "-p"])
        self.assertIn("-s", captured["command"])
        self.assertIn("Original tweet body", captured["command"][4])

    def test_summarize_to_japanese_raises_when_copilot_returns_empty_output(self) -> None:
        def fake_runner(command: list[str], *, working_directory: object | None = None) -> SimpleNamespace:
            return SimpleNamespace(stdout="   ", stderr="")

        with self.assertRaisesRegex(RuntimeError, "empty summary"):
            copilot_summary.summarize_to_japanese(
                "Original tweet body",
                command_runner=fake_runner,
            )

    def test_summarize_to_japanese_raises_on_copilot_failure(self) -> None:
        def failing_runner(command: list[str], *, working_directory: object | None = None) -> SimpleNamespace:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=command,
                stderr="authentication failed",
            )

        with self.assertRaisesRegex(RuntimeError, "authentication failed"):
            copilot_summary.summarize_to_japanese(
                "Original tweet body",
                command_runner=failing_runner,
            )

    def test_summarize_to_japanese_result_collects_usage_lines_from_stderr(self) -> None:
        result = copilot_summary.summarize_to_japanese_result(
            "Original tweet body",
            command_runner=lambda command, *, working_directory=None: SimpleNamespace(
                stdout="要約結果",
                stderr="Used 1 premium request\nRemaining quota: 99",
            ),
        )

        self.assertEqual(result.summary, "要約結果")
        self.assertEqual(result.usage_lines, ["Used 1 premium request", "Remaining quota: 99"])


if __name__ == "__main__":
    main()
