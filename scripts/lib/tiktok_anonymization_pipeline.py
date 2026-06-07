from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tiktok_downloader import download_tiktok_video_job
from tiktok_export import export_validated_video
from tiktok_face_detector import detect_faces_in_video
from tiktok_face_overlay import overlay_faces_on_video
from tiktok_face_tracker import track_faces_in_detections
from tiktok_final_validator import validate_final_video
from tiktok_reference_audio import extract_reference_audio_from_tiktok
from tiktok_similarity_variant import generate_similarity_variant
from tiktok_processing_state import (
    begin_attempt,
    create_initial_state,
    load_processing_state,
    processing_lock,
    record_failure,
    save_processing_state,
    set_export_details,
    should_skip_as_exported,
    transition_state,
)

logger = logging.getLogger(__name__)

_DEFAULT_VARIANT_BRIGHTNESS = -0.12
_DEFAULT_VARIANT_CONTRAST = 0.95
_DEFAULT_VARIANT_SATURATION = 0.92
_DEFAULT_VARIANT_SPEED = 0.8
_DEFAULT_VARIANT_MOSAIC_BOTTOM_RATIO = 0.35
_DEFAULT_VARIANT_MOSAIC_BLOCK_SIZE = 24


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _resolve_stamp_asset(stamp_type: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    candidate = root / "assets" / "face_stamps" / f"{stamp_type}.png"
    if not candidate.exists():
        raise FileNotFoundError(f"stamp asset not found: {candidate}")
    return candidate


def _result_payload(
    *,
    ok: bool,
    video_id: str,
    current_state: str,
    input_url: str,
    job_dir: Path,
    state_path: Path,
    processing_seconds: float,
    failure: dict[str, Any] | None = None,
    detected_face_count: int = 0,
    track_count: int = 0,
    validation_ok: bool = False,
    export_payload: dict[str, Any] | None = None,
    similarity_variant_applied: bool = False,
    used_external_reference_audio: bool = False,
    reference_audio_url: str = "",
) -> dict[str, Any]:
    payload = {
        "ok": ok,
        "video_id": video_id,
        "input_url": input_url,
        "current_state": current_state,
        "job_dir": str(job_dir),
        "state_path": str(state_path),
        "processing_seconds": round(processing_seconds, 6),
        "detected_face_count": int(detected_face_count),
        "track_count": int(track_count),
        "validation_ok": bool(validation_ok),
        "similarity_variant_applied": bool(similarity_variant_applied),
        "used_external_reference_audio": bool(used_external_reference_audio),
        "reference_audio_url": str(reference_audio_url or ""),
        "failure": dict(failure or {}),
        "result_path": str(job_dir / "result.json"),
        "output_filename": "ready_to_post.mp4" if export_payload else "",
        "export_dir_name": Path(export_payload.get("export_dir", "")).name if export_payload else "",
    }
    if export_payload:
        payload["export"] = dict(export_payload)
    return payload


def _run_with_retry(
    *,
    attempts: int,
    phase: str,
    func: Callable[[], dict[str, Any]],
    retryable: Callable[[Exception], bool],
) -> dict[str, Any]:
    last_error: Exception | None = None
    for index in range(1, max(1, attempts) + 1):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - exercised through caller tests
            last_error = exc
            if index >= attempts or not retryable(exc):
                break
            logger.warning("Retrying %s after attempt %s/%s: %s", phase, index, attempts, exc)
    if last_error is None:
        raise RuntimeError(f"{phase} failed without an error")
    raise last_error


def _is_filesystem_retryable(error: Exception) -> bool:
    if isinstance(error, OSError):
        return True
    message = str(error).lower()
    return any(marker in message for marker in ("tempor", "locked", "busy", "denied", "network"))


def run_tiktok_anonymization_pipeline(
    *,
    tiktok_url: str,
    output_root: str | Path,
    export_dir: str | Path | None = None,
    reference_audio_url: str = "",
    apply_similarity_variant: bool = True,
    variant_speed: float = _DEFAULT_VARIANT_SPEED,
    variant_brightness: float = _DEFAULT_VARIANT_BRIGHTNESS,
    variant_contrast: float = _DEFAULT_VARIANT_CONTRAST,
    variant_saturation: float = _DEFAULT_VARIANT_SATURATION,
    variant_mosaic_bottom_ratio: float = _DEFAULT_VARIANT_MOSAIC_BOTTOM_RATIO,
    variant_mosaic_block_size: int = _DEFAULT_VARIANT_MOSAIC_BLOCK_SIZE,
    stamp_type: str = "default",
    stamp_scale: float = 1.6,
    force: bool = False,
    max_retries: int = 2,
    detector_min_confidence: float = 0.5,
    preview_interval: int = 30,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    output_root_path = Path(output_root)
    downloads_root = output_root_path / "downloads"
    jobs_root = output_root_path / "jobs"
    state_root = output_root_path / "state"
    latest_result = output_root_path / "latest-result.json"
    raw_export_dir = str(export_dir or os.environ.get("TIKTOK_EXPORT_DIR", "")).strip()
    if not raw_export_dir:
        raise RuntimeError("export_dir or TIKTOK_EXPORT_DIR is required")
    export_root = Path(raw_export_dir).expanduser()
    normalized_reference_audio_url = str(reference_audio_url or "").strip()

    stamp_path = _resolve_stamp_asset(stamp_type)

    download_job = _run_with_retry(
        attempts=max_retries,
        phase="download",
        func=lambda: download_tiktok_video_job(
            tiktok_url,
            downloads_root,
            dry_run=False,
            force=force,
        ).to_dict(),
        retryable=lambda exc: _is_filesystem_retryable(exc),
    )
    if not bool(download_job.get("ok")):
        raise RuntimeError(download_job.get("message") or "TikTok download failed")

    video_id = str(download_job.get("video_id") or "").strip()
    if not video_id:
        raise RuntimeError("download result did not include video_id")

    state_path = state_root / f"{video_id}.json"
    job_dir = jobs_root / video_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with processing_lock(state_root / f"{video_id}.lock"):
        state = load_processing_state(state_path)
        if not state:
            state = create_initial_state(
                video_id=video_id,
                input_url=tiktok_url,
                canonical_url=str(download_job.get("resolved_url") or tiktok_url),
                source_sha256="",
                config={
                    "stamp_type": stamp_type,
                    "stamp_scale": float(stamp_scale),
                    "apply_similarity_variant": bool(apply_similarity_variant),
                    "reference_audio_url": normalized_reference_audio_url,
                    "variant_speed": float(variant_speed),
                    "variant_brightness": float(variant_brightness),
                    "variant_contrast": float(variant_contrast),
                    "variant_saturation": float(variant_saturation),
                    "variant_mosaic_bottom_ratio": float(variant_mosaic_bottom_ratio),
                    "variant_mosaic_block_size": int(variant_mosaic_block_size),
                    "max_retries": int(max_retries),
                    "detector_min_confidence": float(detector_min_confidence),
                    "preview_interval": int(preview_interval),
                },
            )
        if should_skip_as_exported(state, force=force):
            result = _result_payload(
                ok=True,
                video_id=video_id,
                current_state="EXPORTED",
                input_url=tiktok_url,
                job_dir=job_dir,
                state_path=state_path,
                processing_seconds=time.perf_counter() - started_at,
                validation_ok=True,
                export_payload=state.get("export") or {},
                similarity_variant_applied=bool(state.get("artifacts", {}).get("variant_video_path")),
                used_external_reference_audio=bool(state.get("artifacts", {}).get("reference_audio_path")),
                reference_audio_url=normalized_reference_audio_url,
            )
            _write_json(job_dir / "result.json", result)
            _write_json(latest_result, result)
            return result

        begin_attempt(state, force=force)
        save_processing_state(state_path, state)

        normalized_path = Path(download_job.get("normalized_path") or download_job.get("output_path") or "")
        if not normalized_path.exists():
            raise FileNotFoundError(f"normalized video not found: {normalized_path}")

        transition_state(
            state,
            "DOWNLOADED",
            message="download completed",
            artifacts={
                "source_path": str(download_job.get("source_path") or ""),
                "normalized_path": str(normalized_path),
                "download_result_path": str(download_job.get("result_path") or ""),
            },
        )
        save_processing_state(state_path, state)
        transition_state(state, "NORMALIZED", message="normalized video ready")
        save_processing_state(state_path, state)

        try:
            reference_video_path = normalized_path
            detection_input_path = normalized_path
            used_external_reference_audio = False
            if apply_similarity_variant:
                variant_dir = job_dir / "variant"
                variant_video_path = variant_dir / "variant.mp4"
                reference_audio_path = None
                if normalized_reference_audio_url:
                    reference_audio_job = extract_reference_audio_from_tiktok(
                        normalized_reference_audio_url,
                        downloads_root / "reference-audio",
                        force=force,
                    )
                    reference_audio_path = Path(reference_audio_job.audio_path)
                    used_external_reference_audio = True
                variant_summary_path = variant_dir / "variant-summary.json"
                if variant_summary_path.exists() and variant_video_path.exists() and not force:
                    _read_json(variant_summary_path)
                else:
                    generate_similarity_variant(
                        normalized_path,
                        variant_video_path,
                        speed=variant_speed,
                        brightness=variant_brightness,
                        contrast=variant_contrast,
                        saturation=variant_saturation,
                        mosaic_bottom_ratio=variant_mosaic_bottom_ratio,
                        mosaic_block_size=variant_mosaic_block_size,
                        audio_input=reference_audio_path,
                        force=force,
                    )
                reference_video_path = variant_video_path
                detection_input_path = variant_video_path
                transition_state(
                    state,
                    "VARIANT_GENERATED",
                    message="similarity variant generated",
                    artifacts={
                        "variant_video_path": str(variant_video_path),
                        "variant_summary_path": str(variant_summary_path),
                        "reference_audio_path": str(reference_audio_path or ""),
                    },
                )
                save_processing_state(state_path, state)

            detection_dir = job_dir / "faces"
            detections_path = detection_dir / "detections.json"
            detection_summary_path = detection_dir / "summary.json"
            if detection_summary_path.exists() and detections_path.exists() and not force:
                detection_summary = _read_json(detection_summary_path)
            else:
                detection_summary = detect_faces_in_video(
                    detection_input_path,
                    detection_dir,
                    min_confidence=detector_min_confidence,
                    preview_interval=preview_interval,
                    force=force,
                )
            transition_state(
                state,
                "FACE_DETECTED",
                message="face detection completed",
                artifacts={
                    "detections_path": str(detections_path),
                    "detection_summary_path": str(detection_summary_path),
                },
            )
            save_processing_state(state_path, state)

            tracking_dir = job_dir / "tracks"
            tracked_path = tracking_dir / "tracked_detections.json"
            tracking_summary_path = tracking_dir / "tracking_summary.json"
            if tracking_summary_path.exists() and tracked_path.exists() and not force:
                tracking_summary = _read_json(tracking_summary_path)
            else:
                tracking_summary = track_faces_in_detections(
                    detections_path,
                    tracking_dir,
                    preview_interval=preview_interval,
                    force=force,
                )
            transition_state(
                state,
                "FACE_TRACKED",
                message="face tracking completed",
                artifacts={
                    "tracked_detections_path": str(tracked_path),
                    "tracking_summary_path": str(tracking_summary_path),
                },
            )
            save_processing_state(state_path, state)

            edited_dir = job_dir / "edited"
            candidate_video_path = edited_dir / "ready_to_post.mp4"
            overlay_summary_path = edited_dir / "overlay-summary.json"
            coverage_report_path = edited_dir / "face-coverage-report.json"
            if overlay_summary_path.exists() and candidate_video_path.exists() and not force:
                overlay_summary = _read_json(overlay_summary_path)
            else:
                overlay_summary = overlay_faces_on_video(
                    detection_input_path,
                    tracked_path,
                    stamp_path,
                    candidate_video_path,
                    scale=stamp_scale,
                    force=force,
                )
            transition_state(
                state,
                "STAMPED",
                message="face stamp overlay completed",
                artifacts={
                    "candidate_video_path": str(candidate_video_path),
                    "overlay_summary_path": str(overlay_summary_path),
                    "coverage_report_path": str(coverage_report_path),
                },
            )
            save_processing_state(state_path, state)

            validation_dir = job_dir / "validation"
            validation_result_path = validation_dir / "validation_result.json"
            if validation_result_path.exists() and not force:
                validation_payload = _read_json(validation_result_path)
            else:
                validation_payload = validate_final_video(
                    reference_video_path,
                    candidate_video_path,
                    coverage_report_path=coverage_report_path,
                    overlay_summary_path=overlay_summary_path,
                    preview_image_path=None,
                    output_dir=validation_dir,
                )
            transition_state(
                state,
                "VALIDATED",
                message="final validation completed",
                artifacts={"validation_result_path": str(validation_result_path)},
            )
            save_processing_state(state_path, state)

            export_payload = _run_with_retry(
                attempts=max_retries,
                phase="export",
                func=lambda: export_validated_video(
                    candidate_video_path=candidate_video_path,
                    validation_result_path=validation_result_path,
                    export_root=export_root,
                    video_id=video_id,
                    source_url=tiktok_url,
                    force=force,
                ),
                retryable=_is_filesystem_retryable,
            )
            set_export_details(state, export_payload)
            transition_state(
                state,
                "EXPORTED",
                message="export completed",
                artifacts={
                    "export_result_path": str(export_payload.get("result_path") or ""),
                    "export_dir": str(export_payload.get("export_dir") or ""),
                },
            )
            save_processing_state(state_path, state)
        except Exception as exc:
            record_failure(
                state,
                phase=str(state.get("current_state") or "unknown"),
                category=type(exc).__name__,
                message=str(exc),
                retryable=_is_filesystem_retryable(exc),
            )
            save_processing_state(state_path, state)
            result = _result_payload(
                ok=False,
                video_id=video_id,
                current_state="FAILED",
                input_url=tiktok_url,
                job_dir=job_dir,
                state_path=state_path,
                processing_seconds=time.perf_counter() - started_at,
                failure=state.get("failure") or {},
                similarity_variant_applied=bool(state.get("artifacts", {}).get("variant_video_path")),
                used_external_reference_audio=bool(state.get("artifacts", {}).get("reference_audio_path")),
                reference_audio_url=normalized_reference_audio_url,
            )
            _write_json(job_dir / "result.json", result)
            _write_json(latest_result, result)
            return result

        result = _result_payload(
            ok=True,
            video_id=video_id,
            current_state="EXPORTED",
            input_url=tiktok_url,
            job_dir=job_dir,
            state_path=state_path,
            processing_seconds=time.perf_counter() - started_at,
            detected_face_count=int(detection_summary.get("total_detections") or 0),
            track_count=int(tracking_summary.get("track_count") or 0),
            validation_ok=bool(validation_payload.get("ok")),
            export_payload=export_payload,
            similarity_variant_applied=apply_similarity_variant,
            used_external_reference_audio=used_external_reference_audio,
            reference_audio_url=normalized_reference_audio_url,
        )
        _write_json(job_dir / "result.json", result)
        _write_json(latest_result, result)
        return result
