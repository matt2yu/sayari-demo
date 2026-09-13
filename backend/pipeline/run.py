"""Pipeline orchestrator -- runs every stage and writes the snapshot the API serves.

    uv run python -m pipeline.run                 # full run
    uv run python -m pipeline.run --from enrich   # resume from a stage

Each stage persists its own artifact, so a later stage can be re-run without
repeating the API calls of the ones before it. That matters: a full run takes a
while because we deliberately stay under the rate limit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from typing import Any

from . import adjudicate, classify, enrich, external, ontology, resolve
from .client import SayariClient
from .paths import SNAPSHOT, check_chain, read_stage

STAGES = ["resolve", "adjudicate", "enrich", "external", "classify"]

# Shipped in the snapshot and rendered in the UI, not buried in the report. Every
# one of these bounds a claim the app makes.
CAVEATS = [
    ("Sayari trade data is largely pre-shipment bills of lading from a freight "
     "consortium, not confirmed customs clearance. A bill of lading records an "
     "intent to ship."),
    ("Trade coverage spans 77 countries and 25 of them are sea-only, including US "
     "imports, China, Germany, the UK and Spain. Air and land freight from those "
     "origins is structurally invisible."),
    ("Network risk factors are refreshed roughly every two weeks, so a value here "
     "can be that stale."),
    "Forced-labour trade factors only consider activity in the last 730 days.",
    ("A flag reached by traversing the graph describes a relationship, not a "
     "property of the brand."),
]


def _usage(client: SayariClient) -> dict[str, Any]:
    """Measured API consumption, so the writeup can state cost rather than estimate."""
    try:
        today = dt.datetime.now(dt.UTC).date()
        response = client.usage(from_=today - dt.timedelta(days=30), to=today)
        usage = response.usage
        return usage if isinstance(usage, dict) else usage.dict()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def build_snapshot(client: SayariClient, rows: list[dict[str, Any]]) -> dict[str, Any]:
    factors = ontology.load(client)
    glossary = {
        flag["id"]: {k: factors.get(flag["id"], {}).get(k)
                     for k in ("label", "description", "level", "risk_type", "categories")}
        for row in rows for flag in row["flags"]
    }
    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "product_count": len(rows),
        "personas": classify.PERSONAS,
        "regimes": [{k: v for k, v in regime.items() if k != "entities"}
                    for regime in external.REGIMES],
        "glossary": glossary,
        "api": {**client.call_report(), "usage_last_30d": _usage(client)},
        "caveats": CAVEATS,
        "products": rows,
    }


def main(start: str = "resolve", refresh_sdn: bool = False) -> dict[str, Any]:
    if start not in STAGES:
        raise SystemExit(f"--from must be one of {STAGES}")
    todo = STAGES[STAGES.index(start):]
    client = SayariClient()

    if "resolve" in todo:
        print("\n[1/5] resolve")
        resolve.run(client)
    if "adjudicate" in todo:
        print("\n[2/5] adjudicate")
        adjudicate.run()
    if "enrich" in todo:
        print("\n[3/5] enrich")
        enrich.run(client)
    if "external" in todo:
        print("\n[4/5] external enrichment")
        external.run(refresh_sdn=refresh_sdn)
    if "classify" in todo:
        print("\n[5/5] classify")
        classify.run()

    rows = read_stage("05_classified")
    snapshot = build_snapshot(client, rows)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False, default=str))

    resolved = sum(1 for r in rows if r["resolved"])
    restricted = sum(1 for r in rows if r["worst_status"] != "no_restriction")
    print(f"\nwrote {SNAPSHOT}")
    print(f"  {resolved}/{len(rows)} resolved, {restricted} with a restriction for some buyer")
    print(f"  {snapshot['api']['total_calls']} API calls this run")
    return snapshot


ARTIFACT_NAMES = ["01_candidates", "02_families", "03_enriched",
                  "04_external", "05_classified"]


def check() -> bool:
    """Print the stage chain and whether each ran against current input.

    Re-running stages out of order leaves mtimes that look fresh over stale
    content, so each artifact records the fingerprint of what it consumed and this
    verifies the chain rather than trusting timestamps.
    """
    report = check_chain(ARTIFACT_NAMES)
    print(f"{'stage':16} {'rows':>5}  {'status':7}  written")
    print("-" * 64)
    healthy = True
    for entry in report:
        if entry["status"] != "ok":
            healthy = False
        written = (entry.get("written_at") or "")[:19]
        print(f"{entry['stage']:16} {entry.get('rows', '-')!s:>5}  "
              f"{entry['status']:7}  {written}")
    if not healthy:
        print("\nA STALE stage ran against an older version of its input. "
              "Re-run from the first stale stage:  --from <stage>")
    return healthy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", default="resolve", choices=STAGES)
    parser.add_argument("--refresh-sdn", action="store_true",
                        help="re-download the OFAC SDN list instead of using the cache")
    parser.add_argument("--check", action="store_true",
                        help="verify stage freshness without running anything")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(0 if check() else 1)
    main(start=args.start, refresh_sdn=args.refresh_sdn)
