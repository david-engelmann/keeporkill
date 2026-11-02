import copy

import pytest

from keeporkill.errors import KeeporkillError
from keeporkill.ingest import read_catchledger_packs
from keeporkill.packs import assemble_packs
from synthetic_data import (
    make_blindness_document,
    make_canary_document,
    make_cl_pack,
    make_ledger,
    make_trace,
)


def test_pack_input_is_read_exactly():
    pack = make_cl_pack()
    packs = read_catchledger_packs(pack)
    assert len(packs) == 1
    assert packs[0] == pack
    assert set(packs[0]) == {
        "format",
        "repo",
        "check",
        "scorecard",
        "catch_record",
        "canaryfield_results",
        "false_block_rate",
        "pricing",
        "source",
        "history_window",
    }


def test_ledger_input_derives_the_same_packs():
    first = make_cl_pack(check="unit checks")
    second = make_cl_pack(check="style checks")
    derived = read_catchledger_packs(make_ledger([first, second]))
    direct = read_catchledger_packs(first) + read_catchledger_packs(second)
    assert sorted(derived, key=lambda pack: pack["check"]) == sorted(
        direct, key=lambda pack: pack["check"]
    )
    for pack in derived:
        assert pack["format"] == "catchledger-pack/1"
        assert pack["false_block_rate"] == pack["scorecard"]["false_block_rate"]
        assert pack["pricing"] == first["pricing"]
        assert pack["source"] == first["source"]


def test_catchledger_input_with_a_missing_or_unexpected_field_is_refused():
    pack = make_cl_pack()
    missing = copy.deepcopy(pack)
    del missing["pricing"]
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(missing)
    unexpected = copy.deepcopy(pack)
    unexpected["notes"] = "extra"
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(unexpected)
    thin_scorecard = copy.deepcopy(pack)
    del thin_scorecard["scorecard"]["fires"]
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(thin_scorecard)
    ledger = make_ledger([make_cl_pack()])
    del ledger["checks"][0]["name"]
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(ledger)


def test_catchledger_input_with_a_wrong_format_name_is_refused():
    pack = make_cl_pack()
    pack["format"] = "catchledger-pack/2"
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(pack)
    with pytest.raises(KeeporkillError):
        read_catchledger_packs({"format": "something-else/1"})


def test_catchledger_pack_with_a_disagreeing_false_block_rate_is_refused():
    pack = make_cl_pack()
    pack["false_block_rate"] = 0.99
    with pytest.raises(KeeporkillError) as caught:
        read_catchledger_packs(pack)
    assert "disagrees with its scorecard" in str(caught.value)


def test_direct_canaryfield_document_with_a_repeated_seed_is_refused():
    document = make_canary_document({"unit checks": ["caught", "caught"]})
    document["rows"].append(copy.deepcopy(document["rows"][0]))
    with pytest.raises(KeeporkillError) as caught:
        assemble_packs([make_cl_pack()], document)
    assert "repeats a seed" in str(caught.value)


def test_names_with_newlines_are_refused_at_ingest():
    pack = make_cl_pack(check="unit checks\nInjected line")
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(pack)
    pack = make_cl_pack(repo="synthetic-repo\nInjected line")
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(pack)
    ledger = make_ledger([make_cl_pack(check="style checks")])
    ledger["checks"][0]["name"] = "style checks\nInjected line"
    with pytest.raises(KeeporkillError):
        read_catchledger_packs(ledger)


def test_direct_canaryfield_results_are_normalized_for_the_matching_check():
    document = make_canary_document(
        {"unit checks": ["caught", "waved-through", "gate-broken", "not-applicable"]}
    )
    packs = assemble_packs([make_cl_pack()], document)
    performance = next(iter(packs.values()))["canary_performance"]
    assert performance["gate"] == "unit checks"
    assert performance["counts"] == {
        "caught": 1,
        "waved-through": 1,
        "not-applicable": 1,
        "gate-broken": 1,
    }
    assert performance["scored"] == 3
    assert performance["catch_rate"] == 0.333333
    assert [row["seed"] for row in performance["results"]] == [
        "seed-00",
        "seed-01",
        "seed-02",
        "seed-03",
    ]
    assert performance["results"][0]["planted_files"] == ["src/synthetic.py"]


def test_malformed_canaryfield_document_is_refused():
    cl_pack = make_cl_pack()
    with pytest.raises(KeeporkillError):
        assemble_packs([cl_pack], {"gates": ["unit checks"]})
    bad_word = make_canary_document({"unit checks": ["caught"]})
    bad_word["rows"][0]["gates"]["unit checks"] = "missed"
    with pytest.raises(KeeporkillError):
        assemble_packs([cl_pack], bad_word)
    missing_gate = make_canary_document(
        {"unit checks": ["caught"], "style checks": ["caught"]}
    )
    del missing_gate["rows"][0]["gates"]["style checks"]
    with pytest.raises(KeeporkillError):
        assemble_packs([cl_pack], missing_gate)


def test_malformed_blindness_document_is_refused():
    cl_pack = make_cl_pack()
    wrong_format = make_blindness_document([make_trace("unit checks")])
    wrong_format["format"] = "blindgate-evidence/2"
    with pytest.raises(KeeporkillError):
        assemble_packs([cl_pack], None, wrong_format)
    thin_trace = make_blindness_document([make_trace("unit checks")])
    del thin_trace["traces"][0]["detail"]
    with pytest.raises(KeeporkillError):
        assemble_packs([cl_pack], None, thin_trace)
    empty_field = make_blindness_document(
        [make_trace("unit checks", observation="")]
    )
    with pytest.raises(KeeporkillError):
        assemble_packs([cl_pack], None, empty_field)
