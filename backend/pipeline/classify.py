"""Stage 5 -- verdict per buyer persona.

The thesis of the whole deliverable: "legal" is not a property of the product, it
is a property of the buyer. The same router is unremarkable in a house and
prohibited in a defence contractor's office. So there is no single verdict -- there
are four, and switching between them is what makes the point.

Two rules govern everything here:

  A verdict cites a statute or it does not render. No ethical language, no scoring
  of morality. We report legal restriction by buyer class, nothing else.

  Absence of evidence is reported as absence of evidence. Ring has zero flags only
  because Amazon imports on its behalf, so its verdict carries a coverage warning
  rather than a clean bill of health.
"""

from __future__ import annotations

from typing import Any

from .paths import fingerprint, read_stage, write_stage

# Ordered from the least to the most constrained buyer. Each persona inherits the
# regimes above it, which is why the same product changes colour as you move down.
PERSONAS = [
    {
        "key": "consumer",
        "label": "Consumer",
        "blurb": "Buying for a private household.",
        # Only OFAC reaches a private individual. The FCC Covered List bars new
        # equipment *authorisation* -- it binds the importer and the seller, not the
        # household -- so listing it here would tell a consumer they are prohibited
        # from something they are not.
        "regimes": ["ofac_sdn"],
        "applies_to": ["direct", "seed_risk", "owner"],
    },
    {
        "key": "enterprise",
        "label": "Enterprise IT",
        "blurb": "A private company with no federal contracts. Deploying and "
                 "reselling equipment brings FCC authorisation into scope.",
        "regimes": ["ofac_sdn", "fcc_covered"],
    },
    {
        "key": "federal_contractor",
        "label": "Federal Contractor",
        "blurb": "Holds any federal contract. Section 889 reaches the whole business, "
                 "not only the federally funded part.",
        "regimes": ["fcc_covered", "ofac_sdn", "section_889"],
    },
    {
        "key": "dod",
        "label": "DoD Supplier",
        "blurb": "Sells to the Department of Defense.",
        "regimes": ["fcc_covered", "ofac_sdn", "section_889", "section_1260h"],
    },
]

PROHIBITED, REVIEW, NO_RESTRICTION = "prohibited", "review", "no_restriction"

# Severity depends on how the hit was reached AND which regime reached it, because
# the regimes do not extend equally far.
#
#   direct / seed_risk  the entity is itself on the list.
#   owner               reached through ownership. Section 889 names Hikvision and
#                       extends by its own terms to "subsidiaries and affiliates",
#                       so an ownership link there is a bar for the buyer class it
#                       binds. The FCC Covered List restricts authorisation of the
#                       equipment rather than the corporate group, so the identical
#                       link is a diligence trigger there, not a prohibition.
HOW_SEVERITY = {"direct": PROHIBITED, "seed_risk": PROHIBITED, "owner": REVIEW}

# Section 889 covers a named company "or any subsidiary or affiliate". Whether an
# ownership link meets that depends on the size of the stake, which stage 4 reads
# from the graph rather than assuming. Hikvision holds 48-60% of EZVIZ across
# Sayari's source records, which is a subsidiary on any reading.
AFFILIATE_THRESHOLD_PCT = 25


def _severity(hit: dict[str, Any]) -> str:
    if hit["how"] != "owner":
        return HOW_SEVERITY.get(hit["how"], REVIEW)
    if hit["regime"] != "section_889":
        # The FCC Covered List restricts authorisation of the equipment, not the
        # corporate group, so an ownership link is a diligence trigger there.
        return REVIEW
    stake = hit.get("stake_pct")
    return PROHIBITED if stake is not None and stake >= AFFILIATE_THRESHOLD_PCT else REVIEW


def _verdict_for(persona: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    allowed_how = persona.get("applies_to")
    applicable = [
        h for h in row["regime_hits"]
        if h["regime"] in persona["regimes"]
        and (allowed_how is None or h["how"] in allowed_how)
        # Trade with a party that was sanctioned only *after* the shipments is not a
        # restriction on anyone. Every such relationship in this dataset ended before
        # designation, and counting them let the weakest finding here outweigh the
        # strongest: it flagged seven brands and buried the two that actually matter.
        # It stays on the product page as context.
        and not (h["how"] == "trade_counterparty" and not h.get("post_designation"))
    ]
    if not applicable:
        return {
            "status": NO_RESTRICTION,
            "headline": "No restriction identified",
            "reasons": [],
            "coverage_warning": _coverage_warning(row),
        }

    severities = {_severity(h) for h in applicable}
    status = PROHIBITED if PROHIBITED in severities else REVIEW

    reasons = []
    for hit in applicable:
        if hit["how"] == "owner":
            hops = hit["hops"]
            stake = hit.get("stake_pct")
            detail = (
                f"Owned {hops} {'hop' if hops == 1 else 'hops'} upstream by "
                f"{hit['owner']}, which is on this list"
                + (f", holding {stake}% of the shares." if stake else ".")
            )
        elif hit["how"] == "direct":
            detail = f"{hit['entity']} is listed as {hit['matched']}"
        elif hit["how"] == "trade_counterparty":
            after = hit.get("post_designation", 0)
            detail = (
                f"Shipped to {hit['counterparty']}, on the OFAC SDN list"
                + (f" under programme {hit['program']}" if hit.get('program') else '')
                + f" ({hit.get('shipments', 0):,} shipments). "
                + (f"{after} of them on or after designation."
                   if after else "All of them predate the designation date.")
            )
        else:
            # A seed listing is the strongest evidence there is: the entity is on
            # the list itself, not reached through anything. Say which entity and
            # which list, otherwise it reads as weaker than an ownership chain
            # purely because there is no chain to draw.
            # Prefer the registry label over the translation here. A family
            # member is the brand's own entity and is usually Latin-named, and
            # TP-Link's translation is "Pulian Technology Co., Ltd." -- correct,
            # but unrecognisable to a reader looking at a TP-Link card.
            # Translations matter for chain hops, which are often Chinese
            # registry entries; they do not help here.
            listed = next(
                (m.get("label") or m.get("translated_label")
                 for m in row.get("family", [])
                 if m["id"] in (hit.get("entity_ids") or [])),
                None,
            )
            source = next(
                (", ".join(f["sources"]) for f in row.get("flags", [])
                 if f["id"] == hit.get("factor") and f.get("sources")),
                hit["authority"],
            )
            detail = (
                f"{listed} is itself on the {source}."
                if listed else
                f"This entity is itself on the {source}."
            )
        reasons.append({
            "authority": hit["authority"],
            "citation": hit["citation"],
            "binds": hit["binds"],
            "severity": _severity(hit),
            "detail": detail,
        })

    top = next(r for r in reasons if r["severity"] == status)
    headline = ("Prohibited: " if status == PROHIBITED else "Diligence required: ") + top["authority"]
    return {"status": status, "headline": headline, "reasons": reasons,
            "coverage_warning": _coverage_warning(row)}


def _coverage_warning(row: dict[str, Any]) -> str | None:
    """Say when we cannot see, rather than implying we looked and found nothing."""
    if not row["resolved"] or not row["family"]:
        return "This brand did not resolve to any Sayari entity. Nothing was screened."
    if row["family_flow"] == 0:
        return (
            "No shipment records under this brand's own entities. Its goods are "
            "imported under another company's name, so trade-derived findings cannot "
            "appear here. Absence of evidence is not evidence of absence."
        )
    if row["family_flow"] < 1000:
        return (
            "Very few shipment records under this brand's own entities, so trade-derived "
            "coverage is thin."
        )
    return None


def classify_one(row: dict[str, Any]) -> dict[str, Any]:
    verdicts = {p["key"]: _verdict_for(p, row) for p in PERSONAS}
    return {**row, "verdicts": verdicts,
            "worst_status": (
                PROHIBITED if any(v["status"] == PROHIBITED for v in verdicts.values())
                else REVIEW if any(v["status"] == REVIEW for v in verdicts.values())
                else NO_RESTRICTION
            )}


def run() -> list[dict[str, Any]]:
    external_rows = read_stage("04_external")
    rows = [classify_one(row) for row in external_rows]
    for row in rows:
        summary = " ".join(
            f"{p['key'][:4]}={row['verdicts'][p['key']]['status'][:4]}" for p in PERSONAS
        )
        print(f"  classify {row['brand']:10} {summary}")
    write_stage("05_classified", rows, consumed=fingerprint(external_rows))
    return rows


if __name__ == "__main__":
    run()
