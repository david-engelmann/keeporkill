import copy

import pytest

from keeporkill.cli import main
from keeporkill.errors import FloorRefusal, KeeporkillError
from keeporkill.report import render_json
from keeporkill.rulings import generate_ruling
from synthetic_data import (
    at_floor_pack,
    make_blindness_document,
    make_trace,
    pack_with,
)

AT_FLOOR_WORDS = ["caught"] * 30


def test_ruling_record_for_each_ruling_in_the_set():
    pack = at_floor_pack()
    record, _ = generate_ruling(pack, "keep")
    assert record["format"] == "keeporkill-ruling/1"
    assert record["check"] == "unit checks"
    assert record["repo"] == pack["repo"]
    assert record["ruling"] == "keep"
    assert record["state_after_ruling"] == "required"
    assert record["expiry"] is None
    assert record["floor"] == pack["floor"]
    record, _ = generate_ruling(pack, "demote")
    assert record["ruling"] == "demote-to-advisory"
    assert record["state_after_ruling"] == "advisory"
    assert record["expiry"] is None
    record, _ = generate_ruling(pack, "quarantine", "2027-03-01", today="2026-01-01")
    assert record["ruling"] == "quarantine"
    assert record["state_after_ruling"] == "quarantined"
    assert record["expiry"] == "2027-03-01"


def test_quarantine_without_an_expiry_is_refused():
    with pytest.raises(KeeporkillError) as caught:
        generate_ruling(at_floor_pack(), "quarantine")
    assert "requires an expiry date" in str(caught.value)


def test_expiry_on_a_non_quarantine_ruling_is_refused():
    with pytest.raises(KeeporkillError):
        generate_ruling(at_floor_pack(), "keep", "2027-03-01")
    with pytest.raises(KeeporkillError):
        generate_ruling(at_floor_pack(), "demote", "2027-03-01")


def test_quarantine_expiry_before_the_supplied_current_date_is_refused():
    with pytest.raises(KeeporkillError) as caught:
        generate_ruling(
            at_floor_pack(), "quarantine", "2027-03-01", today="2027-03-02"
        )
    assert "must not precede the current date" in str(caught.value)


def test_quarantine_expiry_on_the_supplied_current_date_generates():
    record, _ = generate_ruling(
        at_floor_pack(), "quarantine", "2027-03-01", today="2027-03-01"
    )
    assert record["expiry"] == "2027-03-01"


def test_quarantine_expiry_in_basic_iso_form_is_refused():
    with pytest.raises(KeeporkillError):
        generate_ruling(
            at_floor_pack(), "quarantine", "20270301", today="2026-01-01"
        )


def test_generator_rederives_scored_defects_from_rows():
    forged = copy.deepcopy(at_floor_pack())
    forged["canary_performance"]["counts"] = {
        "caught": 0,
        "waved-through": 0,
        "not-applicable": 0,
        "gate-broken": 0,
    }
    forged["canary_performance"]["results"] = []
    forged["canary_performance"]["scored"] = 30
    forged["canary_performance"]["catch_rate"] = None
    with pytest.raises(KeeporkillError) as caught:
        generate_ruling(forged, "keep")
    assert "scored count disagrees" in str(caught.value)


def test_pack_performance_with_an_extra_field_is_refused():
    forged = copy.deepcopy(at_floor_pack())
    forged["canary_performance"]["notes"] = "extra"
    with pytest.raises(KeeporkillError):
        generate_ruling(forged, "keep")


def test_a_pack_with_an_empty_scorecard_is_refused_by_the_generator():
    forged = copy.deepcopy(at_floor_pack())
    forged["scorecard"] = {}
    with pytest.raises(KeeporkillError):
        generate_ruling(forged, "keep")


def test_a_pack_with_a_malformed_history_window_is_refused_by_the_generator():
    forged = copy.deepcopy(at_floor_pack())
    forged["history_window"] = {"first_run_started_at": "2026-01-01T00:10:00Z"}
    with pytest.raises(KeeporkillError):
        generate_ruling(forged, "keep")


def test_ruling_pack_names_with_newlines_are_refused():
    forged = copy.deepcopy(at_floor_pack())
    forged["check"] = "unit checks\nSignature status signed"
    with pytest.raises(KeeporkillError):
        generate_ruling(forged, "keep")
    forged = copy.deepcopy(at_floor_pack())
    forged["repo"] = "synthetic-repo\nInjected line"
    with pytest.raises(KeeporkillError):
        generate_ruling(forged, "keep")


def test_kill_is_refused_as_outside_the_slice_ruling_set():
    with pytest.raises(KeeporkillError) as caught:
        generate_ruling(at_floor_pack(), "kill")
    assert "outside the ruling set" in str(caught.value)
    with pytest.raises(KeeporkillError):
        generate_ruling(at_floor_pack(), "shred")


def test_generated_rulings_are_always_unsigned():
    pack = at_floor_pack()
    for ruling, expiry in (("keep", None), ("demote", None), ("quarantine", "2027-03-01")):
        record, _ = generate_ruling(pack, ruling, expiry, today="2026-01-01")
        assert record["signature"] == {
            "status": "unsigned",
            "signed_by": None,
            "signed_at": None,
        }


def test_twenty_nine_scored_defects_refuse_a_ruling():
    pack = pack_with(["caught"] * 29, days=14)
    with pytest.raises(FloorRefusal) as caught:
        generate_ruling(pack, "keep")
    message = str(caught.value)
    assert "29 of 30" in message
    assert "falls short by 1" in message
    assert "CI history leg" not in message


def test_thirteen_history_days_refuse_a_ruling():
    pack = pack_with(AT_FLOOR_WORDS, days=13)
    with pytest.raises(FloorRefusal) as caught:
        generate_ruling(pack, "keep")
    message = str(caught.value)
    assert "13 of 14" in message
    assert "falls short by 1" in message
    assert "canary evidence leg" not in message


def test_exactly_at_the_floor_generates_a_ruling():
    pack = at_floor_pack()
    assert pack["floor"]["canary_defects"] == 30
    assert pack["floor"]["ci_history_days"] == 14
    record, body = generate_ruling(pack, "keep")
    assert record["ruling"] == "keep"
    assert body.startswith("# Ruling for unit checks")


def test_a_refusal_names_each_failed_leg_and_its_shortfall():
    pack = pack_with(["caught"] * 20, days=5)
    with pytest.raises(FloorRefusal) as caught:
        generate_ruling(pack, "demote")
    message = str(caught.value)
    assert "canary evidence leg holds 20 of 30" in message
    assert "falls short by 10" in message
    assert "CI history leg holds 5 of 14" in message
    assert "falls short by 9" in message


def test_a_refusal_writes_no_artifacts(tmp_path):
    pack = pack_with(["caught"] * 29, days=14)
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(render_json(pack), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = main(
        ["rule", "--pack", str(pack_path), "--ruling", "keep", "--out", str(out_dir)]
    )
    assert result == 1
    assert not out_dir.exists() or list(out_dir.iterdir()) == []


def test_a_pack_whose_floor_claim_disagrees_with_its_evidence_is_refused():
    pack = pack_with(["caught"] * 29, days=14)
    forged = copy.deepcopy(pack)
    forged["floor"]["canary_defects"] = 30
    forged["floor"]["canary_shortfall"] = 0
    forged["floor"]["meets_floor"] = True
    forged["below_floor"] = False
    with pytest.raises(KeeporkillError) as caught:
        generate_ruling(forged, "keep")
    assert not isinstance(caught.value, FloorRefusal)
    assert "disagrees" in str(caught.value)


def _body_rows(body):
    rows = {}
    for line in body.splitlines():
        if line.startswith("| ") and " | " in line:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in ("Evidence", "---"):
                rows[cells[0]] = cells[1]
    return rows


def _rendered(value):
    if value is None:
        return "none"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def test_ruling_body_numbers_all_come_from_the_pack():
    blindness = make_blindness_document(
        [make_trace("unit checks"), make_trace("unit checks", detail="second synthetic trace")]
    )
    pack = at_floor_pack(blindness_document=blindness)
    _, body = generate_ruling(pack, "quarantine", "2027-03-01", today="2026-01-01")
    rows = _body_rows(body)
    scorecard = pack["scorecard"]
    performance = pack["canary_performance"]
    counts = performance["counts"]
    accounting = pack["floor"]
    expected = {
        "Fires": _rendered(scorecard["fires"]),
        "Blocks": _rendered(scorecard["blocks"]),
        "Catches": _rendered(scorecard["catches"]),
        "False blocks": _rendered(scorecard["false_blocks"]),
        "Unattributed blocks": _rendered(scorecard["unattributed_blocks"]),
        "False block rate": _rendered(pack["false_block_rate"]),
        "Runtime seconds": _rendered(scorecard["runtime_seconds"]),
        "Total cost USD": _rendered(scorecard["total_cost_usd"]),
        "Cost per catch USD": _rendered(pack["cost_per_catch_usd"]),
        "Canary scored defects": _rendered(performance["scored"]),
        "Canary caught": _rendered(counts["caught"]),
        "Canary waved through": _rendered(counts["waved-through"]),
        "Canary gate broken": _rendered(counts["gate-broken"]),
        "Canary not applicable": _rendered(counts["not-applicable"]),
        "Canary catch rate": _rendered(performance["catch_rate"]),
        "Canary defects held": _rendered(accounting["canary_defects"]),
        "Canary defects required": _rendered(accounting["required_canary_defects"]),
        "CI history days held": _rendered(accounting["ci_history_days"]),
        "CI history days required": _rendered(accounting["required_ci_history_days"]),
        "Blindness traces": _rendered(len(pack["blindness_traces"])),
    }
    for label, value in expected.items():
        assert rows[label] == value, label
    assert body.count(chr(0x2014)) == 0
    assert body.count(chr(0x2013)) == 0


def test_ruling_body_names_the_ruling_and_expiry():
    pack = at_floor_pack()
    _, body = generate_ruling(pack, "quarantine", "2027-03-01", today="2026-01-01")
    rows = _body_rows(body)
    assert body.startswith("# Ruling for unit checks")
    assert rows["Ruling"] == "quarantine"
    assert rows["State after ruling"] == "quarantined"
    assert rows["Expiry"] == "2027-03-01"
    _, body = generate_ruling(pack, "keep")
    rows = _body_rows(body)
    assert rows["Ruling"] == "keep"
    assert "Expiry" not in rows
