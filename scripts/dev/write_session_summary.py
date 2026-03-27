from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

sys.path.append(str((Path(__file__).resolve().parents[1] / "lib").resolve()))

from session_summary import (
    build_session_log_filename,
    build_summary_prompt,
    render_fallback_summary,
    render_summary_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    return parser.parse_args()


def git_status_lines(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "--no-pager", "status", "--short", "--untracked-files=all"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]


def changed_files_from_status(lines: list[str]) -> list[str]:
    files: list[str] = []
    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            files.append(parts[1].strip())
    return files


def summarize_with_copilot(repo_root: Path, exit_reason: str) -> str:
    env = os.environ.copy()
    env["COPILOT_SESSION_SUMMARY_MODE"] = "1"
    prompt = build_summary_prompt(project_name=repo_root.name, exit_reason=exit_reason)
    result = subprocess.run(
        ["copilot", "--continue", "-p", prompt, "--allow-all-tools", "--add-dir", str(repo_root), "-s"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError("copilot summary command failed")
    return result.stdout.strip()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().astimezone()
    exit_reason = "normal_exit" if args.exit_code == 0 else f"exit_code_{args.exit_code}"
    status_lines = git_status_lines(repo_root)
    changed_files = changed_files_from_status(status_lines)
    output_path = output_dir / build_session_log_filename(now)

    try:
        summary_text = summarize_with_copilot(repo_root, exit_reason)
        content = render_summary_document(
            project_name=repo_root.name,
            exit_reason=exit_reason,
            timestamp=now,
            summary_text=summary_text,
        )
    except (RuntimeError, OSError):
        content = render_fallback_summary(
            project_name=repo_root.name,
            exit_reason=exit_reason,
            timestamp=now,
            changed_files=changed_files,
            git_status_lines=status_lines,
        )

    output_path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
