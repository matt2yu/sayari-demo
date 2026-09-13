"""Sanctions dating tests.

This stage exists to stop a specific overstatement. Undated, the finding reads
"five consumer brands ship to an OFAC-SDN Russian entity". Dated, every one of
the 2,696 shipments turns out to predate the counterparty's designation. The
first version would have been the headline; the second is the truth.
"""

import typing

from pipeline.sanctions import _earliest_designation, assess


class FakeNames:
    def __init__(self, sanctioned_ids):
        self._sanctioned = set(sanctioned_ids)

    def get(self, entity_id):
        return {
            "id": entity_id,
            "label": f"ENTITY {entity_id}",
            "countries": ["RUS"],
            "sanctioned": entity_id in self._sanctioned,
            "seed_risks": ["sanctioned_usa_ofac_sdn"] if entity_id in self._sanctioned else [],
        }


class FakeClient:
    """Returns a fixed designation date and a fixed set of dated shipments."""

    def __init__(self, designation, shipment_dates):
        self.designation = designation
        self.shipment_dates = shipment_dates

    def get_entity(self, _id):
        class E:
            attributes: typing.ClassVar = {"risk_intelligence": {"data": [
                {"properties": {"type": "sanctioned", "list": "OFAC SDN",
                                "from_date": self.designation}},
            ]}}
        return E()

    def search_shipments(self, limit, filter):
        dates = self.shipment_dates

        class Size:
            count = len(dates)

        class Shipment:
            def __init__(self, date):
                self.arrival_date = [date]
                self.departure_date = []
                self.supplier = []
                self.product_descriptions = ["TV panels"]
                self.hs_codes = ["8529"]

        class R:
            size = Size()
            data: typing.ClassVar = [Shipment(d) for d in dates]
        return R()


def product(paths, family=("fam1",)):
    return {
        "brand": "TCL",
        "family": [{"id": f} for f in family],
        "flags": [{"id": "some_network_factor", "chains": [{"raw": p} for p in paths]}],
        "dropped_flags": [],
    }


TRADE_PATH = "fam1|ships_to|BAD"
OWNERSHIP_PATH = "fam1|has_shareholder|OWNER"


def test_all_shipments_predating_designation_is_reported_as_lawful():
    client = FakeClient("2024-02-23", ["2022-12-24", "2023-01-08", "2023-07-11"])
    out = assess(client, product([TRADE_PATH]), FakeNames({"BAD"}))
    finding = out["sanctioned_trade"][0]
    assert finding["count_after"] == 0
    assert finding["count_before"] == 3
    assert "not evidence of a violation" in finding["assessment"]


def test_post_designation_shipments_are_counted_and_surfaced():
    client = FakeClient("2024-02-23", ["2023-01-01", "2024-06-01", "2025-02-02"])
    out = assess(client, product([TRADE_PATH]), FakeNames({"BAD"}))
    finding = out["sanctioned_trade"][0]
    assert finding["count_after"] == 2
    assert finding["count_before"] == 1
    assert "on or after the designation date" in finding["assessment"]


def test_missing_designation_date_refuses_to_guess():
    """Sources disagree: the Ukraine registry publishes from_date, the OFAC record
    for the same entity publishes only a programme. Without a date we say so."""
    client = FakeClient(None, ["2023-01-01", "2025-01-01"])
    out = assess(client, product([TRADE_PATH]), FakeNames({"BAD"}))
    finding = out["sanctioned_trade"][0]
    assert finding["designated_on"] is None
    assert finding["count_after"] == 0 and finding["count_before"] == 0
    assert finding["count_undatable"] == 2
    assert "cannot be placed before or after" in finding["assessment"]


def test_ownership_paths_are_left_to_the_ownership_finding():
    client = FakeClient("2024-01-01", ["2025-01-01"])
    out = assess(client, product([OWNERSHIP_PATH]), FakeNames({"OWNER"}))
    assert out["sanctioned_trade"] == []


def test_unsanctioned_counterparties_are_ignored():
    client = FakeClient("2024-01-01", ["2025-01-01"])
    out = assess(client, product([TRADE_PATH]), FakeNames(set()))
    assert out["sanctioned_trade"] == []


def test_completeness_is_recorded_so_a_sample_is_never_read_as_the_population():
    client = FakeClient("2024-02-23", ["2022-01-01"] * 10)
    finding = assess(client, product([TRADE_PATH]), FakeNames({"BAD"}))["sanctioned_trade"][0]
    assert finding["examined"] == finding["shipment_total"]
    assert finding["complete"] is True


def test_no_shipments_is_stated_plainly():
    client = FakeClient("2024-02-23", [])
    finding = assess(client, product([TRADE_PATH]), FakeNames({"BAD"}))["sanctioned_trade"][0]
    assert finding["shipment_total"] == 0
    assert "No shipments found" in finding["assessment"]


def test_earliest_designation_prefers_the_first_dated_listing():
    assert _earliest_designation([
        {"from_date": None}, {"from_date": "2025-04-18"}, {"from_date": "2024-02-23"},
    ]) == "2024-02-23"
    assert _earliest_designation([{"from_date": None}]) is None
