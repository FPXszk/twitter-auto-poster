from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_final_validator.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_final_validator_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok final validator helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

validate_final_video = helper_module.validate_final_video


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a final TikTok-ready video artifact.")
    parser.add_argument("--reference-video", type=Path, required=True)
    parser.add_argument("--candidate-video", type=Path, required=True)
    parser.add_argument("--coverage-report", type=Path, default=None)
    parser.add_argument("--overlay-summary", type=Path, default=None)
    parser.add_argument("--preview-image", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--duration-tolerance-seconds", type=float, default=0.1)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        payload = validate_final_video(
            args.reference_video,
            args.candidate_video,
            coverage_report_path=args.coverage_report,
            overlay_summary_path=args.overlay_summary,
            preview_image_path=args.preview_image,
            output_dir=args.output_dir,
            duration_tolerance_seconds=args.duration_tolerance_seconds,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
