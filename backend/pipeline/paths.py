"""Shared filesystem locations and stage artifact IO.

Each stage reads the previous stage's artifact and writes its own, so any stage
can be re-run in isolation without repeating upstream API calls.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

BACKEND = pathlib.Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
DATA = REPO / "data"
PRODUCTS = DATA / "products.json"
ARTIFACTS = BACKEND / "snapshots" / "stages"
SNAPSHOT = BACKEND / "snapshots" / "snapshot.json"
SAMPLE_SNAPSHOT = BACKEND / "snapshots" / "sample.snapshot.json"
CACHE = BACKEND / "pipeline" / "cache"


def load_products() -> list[dict[str, Any]]:
    return json.loads(PRODUCTS.read_text())["products"]


def write_stage(name: str, payload: Any) -> pathlib.Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str))
    return path


def read_stage(name: str) -> Any:
    path = ARTIFACTS / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Stage artifact {path} is missing. Run the earlier pipeline stages first."
        )
    return json.loads(path.read_text())
