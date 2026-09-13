"""Stage 2 -- decide which candidates actually belong to the brand.

Screening output is only as good as the match behind it, so this stage is part of
the deliverable rather than plumbing. Rejected candidates are kept in the output
with the reason, because "we considered NIPPON PISTON RING and threw it out" is
more credible than silently not mentioning it.

A brand resolves to an entity *family*, not one node: TCL returns ~59 plausible
nodes, Hisense ~80. Screening a single node misses the rest of the group, so risk
is unioned across the family and the provenance of each flag is preserved.
"""

from __future__ import annotations

from typing import Any

from .matching import (
    distinctive_tokens,
    is_composite_party,
    is_logistics,
    name_matches,
)
from .paths import fingerprint, load_products, read_stage, write_stage


def _rejection_reason(product: dict[str, Any], candidate: dict[str, Any]) -> str | None:
    """Why this candidate is not the brand, or None if it survives.

    Judged against the name that found it, not the brand. The correct entity often
    does not contain the brand string at all -- Ring resolves as BOT HOME
    AUTOMATION, Eufy as ANKER INNOVATIONS -- so brand matching rejects the right
    answer for any sub-brand or renamed company.
    """
    # Hand-verified entities bypass the name rules by design. The registry node for
    # EZVIZ is labelled 杭州萤石网络股份有限公司 and matches no Latin name test, yet it
    # is the node carrying the ownership chain to Hikvision and CETC.
    if candidate.get("via") == "anchor":
        return None
    label = candidate.get("label")
    if not label:
        return "no label"
    lowered = label.lower()
    for pattern in product.get("reject_patterns", []):
        if pattern.lower() in lowered:
            return f"matches reject pattern {pattern!r}"
    if is_logistics(label):
        return "freight forwarder or marketplace, not the manufacturer"
    if is_composite_party(label):
        return "composite bill-of-lading party string naming two companies"
    queried = candidate.get("queried_name") or product["brand"]
    if not name_matches(queried, label):
        return f"label does not match the searched name {queried!r}"

    # Name matching so far is one-directional: it asks whether the query's words
    # appear in the label. That accepts any longer company name built around the
    # same word -- searching "Ring LLC" keeps RING CONCIERGE (jewellery), X-RING
    # PROTECTIVE TRAINING and ELLIS RING FAMILY MANAGEMENT, and RING CONCIERGE's
    # 414 shipments were being counted as Ring's.
    #
    # Sayari scores all of those `weak`. So for weak matches we also look the other
    # way: if the label introduces distinctive words the query never had, it is a
    # different company. Anchors and trade-sourced candidates carry no
    # match_strength and are unaffected.
    if candidate.get("match_strength") == "weak":
        wanted = set(distinctive_tokens(queried))
        extra = [
            token for token in distinctive_tokens(label)
            if token not in wanted and not any(token.startswith(w) or w.startswith(token)
                                               for w in wanted)
        ]
        if extra:
            return (f"weak match introducing unrelated terms {extra[:3]} absent from "
                    f"the searched name {queried!r}")
    return None


def _dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated identical labels.

    Sayari's own docs note that "entity resolution is not perfect, and we
    frequently store duplicated entities" -- Ring returns ten distinct entity IDs
    all labelled RING LLC. Keeping one per label stops the family count from
    implying more corporate structure than exists; the dropped ids are recorded.
    """
    seen: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = (candidate.get("label") or "").strip().lower()
        if key in seen:
            seen[key].setdefault("duplicate_ids", []).append(candidate["id"])
            continue
        seen[key] = dict(candidate)
    return list(seen.values())


def adjudicate_one(row: dict[str, Any]) -> dict[str, Any]:
    product = row["product"]
    accepted, rejected = [], []
    for candidate in row["candidates"]:
        reason = _rejection_reason(product, candidate)
        if reason:
            rejected.append({**candidate, "rejected_because": reason})
        else:
            accepted.append(candidate)
    accepted = _dedupe(accepted)
    return {
        "id": product["id"],
        "brand": product["brand"],
        "product": product["product"],
        "category": product["category"],
        "legal_name": product["legal_name"],
        "country": product["country"],
        "parent": product.get("parent"),
        "notes": product.get("notes"),
        "resolved": bool(accepted),
        "family": accepted,
        "rejected": rejected,
    }


def run() -> list[dict[str, Any]]:
    # Re-read products.json rather than trusting the copy stage 1 embedded. Reject
    # rules are tuned by hand against what resolution actually returned, and tuning
    # them must not require re-running resolution.
    current = {p["id"]: p for p in load_products()}
    candidates = read_stage("01_candidates")
    rows = [
        adjudicate_one({**row, "product": current.get(row["product"]["id"], row["product"])})
        for row in candidates
    ]
    for row in rows:
        status = f"{len(row['family'])} kept" if row["resolved"] else "UNRESOLVED"
        print(f"  adjudicate {row['brand']:10} {status:>14}  {len(row['rejected'])} rejected")
    write_stage("02_families", rows, consumed=fingerprint(candidates))
    return rows


if __name__ == "__main__":
    run()
