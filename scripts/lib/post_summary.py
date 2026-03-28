from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Callable

from copilot_summary import DEFAULT_COPILOT_MODEL, summarize_to_japanese_result as summarize_with_copilot_cli_result
from google_translate_summary import translate_to_japanese as translate_with_legacy_google_translate

SUMMARY_SEPARATOR = "---"
URL_PATTERN = re.compile(r"https?://\S+")
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "]",
)
LIST_MARKER_PATTERN = re.compile(r"^(?:[-*•・▪▫◦‣⁃]+|\d+[.)])\s*")
X_SHORT_URL_LENGTH = 23
MAX_X_POST_LENGTH = 280
THREAD_BODY_MAX_LENGTH = 275
MAX_THREAD_TWEETS = 5
THREAD_CONTINUATION_SUFFIX = "（続く"
SOURCE_LINK_PREFIX = "\n🔗 "
SENTENCE_BOUNDARY_CHARS = "。！？!?\n"
THREAD_BOUNDARY_CHARS = "。！？!?、\n"
TRAILING_CLOSERS = "」』）】〉》〕〗〙〛\"'”’ \t\r\n"
DEFAULT_SUMMARY_PROVIDER = "legacy_google_translate"


def clean_source_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \"'|")


def clean_post_source_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    cleaned_lines: list[str] = []
    blank_pending = False
    for raw_line in text.split("\n"):
        normalized_line = re.sub(r"[ \t]+", " ", raw_line).strip(" \"'| ")
        if not normalized_line:
            if cleaned_lines:
                blank_pending = True
            continue
        if blank_pending:
            cleaned_lines.append("")
            blank_pending = False
        cleaned_lines.append(normalized_line)

    return "\n".join(cleaned_lines).strip(" \n\"'|")


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


def resolve_summary_provider(provider: str | None) -> str:
    normalized = str(provider or DEFAULT_SUMMARY_PROVIDER).strip().lower()
    aliases = {
        "": DEFAULT_SUMMARY_PROVIDER,
        "googletrans": DEFAULT_SUMMARY_PROVIDER,
        "google_translate": DEFAULT_SUMMARY_PROVIDER,
        "legacy_google_translate": DEFAULT_SUMMARY_PROVIDER,
        "copilot": "copilot_cli",
        "copilot_cli": "copilot_cli",
    }
    resolved = aliases.get(normalized)
    if resolved is None:
        raise ValueError(f"unsupported summary provider: {provider}")
    return resolved


def translate_to_japanese(text: str, *, translator: object | None = None) -> str:
    cleaned = clean_post_source_text(text)
    if not cleaned:
        return cleaned
    return translate_with_legacy_google_translate(cleaned, translator=translator)


def build_source_tweet_url(screen_name: str, tweet_id: str, *, source_username: str = "") -> str:
    normalized_screen_name = (screen_name or source_username).strip().lstrip("@")
    normalized_tweet_id = tweet_id.strip()
    if not normalized_screen_name or not normalized_tweet_id:
        return ""
    return f"https://x.com/{normalized_screen_name}/status/{normalized_tweet_id}"


def normalize_summary_body(body_text: str) -> str:
    return body_text.strip()


def strip_summary_emoji(text: str) -> str:
    return EMOJI_PATTERN.sub("", text).replace("\u200d", "").replace("\ufe0f", "")


def normalize_single_post_summary_body(body_text: str) -> str:
    normalized = normalize_summary_body(body_text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = strip_summary_emoji(normalized)

    compact_lines: list[str] = []
    for raw_line in normalized.split("\n"):
        cleaned_line = LIST_MARKER_PATTERN.sub("", raw_line.strip())
        if not cleaned_line:
            continue
        compact_lines.append(cleaned_line)

    compacted = " ".join(compact_lines)
    compacted = re.sub(r"\s+", " ", compacted).strip()
    compacted = re.sub(r"\s+([、。！？!?,.:;])", r"\1", compacted)
    compacted = re.sub(r"([（\(])\s+", r"\1", compacted)
    compacted = re.sub(r"\s+([）\)])", r"\1", compacted)
    return compacted


def format_full_translation_post(body_text: str) -> str:
    normalized_body = normalize_summary_body(body_text)
    return normalized_body.rstrip()


def format_translation_post(body_text: str, *, max_length: int) -> str:
    effective_max_length = max(max_length, 0)
    normalized_body = normalize_single_post_summary_body(body_text)
    available_body_length = max(effective_max_length, 0)
    formatted_body = (
        truncate_text_naturally(normalized_body, available_body_length, measure_length=estimate_x_text_length)
        if available_body_length
        else ""
    )
    return truncate_post_text(formatted_body.rstrip(), effective_max_length)


def compose_source_link_post(body_text: str, *, source_url: str, source_reference_mode: str = "url") -> str:
    if source_reference_mode == "none" or not source_url:
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
    source_reference_mode: str = "url",
    max_body_length: int = THREAD_BODY_MAX_LENGTH,
    single_post_max_length: int = MAX_X_POST_LENGTH,
    max_posts: int = MAX_THREAD_TWEETS,
) -> list[str]:
    normalized = text.strip()
    if not normalized:
        raise ValueError("thread text is empty")
    if single_post_max_length <= 0:
        raise ValueError("single_post_max_length must be > 0")
    resolved_single_post_max_length = min(single_post_max_length, MAX_X_POST_LENGTH)

    single_post = compose_source_link_post(
        normalized,
        source_url=source_url,
        source_reference_mode=source_reference_mode,
    )
    if _fits_post_text(single_post, resolved_single_post_max_length):
        return [single_post]

    def first_predicate(candidate: str) -> bool:
        return _fits_body_text(candidate, max_body_length) and _fits_post_text(
            f"{candidate.rstrip()}{THREAD_CONTINUATION_SUFFIX}"
        )

    def middle_predicate(candidate: str) -> bool:
        return _fits_body_text(candidate, max_body_length) and _fits_post_text(candidate)

    def final_predicate(candidate: str) -> bool:
        return _fits_body_text(candidate, max_body_length) and _fits_post_text(
            compose_source_link_post(
                candidate,
                source_url=source_url,
                source_reference_mode=source_reference_mode,
            )
        )

    posts: list[str] = []
    remaining = normalized
    while remaining:
        if posts and final_predicate(remaining):
            posts.append(
                compose_source_link_post(
                    remaining,
                    source_url=source_url,
                    source_reference_mode=source_reference_mode,
                )
            )
            break

        if not posts and final_predicate(remaining):
            posts.append(
                compose_source_link_post(
                    remaining,
                    source_url=source_url,
                    source_reference_mode=source_reference_mode,
                )
            )
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
            posts.append(
                compose_source_link_post(
                    segment,
                    source_url=source_url,
                    source_reference_mode=source_reference_mode,
                )
            )
            break

        if not posts:
            posts.append(f"{segment}{THREAD_CONTINUATION_SUFFIX}")
        else:
            posts.append(segment)

    return posts


def build_summary_body(
    text: str,
    *,
    language: str,
    translator: object | None = None,
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    copilot_model: str = DEFAULT_COPILOT_MODEL,
    copilot_prompt_path: str = "",
    command_runner: Callable[..., object] | None = None,
    working_directory: str | Path | None = None,
    diagnostics_sink: dict[str, object] | None = None,
) -> str:
    cleaned = clean_post_source_text(text)
    if language == "raw":
        return cleaned
    if not cleaned:
        return cleaned

    resolved_provider = resolve_summary_provider(provider)
    if resolved_provider == DEFAULT_SUMMARY_PROVIDER:
        return translate_with_legacy_google_translate(cleaned, translator=translator)

    result = summarize_with_copilot_cli_result(
        cleaned,
        model=copilot_model,
        prompt_path=copilot_prompt_path,
        command_runner=command_runner,
        working_directory=working_directory,
    )
    if diagnostics_sink is not None:
        diagnostics_sink.clear()
        diagnostics_sink.update(
            {
                "provider": resolved_provider,
                "model": copilot_model or DEFAULT_COPILOT_MODEL,
                "stderr": result.stderr,
                "usage_lines": result.usage_lines,
            }
        )
    return result.summary


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
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    copilot_model: str = DEFAULT_COPILOT_MODEL,
    copilot_prompt_path: str = "",
    command_runner: Callable[..., object] | None = None,
    working_directory: str | Path | None = None,
    diagnostics_sink: dict[str, object] | None = None,
) -> str:
    del prefix, screen_name, tweet_id, source_username
    body = build_summary_body(
        text,
        language=language,
        translator=translator,
        provider=provider,
        copilot_model=copilot_model,
        copilot_prompt_path=copilot_prompt_path,
        command_runner=command_runner,
        working_directory=working_directory,
        diagnostics_sink=diagnostics_sink,
    )
    if not body:
        body = "$MU関連の注目投稿"
    return format_translation_post(body, max_length=max_length)


def build_thread_summary(
    text: str,
    *,
    language: str,
    translator: object | None = None,
    provider: str = DEFAULT_SUMMARY_PROVIDER,
    copilot_model: str = DEFAULT_COPILOT_MODEL,
    copilot_prompt_path: str = "",
    command_runner: Callable[..., object] | None = None,
    working_directory: str | Path | None = None,
    diagnostics_sink: dict[str, object] | None = None,
) -> str:
    body = build_summary_body(
        text,
        language=language,
        translator=translator,
        provider=provider,
        copilot_model=copilot_model,
        copilot_prompt_path=copilot_prompt_path,
        command_runner=command_runner,
        working_directory=working_directory,
        diagnostics_sink=diagnostics_sink,
    )
    if not body:
        body = "$MU関連の注目投稿"
    return format_full_translation_post(body)
