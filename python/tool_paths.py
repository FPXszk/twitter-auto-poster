from __future__ import annotations

import os
from pathlib import Path


def default_twitter_bin() -> Path:
    override = os.environ.get("TWITTER_BIN", "").strip()
    if override:
        return Path(override)

    if os.name == "nt":
        return Path("python/.venv/Scripts/twitter.exe")

    return Path("python/.venv/bin/twitter")
