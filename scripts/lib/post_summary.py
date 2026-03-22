from __future__ import annotations

import logging
import re

LOGGER = logging.getLogger(__name__)

TRANSLATION_HEADER = "【🌐 日本語訳】"
TRANSLATION_SEPARATOR = "---"


def clean_source_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \"'|")


def load_translator() -> object:
    from googletrans import Translator

    return Translator()


def truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip(" ,.;:") + "…"


def translate_to_japanese(text: str, *, translator: object | None = None) -> str:
    cleaned = clean_source_text(text)
    if not cleaned:
        return cleaned

    active_translator = translator or load_translator()
    try:
        response = active_translator.translate(cleaned, dest="ja")
    except Exception as exc:
        LOGGER.warning("googletrans failed; falling back to source text: %s", exc)
        return cleaned

    translated = str(getattr(response, "text", "") or "").strip()
    if not translated:
        LOGGER.warning("googletrans returned empty text; falling back to source text")
        return cleaned
    return translated


def build_source_tweet_url(screen_name: str, tweet_id: str, *, source_username: str = "") -> str:
    normalized_screen_name = (screen_name or source_username).strip().lstrip("@")
    normalized_tweet_id = tweet_id.strip()
    if not normalized_screen_name or not normalized_tweet_id:
        return ""
    return f"https://x.com/{normalized_screen_name}/status/{normalized_tweet_id}"


def format_translation_post(body_text: str, *, source_url: str, max_length: int) -> str:
    header = f"{TRANSLATION_HEADER}\n\n"
    suffix = f"\n\n{TRANSLATION_SEPARATOR}\n{source_url}" if source_url else ""
    available_body_length = max(max_length - len(header) - len(suffix), 0)
    formatted_body = truncate_text(body_text, available_body_length) if available_body_length else ""
    return truncate_text(f"{header}{formatted_body}{suffix}".rstrip(), max_length)


def build_summary_body(text: str, *, language: str, translator: object | None = None) -> str:
    if language == "raw":
        return clean_source_text(text)
    return translate_to_japanese(text, translator=translator)


def build_summary(
    text: str,
    *,
    prefix: str,
    language: str,
    max_length: int,
    screen_name: str = "",
    tweet_id: str = "",
    source_username: str = "",
    translator: object | None = None,
) -> str:
    del prefix
    body = build_summary_body(text, language=language, translator=translator)
    if not body:
        body = "$MU関連の注目投稿"
    source_url = build_source_tweet_url(screen_name, tweet_id, source_username=source_username)
    return format_translation_post(body, source_url=source_url, max_length=max_length)
