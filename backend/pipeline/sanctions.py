"""Stage 3b -- dated shipment evidence for sanctioned trade counterparties.

Several brands reach a sanctioned party through trade edges rather than ownership.
That is a weaker and more easily overstated claim than ownership, for two reasons:

  1. `ships_to` is a *derived, aggregated* edge over many bills of lading. It says
     goods moved, not that a commercial relationship of any particular kind exists.
  2. A shipment predating the counterparty's designation is not a violation. It is
     ordinary trade that later became restricted.

So this stage pulls the actual shipments behind each brand -> sanctioned-party
edge, dates them, and splits them against the designation date. Where no
designation date is published in the source, we say so rather than guessing --
an undated split presented as pre/post would be a fabricated finding.

Designation dates come from the counterparty's own `risk_intelligence` attribute,
which is where Sayari records the authority, list, programme and dates for a seed
risk factor. Note the coverage is uneven: the Ukraine registry publishes
`from_date`, the OFAC SDN record for the same entity publishes only a programme.
"""

from __future__ import annotations

from typing import Any

from .client import SayariClient
from .enrich import _as_dict, _NameCache, classify_path
from .paths import fingerprint, read_stage, write_stage

# Every shipment is counted, not sampled. "All sampled shipments predate the
# designation" is only worth saying if the sample is the population -- a 25-row
# sample of 1,554 unsorted shipments could easily miss the ones that matter, and
# the whole point of this stage is to not overstate. The endpoint accepts up to
# 3000 and the largest pair here is ~1,550, so one call covers it.
SHIPMENT_FETCH_LIMIT = 3000
EXAMPLES_KEPT = 5             # retained per side, purely for display
MAX_COUNTERPARTIES = 3        # per brand; illustrative, not exhaustive


def _sanctioned_nodes(row: dict[str, Any], names: _NameCache) -> dict[str, dict[str, Any]]:
    """Sanctioned entities this brand reaches through a *trade* edge.

    Enrich deliberately leaves trade-chain hops unresolved -- resolving every node
    of every chain was thousands of calls for labels the UI never showed. So this
    stage resolves the trade endpoints itself, through the same on-disk name cache,
    and only for nodes that a trade chain actually terminates on.
    """
    found: dict[str, dict[str, Any]] = {}
    # Deprecated flags are included here *as routes only*. sanctioned_adjacent is
    # deprecated and never supports a finding, but the traversal path it carries is
    # still factual -- what Sayari retired is the scoring, not the edge. So we walk
    # the path and then assert against the target entity's own seed sanction risk,
    # which is the rule in AGENTS.md. Without this the counterparties are
    # unreachable, because sanctioned_adjacent is the only factor that points at
    # them.
    for flag in [*row.get("flags", []), *row.get("dropped_flags", [])]:
        for chain in flag.get("chains", []) or [
            {"raw": p} for p in flag.get("paths", [])
        ]:
            raw = chain.get("raw", "")
            if not raw or classify_path(raw) == "ownership":
                continue  # ownership is handled as its own, stronger finding
            parts = raw.split("|")
            node_ids, edges = parts[0::2], parts[1::2]
            if len(node_ids) < 2:
                continue
            # Terminal node only. A network risk path ends at the entity carrying
            # the seed risk -- that is where the sanctioned party sits. Checking
            # every intermediate hop would multiply lookups by the chain length for
            # nodes that are, by construction, not the risk target.
            node_id, index = node_ids[-1], len(node_ids) - 1
            if "/" in node_id or node_id in found:
                continue
            info = names.get(node_id)
            if not info.get("sanctioned"):
                continue
            found[node_id] = {
                "id": node_id,
                "label": info.get("label"),
                "countries": info.get("countries", []),
                "edge": edges[-1] if edges else None,
                "hops": index,
                "via_factor": flag["id"],
                "seed_risks": [r for r in info.get("seed_risks", []) if "sanction" in r],
            }
    return found


def designation_dates(client: SayariClient, entity_id: str) -> list[dict[str, Any]]:
    """Sanction listings for an entity, with dates where the source publishes them."""
    try:
        entity = client.get_entity(entity_id)
    except Exception:  # noqa: BLE001
        return []
    attributes = _as_dict(entity.attributes)
    rows = (_as_dict(attributes.get("risk_intelligence")) or {}).get("data") or []
    listings = []
    for row in rows:
        properties = _as_dict(_as_dict(row).get("properties"))
        if "sanction" not in (properties.get("type") or "") and not properties.get("list"):
            continue
        listings.append({
            "type": properties.get("type"),
            "list": properties.get("list"),
            "program": properties.get("program"),
            "from_date": properties.get("from_date"),
            "to_date": properties.get("to_date"),
        })
    # Dated listings first so the earliest usable date is easy to find.
    listings.sort(key=lambda x: (x["from_date"] is None, x["from_date"] or ""))
    return listings


def _earliest_designation(listings: list[dict[str, Any]]) -> str | None:
    dates = [x["from_date"] for x in listings if x.get("from_date")]
    return min(dates) if dates else None


def shipments_between(
    client: SayariClient, supplier_ids: list[str], buyer_id: str,
) -> list[dict[str, Any]]:
    """Dated shipments from this brand's entities to one counterparty."""
    try:
        response = client.search_shipments(
            limit=SHIPMENT_FETCH_LIMIT,
            filter={"buyer_id": [buyer_id], "supplier_id": supplier_ids},
        )
    except Exception:  # noqa: BLE001
        return []
    out = []
    for shipment in response.data or []:
        arrival = shipment.arrival_date or []
        departure = shipment.departure_date or []
        out.append({
            "arrival_date": arrival[0] if arrival else None,
            "departure_date": departure[0] if departure else None,
            "supplier": [n for x in (shipment.supplier or []) for n in (x.names or [])][:1],
            "descriptions": (shipment.product_descriptions or [])[:2],
            "hs_codes": (shipment.hs_codes or [])[:3],
        })
    total = response.size.count if response.size else len(out)
    for row in out:
        row["_total"] = total
    return out


def assess(client: SayariClient, row: dict[str, Any], names: _NameCache) -> dict[str, Any]:
    findings = []
    family_ids = [m["id"] for m in row.get("family", [])]
    for node in list(_sanctioned_nodes(row, names).values())[:MAX_COUNTERPARTIES]:
        listings = designation_dates(client, node["id"])
        designated_on = _earliest_designation(listings)
        shipments = shipments_between(client, family_ids, node["id"]) if family_ids else []

        before, after, undated = [], [], []
        for shipment in shipments:
            date = shipment.get("arrival_date") or shipment.get("departure_date")
            if not date or not designated_on:
                undated.append(shipment)
            elif date >= designated_on:
                after.append(shipment)
            else:
                before.append(shipment)

        reported = shipments[0]["_total"] if shipments else 0
        complete = len(shipments) >= reported  # did one call cover the population?
        latest = max((s.get("arrival_date") or s.get("departure_date") or ""
                      for s in shipments), default=None) or None

        findings.append({
            **node,
            "listings": listings,
            "designated_on": designated_on,
            "shipment_total": reported,
            "examined": len(shipments),
            "complete": complete,
            "latest_shipment": latest,
            "count_after": len(after),
            "count_before": len(before),
            "count_undatable": len(undated),
            "after_designation": after[:EXAMPLES_KEPT],
            "before_designation": before[:EXAMPLES_KEPT],
            # The honest headline. Anything stronger would assert more than we know.
            "assessment": (
                "No shipments found between this brand's entities and this party."
                if not shipments else
                "This party's designation date is not published in the available "
                "source, so these shipments cannot be placed before or after it."
                if not designated_on else
                f"{len(after)} of {len(shipments)} shipments arrived on or after the "
                f"designation date of {designated_on}."
                if after else
                f"All {len(shipments)} shipments predate the designation date of "
                f"{designated_on} (latest {latest}), so this was ordinary trade at "
                f"the time and is not evidence of a violation."
            ),
        })
    return {**row, "sanctioned_trade": findings}


def run(client: SayariClient) -> list[dict[str, Any]]:
    before = sum(client.calls.values())
    enriched = read_stage("03_enriched")
    names = _NameCache(client)
    rows = []
    for row in enriched:
        assessed = assess(client, row, names)
        rows.append(assessed)
        n = len(assessed["sanctioned_trade"])
        if n:
            total = sum(f["shipment_total"] for f in assessed["sanctioned_trade"])
            print(f"  sanctions {row['brand']:10} {n} counterpart(ies), "
                  f"{total:,} shipments")
    names.save()
    write_stage("03b_sanctions", rows, consumed=fingerprint(enriched),
                calls={"total": sum(client.calls.values()) - before})
    return rows


if __name__ == "__main__":
    run(SayariClient())
