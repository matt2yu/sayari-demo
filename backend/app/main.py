"""FastAPI app serving the screening snapshot.

The pipeline writes a snapshot; this serves it. That split keeps the demo fast and
working even when the API key is rate-limited, and lets a reviewer read the JSON
directly. POST /api/refresh re-runs the pipeline live, so the SDK path is real and
exercised rather than decorative.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pipeline.paths import SAMPLE_SNAPSHOT, SNAPSHOT

app = FastAPI(
    title="Who's Allowed To Buy This?",
    description="Consumer smart-device screening against US restriction regimes.",
    version="1.0.0",
)

# Vite dev server. A single-origin deployment would drop this entirely.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_refresh_lock = threading.Lock()
_refresh_state: dict[str, Any] = {"running": False, "last_error": None}


def load_snapshot() -> dict[str, Any]:
    """Prefer the live snapshot; fall back to the committed sample.

    The sample is what makes the frontend reviewable without API credentials.
    """
    for path in (SNAPSHOT, SAMPLE_SNAPSHOT):
        if path.exists():
            data = json.loads(path.read_text())
            data["_source"] = path.name
            return data
    raise HTTPException(
        status_code=503,
        detail="No snapshot found. Run: uv run python -m pipeline.run",
    )


@app.get("/api/products")
def list_products() -> dict[str, Any]:
    """Card data for the grid. Deliberately excludes chains and rejected candidates,
    which are large and only needed on the detail view."""
    snapshot = load_snapshot()
    cards = [{
        "id": product["id"],
        "brand": product["brand"],
        "product": product["product"],
        "category": product["category"],
        "country": product["country"],
        "parent": product.get("parent"),
        "resolved": product["resolved"],
        "family_size": product["family_size"],
        "family_flow": product["family_flow"],
        "flag_count": len(product["flags"]),
        "seed_flag_count": sum(1 for f in product["flags"] if f["risk_type"] == "seed"),
        "worst_status": product["worst_status"],
        "verdicts": product["verdicts"],
    } for product in snapshot["products"]]
    return {
        "generated_at": snapshot["generated_at"],
        "source": snapshot["_source"],
        "personas": snapshot["personas"],
        "products": cards,
    }


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    """Everything behind one card, including how we know and what we rejected."""
    snapshot = load_snapshot()
    for product in snapshot["products"]:
        if product["id"] == product_id:
            return {
                **product,
                "glossary": {f["id"]: snapshot["glossary"].get(f["id"])
                             for f in product["flags"]},
                "caveats": snapshot["caveats"],
            }
    raise HTTPException(status_code=404, detail=f"No product {product_id!r}")


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """Provenance: when the snapshot was built, what it cost, and what it cannot see."""
    snapshot = load_snapshot()
    return {
        "generated_at": snapshot["generated_at"],
        "source": snapshot["_source"],
        "product_count": snapshot["product_count"],
        "personas": snapshot["personas"],
        "regimes": snapshot["regimes"],
        "caveats": snapshot["caveats"],
        "api": snapshot["api"],
        "refresh": _refresh_state,
    }


@app.post("/api/refresh")
def refresh(stage: str = "external") -> dict[str, Any]:
    """Re-run the pipeline against the live API.

    Defaults to the cheap tail of the pipeline. A full run makes hundreds of calls
    and deliberately stays under the rate limit, so it takes minutes -- too long to
    hold an HTTP connection open, hence the background thread and the status field
    on /api/meta.
    """
    if _refresh_state["running"]:
        raise HTTPException(status_code=409, detail="A refresh is already running.")

    def _work() -> None:
        with _refresh_lock:
            _refresh_state.update(running=True, last_error=None)
            try:
                from pipeline.run import main as run_pipeline
                run_pipeline(start=stage)
            except Exception as exc:  # noqa: BLE001
                _refresh_state["last_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                _refresh_state["running"] = False

    threading.Thread(target=_work, daemon=True).start()
    return {"started": True, "from_stage": stage}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "snapshot": SNAPSHOT.exists() or SAMPLE_SNAPSHOT.exists()}
