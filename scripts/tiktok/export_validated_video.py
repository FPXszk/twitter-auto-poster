from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_export.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_export_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load TikTok export helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

export_validated_video = helper_module.export_validated_video


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a validated TikTok-ready video to iCloud Drive.")
    parser.add_argument("--candidate-video", type=Path, required=True)
    parser.add_argument("--validation-result", type=Path, required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        payload = export_validated_video(
            candidate_video_path=args.candidate_video,
            validation_result_path=args.validation_result,
            export_root=args.export_dir,
            video_id=args.video_id,
            source_url=args.source_url,
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
