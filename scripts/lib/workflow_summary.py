from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def load_latest_candidate_payload(
    candidate_files: Sequence[Path],
) -> tuple[dict[str, Any] | None, str | None]:
    if not candidate_files:
        return None, None

    candidate_path = candidate_files[-1]
    raw = candidate_path.read_text(encoding="utf-8")
    if not raw.strip():
        return None, f"{candidate_path.name}: candidate file is empty"

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{candidate_path.name}: candidate file contains invalid JSON ({exc})"

    if not isinstance(payload, Mapping):
        return None, f"{candidate_path.name}: candidate file did not contain a JSON object"

    return dict(payload), None
