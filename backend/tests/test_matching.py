"""Regression tests for the false positives we actually hit against live data."""

import pytest

from pipeline.matching import brand_matches, is_logistics, token_match


@pytest.mark.parametrize(
    "needle,haystack",
    [
        # The one that matters most: a 3-letter restriction-list token inside an
        # unrelated word would have produced a false FCC Covered List hit.
        ("ZTE", "REOLINK EZTECH DIGITAL INC"),
        ("Ring", "NIPPON PISTON RING COMPANY LIMITED"),  # token rule alone passes;
        ("Govee", "GOVE ALUMINIUM FINANCE LIMITED"),
        ("Sonos", "ARVATO DIGITAL SERVICES LLC"),
        ("Hikvision", "REOLINK TECHNOLOGY PTE. LTD."),
    ],
)
def test_rejects_known_false_positives(needle, haystack):
    if needle == "Ring":
        # "RING" *is* a whole token here, so token matching cannot save us. This
        # case is only caught by the per-product reject rules in products.json --
        # asserting that so nobody later assumes token matching is sufficient.
        assert token_match(needle, haystack) is True
        return
    assert token_match(needle, haystack) is False


@pytest.mark.parametrize(
    "needle,haystack",
    [
        ("TP-Link", "TP-LINK TECHNOLOGIES CO.,LTD."),
        ("Hikvision", "Hangzhou Hikvision Digital Technology Co., Ltd."),
        ("EZVIZ", "HANGZHOU EZVIZ NETWORK CO.,LTD"),
        ("Tenda", "SHENZHEN TENDA TECHNOLOGY CO.,LTD"),
        ("ZTE", "ZTE CORPORATION"),
        ("D-Link", "D-LINK INTERNATIONAL PTE LTD"),
        ("Anker", "ANKER INNOVATIONS LIMITED"),
    ],
)
def test_accepts_real_matches(needle, haystack):
    assert token_match(needle, haystack) is True


def test_brand_matches_is_case_and_punctuation_insensitive():
    assert brand_matches("tp-link", "TP LINK TECHNOLOGIES")
    assert brand_matches("TPLink", "TP-Link Technologies Co., Ltd.")


@pytest.mark.parametrize(
    "label",
    [
        "SCHENKER INC",
        "AMAZON.COM SERVICES LLC",
        "DHL CUSTOMS (COSTA RICA) SA",
        "EMO TRANS, INC",  # matched via "trans"? no -- ensure we don't over-reject
    ],
)
def test_logistics_detection(label):
    # EMO TRANS is not in our term list; assert the others are caught and that we
    # are not silently rejecting everything.
    if label == "EMO TRANS, INC":
        assert is_logistics(label) is False
    else:
        assert is_logistics(label) is True


def test_empty_inputs_do_not_match():
    assert token_match("", "ANYTHING") is False
    assert token_match("ZTE", None) is False
