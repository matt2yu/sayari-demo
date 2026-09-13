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
from .paths import CACHE, fingerprint, read_stage, write_stage

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


def ofac_sdn_records(refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Live OFAC SDN download, keyed by normalised name. Cached after first fetch."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "ofac_sdn.csv"
    if refresh or not path.exists():
        # httpx rather than urllib: urllib uses the system trust store, which fails
        # cert verification under uv-managed CPython on this machine.
        response = httpx.get(OFAC_SDN_URL, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=120.0, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
    # SDN.CSV columns: ent_num, name, type, program, title, call_sign, vessel
    # fields..., remarks. We keep the fields that change what a reader concludes:
    # the sanctions programme (a Russia EO is a different fact from a narcotics
    # designation), the party type, and the remarks, which carry aliases and the
    # designation context. Downloading 5.7MB to use only the name column would be
    # fetching data for no reason.
    records: dict[str, dict[str, Any]] = {}
    for row in csv.reader(io.StringIO(path.read_text(errors="replace"))):
        if len(row) < 4:
            continue
        name = row[1].strip().strip('"')
        if len(name) <= 6:
            continue
        clean = lambda value: None if value.strip(' "') in ("-0-", "") else value.strip(' "')
        records.setdefault(normalise(name), {
            "sdn_name": name,
            "ent_num": clean(row[0]),
            "type": clean(row[2]),
            "program": clean(row[3]),
            "remarks": clean(row[11]) if len(row) > 11 else None,
        })
    return records


# Section 889 covers a named company "or any subsidiary or affiliate". Whether an
# ownership link clears that bar is a question about the size of the stake, so we
# read it rather than assume it. Below the threshold the link is a diligence
# trigger; at or above it, the statutory language is met on its face.
AFFILIATE_THRESHOLD_PCT = 25


def shareholding_pct(client: Any, owned_id: str, owner_label: str) -> int | None:
    """Largest reported stake the named owner holds in this entity, if published."""
    try:
        entity = client.get_entity(owned_id, relationships_limit=50)
    except Exception:  # noqa: BLE001
        return None
    rels = entity.relationships
    rels = rels.dict() if hasattr(rels, "dict") else rels
    wanted = normalise(owner_label)
    best: list[int] = []
    for rel in (rels or {}).get("data", []):
        target = rel.get("target") or {}
        label = target.get("translated_label") or target.get("label") or ""
        if normalise(label) != wanted:
            continue
        for infos in (rel.get("types") or {}).values():
            for info in infos:
                for share in (info.get("attributes") or {}).get("shares") or []:
                    pct = share.get("percentage")
                    if isinstance(pct, (int, float)):
                        best.append(int(pct))
    return max(best) if best else None


def _listed_as(label: str | None) -> list[str]:
    """Which statutory list entries this label matches."""
    return [listed for stem, listed in LIST_STEMS.items() if token_match(stem, label)]


def assess(
    row: dict[str, Any],
    sdn: dict[str, dict[str, Any]],
    client: Any = None,
) -> dict[str, Any]:
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
                    pct = (
                        shareholding_pct(client, row["family"][0]["id"], hop["label"])
                        if client and row.get("family") else None
                    )
                    for regime in (SECTION_889, FCC_COVERED):
                        add(regime, "owner", owner=hop["label"], matched=listed,
                            hops=hop["hop"], edge=hop["edge"], via_factor=flag["id"],
                            stake_pct=pct)
                if normalise(hop.get("label")) in sdn:
                    add(OFAC, "owner", owner=hop["label"], matched="OFAC SDN",
                        hops=hop["hop"], edge=hop["edge"], via_factor=flag["id"])

    # 4. Cross-check sanctioned trade counterparties against the live OFAC SDN
    #    download. This is the point of fetching it: Sayari says the party is
    #    sanctioned, and the US Treasury list either corroborates that by name or
    #    it does not. Independent confirmation is worth more than either source
    #    alone, and a disagreement is worth showing rather than hiding.
    for finding in row.get("sanctioned_trade", []):
        label = finding.get("label")
        record = sdn.get(normalise(label))
        finding["ofac_sdn_confirmed"] = record is not None
        finding["ofac_sdn"] = record
        finding["corroboration"] = (
            f"Confirmed against the live OFAC SDN download under programme "
            f"{record['program']}." if record and record.get("program") else
            "Confirmed by name against the live OFAC SDN download." if record else
            "Sayari records this party as sanctioned, but its name does not match an "
            "OFAC SDN entry. It may be listed by another authority, or under a "
            "different transliteration."
        )
        if record:
            add(OFAC, "trade_counterparty", counterparty=label,
                matched="OFAC SDN", edge=finding.get("edge"),
                program=record.get("program"),
                shipments=finding.get("shipment_total"),
                post_designation=finding.get("count_after", 0))

    # Dedupe: the same owner surfaces through several risk factors.
    seen, unique = set(), []
    for hit in hits:
        key = (hit["regime"], hit["how"], hit.get("entity") or hit.get("owner"),
               hit.get("matched"), hit.get("hops"))
        if key not in seen:
            seen.add(key)
            unique.append(hit)
    return {**row, "regime_hits": unique}


def run(refresh_sdn: bool = False, client: Any = None) -> list[dict[str, Any]]:
    sdn = ofac_sdn_records(refresh=refresh_sdn)
    enriched = read_stage("03b_sanctions")
    rows = [assess(row, sdn, client) for row in enriched]
    for row in rows:
        regimes = sorted({h["regime"] for h in row["regime_hits"]})
        print(f"  external {row['brand']:10} {len(row['regime_hits']):>2} hit(s)  {regimes}")
    write_stage("04_external", rows, consumed=fingerprint(enriched))
    return rows


if __name__ == "__main__":
    run()
