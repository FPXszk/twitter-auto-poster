from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_anonymization_pipeline.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_anonymization_pipeline_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load TikTok anonymization pipeline helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

run_tiktok_anonymization_pipeline = helper_module.run_tiktok_anonymization_pipeline


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TikTok anonymization pipeline end-to-end.")
    parser.add_argument("--url", required=True, help="TikTok video URL.")
    parser.add_argument("--output-root", type=Path, required=True, help="Root directory for job artifacts.")
    parser.add_argument("--export-dir", type=Path, default=None, help="Override TIKTOK_EXPORT_DIR.")
    parser.add_argument("--stamp-type", default="default")
    parser.add_argument("--stamp-scale", type=float, default=1.6)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--detector-min-confidence", type=float, default=0.5)
    parser.add_argument("--preview-interval", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        payload = run_tiktok_anonymization_pipeline(
            tiktok_url=args.url,
            output_root=args.output_root,
            export_dir=args.export_dir,
            stamp_type=args.stamp_type,
            stamp_scale=args.stamp_scale,
            force=args.force,
            max_retries=args.max_retries,
            detector_min_confidence=args.detector_min_confidence,
            preview_interval=args.preview_interval,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
