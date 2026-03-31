from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_posted_ids(path: str | Path) -> set[str]:
    """Read a line-based state file and return the set of posted IDs."""
    state_path = Path(path)
    if not state_path.exists():
        return set()
    return {
        line.strip()
        for line in state_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def is_posted(video_id: str, posted_ids: set[str]) -> bool:
    """Check whether a video ID has already been posted."""
    return str(video_id or "").strip() in posted_ids


def mark_posted(video_id: str, path: str | Path, *, dry_run: bool = False) -> bool:
    """Append video_id to the state file. Returns True if written, False otherwise."""
    normalized = str(video_id or "").strip()
    if dry_run or not normalized:
        return False
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_posted_ids(state_path)
    if normalized in existing:
        return True
    with state_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{normalized}\n")
    return True
