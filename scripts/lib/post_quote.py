from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from twitter_cli.auth import get_cookies
from twitter_cli.client import TwitterClient
from twitter_cli.config import load_config
from twitter_cli.exceptions import TwitterAPIError
from twitter_cli.graphql import FEATURES
from twitter_cli.parser import _deep_get


def build_quote_reply_variables(
    text: str,
    *,
    quote_tweet_id: str,
    reply_to_id: str = "",
) -> dict[str, Any]:
    variables: dict[str, Any] = {
        "tweet_text": text,
        "attachment_url": f"https://x.com/i/status/{quote_tweet_id}",
        "media": {"media_entities": [], "possibly_sensitive": False},
        "semantic_annotation_ids": [],
        "dark_request": False,
    }
    if reply_to_id:
        variables["reply"] = {
            "in_reply_to_tweet_id": reply_to_id,
            "exclude_reply_user_ids": [],
        }
    return variables


def extract_created_tweet_id(data: dict[str, Any]) -> str:
    result = _deep_get(data, "data", "create_tweet", "tweet_results", "result")
    tweet_id = str((result or {}).get("rest_id") or "").strip()
    if not tweet_id:
        raise TwitterAPIError(0, "Failed to create quote tweet")
    return tweet_id


def create_quote_reply_post(
    text: str,
    *,
    quote_tweet_id: str,
    reply_to_id: str = "",
) -> dict[str, Any]:
    config = load_config()
    rate_limit_config = (config or {}).get("rateLimit")
    cookies = get_cookies()
    client = TwitterClient(
        cookies["auth_token"],
        cookies["ct0"],
        rate_limit_config,
        cookie_string=cookies.get("cookie_string"),
    )
    variables = build_quote_reply_variables(
        text,
        quote_tweet_id=quote_tweet_id,
        reply_to_id=reply_to_id,
    )
    data = client._graphql_post("CreateTweet", variables, FEATURES)
    client._write_delay()
    tweet_id = extract_created_tweet_id(data)
    return {
        "success": True,
        "action": "quote" if not reply_to_id else "quote_reply",
        "id": tweet_id,
        "quotedId": quote_tweet_id,
        "replyTo": reply_to_id,
        "url": f"https://x.com/i/status/{tweet_id}",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--quote-tweet-id", required=True)
    parser.add_argument("--reply-to-id", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = create_quote_reply_post(
        args.text,
        quote_tweet_id=args.quote_tweet_id,
        reply_to_id=args.reply_to_id,
    )
    print(json.dumps({"ok": True, "data": payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
