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
        # ...and only where the product's own entity is listed. A brand having once
        # shipped to a sanctioned counterparty is a supply-chain diligence question
        # for a business, not something that restricts a household from buying a TV.
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

# A hit on the entity itself prohibits. A hit reached through ownership is a
# diligence trigger: Section 889's reach to "subsidiaries and affiliates" is a legal
# question about a specific corporate relationship, not something a name match
# settles. Calling it prohibited would overstate what the data supports.
HOW_SEVERITY = {
    "direct": PROHIBITED,
    "seed_risk": PROHIBITED,
    "owner": REVIEW,
    # The brand is not the sanctioned party here -- a counterparty it shipped to is.
    # Every such relationship in this dataset also predates the designation, so
    # treating it as a prohibition on the brand would be plainly wrong.
    "trade_counterparty": REVIEW,
}


def _verdict_for(persona: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    allowed_how = persona.get("applies_to")
    applicable = [
        h for h in row["regime_hits"]
        if h["regime"] in persona["regimes"]
        and (allowed_how is None or h["how"] in allowed_how)
    ]
    if not applicable:
        return {
            "status": NO_RESTRICTION,
            "headline": "No restriction identified",
            "reasons": [],
            "coverage_warning": _coverage_warning(row),
        }

    severities = {HOW_SEVERITY.get(h["how"], REVIEW) for h in applicable}
    status = PROHIBITED if PROHIBITED in severities else REVIEW

    reasons = []
    for hit in applicable:
        if hit["how"] == "owner":
            hops = hit["hops"]
            detail = (
                f"Owned {hops} {'hop' if hops == 1 else 'hops'} upstream by "
                f"{hit['owner']}, which is on this list."
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
            detail = f"Sayari records this entity on the list directly ({hit['factor']})"
        reasons.append({
            "authority": hit["authority"],
            "citation": hit["citation"],
            "binds": hit["binds"],
            "severity": HOW_SEVERITY.get(hit["how"], REVIEW),
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
