"""自動投稿への返信を検出し、Copilot で生成した返答を送る。

投稿済み tweet 履歴 (feedback history) から直近の投稿を取得し、
twitter-cli でリプライツリーを取得して未返信の他者リプライに対して
Copilot で生成した当たり障りのない返信を送信する。
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_MAX_REPLY_LENGTH = 140
DEFAULT_REPLY_PROMPT = (
    "あなたはX（旧Twitter）上のフレンドリーなアカウントです。\n"
    "以下の「元投稿」に対する「受信リプライ」に短く返信してください。\n\n"
    "ルール:\n"
    "- 出力は返信本文のみ（前置き・後書き不要）\n"
    "- 日本語で書く\n"
    "- 攻撃的・断定的な表現は使わない\n"
    "- 個人情報・宣伝・勧誘を含めない\n"
    "- {max_length}文字以内に収める\n"
    "- 絵文字は1つまで\n"
    "- 自然で親しみやすい口調にする\n\n"
    "元投稿:\n{original_text}\n\n"
    "受信リプライ:\n{reply_text}\n"
)


CommandRunner = Callable[..., Any]


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_reply_targets(
    feedback_history: Sequence[Mapping[str, Any]],
    max_checks: int,
    *,
    now: datetime | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[dict[str, Any]]:
    """feedback history から返信チェック対象の posted tweet を抽出する。"""
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=max(lookback_days, 1))
    targets: list[dict[str, Any]] = []

    sorted_entries = sorted(
        feedback_history,
        key=lambda e: _parse_datetime(e.get("posted_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    for entry in sorted_entries:
        if len(targets) >= max(max_checks, 1):
            break
        tweet_id = str(entry.get("posted_tweet_id") or "").strip()
        if not tweet_id:
            continue
        posted_at = _parse_datetime(entry.get("posted_at"))
        if posted_at is None or posted_at < cutoff:
            continue
        targets.append(dict(entry))
    return targets


def extract_replies_from_tweet_detail(
    tweet_detail_data: Sequence[Mapping[str, Any]],
    *,
    original_tweet_id: str,
    bot_username: str,
) -> list[dict[str, Any]]:
    """tweet detail レスポンスからボット自身と元投稿を除いた返信を抽出する。"""
    bot_lower = bot_username.lower()
    replies: list[dict[str, Any]] = []
    for item in tweet_detail_data:
        tweet_id = str(item.get("id") or "").strip()
        if not tweet_id or tweet_id == original_tweet_id:
            continue
        author = item.get("author") or {}
        screen_name = str(author.get("screenName") or author.get("screen_name") or "").strip()
        if screen_name.lower() == bot_lower:
            continue
        replies.append(dict(item))
    return replies


def load_replied_state(path: Path) -> dict[str, str]:
    """返信済みリプライ ID → 元ツイート ID のマッピングを読む。"""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, Mapping):
            reply_id = str(entry.get("reply_id") or "").strip()
            original_id = str(entry.get("original_tweet_id") or "").strip()
            if reply_id:
                result[reply_id] = original_id
    return result


def save_replied_state(path: Path, replied: Mapping[str, str]) -> None:
    """返信済みリプライ state を JSONL で書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for reply_id, original_id in replied.items():
        lines.append(
            json.dumps(
                {"reply_id": reply_id, "original_tweet_id": original_id},
                ensure_ascii=False,
            )
        )
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def filter_unreplied(
    replies: Sequence[Mapping[str, Any]],
    already_replied: Mapping[str, str],
) -> list[dict[str, Any]]:
    """既に返信済みのリプライを除外する。"""
    return [
        dict(r) for r in replies
        if str(r.get("id") or "").strip() not in already_replied
    ]


def _default_command_runner(cmd: list[str], **kwargs: Any) -> Any:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def fetch_bot_username(
    twitter_bin: str,
    *,
    command_runner: CommandRunner | None = None,
) -> str:
    """twitter whoami で認証ユーザーの screenName を返す。"""
    runner = command_runner or _default_command_runner
    result = runner([twitter_bin, "whoami", "--json"])
    if getattr(result, "returncode", 1) != 0:
        stderr = str(getattr(result, "stderr", "") or "").strip()
        raise RuntimeError(stderr or "twitter whoami failed")
    payload = json.loads(str(getattr(result, "stdout", "") or ""))
    if payload.get("ok") is not True:
        raise RuntimeError("twitter whoami response was not ok")
    data = payload.get("data") or {}
    user = data.get("user") or {}
    username = str(user.get("screenName") or user.get("screen_name") or "").strip()
    if not username:
        raise RuntimeError("twitter whoami did not return username")
    return username


def fetch_tweet_detail(
    twitter_bin: str,
    tweet_id: str,
    *,
    command_runner: CommandRunner | None = None,
) -> list[dict[str, Any]]:
    """twitter tweet <id> --json で投稿 + リプライ一覧を取得する。"""
    runner = command_runner or _default_command_runner
    result = runner([twitter_bin, "tweet", tweet_id, "--json"])
    if getattr(result, "returncode", 1) != 0:
        stderr = str(getattr(result, "stderr", "") or "").strip()
        raise RuntimeError(stderr or f"twitter tweet {tweet_id} failed")
    payload = json.loads(str(getattr(result, "stdout", "") or ""))
    if payload.get("ok") is not True:
        raise RuntimeError(f"twitter tweet {tweet_id} response was not ok")
    data = payload.get("data") or []
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, Mapping)]
    return []


def _load_reply_prompt(prompt_path: str) -> str:
    """返信用プロンプトテンプレートを読み込む。"""
    if not str(prompt_path).strip():
        return DEFAULT_REPLY_PROMPT
    path = Path(prompt_path)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return DEFAULT_REPLY_PROMPT


def generate_reply_text(
    *,
    model: str,
    original_text: str,
    reply_text: str,
    prompt_path: str,
    command_runner: CommandRunner | None = None,
    max_reply_length: int = DEFAULT_MAX_REPLY_LENGTH,
) -> str:
    """Copilot CLI で返信テキストを生成し、検証して返す。"""
    prompt_template = _load_reply_prompt(prompt_path)
    prompt = prompt_template.replace("{original_text}", original_text)
    prompt = prompt.replace("{reply_text}", reply_text)
    prompt = prompt.replace("{max_length}", str(max_reply_length))

    command = ["copilot", "--model", model, "-p", prompt, "-s"]
    runner = command_runner or _default_command_runner

    try:
        result = runner(command)
    except FileNotFoundError as exc:
        raise RuntimeError("copilot CLI is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"copilot CLI failed: {exc}") from exc

    if getattr(result, "returncode", 0) != 0:
        stderr = str(getattr(result, "stderr", "") or "").strip()
        raise RuntimeError(stderr or "copilot CLI exited with non-zero status")

    text = str(getattr(result, "stdout", "") or "").strip()
    if not text:
        raise RuntimeError("copilot CLI returned empty reply text")
    if len(text) > max_reply_length:
        raise RuntimeError(
            f"generated reply exceeds max length ({len(text)} > {max_reply_length})"
        )
    return text


def send_reply(
    twitter_bin: str,
    reply_to_id: str,
    text: str,
    *,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """twitter reply で返信を送信する。"""
    runner = command_runner or _default_command_runner
    result = runner([twitter_bin, "reply", reply_to_id, text, "--json"])
    if getattr(result, "returncode", 1) != 0:
        stderr = str(getattr(result, "stderr", "") or "").strip()
        raise RuntimeError(stderr or f"twitter reply to {reply_to_id} failed")
    payload = json.loads(str(getattr(result, "stdout", "") or ""))
    if payload.get("ok") is not True:
        raise RuntimeError(f"twitter reply to {reply_to_id} response was not ok")
    data = payload.get("data") or {}
    return dict(data) if isinstance(data, Mapping) else {}


def run_auto_reply(
    *,
    feedback_history: Sequence[Mapping[str, Any]],
    twitter_bin: str,
    bot_username: str,
    replied_state_path: Path,
    max_reply_checks: int = 5,
    max_replies: int = 3,
    copilot_model: str = "gpt-5-mini",
    reply_prompt_path: str = "",
    now: datetime | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_reply_length: int = DEFAULT_MAX_REPLY_LENGTH,
    fetch_tweet_detail_fn: Callable | None = None,
    generate_reply_fn: Callable | None = None,
    send_reply_fn: Callable | None = None,
) -> dict[str, Any]:
    """自動返信の全体フローを実行する。"""
    current = now or datetime.now(timezone.utc)
    targets = extract_reply_targets(
        feedback_history, max_reply_checks, now=current, lookback_days=lookback_days,
    )
    replied_state = load_replied_state(replied_state_path)

    _fetch = fetch_tweet_detail_fn or (
        lambda tb, tid: fetch_tweet_detail(tb, tid)
    )
    _generate = generate_reply_fn or (
        lambda model, original_text, reply_text, prompt_path, **kw: generate_reply_text(
            model=model, original_text=original_text, reply_text=reply_text,
            prompt_path=prompt_path, max_reply_length=max_reply_length,
        )
    )
    _send = send_reply_fn or (
        lambda tb, rid, txt, **kw: send_reply(tb, rid, txt)
    )

    summary: dict[str, Any] = {
        "status": "ok",
        "checked_tweets": 0,
        "total_replies_found": 0,
        "replies_sent": 0,
        "replies_skipped_already_replied": 0,
        "errors": [],
    }
    replies_sent = 0

    for target in targets:
        if replies_sent >= max(max_replies, 0):
            break
        posted_tweet_id = str(target.get("posted_tweet_id") or "").strip()
        if not posted_tweet_id:
            continue

        try:
            detail_data = _fetch(twitter_bin, posted_tweet_id)
        except Exception as exc:
            summary["errors"].append(
                {"tweet_id": posted_tweet_id, "stage": "fetch_detail", "error": str(exc)}
            )
            continue

        summary["checked_tweets"] += 1
        original_text = ""
        for item in detail_data:
            if str(item.get("id") or "") == posted_tweet_id:
                original_text = str(item.get("text") or "")
                break

        external_replies = extract_replies_from_tweet_detail(
            detail_data, original_tweet_id=posted_tweet_id, bot_username=bot_username,
        )
        unreplied = filter_unreplied(external_replies, replied_state)
        summary["total_replies_found"] += len(external_replies)
        summary["replies_skipped_already_replied"] += len(external_replies) - len(unreplied)

        for reply_item in unreplied:
            if replies_sent >= max(max_replies, 0):
                break
            reply_id = str(reply_item.get("id") or "").strip()
            reply_text = str(reply_item.get("text") or "").strip()
            if not reply_id or not reply_text:
                continue

            try:
                generated = _generate(
                    copilot_model, original_text, reply_text, reply_prompt_path,
                )
            except Exception as exc:
                summary["errors"].append(
                    {"reply_id": reply_id, "stage": "generate", "error": str(exc)}
                )
                continue

            try:
                send_result = _send(twitter_bin, reply_id, generated)
            except Exception as exc:
                summary["errors"].append(
                    {"reply_id": reply_id, "stage": "send", "error": str(exc)}
                )
                continue

            replied_state[reply_id] = posted_tweet_id
            replies_sent += 1

        summary["replies_sent"] = replies_sent

    save_replied_state(replied_state_path, replied_state)
    return summary
