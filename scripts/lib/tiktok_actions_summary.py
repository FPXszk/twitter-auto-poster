from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_result_payload(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("result payload must be a JSON object")
    return payload


def render_actions_summary(payload: Mapping[str, Any]) -> list[str]:
    state = str(payload.get("current_state") or payload.get("final_state") or "unknown")
    lines = ["## TikTok anonymization run", ""]
    lines.append(f"- Result: `{'ok' if payload.get('ok') else 'error'}`")
    lines.append(f"- Video ID: `{payload.get('video_id', '')}`")
    lines.append(f"- Current/final phase: `{state}`")
    lines.append(f"- Detected face count: `{payload.get('detected_face_count', 0)}`")
    lines.append(f"- Track count: `{payload.get('track_count', 0)}`")
    lines.append(f"- Validation result: `{payload.get('validation_ok', False)}`")
    lines.append(f"- Similarity variant applied: `{payload.get('similarity_variant_applied', False)}`")
    lines.append(f"- External reference audio used: `{payload.get('used_external_reference_audio', False)}`")
    lines.append(f"- Cloud export destination: `{payload.get('export_dir_name', '')}`")
    lines.append(f"- Output filename: `{payload.get('output_filename', '')}`")
    lines.append(f"- Processing duration: `{payload.get('processing_seconds', 0)}`")
    failure = payload.get("failure") or {}
    if failure:
        lines.append(f"- Failure category: `{failure.get('category', '')}`")
        lines.append(f"- Failure reason: `{failure.get('message', '')}`")
    else:
        lines.append("- Failure category: ``")
        lines.append("- Failure reason: ``")
    if payload.get("result_path"):
        lines.append(f"- Result JSON: `{payload['result_path']}`")
    return lines
