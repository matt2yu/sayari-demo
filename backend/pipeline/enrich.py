"""Stage 3 -- pull profiles and turn raw risk flags into evidence.

Three things happen here that the raw API response does not give you:

1. Risk is unioned across the entity *family*, recording which member carried each
   flag. Screening one node of a 59-node family (TCL) misses most of the group.

2. Every flag is classified against the ontology into seed / network / psa /
   context, and deprecated factors are dropped. A network flag is derived by
   traversing the graph and must never be presented as a property of the brand.

3. Network flags carry a `traversal_path` of entity ids. Those ids are resolved to
   names so the chain is legible, and the resulting endpoint is checked for its own
   seed risk -- which is where the real citation lives, since `risk_intelligence`
   exists only on seed factors.
"""

from __future__ import annotations

import json
from typing import Any

from . import ontology
from .client import SayariClient
from .paths import CACHE, fingerprint, read_stage, write_stage

# Ownership edges, used to decide whether a resolved chain is an ownership story
# or a trade story. Sayari's own owned_by_* factors use this set.
OWNERSHIP_EDGES = frozenset({
    "has_shareholder", "shareholder_of", "has_beneficial_owner", "beneficial_owner_of",
    "subsidiary_of", "has_subsidiary", "branch_of", "has_branch",
    "has_owner", "owner_of", "has_partner", "partner_of",
})
TRADE_EDGES = frozenset({"ships_to", "receives_from", "shipper_of", "notify_party_of", "carrier_of"})

# How many chains per product get their node names resolved. Only ownership
# chains are rendered as evidence, and no product shows more than a handful.
MAX_RESOLVED_CHAINS_PER_PRODUCT = 6


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "dict"):
        if hasattr(obj, attr):
            return getattr(obj, attr)()
    return {}


class _NameCache:
    """Entity id -> display name, persisted across runs.

    Chains repeat nodes heavily within a run, and entity labels barely change
    between runs, so this is the difference between a re-run costing hundreds of
    calls and costing almost none. Risk data is never cached here -- only labels,
    countries and the sanctioned flag, which is what the chain renderer needs.
    """

    def __init__(self, client: SayariClient) -> None:
        self._client = client
        self._path = CACHE / "entity_names.json"
        self._dirty = False
        try:
            self._cache: dict[str, dict[str, Any]] = json.loads(self._path.read_text())
        except (OSError, ValueError):
            self._cache = {}

    def save(self) -> None:
        if not self._dirty:
            return
        CACHE.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._cache, ensure_ascii=False))
        self._dirty = False

    def get(self, entity_id: str) -> dict[str, Any]:
        if entity_id not in self._cache:
            # shipper_of / notify_party_of / carrier_of point at a *shipment*, not a
            # company. Shipment ids are slash-delimited record ids and are not
            # retrievable via entity_summary. Rendering one as a hop in an ownership
            # chain would read as "owned by 10013160/170524/3167957".
            if "/" in entity_id:
                self._dirty = True
                self._cache[entity_id] = {
                    "id": entity_id, "label": "(shipment record)", "is_shipment": True,
                    "countries": [], "sanctioned": False, "seed_risks": [],
                }
                return self._cache[entity_id]
            try:
                summary = self._client.entity_summary(entity_id)
            except Exception:  # noqa: BLE001
                self._dirty = True
                self._cache[entity_id] = {"id": entity_id, "label": entity_id, "unresolved": True}
                return self._cache[entity_id]
            risk = _as_dict(summary.risk)
            self._dirty = True
            self._cache[entity_id] = {
                "id": entity_id,
                # Chinese-registry labels are in Hanzi; the translation is what makes
                # the chain readable and what Latin name matching can work against.
                "label": summary.translated_label or summary.label,
                "original_label": summary.label,
                "countries": list(summary.countries or []),
                "sanctioned": bool(summary.sanctioned),
                "seed_risks": sorted(risk.keys()),
            }
        return self._cache[entity_id]


def _parse_path(path: str) -> tuple[list[str], list[str]]:
    """Split "id|edge|id|edge|id" into (node ids, edge labels)."""
    parts = path.split("|")
    return parts[0::2], parts[1::2]


def classify_path(path: str) -> str:
    """ownership | trade | mixed, from the path string alone.

    The edge names are already in the traversal_path, so this costs nothing. That
    matters: resolving every node of every chain is thousands of entity_summary
    calls, and the UI only renders ownership chains. Knowing the kind up front
    lets us fetch names for the handful of chains we actually show.
    """
    _, edges = _parse_path(path)
    kinds = set(edges)
    if kinds & OWNERSHIP_EDGES and not kinds & TRADE_EDGES:
        return "ownership"
    if kinds & TRADE_EDGES and not kinds & OWNERSHIP_EDGES:
        return "trade"
    return "mixed"


def _describe_chain(path: str, names: _NameCache, resolve_names: bool) -> dict[str, Any]:
    """Render one path. When resolve_names is False the hops carry edges and ids
    but no labels -- enough to show the shape without paying for the lookups."""
    node_ids, edges = _parse_path(path)
    hops = []
    for index, node_id in enumerate(node_ids[1:], start=1):
        info = names.get(node_id) if resolve_names else {}
        hops.append({
            "hop": index,
            "edge": edges[index - 1] if index - 1 < len(edges) else None,
            "id": node_id,
            "label": info.get("label"),
            "countries": info.get("countries", []),
            "sanctioned": info.get("sanctioned", False),
            "seed_risks": info.get("seed_risks", []),
            "resolved": resolve_names,
        })
    return {"kind": classify_path(path), "hops": hops, "raw": path}


def enrich_one(
    row: dict[str, Any],
    client: SayariClient,
    factors: dict[str, dict[str, Any]],
    names: _NameCache,
) -> dict[str, Any]:
    members: list[dict[str, Any]] = []
    # flag id -> the record we will report, plus which family members carried it
    flags: dict[str, dict[str, Any]] = {}

    unavailable: list[dict[str, Any]] = []
    for candidate in row["family"]:
        try:
            summary = client.entity_summary(candidate["id"])
        except Exception as exc:  # noqa: BLE001
            # One unreachable entity must not discard the other 24 brands' work.
            # Recorded rather than swallowed: a family we only partly retrieved is
            # a coverage gap, and the UI has to be able to say so.
            unavailable.append({"id": candidate["id"], "label": candidate.get("label"),
                                "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            print(f"           ! {candidate.get('label', candidate['id'])[:40]} unavailable")
            continue
        risk = _as_dict(summary.risk)
        trade = _as_dict(summary.trade_count)
        members.append({
            "id": candidate["id"],
            "via": candidate["via"],
            "label": summary.label,
            "translated_label": summary.translated_label,
            "countries": list(summary.countries or []),
            "degree": summary.degree or 0,
            "sent": trade.get("sent", 0) or 0,
            "received": trade.get("received", 0) or 0,
            "sanctioned": bool(summary.sanctioned),
            "duplicate_ids": candidate.get("duplicate_ids", []),
            "n_risk": len(risk),
        })
        for flag_id, payload in risk.items():
            payload = _as_dict(payload)
            record = flags.setdefault(flag_id, {
                "id": flag_id,
                "level": payload.get("level"),
                "value": payload.get("value"),
                "carried_by": [],
                "paths": [],
                "sources": [],
            })
            record["carried_by"].append(candidate["id"])
            meta = _as_dict(payload.get("metadata"))
            for path in meta.get("traversal_path") or []:
                if path not in record["paths"]:
                    record["paths"].append(path)
            for source in meta.get("source") or []:
                if source not in record["sources"]:
                    record["sources"].append(source)

    reportable, context, dropped = [], [], []
    for flag_id, record in flags.items():
        described = ontology.classify(flag_id, factors)
        entry = {**record, **{k: described[k] for k in
                              ("label", "description", "risk_type", "categories",
                               "deprecated", "deprecation_source", "is_context", "known")}}
        if described["deprecated"]:
            dropped.append({**entry,
                            "dropped_because": described["deprecation_source"]
                            or "deprecated in the Sayari ontology"})
            continue
        if described["is_context"]:
            context.append(entry)
            continue
        entry["chains"] = [
            {"kind": classify_path(p), "raw": p} for p in record["paths"][:3]
        ]
        reportable.append(entry)

    reportable.sort(key=lambda f: (f["risk_type"] != "seed", f["id"]))

    # Names are fetched only for the chains the UI renders. Ownership chains are
    # the finding (EZVIZ -> Hikvision -> CETC); trade chains are shown as shape
    # only. Resolving everything cost thousands of calls per run and rate-limited
    # us, for labels nobody ever saw.
    budget = MAX_RESOLVED_CHAINS_PER_PRODUCT
    for flag in reportable:
        for index, chain in enumerate(flag["chains"]):
            wanted = chain["kind"] == "ownership" and budget > 0
            flag["chains"][index] = _describe_chain(chain["raw"], names, wanted)
            if wanted:
                budget -= 1

    return {
        **{k: row[k] for k in ("id", "brand", "product", "category", "legal_name",
                               "country", "parent", "notes", "resolved")},
        "family": members,
        "family_size": len(members),
        "unavailable": unavailable,
        "family_flow": sum(m["sent"] + m["received"] for m in members),
        "rejected": row["rejected"],
        "flags": reportable,
        "context_flags": context,
        "dropped_flags": dropped,
    }


def run(client: SayariClient) -> list[dict[str, Any]]:
    factors = ontology.load(client)
    names = _NameCache(client)
    families = read_stage("02_families")
    rows = []
    for row in families:
        enriched = enrich_one(row, client, factors, names)
        rows.append(enriched)
        seeds = sum(1 for f in enriched["flags"] if f["risk_type"] == "seed")
        print(f"  enrich   {enriched['brand']:10} fam={enriched['family_size']:>2} "
              f"flow={enriched['family_flow']:>9,} flags={len(enriched['flags']):>2} "
              f"(seed {seeds}) dropped={len(enriched['dropped_flags'])}")
    names.save()
    write_stage("03_enriched", rows, consumed=fingerprint(families))
    return rows


if __name__ == "__main__":
    run(SayariClient())
