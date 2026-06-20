from pathlib import Path

import yaml


def main() -> int:
    paths = sorted(Path("config").glob("*.yaml")) + sorted(Path(".github/workflows").glob("*.yml"))
    if not paths:
        raise SystemExit("No YAML files found.")

    for path in paths:
        yaml.safe_load(path.read_text(encoding="utf-8"))
        print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
