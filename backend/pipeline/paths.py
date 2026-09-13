"""Shared filesystem locations and stage artifact IO.

Each stage reads the previous stage's artifact and writes its own, so any stage
can be re-run in isolation without repeating upstream API calls.
"""

from __future__ import annotations

import datetime as dt
import hashlib
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


def fingerprint(payload: Any) -> str:
    """Content hash of a stage's rows, used to prove what a later stage consumed."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def write_stage(
    name: str,
    rows: Any,
    consumed: str | None = None,
    calls: dict[str, int] | None = None,
) -> pathlib.Path:
    """Persist a stage's output along with the fingerprint of its input.

    Timestamps are not enough to tell whether a stage ran against current data --
    re-running stages out of order, or a chain that silently short-circuits, leaves
    a mtime that looks fresh over stale content. Recording what each stage actually
    consumed makes that detectable instead of guessable.

    `calls` records the API calls that stage made. Stages are routinely re-run
    individually, so a single run's counter is not the cost of the snapshot --
    summing the per-stage figures is.
    """
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f"{name}.json"
    document = {
        "_meta": {
            "stage": name,
            "written_at": dt.datetime.now(dt.UTC).isoformat(),
            "rows": len(rows) if hasattr(rows, "__len__") else None,
            "self": fingerprint(rows),
            "consumed": consumed,
            "calls": calls or {},
        },
        "rows": rows,
    }
    path.write_text(json.dumps(document, indent=1, ensure_ascii=False, default=str))
    return path


def read_stage(name: str) -> Any:
    """Rows only. Use `read_stage_meta` when provenance matters."""
    return _read_document(name)["rows"]


def read_stage_meta(name: str) -> dict[str, Any]:
    return _read_document(name)["_meta"]


def _read_document(name: str) -> dict[str, Any]:
    path = ARTIFACTS / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Stage artifact {path} is missing. Run the earlier pipeline stages first."
        )
    data = json.loads(path.read_text())
    # Artifacts written before provenance stamping were a bare list.
    if isinstance(data, list):
        return {"_meta": {"stage": name, "self": fingerprint(data),
                          "consumed": None, "rows": len(data),
                          "written_at": None, "legacy": True},
                "rows": data}
    return data


def check_chain(stages: list[str]) -> list[dict[str, Any]]:
    """Report, per stage, whether it ran against its predecessor's current output."""
    report, previous = [], None
    for stage in stages:
        try:
            meta = read_stage_meta(stage)
        except FileNotFoundError:
            report.append({"stage": stage, "status": "missing"})
            previous = None
            continue
        if previous is None or meta.get("consumed") == previous["self"]:
            status = "ok"
        else:
            status = "STALE"
        report.append({**meta, "status": status})
        previous = meta
    return report
