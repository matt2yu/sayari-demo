"""Persona verdict tests.

The point of the app is that the same product gets different answers for different
buyers, so the cases that matter are the ones where the verdict *changes* across
personas. Both fixtures below are the real shape of live pipeline output.
"""

from pipeline.classify import (
    NO_RESTRICTION,
    PERSONAS,
    PROHIBITED,
    REVIEW,
    _coverage_warning,
    classify_one,
)


def product(**overrides):
    base = {
        "brand": "Test", "resolved": True,
        "family": [{"id": "e1", "label": "TEST CO"}],
        "family_flow": 50_000,
        "flags": [], "regime_hits": [],
    }
    return {**base, **overrides}


TP_LINK_HIT = {
    "regime": "section_1260h", "how": "seed_risk",
    "authority": "Section 1260H, FY2021 NDAA -- Chinese Military Companies",
    "citation": "10 U.S.C. 113 note; procurement bar under Sec. 805, FY2024 NDAA",
    "binds": "Department of Defense procurement only",
    "factor": "usa_section_1260h", "level": "high", "entity_ids": ["e1"],
}

EZVIZ_HIT = {
    "regime": "section_889", "how": "owner",
    "authority": "Section 889, FY2019 NDAA",
    "citation": "Pub. L. 115-232; 48 CFR 52.204-25",
    "binds": "federal agencies and federal contractors",
    "owner": "Hangzhou Hikvision Digital Technology Co., Ltd.",
    "matched": "Hangzhou Hikvision Digital Technology", "hops": 1,
    "edge": "has_shareholder", "via_factor": "owned_by_usa_bis_entity",
    "stake_pct": 60,
}


def test_the_whole_thesis_in_one_assertion():
    """TP-Link is the best-selling router brand in the US and on a DoD prohibition
    list. Both are true, because the two facts bind different buyers."""
    out = classify_one(product(brand="TP-Link", regime_hits=[TP_LINK_HIT]))
    assert out["verdicts"]["consumer"]["status"] == NO_RESTRICTION
    assert out["verdicts"]["enterprise"]["status"] == NO_RESTRICTION
    assert out["verdicts"]["dod"]["status"] == PROHIBITED


def test_section_889_reaches_contractors_but_not_households():
    """The escalation ladder. Section 889 binds federal contractors across their
    whole business and extends by its own terms to subsidiaries and affiliates, so
    the same product goes from unrestricted to barred purely by who is asking."""
    out = classify_one(product(brand="EZVIZ", regime_hits=[EZVIZ_HIT]))
    assert out["verdicts"]["consumer"]["status"] == NO_RESTRICTION
    assert out["verdicts"]["federal_contractor"]["status"] == PROHIBITED
    assert out["verdicts"]["dod"]["status"] == PROHIBITED


def test_ownership_severity_depends_on_how_far_the_regime_reaches():
    """The same ownership link means different things under different regimes.

    Section 889 names Hikvision and extends to "subsidiaries and affiliates", so an
    ownership link is a bar. The FCC Covered List restricts authorisation of the
    equipment rather than the corporate group, so the identical link is a diligence
    trigger there. Flattening both to one severity was what made Enterprise IT and
    Federal Contractor produce identical results.
    """
    fcc = {**EZVIZ_HIT, "regime": "fcc_covered", "authority": "FCC Covered List",
           "citation": "47 CFR 1.50002", "binds": "equipment authorisation"}
    out = classify_one(product(regime_hits=[fcc, EZVIZ_HIT]))
    assert out["verdicts"]["enterprise"]["status"] == REVIEW
    assert out["verdicts"]["federal_contractor"]["status"] == PROHIBITED


def test_section_889_severity_follows_the_actual_stake():
    """Whether an ownership link is a bar depends on the size of the stake, which
    the pipeline reads from the graph. Hikvision holds 48-60% of EZVIZ, which is a
    subsidiary on any reading -- but a small minority holding is not, and must not
    be reported as one."""
    minority = {**EZVIZ_HIT, "stake_pct": 5}
    assert (
        classify_one(product(regime_hits=[minority]))["verdicts"]
        ["federal_contractor"]["status"] == REVIEW
    )
    unknown = {**EZVIZ_HIT, "stake_pct": None}
    assert (
        classify_one(product(regime_hits=[unknown]))["verdicts"]
        ["federal_contractor"]["status"] == REVIEW
    ), "an unmeasured stake must not be assumed to clear the threshold"


def test_trade_predating_designation_is_not_a_restriction():
    """Shipments that ended before the counterparty was listed restrict nobody.

    Counting them flagged seven brands on the weakest evidence in the dataset and
    buried the two findings that actually bind someone. It stays on the product
    page as context instead.
    """
    historic = {
        "regime": "ofac_sdn", "how": "trade_counterparty",
        "authority": "OFAC Specially Designated Nationals",
        "citation": "31 CFR 501", "binds": "all US persons",
        "counterparty": "OBLTRANSTERMINAL", "shipments": 69, "post_designation": 0,
    }
    out = classify_one(product(regime_hits=[historic]))
    assert out["worst_status"] == NO_RESTRICTION

    current = {**historic, "post_designation": 12}
    still = classify_one(product(regime_hits=[current]))
    assert still["verdicts"]["enterprise"]["status"] == REVIEW


def test_every_reason_carries_a_statute():
    """A verdict cites an authority or it does not render. No ethical language."""
    out = classify_one(product(regime_hits=[TP_LINK_HIT, EZVIZ_HIT]))
    for verdict in out["verdicts"].values():
        for reason in verdict["reasons"]:
            assert reason["authority"] and reason["citation"] and reason["binds"]


def test_clean_product_is_unrestricted_for_everyone():
    out = classify_one(product(regime_hits=[]))
    assert all(v["status"] == NO_RESTRICTION for v in out["verdicts"].values())
    assert out["worst_status"] == NO_RESTRICTION


# --------------------------------------------------------- coverage honesty

def test_no_shipments_is_reported_as_a_gap_not_a_clean_result():
    """Ring resolves with zero flags only because Amazon imports on its behalf."""
    warning = _coverage_warning(product(family_flow=0))
    assert warning is not None
    assert "not evidence of absence" in warning


def test_unresolved_brand_says_nothing_was_screened():
    warning = _coverage_warning(product(resolved=False, family=[]))
    assert "Nothing was screened" in warning


def test_well_covered_product_has_no_warning():
    assert _coverage_warning(product(family_flow=1_000_000)) is None


def test_personas_are_ordered_least_to_most_constrained():
    sizes = [len(p["regimes"]) for p in PERSONAS]
    assert sizes == sorted(sizes), "each persona should inherit the ones before it"
