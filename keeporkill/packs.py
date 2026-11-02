"""Evidence pack assembly, floor accounting, and pack validation."""

from __future__ import annotations

from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP

from .errors import KeeporkillError, PackValidationError
from .ingest import (
    RESULT_WORDS,
    normalize_canary_document,
    parse_timestamp,
    read_blindness_traces,
    tally_canary_results,
    validate_catch_record,
    validate_normalized_canary,
)
from .names import slugify_check

PACK_FORMAT = "keeporkill-pack/1"
REQUIRED_CANARY_DEFECTS = 30
REQUIRED_CI_HISTORY_DAYS = 14

_SIX_PLACES = Decimal("0.000001")


def _ratio(numerator, denominator):
    if denominator == 0:
        return None
    value = Decimal(numerator) / Decimal(denominator)
    return float(value.quantize(_SIX_PLACES, rounding=ROUND_HALF_UP))


_PERFORMANCE_FIELDS = {"gate", "counts", "scored", "catch_rate", "results"}
_PERFORMANCE_ROW_FIELDS = {"seed", "name", "defect_class", "result", "planted_files"}


def _derived_scored(counts):
    return counts["caught"] + counts["waved-through"] + counts["gate-broken"]


def validate_canary_performance(performance):
    """Validate a pack canary performance against its own row evidence."""

    if performance is None:
        return None
    if not isinstance(performance, dict) or set(performance) != _PERFORMANCE_FIELDS:
        raise KeeporkillError("the canary performance has the wrong fields")
    gate = performance["gate"]
    if not isinstance(gate, str) or not gate.strip() or "\n" in gate or "\r" in gate:
        raise KeeporkillError("the canary performance needs a gate name")
    counts = performance["counts"]
    if not isinstance(counts, dict) or set(counts) != set(RESULT_WORDS):
        raise KeeporkillError("the canary performance counts must cover the four result words")
    if not all(type(count) is int and count >= 0 for count in counts.values()):
        raise KeeporkillError("the canary performance counts must be nonnegative whole numbers")
    results = performance["results"]
    if not isinstance(results, list):
        raise KeeporkillError("the canary performance results must be a list")
    for row in results:
        if not isinstance(row, dict) or set(row) != _PERFORMANCE_ROW_FIELDS:
            raise KeeporkillError("a canary performance result row has the wrong fields")
        for field in ("seed", "name", "defect_class"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise KeeporkillError(f"a canary performance result row needs a nonempty {field}")
        if row["result"] not in RESULT_WORDS:
            raise KeeporkillError("a canary performance result word is not a known result word")
        if not isinstance(row["planted_files"], list) or not all(
            isinstance(path, str) for path in row["planted_files"]
        ):
            raise KeeporkillError("a canary performance result row carries malformed planted files")
    if counts != tally_canary_results(results):
        raise KeeporkillError("the canary performance counts disagree with their result rows")
    scored = _derived_scored(counts)
    if type(performance["scored"]) is not int or performance["scored"] != scored:
        raise KeeporkillError("the canary performance scored count disagrees with its rows")
    if performance["catch_rate"] != _ratio(counts["caught"], scored):
        raise KeeporkillError("the canary performance catch rate disagrees with its rows")
    return performance


def canary_performance(normalized):
    """Build the pack's canary performance from normalized canaryfield evidence.

    A planted defect is scored for the check when the gate was exercised
    against it, so every result word except not-applicable counts as scored.
    The counts are tallied from the rows, and recorded counts that disagree
    with those rows are refused before a performance is built.
    """

    if normalized is None:
        return None
    validate_normalized_canary(normalized)
    counts = tally_canary_results(normalized["results"])
    scored = _derived_scored(counts)
    return {
        "gate": normalized["gate"],
        "counts": counts,
        "scored": scored,
        "catch_rate": _ratio(counts["caught"], scored),
        "results": normalized["results"],
    }


def catch_record_days(catch_record):
    """Count the UTC calendar days one check catch record spans.

    The count runs from the date of the earliest started at timestamp
    through the date of the latest started at timestamp inclusive, after
    each timestamp is converted to UTC. An empty record holds zero days.
    """

    validate_catch_record(catch_record)
    if not catch_record:
        return 0
    moments = [
        parse_timestamp(entry["started_at"], "catch record started at timestamp")
        .astimezone(timezone.utc)
        for entry in catch_record
    ]
    return (max(moment.date() for moment in moments) - min(moment.date() for moment in moments)).days + 1


def floor_accounting(performance, catch_record):
    """Account one check's evidence against the floor on both legs."""

    if performance is not None:
        validate_canary_performance(performance)
    held_defects = _derived_scored(performance["counts"]) if performance is not None else 0
    held_days = catch_record_days(catch_record)
    return {
        "required_canary_defects": REQUIRED_CANARY_DEFECTS,
        "required_ci_history_days": REQUIRED_CI_HISTORY_DAYS,
        "canary_defects": held_defects,
        "ci_history_days": held_days,
        "canary_shortfall": max(0, REQUIRED_CANARY_DEFECTS - held_defects),
        "ci_history_shortfall": max(0, REQUIRED_CI_HISTORY_DAYS - held_days),
        "meets_floor": held_defects >= REQUIRED_CANARY_DEFECTS
        and held_days >= REQUIRED_CI_HISTORY_DAYS,
    }


def _assemble_one(
    catchledger_pack,
    canary_document,
    traces_by_check,
    blindness_supplied,
    unmatched_trace_count=0,
):
    check = catchledger_pack["check"]
    if canary_document is not None:
        origin = "direct"
        performance = canary_performance(normalize_canary_document(canary_document, check))
    elif catchledger_pack["canaryfield_results"] is not None:
        origin = "embedded"
        performance = canary_performance(catchledger_pack["canaryfield_results"])
    else:
        origin = "none"
        performance = None
    if traces_by_check is None:
        traces = []
    else:
        traces = list(traces_by_check.get(check, []))
    window = catchledger_pack.get("history_window")
    accounting = floor_accounting(performance, catchledger_pack["catch_record"])
    return {
        "format": PACK_FORMAT,
        "repo": catchledger_pack["repo"],
        "check": check,
        "scorecard": catchledger_pack["scorecard"],
        "catch_record": catchledger_pack["catch_record"],
        "history_window": window,
        "false_block_rate": catchledger_pack["false_block_rate"],
        "cost_per_catch_usd": catchledger_pack["scorecard"]["cost_per_catch_usd"],
        "canary_performance": performance,
        "blindness_traces": traces,
        "floor": accounting,
        "below_floor": not accounting["meets_floor"],
        "sources": {
            "catchledger_source": catchledger_pack["source"],
            "canary_origin": origin,
            "blindgate_evidence_supplied": blindness_supplied,
            "blindgate_unmatched_trace_count": unmatched_trace_count,
        },
    }


def _pack_filename(index, check):
    return f"{index:03d}-{slugify_check(check)}.json"


def assemble_packs(catchledger_packs, canary_document=None, blindness_document=None):
    """Assemble one evidence pack per check, keyed by deterministic file name."""

    traces_by_check = None
    unmatched_trace_count = 0
    if blindness_document is not None:
        traces_by_check = read_blindness_traces(blindness_document)
        known_checks = {pack["check"] for pack in catchledger_packs}
        unmatched_trace_count = sum(
            len(traces)
            for check, traces in traces_by_check.items()
            if check not in known_checks
        )
    packs = {}
    ordered = sorted(catchledger_packs, key=lambda pack: pack["check"])
    for index, catchledger_pack in enumerate(ordered, start=1):
        pack = _assemble_one(
            catchledger_pack,
            canary_document,
            traces_by_check,
            blindness_document is not None,
            unmatched_trace_count,
        )
        packs[_pack_filename(index, pack["check"])] = pack
    return packs


def validate_pack(pack, catchledger_packs, canary_document=None, blindness_document=None):
    """Return True when a pack exactly matches the pack rebuilt from its inputs."""

    if not isinstance(pack, dict):
        raise PackValidationError("an evidence pack must be an object")
    check_name = pack.get("check")
    if not isinstance(check_name, str) or not check_name:
        raise PackValidationError("an evidence pack needs a check name")
    expected = None
    for candidate in assemble_packs(
        catchledger_packs, canary_document, blindness_document
    ).values():
        if candidate["check"] == check_name:
            expected = candidate
            break
    if expected is None:
        raise PackValidationError("the evidence pack names a check outside its inputs")
    if pack != expected:
        raise PackValidationError("the evidence pack disagrees with its rebuilt pack")
    return True


def recompute_floor(pack):
    """Recompute a pack's floor accounting from the pack's own evidence."""

    if not isinstance(pack, dict):
        raise KeeporkillError("an evidence pack must be an object")
    return floor_accounting(pack.get("canary_performance"), pack.get("catch_record"))
