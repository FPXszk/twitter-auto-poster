from __future__ import annotations

import logging
import os
import warnings

warnings.simplefilter("ignore", FutureWarning)
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"google\.generativeai(\..*)?",
)
warnings.filterwarnings(
    "ignore",
    message=r".*package has ended.*",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"google\.api_core(\..*)?",
)
warnings.filterwarnings(
    "ignore",
    message=r".*Google will stop supporting.*",
    category=FutureWarning,
)

import google.generativeai as genai
from google.api_core.exceptions import (
    GoogleAPIError,
    NotFound,
    ResourceExhausted,
    RetryError,
)

MODEL_NAME = "gemini-2.0-flash"
PROMPT = """以下の英語を日本語に要約してください：
Apple stock rises 3% after strong earnings report"""


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def summarize_exception(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0]


def extract_response_text(response: object) -> str:
    candidates = getattr(response, "candidates", None) or []
    texts: list[str] = []

    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                texts.append(text.strip())

    message = "\n".join(text for text in texts if text).strip()
    if not message:
        raise ValueError("Gemini response did not contain any text.")
    return message


def main() -> int:
    configure_logging()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logging.error("GEMINI_API_KEY が設定されていません。")
        return 1

    logging.info("Gemini API 呼び出しを開始します。 model=%s", MODEL_NAME)
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    try:
        response = model.generate_content(PROMPT)
        message = extract_response_text(response)
    except NotFound as exc:
        logging.error("指定したモデルが利用できません: %s", summarize_exception(exc))
        return 1
    except ResourceExhausted as exc:
        logging.error(
            "Gemini API のクォータを超過しました。プランまたは請求設定を確認してください: %s",
            summarize_exception(exc),
        )
        return 1
    except (GoogleAPIError, RetryError, ValueError) as exc:
        logging.error("Gemini API 呼び出しに失敗しました: %s", summarize_exception(exc))
        return 1

    logging.info("Gemini API 呼び出しに成功しました。")
    print("=== Gemini response ===")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
