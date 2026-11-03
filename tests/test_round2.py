"""Round 2 pins for the rename obligations and the duplicate key refusal."""

import pytest

from synthetic_data import (
    AT_FLOOR_WORDS,
    at_floor_pack,
    make_blindness_document,
    make_canary_document,
    make_cl_pack,
    make_trace,
)
from tameshi.cli import main
from tameshi.errors import PackValidationError, TameshiError
from tameshi.packs import assemble_packs, validate_pack
from tameshi.report import render_json
from tameshi.rulings import generate_ruling


def _at_floor_inputs():
    words = AT_FLOOR_WORDS + ["not-applicable"] * 3
    return [make_cl_pack(days=14)], make_canary_document({"unit checks": words})


def test_an_evidence_pack_carrying_the_old_format_stem_is_refused_by_the_generator():
    pack = at_floor_pack()
    pack["format"] = "keeporkill-pack/1"
    with pytest.raises(TameshiError) as caught:
        generate_ruling(pack, "keep", today="2026-01-01")
    assert "wrong format name" in str(caught.value)


def test_an_evidence_pack_carrying_the_old_format_stem_fails_validation():
    catchledger_packs, canary_document = _at_floor_inputs()
    pack = at_floor_pack()
    assert validate_pack(pack, catchledger_packs, canary_document) is True
    pack["format"] = "keeporkill-pack/1"
    with pytest.raises(PackValidationError):
        validate_pack(pack, catchledger_packs, canary_document)


def test_assembled_packs_and_rulings_carry_the_tameshi_format_stems():
    pack = at_floor_pack()
    assert pack["format"] == "tameshi-pack/1"
    record, _body = generate_ruling(pack, "keep", today="2026-01-01")
    assert record["format"] == "tameshi-ruling/1"
    packs = assemble_packs([make_cl_pack(days=14)])
    assert {item["format"] for item in packs.values()} == {"tameshi-pack/1"}


def _write_raw(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_document_with_a_repeated_top_level_key_is_refused(tmp_path, capsys):
    text = render_json(make_cl_pack())
    repeated = text.replace(
        '"format": "catchledger-pack/1"',
        '"format": "catchledger-pack/1", "format": "catchledger-pack/1"',
        1,
    )
    assert repeated != text
    document = _write_raw(tmp_path / "catchledger.json", repeated)
    result = main(
        ["assemble", "--catchledger", document, "--packs-dir", str(tmp_path / "packs")]
    )
    assert result == 1
    assert not (tmp_path / "packs").exists()
    message = capsys.readouterr().err
    assert "catchledger evidence" in message
    assert "format" in message


def test_a_document_with_a_repeated_nested_key_is_refused(tmp_path, capsys):
    text = render_json(make_cl_pack())
    repeated = text.replace('"fires": 40', '"fires": 40, "fires": 41', 1)
    assert repeated != text
    document = _write_raw(tmp_path / "catchledger.json", repeated)
    result = main(
        ["assemble", "--catchledger", document, "--packs-dir", str(tmp_path / "packs")]
    )
    assert result == 1
    assert not (tmp_path / "packs").exists()
    message = capsys.readouterr().err
    assert "catchledger evidence" in message
    assert "fires" in message


def test_a_repeated_key_in_an_evidence_pack_is_refused(tmp_path, capsys):
    text = render_json(at_floor_pack())
    repeated = text.replace(
        '"format": "tameshi-pack/1"', '"format": "tameshi-pack/1", "format": "tameshi-pack/1"', 1
    )
    assert repeated != text
    pack_path = _write_raw(tmp_path / "pack.json", repeated)
    out_dir = tmp_path / "out"
    result = main(["rule", "--pack", pack_path, "--ruling", "keep", "--out", str(out_dir)])
    assert result == 1
    assert not out_dir.exists()
    message = capsys.readouterr().err
    assert "evidence pack" in message
    assert "format" in message


def test_a_repeated_key_in_a_canaryfield_or_blindness_document_is_refused(tmp_path, capsys):
    catchledger = _write_raw(tmp_path / "catchledger.json", render_json(make_cl_pack()))
    canary_text = render_json(make_canary_document({"unit checks": ["caught"] * 30}))
    repeated_canary = canary_text.replace(
        '"gates": [', '"gates": [], "gates": [', 1
    )
    assert repeated_canary != canary_text
    canary_path = _write_raw(tmp_path / "canary.json", repeated_canary)
    result = main(
        [
            "assemble",
            "--catchledger",
            catchledger,
            "--canaryfield",
            canary_path,
            "--packs-dir",
            str(tmp_path / "packs-a"),
        ]
    )
    assert result == 1
    message = capsys.readouterr().err
    assert "canaryfield results" in message
    assert "gates" in message
    blindness_text = render_json(make_blindness_document([make_trace("unit checks")]))
    repeated_blindness = blindness_text.replace(
        '"format": "blindgate-evidence/1"',
        '"format": "blindgate-evidence/1", "format": "blindgate-evidence/1"',
        1,
    )
    assert repeated_blindness != blindness_text
    blindness_path = _write_raw(tmp_path / "blindness.json", repeated_blindness)
    result = main(
        [
            "assemble",
            "--catchledger",
            catchledger,
            "--blindgate",
            blindness_path,
            "--packs-dir",
            str(tmp_path / "packs-b"),
        ]
    )
    assert result == 1
    message = capsys.readouterr().err
    assert "blindness evidence" in message
    assert "format" in message
