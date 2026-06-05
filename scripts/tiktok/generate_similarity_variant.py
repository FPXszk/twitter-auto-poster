from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_similarity_variant.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_similarity_variant_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load tiktok similarity variant helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

generate_similarity_variant = helper_module.generate_similarity_variant


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
    parser = argparse.ArgumentParser(description="Generate a similarity-reduction TikTok variant video.")
    parser.add_argument("--input", type=Path, required=True, help="Path to normalized.mp4.")
    parser.add_argument("--output", type=Path, required=True, help="Path to the generated variant MP4.")
    parser.add_argument("--config", type=Path, default=None, help="Optional JSON config file for default values.")
    parser.add_argument("--audio-input", type=Path, default=None, help="Optional reusable audio file to replace source audio.")
    parser.add_argument("--horizontal-flip", default=None, help="Whether to apply horizontal mirroring.")
    parser.add_argument("--speed", type=float, default=None)
    parser.add_argument("--brightness", type=float, default=None)
    parser.add_argument("--contrast", type=float, default=None)
    parser.add_argument("--saturation", type=float, default=None)
    parser.add_argument("--mosaic-bottom-ratio", type=float, default=None)
    parser.add_argument("--mosaic-block-size", type=int, default=None)
    parser.add_argument("--crf", type=int, default=None)
    parser.add_argument("--preset", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pick(config: dict[str, Any], key: str, cli_value: Any, default: Any) -> Any:
    if cli_value is not None:
        return cli_value
    if key in config:
        return config[key]
    return default


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        config = _load_config(args.config)
        horizontal_flip_value = _pick(config, "horizontal_flip", args.horizontal_flip, True)
        payload = generate_similarity_variant(
            args.input,
            args.output,
            horizontal_flip=parse_bool(horizontal_flip_value) if isinstance(horizontal_flip_value, str) else bool(horizontal_flip_value),
            speed=float(_pick(config, "speed", args.speed, 0.8)),
            brightness=float(_pick(config, "brightness", args.brightness, -0.12)),
            contrast=float(_pick(config, "contrast", args.contrast, 0.95)),
            saturation=float(_pick(config, "saturation", args.saturation, 0.92)),
            mosaic_bottom_ratio=float(_pick(config, "mosaic_bottom_ratio", args.mosaic_bottom_ratio, 0.15)),
            mosaic_block_size=int(_pick(config, "mosaic_block_size", args.mosaic_block_size, 24)),
            crf=int(_pick(config, "crf", args.crf, 18)),
            preset=str(_pick(config, "preset", args.preset, "medium")),
            audio_input=args.audio_input,
            force=args.force,
        )
    except Exception as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
