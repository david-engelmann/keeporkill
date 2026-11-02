"""Command line entry point for keeporkill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import KeeporkillError
from .ingest import read_catchledger_packs
from .packs import assemble_packs, validate_pack
from .report import render_json
from .rulings import generate_ruling, ruling_slug


def _read_json(path, label):
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise KeeporkillError(f"the {label} could not be read") from exc
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KeeporkillError(f"the {label} is not valid JSON") from exc


def _write_text(path, text):
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise KeeporkillError("an output could not be written") from exc


def _assemble(args):
    document = _read_json(args.catchledger, "catchledger evidence")
    catchledger_packs = read_catchledger_packs(document)
    canary_document = None
    if args.canaryfield is not None:
        canary_document = _read_json(args.canaryfield, "canaryfield results")
    blindness_document = None
    if args.blindgate is not None:
        blindness_document = _read_json(args.blindgate, "blindness evidence")
    packs = assemble_packs(catchledger_packs, canary_document, blindness_document)
    for filename, pack in packs.items():
        _write_text(Path(args.packs_dir) / filename, render_json(pack))
    return 0


def _rule(args):
    pack = _read_json(args.pack, "evidence pack")
    record, body = generate_ruling(pack, args.ruling, args.expires, today=args.today)
    slug = ruling_slug(pack["check"])
    _write_text(Path(args.out) / f"ruling-{slug}.json", render_json(record))
    _write_text(Path(args.out) / f"ruling-{slug}.md", body)
    return 0


def _validate(args):
    pack = _read_json(args.pack, "evidence pack")
    document = _read_json(args.catchledger, "catchledger evidence")
    catchledger_packs = read_catchledger_packs(document)
    canary_document = None
    if args.canaryfield is not None:
        canary_document = _read_json(args.canaryfield, "canaryfield results")
    blindness_document = None
    if args.blindgate is not None:
        blindness_document = _read_json(args.blindgate, "blindness evidence")
    validate_pack(pack, catchledger_packs, canary_document, blindness_document)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="keeporkill",
        description="Assemble evidence packs for checks and generate their rulings.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    assemble = subparsers.add_parser(
        "assemble", help="assemble one evidence pack per check from local evidence files"
    )
    assemble.add_argument("--catchledger", required=True, help="local catchledger pack or ledger JSON")
    assemble.add_argument("--canaryfield", help="local canaryfield catch table JSON")
    assemble.add_argument("--blindgate", help="local blindgate evidence JSON")
    assemble.add_argument("--packs-dir", required=True, help="directory for evidence pack files")
    assemble.set_defaults(handler=_assemble)

    rule = subparsers.add_parser(
        "rule", help="generate a ruling record and pull request body from an evidence pack"
    )
    rule.add_argument("--pack", required=True, help="local keeporkill evidence pack JSON")
    rule.add_argument(
        "--ruling",
        required=True,
        help="the ruling to issue, one of keep and demote and quarantine",
    )
    rule.add_argument("--expires", help="the expiry date for a quarantine ruling")
    rule.add_argument("--today", help="the current date used for expiry discipline")
    rule.add_argument("--out", required=True, help="directory for the ruling artifacts")
    rule.set_defaults(handler=_rule)

    validate = subparsers.add_parser(
        "validate", help="validate an evidence pack against the pack rebuilt from its inputs"
    )
    validate.add_argument("--pack", required=True, help="local keeporkill evidence pack JSON")
    validate.add_argument("--catchledger", required=True, help="local catchledger pack or ledger JSON")
    validate.add_argument("--canaryfield", help="local canaryfield catch table JSON")
    validate.add_argument("--blindgate", help="local blindgate evidence JSON")
    validate.set_defaults(handler=_validate)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except KeeporkillError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
