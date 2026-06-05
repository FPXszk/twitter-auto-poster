from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_detection_transform.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_detection_transform_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok detection transform helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

transform_tracked_detections = helper_module.transform_tracked_detections


def parse_bool(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transform tracked detections for derived TikTok video variants.")
    parser.add_argument("--detections", type=Path, required=True, help="Path to tracked_detections.json.")
    parser.add_argument("--output", type=Path, required=True, help="Path to write transformed detections JSON.")
    parser.add_argument("--horizontal-flip", default="false")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        payload = transform_tracked_detections(
            args.detections,
            args.output,
            horizontal_flip=parse_bool(args.horizontal_flip),
            speed=args.speed,
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
