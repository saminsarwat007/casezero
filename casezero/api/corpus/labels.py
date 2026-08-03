"""Read the checked-in synthetic evaluation labels without loading email bodies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LABELS_PATH = Path(__file__).resolve().parents[2] / "corpus" / "v1" / "labels.json"


def load_evaluation_labels(path: Path = LABELS_PATH) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text())
    rows = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"Corpus labels at {path} must contain a list of cases.")
    return [dict(row) for row in rows]

