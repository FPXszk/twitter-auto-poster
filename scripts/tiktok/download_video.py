from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_downloader.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_downloader_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok downloader helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

download_tiktok_video_job = helper_module.download_tiktok_video_job


def parse_bool(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a single TikTok video for debugging.")
    parser.add_argument("--url", required=True, help="TikTok video URL to inspect or download.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to store download artifacts.")
    parser.add_argument(
        "--dry-run",
        default="false",
        help="When true, fetch metadata only and skip video download.",
    )
    parser.add_argument("--force", action="store_true", help="Re-download even if source.mp4 already exists.")
    parser.add_argument("--cookies-from-browser", default="", help="Pass through to yt-dlp --cookies-from-browser.")
    parser.add_argument("--cookies-file", type=Path, default=None, help="Pass through to yt-dlp --cookies.")
    parser.add_argument("--max-size-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        job = download_tiktok_video_job(
            args.url,
            args.output_dir,
            max_size_bytes=args.max_size_bytes,
            cookies_from_browser=args.cookies_from_browser,
            cookies_file=args.cookies_file,
            dry_run=parse_bool(args.dry_run),
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    payload = job.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if job.ok:
        LOGGER.info("%s", job.message or "TikTok download job completed")
        return 0

    LOGGER.error("%s", job.message or "TikTok download job failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
