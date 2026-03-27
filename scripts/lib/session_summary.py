from __future__ import annotations

from datetime import datetime
from typing import Sequence


def build_session_log_filename(timestamp: datetime) -> str:
    return f"session-{timestamp.strftime('%Y%m%d_%H%M%S')}.md"


def build_summary_prompt(*, project_name: str, exit_reason: str) -> str:
    return f"""直前に終了した `{project_name}` の Copilot CLI セッションを日本語で簡潔に要約してください。

出力ルール:
- Markdown で出力
- 見出しは `## Purpose`(目的) `## Completed Work`(実施内容) `## Changed Files`(変更ファイル) `## Open Items`(未完了事項) `## Next Steps`(次回の着手点) の順
- 冗長な前置きは禁止
- 変更ファイルは可能な範囲で具体名を書く
- 未完了や次回着手がなければ `なし` と書く
- 今回の終了理由メモ: `{exit_reason}`
"""


def render_summary_document(
    *,
    project_name: str,
    exit_reason: str,
    timestamp: datetime,
    summary_text: str,
) -> str:
    cleaned = summary_text.strip() or "## Purpose\n不明\n\n## Completed Work\nなし\n\n## Changed Files\nなし\n\n## Open Items\nなし\n\n## Next Steps\nなし"
    return (
        "# Session Summary\n\n"
        f"- Project: `{project_name}`\n"
        f"- Timestamp: `{timestamp.isoformat()}`\n"
        f"- Exit reason: `{exit_reason}`\n\n"
        f"{cleaned}\n"
    )


def render_fallback_summary(
    *,
    project_name: str,
    exit_reason: str,
    timestamp: datetime,
    changed_files: Sequence[str],
    git_status_lines: Sequence[str],
) -> str:
    changed = "\n".join(f"- `{item}`" for item in changed_files) if changed_files else "- なし"
    raw_status = "\n".join(git_status_lines) if git_status_lines else "clean"
    return (
        "# Session Summary\n\n"
        f"- Project: `{project_name}`\n"
        f"- Timestamp: `{timestamp.isoformat()}`\n"
        f"- Exit reason: `{exit_reason}`\n\n"
        "## Purpose\n"
        "自動要約の取得に失敗したため、Git 状態ベースの簡易サマリーを保存しました。\n\n"
        "## Completed Work\n"
        "Git の差分から変更候補を確認できる状態です。\n\n"
        "## Changed Files\n"
        f"{changed}\n\n"
        "## Open Items\n"
        "詳細要約の再生成が必要な可能性があります。\n\n"
        "## Next Steps\n"
        "必要なら直前セッションを `copilot --continue` で開き、要約を手動更新してください。\n\n"
        "## Git Status Snapshot\n"
        "```text\n"
        f"{raw_status}\n"
        "```\n"
    )
