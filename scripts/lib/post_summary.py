from __future__ import annotations

import logging
import re
import unicodedata
from typing import Callable

LOGGER = logging.getLogger(__name__)

SUMMARY_HEADER = "【👀 要約】"
SUMMARY_SEPARATOR = "---"
URL_PATTERN = re.compile(r"https?://\S+")
X_SHORT_URL_LENGTH = 23
MAX_X_POST_LENGTH = 280
SENTENCE_BOUNDARY_CHARS = "。！？!?\n"
TRAILING_CLOSERS = "」』）】〉》〕〗〙〛\"'”’ \t\r\n"


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


def estimate_x_text_length(text: str) -> int:
    total = 0
    for character in text:
        if character == "\n":
            total += 1
            continue
        total += 2 if unicodedata.east_asian_width(character) in {"F", "W", "A"} else 1
    return total


def estimate_x_post_length(text: str) -> int:
    total = 0
    cursor = 0
    for match in URL_PATTERN.finditer(text):
        total += estimate_x_text_length(text[cursor : match.start()])
        total += X_SHORT_URL_LENGTH
        cursor = match.end()
    total += estimate_x_text_length(text[cursor:])
    return total


def truncate_text(text: str, max_length: int, *, measure_length: Callable[[str], int] | None = None) -> str:
    resolved_measure_length = measure_length or len
    if resolved_measure_length(text) <= max_length:
        return text
    if max_length <= 0:
        return ""

    ellipsis = "…"
    ellipsis_length = resolved_measure_length(ellipsis)
    if max_length <= ellipsis_length:
        return ellipsis if ellipsis_length <= max_length else ""

    budget = max_length - ellipsis_length
    truncated: list[str] = []
    current_length = 0
    for character in text:
        character_length = resolved_measure_length(character)
        if current_length + character_length > budget:
            break
        truncated.append(character)
        current_length += character_length
    return "".join(truncated).rstrip(" ,.;:") + ellipsis


def truncate_post_text(text: str, max_length: int) -> str:
    if estimate_x_post_length(text) <= max_length:
        return text
    if max_length <= 0:
        return ""

    ellipsis = "…"
    ellipsis_length = estimate_x_text_length(ellipsis)
    if max_length <= ellipsis_length:
        return ellipsis if ellipsis_length <= max_length else ""

    budget = max_length - ellipsis_length
    parts: list[str] = []
    current_length = 0
    cursor = 0

    for match in URL_PATTERN.finditer(text):
        for character in text[cursor : match.start()]:
            character_length = estimate_x_text_length(character)
            if current_length + character_length > budget:
                return "".join(parts).rstrip(" ,.;:") + ellipsis
            parts.append(character)
            current_length += character_length

        url = match.group(0)
        if current_length + X_SHORT_URL_LENGTH > budget:
            return "".join(parts).rstrip(" ,.;:") + ellipsis
        parts.append(url)
        current_length += X_SHORT_URL_LENGTH
        cursor = match.end()

    for character in text[cursor:]:
        character_length = estimate_x_text_length(character)
        if current_length + character_length > budget:
            break
        parts.append(character)
        current_length += character_length

    return "".join(parts).rstrip(" ,.;:") + ellipsis


def trim_to_sentence_boundary(text: str) -> str:
    for index in range(len(text) - 1, -1, -1):
        if text[index] not in SENTENCE_BOUNDARY_CHARS:
            continue
        end = index + 1
        while end < len(text) and text[end] in TRAILING_CLOSERS:
            end += 1
        return text[:end].rstrip()
    return ""


def truncate_text_naturally(
    text: str,
    max_length: int,
    *,
    measure_length: Callable[[str], int] | None = None,
) -> str:
    normalized = text.strip()
    resolved_measure_length = measure_length or len
    if resolved_measure_length(normalized) <= max_length:
        return normalized
    if max_length <= 0:
        return ""

    prefix_chars: list[str] = []
    current_length = 0
    for character in normalized:
        character_length = resolved_measure_length(character)
        if current_length + character_length > max_length:
            break
        prefix_chars.append(character)
        current_length += character_length

    natural = trim_to_sentence_boundary("".join(prefix_chars).rstrip())
    if natural:
        return natural
    return truncate_text(normalized, max_length, measure_length=resolved_measure_length)


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
    effective_max_length = max(min(max_length, MAX_X_POST_LENGTH), 0)
    header = f"{SUMMARY_HEADER}\n\n"
    suffix = f"\n\n{SUMMARY_SEPARATOR}\n{source_url}" if source_url else ""
    available_body_length = max(
        effective_max_length - estimate_x_post_length(header) - estimate_x_post_length(suffix),
        0,
    )
    formatted_body = (
        truncate_text_naturally(body_text, available_body_length, measure_length=estimate_x_text_length)
        if available_body_length
        else ""
    )
    return truncate_post_text(f"{header}{formatted_body}{suffix}".rstrip(), effective_max_length)


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
