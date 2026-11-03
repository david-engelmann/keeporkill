import copy

import pytest

from tameshi.errors import TameshiError, PackValidationError
from tameshi.packs import (
    assemble_packs,
    canary_performance,
    catch_record_days,
    floor_accounting,
    validate_pack,
)
from tameshi.ingest import normalize_canary_document
from synthetic_data import (
    at_floor_pack,
    make_blindness_document,
    make_canary_document,
    make_catch_record,
    make_cl_pack,
    make_embedded_canary,
    make_trace,
    make_window,
    pack_with,
)


def test_embedded_canaryfield_results_are_used_without_a_direct_document():
    embedded = make_embedded_canary(
        words=["caught", "caught", "waved-through", "not-applicable"]
    )
    packs = assemble_packs([make_cl_pack(canaryfield_results=embedded)])
    pack = next(iter(packs.values()))
    performance = pack["canary_performance"]
    assert performance["counts"]["caught"] == 2
    assert performance["scored"] == 3
    assert performance["catch_rate"] == 0.666667
    assert pack["sources"]["canary_origin"] == "embedded"


def test_embedded_canary_counts_are_tallied_from_their_rows():
    embedded = make_embedded_canary(words=["caught", "waved-through", "not-applicable"])
    packs = assemble_packs([make_cl_pack(canaryfield_results=embedded)])
    performance = next(iter(packs.values()))["canary_performance"]
    assert performance["counts"] == embedded["counts"]
    assert performance["scored"] == 2
    forged = copy.deepcopy(embedded)
    forged["counts"]["caught"] = 30
    with pytest.raises(TameshiError):
        assemble_packs([make_cl_pack(canaryfield_results=forged)])


def test_embedded_canary_forgery_with_scored_thirty_and_no_rows_is_refused():
    forged = {
        "source_format": "canaryfield-catch-table",
        "gate": "unit checks",
        "counts": {
            "caught": 0,
            "waved-through": 0,
            "not-applicable": 0,
            "gate-broken": 0,
        },
        "results": [],
        "scored": 30,
    }
    with pytest.raises(TameshiError):
        assemble_packs([make_cl_pack(canaryfield_results=forged)])


def test_canary_catch_rate_is_null_when_no_defect_is_scored():
    document = make_canary_document({"unit checks": ["not-applicable"] * 4})
    performance = canary_performance(
        normalize_canary_document(document, "unit checks")
    )
    assert performance["scored"] == 0
    assert performance["catch_rate"] is None


def test_pack_sources_count_unmatched_blindness_traces():
    blindness = make_blindness_document(
        [
            make_trace("unit checks"),
            make_trace("mystery checks", detail="first unmatched synthetic trace"),
            make_trace("mystery checks", detail="second unmatched synthetic trace"),
        ]
    )
    packs = assemble_packs(
        [make_cl_pack(check="unit checks"), make_cl_pack(check="style checks")],
        None,
        blindness,
    )
    assert packs
    for pack in packs.values():
        assert pack["sources"]["blindgate_unmatched_trace_count"] == 2


def test_direct_canaryfield_document_overrides_embedded_results():
    embedded = make_embedded_canary(words=["caught"] * 5)
    document = make_canary_document({"unit checks": ["caught"] * 2})
    packs = assemble_packs(
        [make_cl_pack(canaryfield_results=embedded)], document
    )
    pack = next(iter(packs.values()))
    assert pack["canary_performance"]["counts"]["caught"] == 2
    assert pack["sources"]["canary_origin"] == "direct"


def test_canaryfield_performance_is_null_without_an_exact_gate_match():
    embedded = make_embedded_canary(words=["caught"] * 5)
    document = make_canary_document({"style checks": ["caught"] * 5})
    packs = assemble_packs(
        [make_cl_pack(canaryfield_results=embedded)], document
    )
    pack = next(iter(packs.values()))
    assert pack["canary_performance"] is None
    assert pack["sources"]["canary_origin"] == "direct"
    packs = assemble_packs([make_cl_pack()])
    pack = next(iter(packs.values()))
    assert pack["canary_performance"] is None
    assert pack["sources"]["canary_origin"] == "none"


def test_pack_carries_the_complete_check_evidence():
    cl_pack = make_cl_pack()
    pack = at_floor_pack()
    assert pack["format"] == "tameshi-pack/1"
    assert pack["repo"] == cl_pack["repo"]
    assert pack["check"] == "unit checks"
    assert pack["catch_record"] == cl_pack["catch_record"]
    assert pack["scorecard"] == cl_pack["scorecard"]
    assert pack["false_block_rate"] == cl_pack["scorecard"]["false_block_rate"]
    assert pack["cost_per_catch_usd"] == cl_pack["scorecard"]["cost_per_catch_usd"]
    assert pack["history_window"] == cl_pack["history_window"]
    assert pack["canary_performance"]["scored"] == 30
    assert pack["floor"] == {
        "required_canary_defects": 30,
        "required_ci_history_days": 14,
        "canary_defects": 30,
        "ci_history_days": 14,
        "canary_shortfall": 0,
        "ci_history_shortfall": 0,
        "meets_floor": True,
    }
    assert pack["below_floor"] is False
    assert pack["blindness_traces"] == []


def test_pack_sources_record_the_evidence_origins():
    cl_pack = make_cl_pack()
    document = make_canary_document({"unit checks": ["caught"]})
    pack = next(iter(assemble_packs([cl_pack], document).values()))
    assert pack["sources"] == {
        "catchledger_source": cl_pack["source"],
        "canary_origin": "direct",
        "blindgate_evidence_supplied": False,
        "blindgate_unmatched_trace_count": 0,
    }
    blindness = make_blindness_document([make_trace("unit checks")])
    pack = next(iter(assemble_packs([make_cl_pack()], None, blindness).values()))
    assert pack["sources"]["canary_origin"] == "none"
    assert pack["sources"]["blindgate_evidence_supplied"] is True


def test_blindness_traces_are_carried_for_their_check():
    traces = [
        make_trace("unit checks", detail="first synthetic trace"),
        make_trace("style checks", detail="other check trace"),
        make_trace("unit checks", detail="second synthetic trace"),
    ]
    blindness = make_blindness_document(traces)
    packs = assemble_packs(
        [make_cl_pack(check="unit checks"), make_cl_pack(check="style checks")],
        None,
        blindness,
    )
    by_check = {pack["check"]: pack for pack in packs.values()}
    assert by_check["unit checks"]["blindness_traces"] == [traces[0], traces[2]]
    assert by_check["style checks"]["blindness_traces"] == [traces[1]]


def test_pack_carries_blindness_traces_only_where_supplied():
    packs = assemble_packs([make_cl_pack()])
    assert next(iter(packs.values()))["blindness_traces"] == []
    blindness = make_blindness_document([make_trace("style checks")])
    packs = assemble_packs([make_cl_pack()], None, blindness)
    assert next(iter(packs.values()))["blindness_traces"] == []


def test_floor_accounting_counts_scored_defects_and_history_days():
    document = make_canary_document({"unit checks": ["caught"] * 12})
    performance = canary_performance(normalize_canary_document(document, "unit checks"))
    accounting = floor_accounting(performance, make_catch_record(days=9))
    assert accounting["canary_defects"] == 12
    assert accounting["ci_history_days"] == 9
    assert accounting["canary_shortfall"] == 18
    assert accounting["ci_history_shortfall"] == 5
    assert accounting["meets_floor"] is False


def test_floor_counts_history_days_from_the_window_span():
    assert catch_record_days(make_catch_record(days=14)) == 14
    assert catch_record_days(make_catch_record(days=13)) == 13
    assert catch_record_days(make_catch_record(days=1)) == 1
    assert catch_record_days([]) == 0
    pack = pack_with(["caught"] * 30, days=14)
    assert pack["history_window"] == make_window(40)
    assert pack["floor"]["ci_history_days"] == 14


def test_a_pack_without_a_history_window_reads_zero_history_days():
    words = ["caught"] * 30
    document = make_canary_document({"unit checks": words})
    absent = next(
        iter(
            assemble_packs(
                [make_cl_pack(days=0, window_days="absent")], document
            ).values()
        )
    )
    assert absent["history_window"] is None
    assert absent["floor"]["ci_history_days"] == 0
    assert absent["floor"]["ci_history_shortfall"] == 14
    assert absent["below_floor"] is True
    null_window = next(
        iter(
            assemble_packs(
                [make_cl_pack(days=14, window_days=None)], document
            ).values()
        )
    )
    assert null_window["history_window"] is None
    assert null_window["floor"]["ci_history_days"] == 14
    assert null_window["below_floor"] is False


def test_one_day_of_own_history_under_a_forty_day_window_refuses():
    pack = pack_with(["caught"] * 30, days=1)
    assert pack["history_window"] == make_window(40)
    assert pack["floor"]["ci_history_days"] == 1
    assert pack["floor"]["ci_history_shortfall"] == 13
    assert pack["below_floor"] is True


def test_an_empty_catch_record_holds_zero_history_days():
    pack = pack_with(["caught"] * 30, days=0)
    assert pack["catch_record"] == []
    assert pack["floor"]["ci_history_days"] == 0
    assert pack["floor"]["ci_history_shortfall"] == 14
    assert pack["below_floor"] is True


def test_floor_days_convert_offset_timestamps_to_utc():
    record = make_catch_record(days=2)
    record[0]["started_at"] = "2026-01-01T00:30:00+05:00"
    record[1]["started_at"] = "2026-01-14T23:30:00+00:00"
    assert catch_record_days(record) == 15


def test_scored_defects_exclude_not_applicable_rows():
    document = make_canary_document(
        {"unit checks": ["caught"] * 10 + ["not-applicable"] * 25}
    )
    performance = canary_performance(normalize_canary_document(document, "unit checks"))
    assert performance["counts"]["not-applicable"] == 25
    assert performance["scored"] == 10


def test_floor_marks_a_pack_below_floor_on_either_leg():
    short_days = pack_with(["caught"] * 30, days=13)
    assert short_days["floor"]["canary_shortfall"] == 0
    assert short_days["floor"]["ci_history_shortfall"] == 1
    assert short_days["floor"]["meets_floor"] is False
    assert short_days["below_floor"] is True
    short_defects = pack_with(["caught"] * 29, days=14)
    assert short_defects["floor"]["canary_shortfall"] == 1
    assert short_defects["floor"]["ci_history_shortfall"] == 0
    assert short_defects["below_floor"] is True
    at_floor = pack_with(["caught"] * 30, days=14)
    assert at_floor["below_floor"] is False


def test_pack_validation_accepts_a_rebuilt_pack():
    cl_pack = make_cl_pack()
    document = make_canary_document({"unit checks": ["caught"] * 3})
    pack = next(iter(assemble_packs([cl_pack], document).values()))
    assert validate_pack(pack, [cl_pack], document) is True


def test_pack_validation_refuses_a_tampered_floor():
    cl_pack = make_cl_pack()
    pack = next(iter(assemble_packs([cl_pack]).values()))
    assert pack["below_floor"] is True
    tampered = copy.deepcopy(pack)
    tampered["floor"]["canary_defects"] = 99
    with pytest.raises(PackValidationError):
        validate_pack(tampered, [cl_pack])
    tampered = copy.deepcopy(pack)
    tampered["below_floor"] = False
    with pytest.raises(PackValidationError):
        validate_pack(tampered, [cl_pack])


def test_pack_validation_refuses_tampered_evidence_and_metadata():
    cl_pack = make_cl_pack()
    pack = next(iter(assemble_packs([cl_pack]).values()))
    tampered = copy.deepcopy(pack)
    tampered["scorecard"]["catches"] = 400
    with pytest.raises(PackValidationError):
        validate_pack(tampered, [cl_pack])
    tampered = copy.deepcopy(pack)
    tampered["check"] = "unknown checks"
    with pytest.raises(PackValidationError):
        validate_pack(tampered, [cl_pack])
    tampered = copy.deepcopy(pack)
    tampered["notes"] = "extra"
    with pytest.raises(PackValidationError):
        validate_pack(tampered, [cl_pack])
    tampered = copy.deepcopy(pack)
    del tampered["floor"]
    with pytest.raises(PackValidationError):
        validate_pack(tampered, [cl_pack])
