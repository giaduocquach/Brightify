"""JSON report writer with validity labels. §8 — Phase 1."""

from __future__ import annotations

import json
import os
from typing import Any


def write_json(report: Any, path: str) -> None:
    """Serialise BacktestReport to JSON, including validity labels."""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    data = report.to_dict()
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=_json_default)


def _json_default(obj: Any):
    """Fallback serialiser for numpy scalars etc."""
    if hasattr(obj, 'item'):
        return obj.item()
    if hasattr(obj, '__float__'):
        return float(obj)
    return str(obj)
