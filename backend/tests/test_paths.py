"""Stage provenance tests.

These exist because of a real incident: several pipeline processes were left
running concurrently, each writing stage artifacts, and the result was a snapshot
whose stage 3 output had been produced from a stage 2 that no longer existed.
Every file had a recent mtime, so nothing looked wrong.

Recording what each stage consumed makes that detectable instead of guessable.
"""

import pytest

from pipeline import paths


@pytest.fixture(autouse=True)
def _isolated_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ARTIFACTS", tmp_path)


def test_fingerprint_is_stable_and_content_sensitive():
    assert paths.fingerprint([{"a": 1}]) == paths.fingerprint([{"a": 1}])
    assert paths.fingerprint([{"a": 1}]) != paths.fingerprint([{"a": 2}])
    # Key order must not matter; stage output is dict-shaped and unordered.
    assert paths.fingerprint([{"a": 1, "b": 2}]) == paths.fingerprint([{"b": 2, "a": 1}])


def test_round_trip_returns_rows_not_the_envelope():
    rows = [{"brand": "TP-Link"}, {"brand": "EZVIZ"}]
    paths.write_stage("01_candidates", rows)
    assert paths.read_stage("01_candidates") == rows


def test_meta_records_what_the_stage_consumed():
    upstream = [{"brand": "Ring"}]
    paths.write_stage("01_candidates", upstream)
    paths.write_stage("02_families", [{"ok": True}],
                      consumed=paths.fingerprint(upstream))
    meta = paths.read_stage_meta("02_families")
    assert meta["consumed"] == paths.fingerprint(upstream)
    assert meta["rows"] == 1


def test_chain_is_ok_when_each_stage_consumed_its_predecessor():
    first = [{"brand": "Ring"}]
    paths.write_stage("01_candidates", first)
    second = [{"brand": "Ring", "family": []}]
    paths.write_stage("02_families", second, consumed=paths.fingerprint(first))
    paths.write_stage("03_enriched", [{"done": True}], consumed=paths.fingerprint(second))

    report = paths.check_chain(["01_candidates", "02_families", "03_enriched"])
    assert [r["status"] for r in report] == ["ok", "ok", "ok"]


def test_chain_detects_an_upstream_rerun_that_downstream_never_saw():
    """The exact failure we hit: stage 1 is re-run, stage 2 is not, and stage 2's
    mtime still looks perfectly fresh."""
    first = [{"brand": "Ring"}]
    paths.write_stage("01_candidates", first)
    paths.write_stage("02_families", [{"family": ["stale"]}],
                      consumed=paths.fingerprint(first))

    paths.write_stage("01_candidates", [{"brand": "Ring", "changed": True}])

    report = paths.check_chain(["01_candidates", "02_families"])
    assert report[0]["status"] == "ok"
    assert report[1]["status"] == "STALE"


def test_missing_stage_is_reported_not_raised():
    report = paths.check_chain(["01_candidates", "02_families"])
    assert report[0]["status"] == "missing"


def test_legacy_bare_list_artifacts_still_load(tmp_path):
    """Artifacts written before provenance stamping were a bare JSON list."""
    import json
    (tmp_path / "02_families.json").write_text(json.dumps([{"brand": "Ring"}]))
    assert paths.read_stage("02_families") == [{"brand": "Ring"}]
    assert paths.read_stage_meta("02_families")["legacy"] is True


def test_reading_an_absent_stage_explains_what_to_run():
    with pytest.raises(FileNotFoundError, match="earlier pipeline stages"):
        paths.read_stage("03_enriched")
