from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_face_overlay.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_face_overlay_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok face overlay helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

overlay_faces_on_video = helper_module.overlay_faces_on_video


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Overlay face stamps on a normalized TikTok video.")
    parser.add_argument("--input", type=Path, required=True, help="Path to normalized.mp4.")
    parser.add_argument("--detections", type=Path, required=True, help="Path to tracked_detections.json.")
    parser.add_argument("--stamp", type=Path, required=True, help="Path to the transparent PNG stamp.")
    parser.add_argument("--output", type=Path, required=True, help="Path to edited.mp4.")
    parser.add_argument("--scale", type=float, default=1.6)
    parser.add_argument("--anchor-y-ratio", type=float, default=0.5)
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
        payload = overlay_faces_on_video(
            args.input,
            args.detections,
            args.stamp,
            args.output,
            scale=args.scale,
            anchor_y_ratio=args.anchor_y_ratio,
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
