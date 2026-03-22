from __future__ import annotations

import logging
import os
import time
import warnings
from collections.abc import Callable

from post_summary import clean_source_text

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
