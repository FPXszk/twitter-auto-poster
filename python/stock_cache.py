from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stock_fetcher import StockSnapshot, snapshots_to_dicts

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STOCK_CACHE_PATH = PROJECT_ROOT / "tmp" / "stock_cache.json"


@dataclass(frozen=True)
class StockCacheBundle:
    metadata: dict[str, Any]
    snapshots: list[StockSnapshot]


def save_stock_cache(
    snapshots: list[StockSnapshot],
    path: Path = DEFAULT_STOCK_CACHE_PATH,
    metadata: dict[str, Any] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Any
    if metadata is None:
        payload = snapshots_to_dicts(snapshots)
    else:
        payload = {
            "metadata": metadata,
            "snapshots": snapshots_to_dicts(snapshots),
        }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _require_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"cache field '{key}' must be a non-empty string")
    return value


def _require_float(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"cache field '{key}' must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"cache field '{key}' must be numeric") from error


def _require_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"cache field '{key}' must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"cache field '{key}' must be an integer") from error


def _snapshot_from_dict(row: dict[str, Any]) -> StockSnapshot:
    return StockSnapshot(
        ticker=_require_str(row, "ticker"),
        name=_require_str(row, "name"),
        sector=_require_str(row, "sector"),
        latest_date=_require_str(row, "latest_date"),
        previous_close=_require_float(row, "previous_close"),
        current_close=_require_float(row, "current_close"),
        pct_change=_require_float(row, "pct_change"),
        volume=_require_int(row, "volume"),
        trading_value=_require_float(row, "trading_value"),
        average_volume_5d=_require_float(row, "average_volume_5d"),
        high_price=_require_float(row, "high_price"),
        fifty_two_week_high=_require_float(row, "fifty_two_week_high"),
    )


def load_stock_cache_bundle(path: Path = DEFAULT_STOCK_CACHE_PATH) -> StockCacheBundle:
    if not path.is_file():
        raise FileNotFoundError(f"stock cache not found: {path}")

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    metadata: dict[str, Any] = {}
    if isinstance(raw_data, list):
        rows = raw_data
    elif isinstance(raw_data, dict):
        metadata = raw_data.get("metadata") or {}
        rows = raw_data.get("snapshots")
        if not isinstance(rows, list):
            raise ValueError(f"stock cache 'snapshots' must contain a JSON list: {path}")
    else:
        raise ValueError(f"stock cache must contain a JSON list or object: {path}")

    snapshots: list[StockSnapshot] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"stock cache row {index} must be an object")
        snapshots.append(_snapshot_from_dict(row))
    return StockCacheBundle(metadata=metadata, snapshots=snapshots)


def load_stock_cache(path: Path = DEFAULT_STOCK_CACHE_PATH) -> list[StockSnapshot]:
    return load_stock_cache_bundle(path).snapshots
