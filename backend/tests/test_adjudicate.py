"""Adjudication tests.

The cases here are all real: every label appeared in live Sayari output during
development, and each one either was, or nearly was, mis-adjudicated.
"""

import pytest

from pipeline.adjudicate import _dedupe, _rejection_reason, adjudicate_one
from pipeline.matching import is_composite_party, name_matches


def candidate(label, queried_name=None, via="resolution", cid=None):
    return {
        "id": cid or label.lower().replace(" ", "-"),
        "label": label,
        "queried_name": queried_name,
        "via": via,
    }


RING = {
    "id": "ring", "brand": "Ring", "product": "Video Doorbell", "category": "camera",
    "legal_name": "Ring LLC", "country": "USA", "parent": "Amazon.com, Inc.",
    "reject_patterns": ["piston", "ring container", "npr manufactur"],
}


# --------------------------------------------------------------- alias matching

def test_alias_resolved_entity_is_kept_even_without_the_brand_token():
    """The regression that matters most.

    BOT HOME AUTOMATION is the correct Ring entity, found via an alias. Judging it
    against the brand token "Ring" rejects the right answer.
    """
    hit = candidate("BOT HOME AUTOMATION, INC.", queried_name="Bot Home Automation, Inc.")
    assert _rejection_reason(RING, hit) is None


def test_subbrand_resolving_to_its_parent_is_kept():
    eufy = {**RING, "id": "eufy", "brand": "Eufy",
            "legal_name": "Anker Innovations Limited", "reject_patterns": []}
    hit = candidate("ANKER INNOVATIONS LIMITED", queried_name="Anker Innovations Limited")
    assert _rejection_reason(eufy, hit) is None


def test_name_matches_tolerates_differing_corporate_form():
    assert name_matches("Reolink Innovation Limited", "REOLINK TECHNOLOGY PTE. LTD.")
    assert name_matches("TP-Link Technologies Co Ltd", "TP-LINK TECHNOLOGIES CO.,LTD.")


def test_name_matches_rejects_an_unrelated_company():
    assert not name_matches("Sonos Inc", "ARVATO DIGITAL SERVICES LLC")
    assert not name_matches("Vizio Inc", "BOEVT (HONGKONG) CO., LIMITED")


def test_name_matching_alone_cannot_save_us_from_common_nouns():
    """Pinning a known limitation rather than pretending it does not exist.

    "Ring LLC" reduces to the single distinctive token "ring", which genuinely
    appears in NIPPON PISTON RING. No amount of name matching fixes that -- only
    the per-product reject_patterns do. Anyone tempted to delete those patterns
    should see this test fail first.
    """
    assert name_matches("Ring LLC", "NIPPON PISTON RING COMPANY LIMITED") is True
    reason = _rejection_reason(RING, candidate("NIPPON PISTON RING COMPANY LIMITED",
                                               queried_name="Ring LLC"))
    assert reason is not None and "reject pattern" in reason


# ------------------------------------------------------------- reject patterns

@pytest.mark.parametrize("label", [
    "NIPPON PISTON RING COMPANY LIMITED",
    "Ring Container Technologies, LLC",
    "NPR MANUFACTURING INDONESIA",
])
def test_reject_patterns_win_over_token_match(label):
    # "RING" is a whole token in these, so token matching alone would accept them.
    reason = _rejection_reason(RING, candidate(label, queried_name="Ring LLC"))
    assert reason is not None and "reject pattern" in reason


def test_freight_forwarders_are_rejected():
    reason = _rejection_reason(RING, candidate("SCHENKER INC", queried_name="Ring LLC"))
    assert reason == "freight forwarder or marketplace, not the manufacturer"


# ----------------------------------------------------------- composite parties

@pytest.mark.parametrize("label", [
    '"Agregator-S Online" LLC через Anker Innovations Ltd',
    "APEX LOGISTICS INT'L (BEIJING) INC. по поручению ANKER",
    "SOME RESELLER LLC on behalf of Hikvision",
])
def test_composite_party_strings_are_detected(label):
    assert is_composite_party(label) is True


def test_composite_party_is_rejected_so_risk_is_not_misattributed():
    eufy = {**RING, "id": "eufy", "brand": "Eufy",
            "legal_name": "Anker Innovations Limited", "reject_patterns": []}
    hit = candidate('"Agregator-S Online" LLC через Anker Innovations Ltd',
                    queried_name="Anker Innovations Limited")
    reason = _rejection_reason(eufy, hit)
    assert reason is not None and "composite" in reason


def test_ordinary_labels_are_not_flagged_as_composite():
    for label in ["ANKER INNOVATIONS LIMITED", "TP-LINK TECHNOLOGIES CO.,LTD."]:
        assert is_composite_party(label) is False


# -------------------------------------------------------------------- dedupe

def test_dedupe_collapses_repeated_labels_and_records_the_ids():
    """Sayari's docs concede it "frequently stores duplicated entities" -- Ring
    returns ten distinct ids all labelled RING LLC."""
    dupes = [candidate("RING LLC", cid=f"id{i}") for i in range(10)]
    result = _dedupe([*dupes, candidate("RING PROTECT INC.", cid="rp")])
    assert len(result) == 2
    ring = next(r for r in result if r["label"] == "RING LLC")
    assert len(ring["duplicate_ids"]) == 9


# ------------------------------------------------------------------ end to end

def test_adjudicate_one_splits_accepted_from_rejected():
    row = {"product": RING, "candidates": [
        candidate("RING LLC", queried_name="Ring LLC"),
        candidate("BOT HOME AUTOMATION, INC.", queried_name="Bot Home Automation, Inc."),
        candidate("NIPPON PISTON RING COMPANY LIMITED", queried_name="Ring LLC"),
    ]}
    out = adjudicate_one(row)
    assert out["resolved"] is True
    assert {c["label"] for c in out["family"]} == {"RING LLC", "BOT HOME AUTOMATION, INC."}
    assert len(out["rejected"]) == 1
    assert "piston" in out["rejected"][0]["rejected_because"]


def test_a_brand_with_no_surviving_candidates_is_marked_unresolved():
    row = {"product": RING, "candidates": [candidate("NIPPON PISTON RING", queried_name="Ring LLC")]}
    out = adjudicate_one(row)
    assert out["resolved"] is False
    assert out["family"] == []
