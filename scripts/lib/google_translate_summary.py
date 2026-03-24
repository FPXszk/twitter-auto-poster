from __future__ import annotations

import logging
from typing import Protocol

LOGGER = logging.getLogger(__name__)


class TranslationResponse(Protocol):
    text: str


class TranslatorProtocol(Protocol):
    def translate(self, text: str, dest: str) -> TranslationResponse: ...


def load_translator() -> TranslatorProtocol:
    from googletrans import Translator

    return Translator()


def translate_to_japanese(text: str, *, translator: TranslatorProtocol | None = None) -> str:
    if not text:
        return text

    active_translator = translator or load_translator()
    try:
        response = active_translator.translate(text, dest="ja")
    except Exception as exc:
        LOGGER.warning("googletrans failed; falling back to source text: %s", exc)
        return text

    translated = str(getattr(response, "text", "") or "").strip()
    if not translated:
        LOGGER.warning("googletrans returned empty text; falling back to source text")
        return text
    return translated
