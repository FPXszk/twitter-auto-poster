from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_validation_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"validation result not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("validation result must be a JSON object")
    if not bool(payload.get("ok")):
        raise RuntimeError("validation result must be ok before export")
    return payload


def _ensure_directory_is_writable(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"export directory not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"export directory is not a directory: {path}")
    probe = path / ".tiktok-export-write-test"
    probe.write_text("ok\n", encoding="utf-8")
    probe.unlink()


def _destination_dir(root: Path, *, video_id: str, force: bool) -> Path:
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    base = root / f"{date_prefix}_{video_id}"
    if not base.exists():
        return base
    if not force:
        raise FileExistsError(f"export destination already exists: {base}")
    suffix = 2
    while True:
        candidate = root / f"{date_prefix}_{video_id}_attempt-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def export_validated_video(
    *,
    candidate_video_path: str | Path,
    validation_result_path: str | Path,
    export_root: str | Path,
    video_id: str,
    source_url: str,
    force: bool = False,
) -> dict[str, Any]:
    candidate = Path(candidate_video_path)
    if not candidate.exists():
        raise FileNotFoundError(f"candidate video not found: {candidate}")

    validation_path = Path(validation_result_path)
    validation_payload = _load_validation_payload(validation_path)

    export_base = Path(export_root)
    _ensure_directory_is_writable(export_base)
    destination_dir = _destination_dir(export_base, video_id=str(video_id or "").strip(), force=force)
    destination_dir.mkdir(parents=True, exist_ok=False)

    destination_video = destination_dir / "ready_to_post.mp4"
    temp_video = destination_dir / "ready_to_post.mp4.partial"
    source_url_path = destination_dir / "source_url.txt"
    readme_path = destination_dir / "README.txt"
    result_path = destination_dir / "result.json"

    shutil.copy2(candidate, temp_video)
    temp_sha256 = _sha256(temp_video)
    candidate_sha256 = _sha256(candidate)
    if temp_sha256 != candidate_sha256:
        temp_video.unlink(missing_ok=True)
        raise RuntimeError("export checksum mismatch after copy")
    temp_video.replace(destination_video)

    source_url_path.write_text(str(source_url or "").strip() + "\n", encoding="utf-8")
    readme_path.write_text(
        "\n".join(
            [
                "TikTok manual publishing package",
                "",
                "1. Review ready_to_post.mp4 completely on iPhone or PC.",
                "2. Open TikTok manually and import this file.",
                "3. Enter caption and hashtags manually.",
                "4. Publish manually after final human review.",
                "",
                f"Video ID: {video_id}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = {
        "ok": True,
        "video_id": str(video_id or "").strip(),
        "ready_to_post_path": str(destination_video),
        "source_url_path": str(source_url_path),
        "readme_path": str(readme_path),
        "validation_result_path": str(validation_path),
        "file_size_bytes": destination_video.stat().st_size,
        "sha256": candidate_sha256,
        "source_url": str(source_url or "").strip(),
        "export_root": str(export_base),
        "export_dir": str(destination_dir),
        "message": "validated video exported to iCloud staging directory",
        "candidate_summary": {
            "duration_seconds": validation_payload.get("candidate", {}).get("duration_seconds", 0.0),
            "video_codec": validation_payload.get("candidate", {}).get("video_codec", ""),
            "audio_codec": validation_payload.get("candidate", {}).get("audio_codec", ""),
            "coverage_ratio": validation_payload.get("coverage_ratio", 0.0),
        },
    }
    _write_json(result_path, payload)
    payload["result_path"] = str(result_path)
    return payload
