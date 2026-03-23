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
THREAD_BODY_MAX_LENGTH = 275
MAX_THREAD_TWEETS = 5
THREAD_CONTINUATION_SUFFIX = " 続きは↓"
SOURCE_LINK_PREFIX = "\n🔗 "
SENTENCE_BOUNDARY_CHARS = "。！？!?\n"
THREAD_BOUNDARY_CHARS = "。！？!?、\n"
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


def normalize_summary_body(body_text: str) -> str:
    return body_text.strip()


def format_full_translation_post(body_text: str) -> str:
    header = f"{SUMMARY_HEADER}\n\n"
    normalized_body = normalize_summary_body(body_text)
    return f"{header}{normalized_body}".rstrip()


def format_translation_post(body_text: str, *, max_length: int) -> str:
    effective_max_length = max(max_length, 0)
    header = f"{SUMMARY_HEADER}\n\n"
    normalized_body = normalize_summary_body(body_text)
    available_body_length = max(
        effective_max_length - estimate_x_post_length(header),
        0,
    )
    formatted_body = (
        truncate_text_naturally(normalized_body, available_body_length, measure_length=estimate_x_text_length)
        if available_body_length
        else ""
    )
    return truncate_post_text(f"{header}{formatted_body}".rstrip(), effective_max_length)


def compose_source_link_post(body_text: str, *, source_url: str) -> str:
    if not source_url:
        return body_text.strip()
    return f"{body_text.rstrip()}{SOURCE_LINK_PREFIX}{source_url}"


def _fits_body_text(text: str, max_length: int) -> bool:
    normalized = text.strip()
    return len(normalized) <= max_length and estimate_x_text_length(normalized) <= max_length


def _fits_post_text(text: str, max_length: int = MAX_X_POST_LENGTH) -> bool:
    normalized = text.strip()
    return len(normalized) <= max_length and estimate_x_post_length(normalized) <= max_length


def _thread_boundary_positions(text: str) -> list[int]:
    positions: list[int] = []
    index = 0
    while index < len(text):
        if text.startswith(" • ", index):
            positions.append(index)
            index += 3
            continue

        character = text[index]
        if character == "\n":
            positions.append(index + 1)
            index += 1
            continue

        if character in THREAD_BOUNDARY_CHARS:
            end = index + 1
            while end < len(text) and text[end] in TRAILING_CLOSERS:
                end += 1
            positions.append(end)
        index += 1

    deduped: list[int] = []
    seen = set()
    for position in positions:
        if position <= 0 or position >= len(text):
            continue
        if position in seen:
            continue
        deduped.append(position)
        seen.add(position)
    return deduped


def split_thread_text(text: str, *, predicate: Callable[[str], bool]) -> tuple[str, str]:
    normalized = text.strip()
    if not normalized:
        return "", ""

    last_boundary_end = -1
    for boundary_end in _thread_boundary_positions(normalized):
        candidate = normalized[:boundary_end].rstrip()
        if predicate(candidate):
            last_boundary_end = boundary_end
            continue
        break
    if last_boundary_end == -1 and predicate(normalized):
        return normalized, ""

    if last_boundary_end == -1:
        raise ValueError("could not split text naturally within tweet limit")

    head = normalized[:last_boundary_end].rstrip()
    tail = normalized[last_boundary_end:].lstrip()
    return head, tail


def split_thread_text_for_final_tail(
    text: str,
    *,
    predicate: Callable[[str], bool],
    tail_predicate: Callable[[str], bool],
) -> tuple[str, str]:
    normalized = text.strip()
    if not normalized:
        return "", ""

    for boundary_end in reversed(_thread_boundary_positions(normalized)):
        head = normalized[:boundary_end].rstrip()
        tail = normalized[boundary_end:].lstrip()
        if not head or not tail:
            continue
        if predicate(head) and tail_predicate(tail):
            return head, tail

    return "", ""


def build_thread_posts(
    text: str,
    *,
    source_url: str,
    max_body_length: int = THREAD_BODY_MAX_LENGTH,
    single_post_max_length: int = MAX_X_POST_LENGTH,
    max_posts: int = MAX_THREAD_TWEETS,
) -> list[str]:
    normalized = text.strip()
    if not normalized:
        raise ValueError("thread text is empty")

    single_post = compose_source_link_post(normalized, source_url=source_url)
    if _fits_post_text(single_post, single_post_max_length):
        return [single_post]

    def first_predicate(candidate: str) -> bool:
        return _fits_body_text(candidate, max_body_length) and _fits_post_text(
            f"{candidate.rstrip()}{THREAD_CONTINUATION_SUFFIX}"
        )

    def middle_predicate(candidate: str) -> bool:
        return _fits_body_text(candidate, max_body_length) and _fits_post_text(candidate)

    def final_predicate(candidate: str) -> bool:
        return _fits_body_text(candidate, max_body_length) and _fits_post_text(
            compose_source_link_post(candidate, source_url=source_url)
        )

    posts: list[str] = []
    remaining = normalized
    while remaining:
        if posts and final_predicate(remaining):
            posts.append(compose_source_link_post(remaining, source_url=source_url))
            break

        if not posts and final_predicate(remaining):
            posts.append(compose_source_link_post(remaining, source_url=source_url))
            break

        if len(posts) >= max_posts - 1:
            raise ValueError(f"text requires more than {max_posts} tweets")

        predicate = first_predicate if not posts else middle_predicate
        original_remaining = remaining
        segment, remaining = split_thread_text_for_final_tail(
            original_remaining,
            predicate=predicate,
            tail_predicate=final_predicate,
        )
        if not segment:
            segment, remaining = split_thread_text(original_remaining, predicate=predicate)
        if not segment:
            raise ValueError("thread segment is empty")
        if not remaining:
            if not final_predicate(segment):
                raise ValueError("final thread segment could not fit with source URL")
            posts.append(compose_source_link_post(segment, source_url=source_url))
            break

        if not posts:
            posts.append(f"{segment}{THREAD_CONTINUATION_SUFFIX}")
        else:
            posts.append(segment)

    return posts


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
    del prefix, screen_name, tweet_id, source_username
    body = build_summary_body(text, language=language, translator=translator)
    if not body:
        body = "$MU関連の注目投稿"
    return format_translation_post(body, max_length=max_length)


def build_thread_summary(
    text: str,
    *,
    language: str,
    translator: object | None = None,
) -> str:
    body = build_summary_body(text, language=language, translator=translator)
    if not body:
        body = "$MU関連の注目投稿"
    return format_full_translation_post(body)
