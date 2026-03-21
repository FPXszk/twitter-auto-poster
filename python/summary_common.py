from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderedVariant:
    label: str
    text: str


@dataclass(frozen=True)
class SummaryBuildResult:
    trade_date: str
    text: str
    variant_label: str
    text_length: int


def ensure_state_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return path


def load_state_entries(path: Path) -> set[str]:
    return {
        line.strip()
        for line in ensure_state_file(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def append_state_entries(entries: Iterable[str], path: Path) -> None:
    existing = load_state_entries(path)
    with ensure_state_file(path).open("a", encoding="utf-8") as handle:
        for entry in entries:
            normalized = entry.strip()
            if normalized and normalized not in existing:
                handle.write(f"{normalized}\n")
                existing.add(normalized)


def short_name(name: str, limit: int) -> str:
    return name if len(name) <= limit else name[:limit]


def code_of(ticker: str) -> str:
    return ticker.removesuffix(".T")


def format_signed_pct(value: float) -> str:
    return f"{value:+.1f}"


def format_price(value: float) -> str:
    return f"{value:,.0f}"


def latest_trade_date(latest_dates: Sequence[str]) -> str:
    return max(latest_dates)


def pick_fitting_variant(
    trade_date: str,
    variants: Sequence[RenderedVariant],
    max_length: int,
) -> SummaryBuildResult:
    for variant in variants:
        if len(variant.text) <= max_length:
            return SummaryBuildResult(
                trade_date=trade_date,
                text=variant.text,
                variant_label=variant.label,
                text_length=len(variant.text),
            )
    raise ValueError(f"could not fit summary within {max_length} characters")


def build_variants(
    render: Callable[..., str],
    variant_specs: Sequence[dict[str, object]],
) -> list[RenderedVariant]:
    variants: list[RenderedVariant] = []
    for spec in variant_specs:
        label = str(spec["label"])
        kwargs = dict(spec["kwargs"])
        variants.append(RenderedVariant(label=label, text=render(**kwargs)))
    return variants


def extract_tweet_id(payload: object) -> str:
    def walk(node: object) -> str:
        if isinstance(node, dict):
            for key in ("id", "rest_id", "tweet_id"):
                value = node.get(key)
                if isinstance(value, str) and value.isdigit():
                    return value
                if isinstance(value, int):
                    return str(value)
            for value in node.values():
                candidate = walk(value)
                if candidate:
                    return candidate
        elif isinstance(node, list):
            for item in node:
                candidate = walk(item)
                if candidate:
                    return candidate
        return ""

    return walk(payload)


def post_summary(tweet_text: str, twitter_bin: Path) -> str:
    if not twitter_bin.is_file():
        raise FileNotFoundError(f"twitter-cli executable not found: {twitter_bin}")

    auth_result = subprocess.run(
        [str(twitter_bin), "status", "--yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    if auth_result.returncode != 0:
        raise RuntimeError("twitter-cli authentication required before posting")

    post_result = subprocess.run(
        [str(twitter_bin), "post", tweet_text, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if post_result.returncode != 0:
        raise RuntimeError(post_result.stderr.strip() or "twitter post command failed")

    try:
        payload = json.loads(post_result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"twitter-cli returned invalid JSON: {error}") from error
    if payload.get("ok") is not True:
        raise RuntimeError("twitter post response did not indicate success")

    tweet_id = extract_tweet_id(payload.get("data") or payload)
    if not tweet_id:
        match = re.search(r"/status/(\d+)", post_result.stdout)
        if match:
            tweet_id = match.group(1)
    if not tweet_id:
        raise RuntimeError("could not extract posted tweet ID")
    return tweet_id
