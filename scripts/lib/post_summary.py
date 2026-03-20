from __future__ import annotations

import re

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


def build_summary(text: str, *, prefix: str, language: str, max_length: int) -> str:
    if language == "raw":
        body = clean_source_text(text)
    else:
        body = translate_to_japanese(text)

    if not body:
        body = "$MU関連の注目投稿"

    if "$MU" in body.upper() and prefix == "Xで反応上位の$MU投稿: ":
        prefix = "Xで反応上位: "

    body = truncate_text(body, max_length - len(prefix))
    summary = prefix + body
    if len(summary) < max_length and not summary.endswith(("。", "！", "?", "？")):
        summary += "。"
    return truncate_text(summary, max_length)
