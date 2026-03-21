from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report Python runtime diagnostics.")
    parser.add_argument("--module", action="append", default=[], dest="modules")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "modules": {
            module_name: bool(importlib.util.find_spec(module_name))
            for module_name in args.modules
        },
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
