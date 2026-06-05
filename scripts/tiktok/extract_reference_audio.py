from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_reference_audio.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_reference_audio_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok reference audio helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

extract_reference_audio_from_tiktok = helper_module.extract_reference_audio_from_tiktok


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract reusable reference audio from a TikTok video URL.")
    parser.add_argument("--url", required=True, help="TikTok video URL to extract reusable audio from.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to store audio artifacts.")
    parser.add_argument("--cookies-from-browser", default="", help="Pass through to yt-dlp --cookies-from-browser.")
    parser.add_argument("--cookies-file", type=Path, default=None, help="Pass through to yt-dlp --cookies.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        payload = extract_reference_audio_from_tiktok(
            args.url,
            args.output_dir,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies_file,
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
