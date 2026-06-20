from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

PIPELINE_STATES = (
    "CREATED",
    "DOWNLOADED",
    "NORMALIZED",
    "VARIANT_GENERATED",
    "FACE_DETECTED",
    "FACE_TRACKED",
    "STAMPED",
    "VALIDATED",
    "EXPORTED",
    "FAILED",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_processing_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {}
    raw = state_path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def save_processing_state(path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    state_path = Path(path)
    payload["updated_at"] = _utc_now()
    _write_json(state_path, payload)
    return payload


def create_initial_state(
    *,
    video_id: str,
    input_url: str,
    canonical_url: str,
    source_sha256: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "schema_version": 1,
        "video_id": str(video_id or "").strip(),
        "input_url": str(input_url or "").strip(),
        "canonical_url": str(canonical_url or "").strip(),
        "source_sha256": str(source_sha256 or "").strip(),
        "current_state": "CREATED",
        "previous_state": "",
        "created_at": now,
        "updated_at": now,
        "attempt_sequence": 0,
        "attempts": [],
        "artifacts": {},
        "config": dict(config or {}),
        "failure": {},
        "export": {},
    }


def current_attempt(payload: dict[str, Any]) -> dict[str, Any] | None:
    attempts = payload.get("attempts") or []
    if not attempts:
        return None
    attempt = attempts[-1]
    return attempt if isinstance(attempt, dict) else None


def begin_attempt(payload: dict[str, Any], *, force: bool) -> dict[str, Any]:
    next_sequence = int(payload.get("attempt_sequence") or 0) + 1
    payload["attempt_sequence"] = next_sequence
    attempt = {
        "attempt_id": f"attempt-{next_sequence:03d}",
        "sequence": next_sequence,
        "force": bool(force),
        "started_at": _utc_now(),
        "completed_at": "",
        "final_state": "",
        "transitions": [],
        "failures": [],
    }
    payload.setdefault("attempts", []).append(attempt)
    return attempt


def transition_state(
    payload: dict[str, Any],
    new_state: str,
    *,
    message: str = "",
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if new_state not in PIPELINE_STATES:
        raise ValueError(f"unsupported state: {new_state}")
    previous = str(payload.get("current_state") or "")
    payload["previous_state"] = previous
    payload["current_state"] = new_state
    if artifacts:
        payload.setdefault("artifacts", {}).update(artifacts)
    transition = {
        "state": new_state,
        "previous_state": previous,
        "at": _utc_now(),
        "message": str(message or ""),
        "artifacts": dict(artifacts or {}),
    }
    attempt = current_attempt(payload)
    if attempt is not None:
        attempt.setdefault("transitions", []).append(transition)
        if new_state == "EXPORTED":
            attempt["completed_at"] = transition["at"]
            attempt["final_state"] = new_state
    if new_state != "FAILED":
        payload["failure"] = {}
    return payload


def record_failure(
    payload: dict[str, Any],
    *,
    phase: str,
    category: str,
    message: str,
    retryable: bool,
) -> dict[str, Any]:
    failure = {
        "phase": str(phase or "").strip(),
        "category": str(category or "").strip(),
        "message": str(message or "").strip(),
        "retryable": bool(retryable),
        "at": _utc_now(),
    }
    payload["previous_state"] = str(payload.get("current_state") or "")
    payload["current_state"] = "FAILED"
    payload["failure"] = failure
    attempt = current_attempt(payload)
    if attempt is not None:
        attempt.setdefault("failures", []).append(failure)
        attempt["completed_at"] = failure["at"]
        attempt["final_state"] = "FAILED"
    return payload


def should_skip_as_exported(payload: dict[str, Any], *, force: bool) -> bool:
    if force:
        return False
    if str(payload.get("current_state") or "") != "EXPORTED":
        return False
    export_payload = payload.get("export") or {}
    return bool(export_payload.get("ready_to_post_path"))


def set_export_details(payload: dict[str, Any], export_payload: dict[str, Any]) -> dict[str, Any]:
    payload["export"] = dict(export_payload)
    return payload


@contextmanager
def processing_lock(path: str | Path) -> Iterator[Path]:
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    acquired = False
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        acquired = True
        os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
        yield lock_path
    except FileExistsError as exc:
        raise RuntimeError(f"processing already in progress: {lock_path}") from exc
    finally:
        if fd is not None:
            os.close(fd)
        if not acquired:
            return
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
