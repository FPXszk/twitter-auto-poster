from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from account_score import analyze_account_score, current_jst_datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Twitter account diagnostics and estimate account score.")
    parser.add_argument("--twitter-bin", type=Path, default=Path("python/.venv/bin/twitter"))
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--history-path", type=Path, required=True)
    parser.add_argument("--recent-post-limit", type=int, default=10)
    parser.add_argument("--assume-premium", choices=("true", "false"), default="true")
    parser.add_argument("--tweet-id", action="append", default=[])
    return parser.parse_args()


def run_json(command: list[str], output_path: Path) -> tuple[int, str, str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    payload = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result.returncode, result.stdout, result.stderr


def load_cli_payload(stdout: str) -> dict[str, object]:
    payload = json.loads(stdout)
    if payload.get("ok") is not True:
        raise RuntimeError("twitter-cli response did not indicate success")
    data = payload.get("data")
    if not isinstance(data, dict) and not isinstance(data, list):
        raise RuntimeError("twitter-cli response data was missing")
    return payload


def append_history(path: Path, entry: dict[str, object], max_entries: int = 400) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    existing.append(json.dumps(entry, ensure_ascii=False))
    trimmed = existing[-max_entries:]
    path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    return len(trimmed)


def build_recent_post_preview(posts: Sequence[dict[str, object]], limit: int = 5) -> list[dict[str, object]]:
    previews: list[dict[str, object]] = []
    for post in posts[:limit]:
        metrics = post.get("metrics") if isinstance(post.get("metrics"), dict) else {}
        text = " ".join(str(post.get("text") or "").split())
        previews.append(
            {
                "id": str(post.get("id") or ""),
                "created_at": str(post.get("createdAtISO") or post.get("createdAt") or ""),
                "views": metrics.get("views", 0),
                "likes": metrics.get("likes", 0),
                "replies": metrics.get("replies", 0),
                "text_snippet": text[:140] + ("…" if len(text) > 140 else ""),
            }
        )
    return previews


def main() -> int:
    args = parse_args()
    diagnostics_dir = args.diagnostics_dir
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    assume_premium = args.assume_premium == "true"
    tweet_ids = [item.strip() for item in args.tweet_id if item.strip()]
    now = current_jst_datetime()

    try:
        whoami_code, whoami_stdout, whoami_stderr = run_json(
            [str(args.twitter_bin), "whoami", "--json"],
            diagnostics_dir / "whoami.json",
        )
        if whoami_code != 0:
            raise RuntimeError(whoami_stderr.strip() or whoami_stdout.strip() or "twitter whoami failed")

        whoami_payload = load_cli_payload(whoami_stdout)
        user = ((whoami_payload.get("data") or {}).get("user") or {})
        if not isinstance(user, dict):
            raise RuntimeError("twitter whoami returned unexpected user payload")

        username = str(user.get("username") or "").strip()
        if not username:
            raise RuntimeError("twitter whoami did not return username")

        recent_posts_code, recent_posts_stdout, recent_posts_stderr = run_json(
            [str(args.twitter_bin), "user-posts", username, "--max", str(args.recent_post_limit), "--json"],
            diagnostics_dir / "recent-posts.json",
        )
        if recent_posts_code != 0:
            raise RuntimeError(recent_posts_stderr.strip() or recent_posts_stdout.strip() or "twitter user-posts failed")

        recent_posts_payload = load_cli_payload(recent_posts_stdout)
        recent_posts = recent_posts_payload.get("data") or []
        if not isinstance(recent_posts, list):
            raise RuntimeError("recent posts payload was not a list")

        score_prediction = analyze_account_score(
            user,
            [item for item in recent_posts if isinstance(item, dict)],
            assume_premium=assume_premium,
            now=now,
        )

        tweet_lookups: list[dict[str, object]] = []
        for tweet_id in tweet_ids:
            code, stdout, stderr = run_json(
                [str(args.twitter_bin), "tweet", tweet_id, "--json"],
                diagnostics_dir / f"tweet-{tweet_id}.json",
            )
            lookup_payload: dict[str, object] = {
                "tweet_id": tweet_id,
                "ok": code == 0,
            }
            if code == 0:
                try:
                    payload = load_cli_payload(stdout)
                    data = payload.get("data") or []
                    tweet = data[0] if isinstance(data, list) and data else data
                    lookup_payload["text"] = str((tweet or {}).get("text") or "")
                except Exception as error:
                    lookup_payload["ok"] = False
                    lookup_payload["error"] = str(error)
            else:
                lookup_payload["error"] = stderr.strip() or stdout.strip() or "tweet lookup failed"
            tweet_lookups.append(lookup_payload)

        history_entry = {
            "run_at_jst": now.isoformat(),
            "date_jst": now.date().isoformat(),
            "username": username,
            "score": score_prediction["score"],
            "distribution": score_prediction["distribution"],
            "components": score_prediction["components"],
            "metrics": score_prediction["metrics"],
            "assume_premium": assume_premium,
        }
        history_length = append_history(args.history_path, history_entry)

        payload = {
            "status": "ok",
            "run_at_jst": now.isoformat(),
            "username": username,
            "name": str(user.get("name") or ""),
            "user_id": str(user.get("id") or ""),
            "assume_premium": assume_premium,
            "score_prediction": score_prediction,
            "history_path": str(args.history_path),
            "history_length": history_length,
            "recent_post_preview": build_recent_post_preview([item for item in recent_posts if isinstance(item, dict)]),
            "tweet_lookups": tweet_lookups,
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    except Exception as error:
        failure_payload = {
            "status": "failed",
            "run_at_jst": now.isoformat(),
            "error": str(error),
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(failure_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
