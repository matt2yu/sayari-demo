"""Stage 1 -- brand -> candidate entities.

A brand is not one node in Sayari. It is typically a registry entity (ownership,
officers, no shipments) plus one or more trade entities (shipments, no ownership),
and the two are not linked to each other. Querying only one side gives the wrong
answer: resolving "TP-Link Technologies Co Ltd" returns a small Vietnamese
subsidiary first, losing both the usa_section_1260h flag and ~553k shipment
records that sit on the trade-side node.

So we gather from both sides and let stage 2 adjudicate. Over-collecting here is
cheap; missing a node is not recoverable downstream.
"""

from __future__ import annotations

from typing import Any

from .client import SayariClient
from .matching import brand_matches, is_logistics
from .paths import load_products, write_stage

RESOLUTION_LIMIT = 10   # API maximum
TRADE_LIMIT = 10


def _resolution_candidates(client: SayariClient, product: dict[str, Any]) -> list[dict[str, Any]]:
    """Try the legal name, then each alias, until something resolves.

    Aliases exist because the obvious legal name often fails outright: "Ring LLC"
    returns nothing but piston-ring manufacturers.
    """
    found: dict[str, dict[str, Any]] = {}
    names = [product["legal_name"], *product.get("resolution_aliases", [])]
    for name in names:
        base: dict[str, Any] = {"name": name, "limit": RESOLUTION_LIMIT}
        if product.get("country"):
            base["country"] = product["country"]

        # Query with and without the address, and union.
        #
        # The address hint raises match strength -- Sayari scores every match "weak"
        # without an address or identifier -- but it also *changes* the result set,
        # not merely reorders it. Supplying EZVIZ's Hangzhou address returned its
        # trade and sales entities and dropped the Chinese registry node that
        # carries the ownership chain to Hikvision and CETC, which is the single
        # most important finding in this dataset. Neither query alone is sufficient.
        variants = [base]
        if product.get("hq_address"):
            variants.append({**base, "address": product["hq_address"]})

        for kwargs in variants:
            response = client.resolve(**kwargs)
            for hit in response.data or []:
                found.setdefault(hit.entity_id, {
                    "id": hit.entity_id,
                    "via": "resolution",
                    "queried_name": name,
                    "with_address": "address" in kwargs,
                    "label": hit.label,
                    "score": hit.score,
                    "match_strength": hit.match_strength.value if hit.match_strength else None,
                    "type": hit.type,
                })
    return list(found.values())


def _trade_candidates(client: SayariClient, product: dict[str, Any]) -> list[dict[str, Any]]:
    """Suppliers whose name carries the brand token.

    The free-text `q` here searches shipment content as well as party names, so
    it returns a lot of noise -- searching "Ring" surfaces piston and bearing
    makers. Filtering on the brand token plus the logistics denylist removes the
    bulk of it; stage 2 removes the rest.
    """
    found: dict[str, dict[str, Any]] = {}
    response = client.search_suppliers(q=product["brand"], limit=TRADE_LIMIT)
    for hit in response.data or []:
        label = getattr(hit, "label", None)
        if is_logistics(label) or not brand_matches(product["brand"], label):
            continue
        found.setdefault(hit.id, {
            "id": hit.id,
            "via": "trade",
            "queried_name": product["brand"],
            "label": label,
            "score": None,
            "match_strength": None,
            "type": getattr(hit, "type", None),
        })
    return list(found.values())


def _anchors(product: dict[str, Any]) -> list[dict[str, Any]]:
    """Hand-verified entities that must always be in the family.

    Pins identity, not data. Downstream stages still fetch every anchored entity's
    risk, ownership and shipments live on each run, so a refresh picks up new
    sanctions and new shipments -- it simply cannot lose the node they sit on.
    """
    return [{
        "id": anchor["id"],
        "via": "anchor",
        "queried_name": anchor["label"],
        "label": anchor["label"],
        "score": None,
        "match_strength": "verified",
        "type": "company",
        "anchor_reason": anchor["why"],
    } for anchor in product.get("anchor_entity_ids", [])]


def run(client: SayariClient) -> list[dict[str, Any]]:
    before = sum(client.calls.values())
    rows = []
    for product in load_products():
        candidates: dict[str, dict[str, Any]] = {}
        # Anchors first so a same-id hit from resolution cannot overwrite the
        # reason we pinned it.
        for candidate in _anchors(product):
            candidates[candidate["id"]] = candidate
        for candidate in _resolution_candidates(client, product):
            candidates.setdefault(candidate["id"], candidate)
        for candidate in _trade_candidates(client, product):
            candidates.setdefault(candidate["id"], candidate)
        rows.append({"product": product, "candidates": list(candidates.values())})
        print(f"  resolve  {product['brand']:10} {len(candidates):>3} candidates")
    # stage 1 consumes products.json, not an artifact, so it has no `consumed`
    write_stage("01_candidates", rows,
                calls={"total": sum(client.calls.values()) - before})
    return rows


if __name__ == "__main__":
    run(SayariClient())
