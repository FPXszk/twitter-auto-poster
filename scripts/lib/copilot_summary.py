from __future__ import annotations

from dataclasses import dataclass
import subprocess
from pathlib import Path
from typing import Callable, Protocol

DEFAULT_COPILOT_MODEL = "gpt-5-mini"
DEFAULT_PROMPT_TEMPLATE = """以下の投稿を日本語で簡潔に要約し、X投稿向けの読みやすい文体へ整えてください。

要件:
- 出力は日本語の要約本文のみ
- 元投稿にない事実は足さない
- 重要な固有名詞・数字・関係国は残す
- 必要に応じて絵文字、短い見出し、箇条書きを使ってよい
- 冗長な前置き、URL、@ユーザー名、ハッシュタグは不要
- 2〜5個の短い段落に収める
- インパクトは出してよいが、煽りすぎない

元ツイート:
{source_text}
"""


class CommandResult(Protocol):
    stdout: str | None
    stderr: str | None


CommandRunner = Callable[..., CommandResult]


@dataclass(frozen=True)
class CopilotSummaryResult:
    summary: str
    stderr: str
    usage_lines: list[str]


def extract_usage_lines(*texts: str) -> list[str]:
    matched_lines: list[str] = []
    seen = set()
    keywords = ("premium", "request", "usage", "quota")
    for text in texts:
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not any(keyword in line.lower() for keyword in keywords):
                continue
            if line in seen:
                continue
            matched_lines.append(line)
            seen.add(line)
    return matched_lines


def resolve_prompt_path(prompt_path: str, *, working_directory: str | Path | None = None) -> Path:
    resolved_path = Path(prompt_path)
    if resolved_path.is_absolute():
        return resolved_path

    if working_directory is not None:
        return Path(working_directory) / resolved_path
    return Path.cwd() / resolved_path


def load_prompt_template(
    prompt_path: str,
    *,
    working_directory: str | Path | None = None,
) -> str:
    if not str(prompt_path).strip():
        return DEFAULT_PROMPT_TEMPLATE

    resolved_path = resolve_prompt_path(prompt_path, working_directory=working_directory)
    return resolved_path.read_text(encoding="utf-8")


def build_prompt(source_text: str, *, prompt_template: str) -> str:
    stripped_template = prompt_template.strip()
    if "{source_text}" in stripped_template:
        return stripped_template.replace("{source_text}", source_text)
    return f"{stripped_template}\n\n元ツイート:\n{source_text}"


def run_copilot_command(
    command: list[str],
    *,
    working_directory: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=str(working_directory) if working_directory is not None else None,
    )


def summarize_to_japanese_result(
    text: str,
    *,
    model: str = DEFAULT_COPILOT_MODEL,
    prompt_path: str = "",
    command_runner: CommandRunner | None = None,
    working_directory: str | Path | None = None,
) -> str:
    if not text:
        return text

    prompt_template = load_prompt_template(prompt_path, working_directory=working_directory)
    prompt = build_prompt(text, prompt_template=prompt_template)
    command = ["copilot", "--model", model or DEFAULT_COPILOT_MODEL, "-p", prompt, "-s"]
    runner = command_runner or run_copilot_command

    try:
        result = runner(command, working_directory=working_directory)
    except FileNotFoundError as exc:
        raise RuntimeError("copilot CLI is not installed") from exc
    except subprocess.CalledProcessError as exc:
        stderr = str(exc.stderr or exc.stdout or "").strip()
        if stderr:
            raise RuntimeError(f"copilot CLI failed: {stderr}") from exc
        raise RuntimeError("copilot CLI failed without output") from exc

    summary = str(getattr(result, "stdout", "") or "").strip()
    if not summary:
        raise RuntimeError("copilot CLI returned empty summary")
    stderr = str(getattr(result, "stderr", "") or "").strip()
    return CopilotSummaryResult(
        summary=summary,
        stderr=stderr,
        usage_lines=extract_usage_lines(summary, stderr),
    )


def summarize_to_japanese(
    text: str,
    *,
    model: str = DEFAULT_COPILOT_MODEL,
    prompt_path: str = "",
    command_runner: CommandRunner | None = None,
    working_directory: str | Path | None = None,
) -> str:
    return summarize_to_japanese_result(
        text,
        model=model,
        prompt_path=prompt_path,
        command_runner=command_runner,
        working_directory=working_directory,
    ).summary
