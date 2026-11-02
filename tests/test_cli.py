import json

from keeporkill.cli import main
from keeporkill.report import render_json
from synthetic_data import (
    at_floor_pack,
    make_blindness_document,
    make_canary_document,
    make_cl_pack,
    make_ledger,
    make_trace,
)


def _write(path, document):
    path.write_text(render_json(document), encoding="utf-8")
    return str(path)


def _assemble_inputs(tmp_path):
    ledger_path = _write(
        tmp_path / "ledger.json",
        make_ledger([make_cl_pack(check="unit checks"), make_cl_pack(check="style checks")]),
    )
    canary_path = _write(
        tmp_path / "canary.json",
        make_canary_document({"unit checks": ["caught"] * 30, "style checks": ["caught"] * 2}),
    )
    blindness_path = _write(
        tmp_path / "blindness.json",
        make_blindness_document([make_trace("unit checks")]),
    )
    return ledger_path, canary_path, blindness_path


def test_cli_writes_deterministic_pack_outputs(tmp_path):
    ledger_path, canary_path, blindness_path = _assemble_inputs(tmp_path)
    outputs = []
    for name in ("first", "second"):
        packs_dir = tmp_path / name
        result = main(
            [
                "assemble",
                "--catchledger",
                ledger_path,
                "--canaryfield",
                canary_path,
                "--blindgate",
                blindness_path,
                "--packs-dir",
                str(packs_dir),
            ]
        )
        assert result == 0
        outputs.append(
            {
                path.name: path.read_bytes()
                for path in sorted(packs_dir.glob("*.json"))
            }
        )
    assert outputs[0] == outputs[1]
    assert sorted(outputs[0]) == ["001-style-checks.json", "002-unit-checks.json"]


def test_cli_writes_deterministic_ruling_outputs(tmp_path):
    pack_path = _write(tmp_path / "pack.json", at_floor_pack())
    outputs = []
    for name in ("first", "second"):
        out_dir = tmp_path / name
        result = main(
            [
                "rule",
                "--pack",
                pack_path,
                "--ruling",
                "quarantine",
                "--expires",
                "2027-03-01",
                "--today",
                "2026-01-01",
                "--out",
                str(out_dir),
            ]
        )
        assert result == 0
        outputs.append(
            {path.name: path.read_bytes() for path in sorted(out_dir.iterdir())}
        )
    assert outputs[0] == outputs[1]
    assert sorted(outputs[0]) == ["ruling-unit-checks.json", "ruling-unit-checks.md"]
    record = json.loads(outputs[0]["ruling-unit-checks.json"])
    assert record["ruling"] == "quarantine"
    assert record["expiry"] == "2027-03-01"


def test_cli_rule_uses_the_supplied_current_date_for_expiry(tmp_path):
    pack_path = _write(tmp_path / "pack.json", at_floor_pack())
    late_out = tmp_path / "late"
    result = main(
        [
            "rule",
            "--pack",
            pack_path,
            "--ruling",
            "quarantine",
            "--expires",
            "2027-03-01",
            "--today",
            "2027-03-02",
            "--out",
            str(late_out),
        ]
    )
    assert result == 1
    assert not late_out.exists() or list(late_out.iterdir()) == []
    current_out = tmp_path / "current"
    result = main(
        [
            "rule",
            "--pack",
            pack_path,
            "--ruling",
            "quarantine",
            "--expires",
            "2027-03-01",
            "--today",
            "2027-03-01",
            "--out",
            str(current_out),
        ]
    )
    assert result == 0
    assert sorted(path.name for path in current_out.iterdir()) == [
        "ruling-unit-checks.json",
        "ruling-unit-checks.md",
    ]


def test_cli_validate_accepts_a_pack_rebuilt_from_its_inputs(tmp_path):
    ledger_path, canary_path, blindness_path = _assemble_inputs(tmp_path)
    packs_dir = tmp_path / "packs"
    assert (
        main(
            [
                "assemble",
                "--catchledger",
                ledger_path,
                "--canaryfield",
                canary_path,
                "--blindgate",
                blindness_path,
                "--packs-dir",
                str(packs_dir),
            ]
        )
        == 0
    )
    pack_path = packs_dir / "002-unit-checks.json"
    assert (
        main(
            [
                "validate",
                "--pack",
                str(pack_path),
                "--catchledger",
                ledger_path,
                "--canaryfield",
                canary_path,
                "--blindgate",
                blindness_path,
            ]
        )
        == 0
    )


def test_cli_validate_refuses_a_tampered_pack(tmp_path):
    ledger_path, canary_path, blindness_path = _assemble_inputs(tmp_path)
    packs_dir = tmp_path / "packs"
    assert (
        main(
            [
                "assemble",
                "--catchledger",
                ledger_path,
                "--canaryfield",
                canary_path,
                "--blindgate",
                blindness_path,
                "--packs-dir",
                str(packs_dir),
            ]
        )
        == 0
    )
    pack_path = packs_dir / "002-unit-checks.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["floor"]["canary_defects"] = 99
    tampered_path = _write(tmp_path / "tampered-pack.json", pack)
    assert (
        main(
            [
                "validate",
                "--pack",
                tampered_path,
                "--catchledger",
                ledger_path,
                "--canaryfield",
                canary_path,
                "--blindgate",
                blindness_path,
            ]
        )
        == 1
    )


def test_missing_inputs_are_refused(tmp_path):
    missing = str(tmp_path / "absent.json")
    assert (
        main(["assemble", "--catchledger", missing, "--packs-dir", str(tmp_path / "packs")])
        == 1
    )
    assert (
        main(
            [
                "rule",
                "--pack",
                missing,
                "--ruling",
                "keep",
                "--out",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )


def test_outputs_carry_no_local_paths(tmp_path):
    ledger_path, canary_path, blindness_path = _assemble_inputs(tmp_path)
    packs_dir = tmp_path / "packs"
    assert (
        main(
            [
                "assemble",
                "--catchledger",
                ledger_path,
                "--canaryfield",
                canary_path,
                "--blindgate",
                blindness_path,
                "--packs-dir",
                str(packs_dir),
            ]
        )
        == 0
    )
    pack_file = packs_dir / "002-unit-checks.json"
    out_dir = tmp_path / "ruling"
    assert (
        main(
            [
                "rule",
                "--pack",
                str(pack_file),
                "--ruling",
                "keep",
                "--out",
                str(out_dir),
            ]
        )
        == 0
    )
    written = list(packs_dir.iterdir()) + list(out_dir.iterdir())
    assert written
    for path in written:
        assert str(tmp_path) not in path.read_text(encoding="utf-8")
