from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
DEFAULT_OUTPUT_PATH = Path("tmp/post-video/post-video-result.json")
HELPER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "post_video.py"

helper_spec = importlib.util.spec_from_file_location("repo_post_video_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load post video helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

build_post_video_failure_payload = helper_module.build_post_video_failure_payload
post_video_tweet = helper_module.post_video_tweet
write_post_video_result = helper_module.write_post_video_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post a local MP4 video to X using twikit.")
    parser.add_argument("--text", required=True, help="Tweet text for the video post.")
    parser.add_argument("--video-path", type=Path, required=True, help="Local path to an MP4 video file.")
    parser.add_argument(
        "--dry-run",
        default="true",
        help="When true, validate the request without posting. Accepts true/false.",
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_bool(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)
    dry_run = True

    try:
        dry_run = parse_bool(args.dry_run)
        payload = post_video_tweet(
            tweet_text=args.text,
            video_path=args.video_path,
            dry_run=dry_run,
        )
    except Exception as error:
        payload = build_post_video_failure_payload(
            message=str(error),
            tweet_text=args.text,
            video_path=args.video_path,
            dry_run=dry_run,
        )
        write_post_video_result(args.output_path, payload)
        LOGGER.error("%s", payload["message"])
        return 1

    write_post_video_result(args.output_path, payload)
    LOGGER.info("%s", payload["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
