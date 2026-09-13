"""Stage 4 -- the Scenario 1 enrichment.

Sayari tells us what an entity is connected to. These lists tell us *who is legally
barred from buying it*, which is the question the app answers. Each regime records
the population it binds, because "restricted" is meaningless without that:

    Section 1260H  binds the Department of Defense only. TP-Link is on it and is
                   also the best-selling router brand in America. Both are true.
    Section 889    binds federal agencies AND their contractors, across the
                   contractor's entire business -- a far larger population.
    FCC Covered    binds equipment authorisation, so it reaches imports.
    OFAC SDN       binds all US persons.

OFAC SDN is fetched live. The other three are short, statutory and stable, and both
fcc.gov and dhs.gov return 403 to automated clients, so they are encoded with
citations rather than scraped.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import httpx

from .matching import normalise, token_match
from .paths import CACHE, read_stage, write_stage

OFAC_SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"

SECTION_889 = {
    "key": "section_889",
    "authority": "Section 889, FY2019 NDAA",
    "citation": "Pub. L. 115-232; 48 CFR 52.204-25",
    "binds": "federal agencies and federal contractors",
    "scope": "Telecommunications and video surveillance equipment. Applies to the "
             "contractor's entire business, not only its federal work. Extends to "
             "subsidiaries and affiliates.",
    "entities": ["Huawei Technologies", "ZTE Corporation", "Hytera Communications",
                 "Hangzhou Hikvision Digital Technology", "Dahua Technology"],
}

FCC_COVERED = {
    "key": "fcc_covered",
    "authority": "FCC Covered List",
    "citation": "47 CFR 1.50002",
    "binds": "equipment authorisation -- import and marketing of new devices",
    "scope": "Huawei and ZTE are covered for all telecom equipment. Hytera, Hikvision "
             "and Dahua are covered for public safety, government facility, critical "
             "infrastructure and national security uses.",
    "entities": ["Huawei Technologies", "ZTE Corporation", "Hytera Communications",
                 "Hangzhou Hikvision Digital Technology", "Dahua Technology",
                 "China Mobile", "China Telecom", "China Unicom", "Pacific Networks",
                 "AO Kaspersky Lab"],
}

SECTION_1260H = {
    "key": "section_1260h",
    "authority": "Section 1260H, FY2021 NDAA -- Chinese Military Companies",
    "citation": "10 U.S.C. 113 note; procurement bar under Sec. 805, FY2024 NDAA",
    "binds": "Department of Defense procurement only",
    "scope": "NOT an import ban and NOT a consumer restriction. Membership is taken "
             "from Sayari's own seed risk factor rather than a scraped list.",
    "entities": [],
    "sayari_seed_factor": "usa_section_1260h",
}

OFAC = {
    "key": "ofac_sdn",
    "authority": "OFAC Specially Designated Nationals",
    "citation": "31 CFR 501",
    "binds": "all US persons -- blocking sanctions",
    "scope": "Property blocked; US persons prohibited from dealing.",
    "entities": [],
    "sayari_seed_factor": "sanctioned_usa_ofac_sdn",
}

REGIMES = [SECTION_889, FCC_COVERED, SECTION_1260H, OFAC]

# Distinctive stems for the short statutory lists. Matched on token boundaries: a
# substring test puts "ZTE" inside "REOLINK EZTECH" and invents an FCC hit.
LIST_STEMS = {
    "huawei": "Huawei Technologies",
    "zte": "ZTE Corporation",
    "hytera": "Hytera Communications",
    "hikvision": "Hangzhou Hikvision Digital Technology",
    "dahua": "Dahua Technology",
    "kaspersky": "AO Kaspersky Lab",
}


def ofac_sdn_names(refresh: bool = False) -> set[str]:
    """Live OFAC SDN download, cached after first fetch."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "ofac_sdn.csv"
    if refresh or not path.exists():
        # httpx rather than urllib: urllib uses the system trust store, which fails
        # cert verification under uv-managed CPython on this machine.
        response = httpx.get(OFAC_SDN_URL, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=120.0, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
    names = set()
    for row in csv.reader(io.StringIO(path.read_text(errors="replace"))):
        if len(row) > 1 and len(row[1].strip()) > 6:
            names.add(normalise(row[1].strip().strip('"')))
    return names


def _listed_as(label: str | None) -> list[str]:
    """Which statutory list entries this label matches."""
    return [listed for stem, listed in LIST_STEMS.items() if token_match(stem, label)]


def assess(row: dict[str, Any], sdn: set[str]) -> dict[str, Any]:
    """Find every regime hit for one product, with the evidence that supports it."""
    hits: list[dict[str, Any]] = []

    def add(regime: dict[str, Any], how: str, **evidence: Any) -> None:
        hits.append({"regime": regime["key"], "authority": regime["authority"],
                     "binds": regime["binds"], "citation": regime["citation"],
                     "how": how, **evidence})

    # 1. Section 1260H and OFAC SDN come from Sayari's own seed risk, which is
    #    stronger evidence than name-matching a scraped list.
    for regime in (SECTION_1260H, OFAC):
        factor = regime["sayari_seed_factor"]
        for flag in row["flags"]:
            if flag["id"] == factor and flag["risk_type"] == "seed":
                add(regime, "seed_risk", entity_ids=flag["carried_by"],
                    factor=factor, level=flag["level"])

    # 2. Direct: a family member is itself a listed company.
    for member in row["family"]:
        for listed in _listed_as(member.get("label")) or []:
            for regime in (SECTION_889, FCC_COVERED):
                add(regime, "direct", entity=member["label"], matched=listed)

    # 3. Owner: a listed company appears in an ownership chain. This is the EZVIZ
    #    case -- EZVIZ is on no list, its shareholder Hikvision is on three.
    for flag in row["flags"]:
        for chain in flag.get("chains", []):
            if chain["kind"] != "ownership":
                continue
            for hop in chain["hops"]:
                for listed in _listed_as(hop.get("label")) or []:
                    for regime in (SECTION_889, FCC_COVERED):
                        add(regime, "owner", owner=hop["label"], matched=listed,
                            hops=hop["hop"], edge=hop["edge"], via_factor=flag["id"])
                if normalise(hop.get("label")) in sdn:
                    add(OFAC, "owner", owner=hop["label"], matched="OFAC SDN",
                        hops=hop["hop"], edge=hop["edge"], via_factor=flag["id"])

    # Dedupe: the same owner surfaces through several risk factors.
    seen, unique = set(), []
    for hit in hits:
        key = (hit["regime"], hit["how"], hit.get("entity") or hit.get("owner"),
               hit.get("matched"), hit.get("hops"))
        if key not in seen:
            seen.add(key)
            unique.append(hit)
    return {**row, "regime_hits": unique}


def run(refresh_sdn: bool = False) -> list[dict[str, Any]]:
    sdn = ofac_sdn_names(refresh=refresh_sdn)
    rows = [assess(row, sdn) for row in read_stage("03_enriched")]
    for row in rows:
        regimes = sorted({h["regime"] for h in row["regime_hits"]})
        print(f"  external {row['brand']:10} {len(row['regime_hits']):>2} hit(s)  {regimes}")
    write_stage("04_external", rows)
    return rows


if __name__ == "__main__":
    run()
