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
}


def test_the_whole_thesis_in_one_assertion():
    """TP-Link is the best-selling router brand in the US and on a DoD prohibition
    list. Both are true, because the two facts bind different buyers."""
    out = classify_one(product(brand="TP-Link", regime_hits=[TP_LINK_HIT]))
    assert out["verdicts"]["consumer"]["status"] == NO_RESTRICTION
    assert out["verdicts"]["enterprise"]["status"] == NO_RESTRICTION
    assert out["verdicts"]["dod"]["status"] == PROHIBITED


def test_section_889_reaches_contractors_but_not_households():
    out = classify_one(product(brand="EZVIZ", regime_hits=[EZVIZ_HIT]))
    assert out["verdicts"]["consumer"]["status"] == NO_RESTRICTION
    assert out["verdicts"]["federal_contractor"]["status"] == REVIEW
    assert out["verdicts"]["dod"]["status"] == REVIEW


def test_ownership_reached_hits_are_review_not_prohibited():
    """Section 889's reach to "subsidiaries and affiliates" is a legal question about
    a specific corporate relationship. A name match up an ownership chain is a
    diligence trigger, not a determination -- calling it prohibited overstates it."""
    out = classify_one(product(regime_hits=[EZVIZ_HIT]))
    assert out["verdicts"]["federal_contractor"]["status"] == REVIEW


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
