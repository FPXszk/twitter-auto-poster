from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)
HELPER_PATH = Path(__file__).resolve().parents[1] / "lib" / "tiktok_actions_summary.py"

helper_spec = importlib.util.spec_from_file_location("repo_tiktok_actions_summary_helper", HELPER_PATH)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"failed to load TikTok actions summary helper from {HELPER_PATH}")
helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

load_result_payload = helper_module.load_result_payload
render_actions_summary = helper_module.render_actions_summary


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(levelname)s] %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write GitHub Actions summary for TikTok anonymization.")
    parser.add_argument("--result-json", type=Path, required=True)
    parser.add_argument("--summary-path", type=Path, required=True)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    try:
        payload = load_result_payload(args.result_json)
        lines = render_actions_summary(payload)
        args.summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as error:
        LOGGER.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
