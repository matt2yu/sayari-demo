"""API tests, run against the committed sample snapshot -- no credentials needed."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def products():
    response = client.get("/api/products")
    assert response.status_code == 200
    return response.json()


def test_health():
    assert client.get("/api/health").json()["ok"] is True


def test_all_25_products_are_served(products):
    assert len(products["products"]) == 25
    assert all(p["resolved"] for p in products["products"])


def test_every_card_has_a_verdict_for_every_persona(products):
    keys = {p["key"] for p in products["personas"]}
    for product in products["products"]:
        assert set(product["verdicts"]) == keys


def test_tp_link_is_unrestricted_for_consumers_and_prohibited_for_dod(products):
    """The whole thesis in one assertion."""
    tp = next(p for p in products["products"] if p["id"] == "tp-link")
    assert tp["verdicts"]["consumer"]["status"] == "no_restriction"
    assert tp["verdicts"]["dod"]["status"] == "prohibited"


def test_ezviz_detail_exposes_the_ownership_chain():
    detail = client.get("/api/products/ezviz").json()
    # Trade-chain hops are deliberately left unresolved (label is None) because the
    # UI never renders them; only ownership chains carry names.
    owners = {
        hop["label"]
        for flag in detail["flags"]
        for chain in flag.get("chains", [])
        if chain["kind"] == "ownership"
        for hop in chain["hops"]
        if hop.get("label")
    }
    assert any("Hikvision" in o for o in owners)
    assert any("China Electronics Technology Group" in o for o in owners)


def test_thin_trade_coverage_is_always_disclosed(products):
    """A brand with little or no shipment data must say so rather than present a
    clean chip. Ring and Vizio look clean only because Amazon and Walmart import on
    their behalf.

    Asserts the invariant, not a particular brand's current numbers -- those move
    whenever match rules change, and a test that pins them just breaks on every
    legitimate improvement.
    """
    thin = [p for p in products["products"] if p["family_flow"] < 1000]
    assert thin, "expected at least one brand with sparse trade coverage"
    for card in thin:
        for verdict in card["verdicts"].values():
            assert verdict["coverage_warning"], (
                f"{card['brand']} has {card['family_flow']} shipments but no warning"
            )


def test_well_covered_brands_carry_no_spurious_warning(products):
    for card in products["products"]:
        if card["family_flow"] > 100_000:
            assert card["verdicts"]["consumer"]["coverage_warning"] is None


def test_every_flag_carries_its_ontology_description():
    """No flag renders as a bare scary string."""
    for pid in ("tp-link", "ezviz", "tcl"):
        detail = client.get(f"/api/products/{pid}").json()
        for flag in detail["flags"]:
            entry = detail["glossary"].get(flag["id"])
            assert entry and entry["description"], f"{pid}/{flag['id']} has no description"


def test_no_deprecated_factor_is_ever_served():
    for pid in ("tp-link", "ezviz", "tcl", "asus"):
        detail = client.get(f"/api/products/{pid}").json()
        for flag in detail["flags"]:
            assert flag["deprecated"] is False
            assert flag["id"] not in ("sanctioned_adjacent", "export_controls_adjacent")


def test_reolink_is_not_matched_to_zte():
    """REOLINK EZTECH DIGITAL contains the letters ZTE. It must never produce an
    FCC Covered List hit."""
    detail = client.get("/api/products/reolink").json()
    for hit in detail["regime_hits"]:
        assert hit.get("matched") != "ZTE Corporation"


def test_rejected_candidates_are_published_with_reasons(products):
    """The adjudication is part of the deliverable, not an appendix.

    Ring is the worst case -- "ring" is a common noun in industrial company names,
    so it attracts piston makers, jewellers and firearms trainers.
    """
    detail = client.get("/api/products/ring").json()
    assert detail["rejected"], "Ring must show the candidates it discarded"
    assert all(r["rejected_because"] for r in detail["rejected"])

    # Across the whole list, adjudication must actually be doing work.
    total = sum(
        len(client.get(f"/api/products/{p['id']}").json()["rejected"])
        for p in products["products"]
    )
    assert total > 20, f"only {total} candidates rejected across 25 brands"


def test_meta_publishes_caveats_and_measured_api_cost():
    meta = client.get("/api/meta").json()
    assert len(meta["caveats"]) >= 4
    assert any("bills of lading" in c for c in meta["caveats"])
    assert "total_calls" in meta["api"]
    assert {r["key"] for r in meta["regimes"]} == {
        "section_889", "fcc_covered", "section_1260h", "ofac_sdn"
    }


def test_every_regime_states_who_it_binds():
    """"Restricted" is meaningless without naming the population it restricts."""
    for regime in client.get("/api/meta").json()["regimes"]:
        assert regime["binds"] and regime["citation"]


def test_unknown_product_is_404():
    assert client.get("/api/products/nope").status_code == 404


def test_sanctioned_trade_is_served_with_full_counts():
    """Nine brands reach a sanctioned counterparty through trade edges."""
    detail = client.get("/api/products/tcl").json()
    findings = detail["sanctioned_trade"]
    assert findings, "TCL reaches sanctioned parties via ships_to"
    for finding in findings:
        assert finding["shipment_total"] > 0
        assert finding["examined"] == finding["shipment_total"], "must count, not sample"
        assert finding["assessment"]


def test_no_sanctions_claim_is_made_without_dating_it(products):
    """Undated, this finding reads 'ships to an OFAC-SDN entity'. Every finding
    must either carry a designation date or say that it has none."""
    for card in products["products"]:
        detail = client.get(f"/api/products/{card['id']}").json()
        for finding in detail.get("sanctioned_trade", []):
            if finding["designated_on"] is None:
                assert "cannot be placed" in finding["assessment"]
            else:
                assert finding["count_after"] + finding["count_before"] + \
                       finding["count_undatable"] == finding["examined"]


def test_lawful_historic_trade_is_not_presented_as_a_violation(products):
    for card in products["products"]:
        detail = client.get(f"/api/products/{card['id']}").json()
        for finding in detail.get("sanctioned_trade", []):
            if finding["count_after"] == 0 and finding["shipment_total"] > 0:
                assert "not evidence of a violation" in finding["assessment"] \
                    or "cannot be placed" in finding["assessment"]
