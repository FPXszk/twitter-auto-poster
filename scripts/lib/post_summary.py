from __future__ import annotations

import logging
import os
import re
import time
import warnings
from collections.abc import Callable

LOGGER = logging.getLogger(__name__)

GEMINI_MODEL_NAME = "gemini-2.0-flash"
GEMINI_REQUEST_SLEEP_SECONDS = 4
GEMINI_RETRY_SLEEP_SECONDS = 10
GEMINI_MAX_INPUT_CHARS = 500
GEMINI_PROMPT_TEMPLATE = """次の英語ツイートを日本語に要約してください。
フォーマット：
🌟タイトル（10〜15字）
背景1〜2行
👉要点を2〜3個
ティッカーは$XXX形式で残す
300字以内に収める

ツイート：{tweet_text}"""

JA_REPLACEMENTS = [
    (r"\bearnings beat expectations\b", "決算が市場予想を上振れ"),
    (r"\brevenue outlook improves\b", "売上見通しが改善"),
    (r"\bearnings\b", "決算"),
    (r"\bexpectation(s)?\b", "期待"),
    (r"\brevenue\b", "売上"),
    (r"\boutlook\b", "見通し"),
    (r"\bguidance\b", "見通し"),
    (r"\bforecast\b", "予想"),
    (r"\bdemand\b", "需要"),
    (r"\bimprove(s|d)?\b", "改善"),
    (r"\bstrong\b", "強い"),
    (r"\bsteady\b", "安定"),
    (r"\brecent\b", "直近"),
    (r"\bpullback\b", "調整"),
    (r"\bmemory\b", "メモリ"),
    (r"\bchip(s)?\b", "半導体"),
    (r"\bsemiconductor(s)?\b", "半導体"),
    (r"\bbeat(s|ing)?\b", "上振れ"),
    (r"\bmiss(es|ing)?\b", "下振れ"),
    (r"\bsurge(s|d)?\b", "急伸"),
    (r"\bjump(s|ed|ing)?\b", "上昇"),
    (r"\brise(s|n|ing)?\b", "上昇"),
    (r"\bfall(s|ing|en)?\b", "下落"),
    (r"\bdrop(s|ped|ping)?\b", "下落"),
    (r"\bgain(s|ed|ing)?\b", "上昇"),
    (r"\bloss(es)?\b", "損失"),
    (r"\bprofit(s)?\b", "利益"),
    (r"\bbullish\b", "強気"),
    (r"\bbearish\b", "弱気"),
    (r"\bupgrade(d)?\b", "格上げ"),
    (r"\bdowngrade(d)?\b", "格下げ"),
    (r"\bAI\b", "AI"),
    (r"\bas\b", "で"),
    (r"\bwith\b", "で"),
    (r"&", "と"),
]


def clean_source_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \"'|")


def translate_to_japanese(text: str) -> str:
    cleaned = clean_source_text(text)
    for pattern, replacement in JA_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,:;")
    return cleaned


def truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip(" ,.;:") + "…"


def build_gemini_prompt(text: str) -> str:
    snippet = clean_source_text(text)[:GEMINI_MAX_INPUT_CHARS].rstrip()
    return GEMINI_PROMPT_TEMPLATE.format(tweet_text=snippet)


def extract_gemini_text(response: object) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None) or []
    parts_text: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                parts_text.append(part_text.strip())

    combined = "\n".join(parts_text).strip()
    if not combined:
        raise ValueError("gemini response did not contain text")
    return combined


def load_gemini_model(api_key: str) -> object:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import google.generativeai as genai

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL_NAME)


def is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True

    code = getattr(exc, "code", None)
    if code == 429:
        return True

    message = str(exc)
    return "429" in message or "ResourceExhausted" in type(exc).__name__


def call_gemini_summary(text: str, *, sleep_func: Callable[[float], None] = time.sleep) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    prompt = build_gemini_prompt(text)
    model = load_gemini_model(api_key)
    last_error: Exception | None = None

    for attempt in range(2):
        should_retry = False
        sleep_func(GEMINI_REQUEST_SLEEP_SECONDS)
        try:
            response = model.generate_content(prompt)
            return extract_gemini_text(response)
        except Exception as exc:
            last_error = exc
            if is_rate_limit_error(exc) and attempt == 0:
                should_retry = True
        finally:
            sleep_func(GEMINI_REQUEST_SLEEP_SECONDS)

        if should_retry:
            LOGGER.warning(
                "gemini API returned 429; retrying once after %s seconds",
                GEMINI_RETRY_SLEEP_SECONDS,
            )
            sleep_func(GEMINI_RETRY_SLEEP_SECONDS)
            continue

        break

    if last_error is not None:
        raise last_error
    raise RuntimeError("gemini summary failed without a captured error")


def build_summary_body(text: str, *, language: str) -> tuple[str, bool, bool]:
    if language == "raw":
        return clean_source_text(text), True, False

    if not os.environ.get("GEMINI_API_KEY", "").strip():
        return translate_to_japanese(text), True, False

    try:
        return call_gemini_summary(text), False, True
    except Exception as exc:
        LOGGER.warning("gemini summary failed; falling back to source text: %s", exc)
        return clean_source_text(text), True, True


def build_summary(text: str, *, prefix: str, language: str, max_length: int) -> str:
    body, use_prefix, preserve_original_text = build_summary_body(text, language=language)

    if not body:
        body = "$MU関連の注目投稿"
        use_prefix = True
        preserve_original_text = False

    if "$MU" in body.upper() and prefix == "Xで反応上位の$MU投稿: ":
        prefix = "Xで反応上位: "

    effective_prefix = prefix if use_prefix else ""
    body = truncate_text(body, max(max_length - len(effective_prefix), 1))
    summary = effective_prefix + body
    if (
        not preserve_original_text
        and len(summary) < max_length
        and not summary.endswith(("。", "！", "?", "？"))
    ):
        summary += "。"
    return truncate_text(summary, max_length)
