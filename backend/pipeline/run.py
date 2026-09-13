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

from . import adjudicate, classify, enrich, external, ontology, resolve, sanctions
from .client import SayariClient
from .paths import (
    SAMPLE_SNAPSHOT,
    SNAPSHOT,
    check_chain,
    fingerprint,
    read_stage,
    read_stage_meta,
    write_stage,
)

STAGES = ["resolve", "adjudicate", "enrich", "sanctions", "external", "classify"]

ARTIFACT_NAMES = ["01_candidates", "02_families", "03_enriched",
                  "03b_sanctions", "04_external", "05_classified"]

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
    """What Sayari metered on the whole account over 30 days.

    This is NOT the cost of building the snapshot -- it includes every exploratory
    call made while developing, so it runs several times higher. Reported under its
    own name so the two are never confused.
    """
    try:
        today = dt.datetime.now(dt.UTC).date()
        response = client.usage(from_=today - dt.timedelta(days=30), to=today)
        usage = response.usage
        return usage if isinstance(usage, dict) else usage.dict()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _snapshot_cost() -> dict[str, Any]:
    """API calls actually spent building this snapshot, summed across stages.

    Stages are routinely re-run individually, so the calls made by the *last*
    invocation are meaningless as a cost figure -- resuming from `classify` reports
    zero, which reads as "this used no API" for a deliverable about API usage. Each
    stage records its own count when it writes, and this totals them.
    """
    per_stage, total = {}, 0
    for name in ARTIFACT_NAMES:
        try:
            calls = (read_stage_meta(name).get("calls") or {}).get("total")
        except FileNotFoundError:
            continue
        if calls is None:
            continue
        per_stage[name] = calls
        total += calls
    return {"total": total, "by_stage": per_stage,
            "complete": len(per_stage) == len(ARTIFACT_NAMES)}


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
        "api": {
            "snapshot_cost": _snapshot_cost(),
            "this_invocation": client.call_report(),
            "account_usage_last_30d": _usage(client),
        },
        "caveats": CAVEATS,
        "products": rows,
    }


def main(start: str = "resolve", refresh_sdn: bool = False) -> dict[str, Any]:
    if start not in STAGES:
        raise SystemExit(f"--from must be one of {STAGES}")
    todo = STAGES[STAGES.index(start):]
    client = SayariClient()

    if "resolve" in todo:
        print("\n[1/6] resolve")
        resolve.run(client)
    if "adjudicate" in todo:
        print("\n[2/6] adjudicate")
        adjudicate.run()
    if "enrich" in todo:
        print("\n[3/6] enrich")
        enrich.run(client)
    if "sanctions" in todo:
        print("\n[4/6] sanctions dating")
        sanctions.run(client)
    if "external" in todo:
        print("\n[5/6] external enrichment")
        external.run(refresh_sdn=refresh_sdn)
    if "classify" in todo:
        print("\n[6/6] classify")
        classify.run()

    rows = read_stage("05_classified")
    snapshot = build_snapshot(client, rows)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False, default=str))

    resolved = sum(1 for r in rows if r["resolved"])
    restricted = sum(1 for r in rows if r["worst_status"] != "no_restriction")
    print(f"\nwrote {SNAPSHOT}")
    print(f"  {resolved}/{len(rows)} resolved, {restricted} with a restriction for some buyer")
    cost = snapshot["api"]["snapshot_cost"]
    print(f"  {cost['total']} API calls to build this snapshot {cost['by_stage']}")
    return snapshot


def rehydrate() -> int:
    """Rebuild stage artifacts from the snapshot, without touching the API.

    The snapshot carries every row the later stages produced, so the chain can be
    reconstructed from it. Useful because stage artifacts are intermediate and
    gitignored: a fresh clone, or a branch switch that predates the ignore rule,
    leaves the snapshot intact and the stages gone. Rebuilding beats spending
    hundreds of API calls to recover data we already have.
    """
    source = SNAPSHOT if SNAPSHOT.exists() else SAMPLE_SNAPSHOT
    if not source.exists():
        raise SystemExit("No snapshot to rehydrate from. Run the pipeline.")
    rows = json.loads(source.read_text())["products"]

    # 05 is the snapshot's rows verbatim; the earlier stages are projections of it.
    external_rows = [{k: v for k, v in r.items()
                      if k not in ("verdicts", "worst_status")} for r in rows]
    sanctions_rows = [{k: v for k, v in r.items() if k != "regime_hits"}
                      for r in external_rows]
    enriched_rows = [{k: v for k, v in r.items() if k != "sanctioned_trade"}
                     for r in sanctions_rows]
    write_stage("03_enriched", enriched_rows)
    write_stage("03b_sanctions", sanctions_rows, consumed=fingerprint(enriched_rows))
    write_stage("04_external", external_rows, consumed=fingerprint(sanctions_rows))
    write_stage("05_classified", rows, consumed=fingerprint(external_rows))
    print(f"rehydrated 03/04/05 from {source.name} ({len(rows)} products, 0 API calls)")
    return len(rows)


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
    parser.add_argument("--rehydrate", action="store_true",
                        help="rebuild stage artifacts from the snapshot, no API calls")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(0 if check() else 1)
    if args.rehydrate:
        rehydrate()
        raise SystemExit(0)
    main(start=args.start, refresh_sdn=args.refresh_sdn)
