from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_face_tracker.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_face_tracker_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok face tracker helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

track_faces_in_detections = helper_module.track_faces_in_detections


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track faces from TikTok face detections.")
    parser.add_argument("--detections", type=Path, required=True, help="Path to detections.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for face tracking artifacts.")
    parser.add_argument("--smoothing-alpha", type=float, default=0.3)
    parser.add_argument("--max-gap-frames", type=int, default=5)
    parser.add_argument("--min-iou", type=float, default=0.05)
    parser.add_argument("--max-center-distance", type=float, default=0.2)
    parser.add_argument("--max-area-ratio", type=float, default=3.0)
    parser.add_argument("--preview-interval", type=int, default=30)
    parser.add_argument("--force", action="store_true")
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
        payload = track_faces_in_detections(
            args.detections,
            args.output_dir,
            smoothing_alpha=args.smoothing_alpha,
            max_gap_frames=args.max_gap_frames,
            min_iou=args.min_iou,
            max_center_distance=args.max_center_distance,
            max_area_ratio=args.max_area_ratio,
            preview_interval=args.preview_interval,
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
