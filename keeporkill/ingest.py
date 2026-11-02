"""Local ingestion for catchledger evidence, canaryfield results, and blindness evidence."""

from __future__ import annotations

from datetime import datetime

from .errors import KeeporkillError

CATCHLEDGER_PACK_FORMAT = "catchledger-pack/1"
CATCHLEDGER_LEDGER_FORMAT = "catchledger-ledger/1"
CANARY_SOURCE_FORMAT = "canaryfield-catch-table"
BLINDNESS_FORMAT = "blindgate-evidence/1"

# The history window record catchledger publishes in its ledger and in every
# pack, under its FIX-7 obligation. It is one record across every ingested
# run, holding the earliest run start and the latest run update, and it
# stands null when no runs stand. A pack written before the window stood
# carries no such field and reads as zero days of history.
HISTORY_WINDOW_FIELD = "history_window"
_WINDOW_FIELDS = {"first_run_started_at", "last_run_updated_at"}

RESULT_WORDS = ("caught", "waved-through", "not-applicable", "gate-broken")
OUTCOME_WORDS = ("catch", "false_block", "unattributed")

_PACK_FIELDS = {
    "format",
    "repo",
    "check",
    "scorecard",
    "catch_record",
    "canaryfield_results",
    "false_block_rate",
    "pricing",
    "source",
}
_LEDGER_FIELDS = {"format", "repo", "pricing", "source", "checks", "totals"}
_LEDGER_ENTRY_FIELDS = {
    "name",
    "scorecard",
    "catch_record",
    "canaryfield_results",
    "evidence_pack_file",
}
_SCORECARD_FIELDS = {
    "fires",
    "blocks",
    "judged_commits",
    "flaky_commits",
    "flake_rate",
    "runtime_seconds",
    "runtime_minutes",
    "catches",
    "false_blocks",
    "unattributed_blocks",
    "false_block_rate",
    "total_cost_usd",
    "cost_per_catch_usd",
}
_CATCH_RECORD_FIELDS = {
    "block_run_id",
    "blocked_commit",
    "started_at",
    "outcome",
    "flagged_paths",
    "evidence",
}
_CATCH_EVIDENCE_FIELDS = {"type", "fix_commits", "validating_run_id", "reason"}
_CANARY_RESULT_FIELDS = {"source_format", "gate", "counts", "results"}
_CANARY_ROW_FIELDS = {"seed", "name", "defect_class", "result", "planted_files"}
_BLINDNESS_TRACE_FIELDS = {"check", "surface", "observation", "detail"}


def _require_exact_fields(value, fields, label):
    if not isinstance(value, dict):
        raise KeeporkillError(f"the {label} must be an object")
    standing = set(value)
    if standing != fields:
        missing = sorted(fields - standing)
        unexpected = sorted(standing - fields)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise KeeporkillError(f"the {label} has the wrong fields ({'; '.join(details)})")


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise KeeporkillError(f"the {label} must be nonempty text")
    return value


def _require_name(value, label):
    _require_text(value, label)
    if "\n" in value or "\r" in value:
        raise KeeporkillError(f"the {label} must not carry a newline")
    return value


def parse_timestamp(value, label):
    """Parse an ISO 8601 timestamp that carries a timezone offset."""

    if not isinstance(value, str) or not value.strip():
        raise KeeporkillError(f"the {label} must be an ISO 8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KeeporkillError(f"the {label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise KeeporkillError(f"the {label} must carry a timezone offset")
    return parsed


def validate_scorecard(scorecard):
    _require_exact_fields(scorecard, _SCORECARD_FIELDS, "catchledger scorecard")


def validate_catch_record(catch_record):
    if not isinstance(catch_record, list):
        raise KeeporkillError("the catch record must be a list")
    for entry in catch_record:
        _require_exact_fields(entry, _CATCH_RECORD_FIELDS, "catch record entry")
        _require_text(entry["block_run_id"], "catch record block run identifier")
        _require_text(entry["blocked_commit"], "catch record blocked commit")
        parse_timestamp(entry["started_at"], "catch record started at timestamp")
        if entry["outcome"] not in OUTCOME_WORDS:
            raise KeeporkillError("a catch record outcome is not a known outcome word")
        if not isinstance(entry["flagged_paths"], list) or not all(
            isinstance(path, str) for path in entry["flagged_paths"]
        ):
            raise KeeporkillError("the catch record flagged paths must be a list of text")
        _require_exact_fields(entry["evidence"], _CATCH_EVIDENCE_FIELDS, "catch evidence")


def tally_canary_results(results):
    """Tally normalized canaryfield rows over the four result words."""

    counts = {word: 0 for word in RESULT_WORDS}
    for row in results:
        counts[row["result"]] += 1
    return counts


def validate_normalized_canary(value):
    if value is None:
        return None
    _require_exact_fields(value, _CANARY_RESULT_FIELDS, "canaryfield results")
    if value["source_format"] != CANARY_SOURCE_FORMAT:
        raise KeeporkillError("the canaryfield results carry an unknown source format")
    _require_name(value["gate"], "canaryfield gate name")
    counts = value["counts"]
    if not isinstance(counts, dict) or set(counts) != set(RESULT_WORDS):
        raise KeeporkillError("the canaryfield counts must cover the four result words")
    if not all(type(count) is int and count >= 0 for count in counts.values()):
        raise KeeporkillError("the canaryfield counts must be nonnegative whole numbers")
    if not isinstance(value["results"], list):
        raise KeeporkillError("the canaryfield results rows must be a list")
    for row in value["results"]:
        _require_exact_fields(row, _CANARY_ROW_FIELDS, "canaryfield result row")
        for field in ("seed", "name", "defect_class"):
            _require_text(row[field], f"canaryfield result row {field}")
        if row["result"] not in RESULT_WORDS:
            raise KeeporkillError("a canaryfield result word is not a known result word")
        if not isinstance(row["planted_files"], list) or not all(
            isinstance(path, str) for path in row["planted_files"]
        ):
            raise KeeporkillError("a canaryfield result row carries malformed planted files")
    if counts != tally_canary_results(value["results"]):
        raise KeeporkillError("the canaryfield counts disagree with their result rows")
    return value


def _require_fields_with_optional_window(value, fields, label):
    if not isinstance(value, dict):
        raise KeeporkillError(f"the {label} must be an object")
    standing = set(value)
    allowed = fields | {HISTORY_WINDOW_FIELD}
    if not fields.issubset(standing) or not standing.issubset(allowed):
        missing = sorted(fields - standing)
        unexpected = sorted(standing - allowed)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise KeeporkillError(f"the {label} has the wrong fields ({'; '.join(details)})")


def validate_history_window(value):
    """Validate a history window record and return it, or None when absent or null."""

    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _WINDOW_FIELDS:
        raise KeeporkillError(
            "the history window must carry a first run start and a last run update"
        )
    first = value["first_run_started_at"]
    last = value["last_run_updated_at"]
    if (first is None) != (last is None):
        raise KeeporkillError("the history window timestamps must stand or fall together")
    if first is not None:
        first_at = parse_timestamp(first, "history window first run start")
        last_at = parse_timestamp(last, "history window last run update")
        if last_at < first_at:
            raise KeeporkillError("the history window last run update precedes its first run start")
    return value


def _validate_catchledger_pack(pack):
    _require_fields_with_optional_window(pack, _PACK_FIELDS, "catchledger pack")
    if pack["format"] != CATCHLEDGER_PACK_FORMAT:
        raise KeeporkillError("the catchledger pack carries the wrong format name")
    _require_name(pack["repo"], "catchledger repository label")
    _require_name(pack["check"], "catchledger check name")
    validate_scorecard(pack["scorecard"])
    if pack["false_block_rate"] != pack["scorecard"]["false_block_rate"]:
        raise KeeporkillError(
            "the catchledger pack false block rate disagrees with its scorecard"
        )
    validate_catch_record(pack["catch_record"])
    validate_normalized_canary(pack["canaryfield_results"])
    if not isinstance(pack["pricing"], dict) or not isinstance(pack["source"], dict):
        raise KeeporkillError("the catchledger pack pricing and source must be objects")
    normalized = dict(pack)
    normalized[HISTORY_WINDOW_FIELD] = validate_history_window(
        pack.get(HISTORY_WINDOW_FIELD)
    )
    return normalized


def read_catchledger_packs(document):
    """Return the catchledger packs a document carries, one per check.

    The document is either a single catchledger pack or a catchledger ledger,
    in which case the packs are derived from the ledger exactly as the
    catchledger contract builds them.
    """

    if not isinstance(document, dict):
        raise KeeporkillError("the catchledger evidence must be an object")
    format_name = document.get("format")
    if format_name == CATCHLEDGER_PACK_FORMAT:
        return [_validate_catchledger_pack(document)]
    if format_name == CATCHLEDGER_LEDGER_FORMAT:
        _require_fields_with_optional_window(document, _LEDGER_FIELDS, "catchledger ledger")
        _require_name(document["repo"], "catchledger repository label")
        if not isinstance(document["checks"], list):
            raise KeeporkillError("the catchledger ledger checks must be a list")
        ledger_window = validate_history_window(document.get(HISTORY_WINDOW_FIELD))
        packs = []
        for entry in document["checks"]:
            _require_exact_fields(entry, _LEDGER_ENTRY_FIELDS, "catchledger ledger entry")
            _require_name(entry["name"], "catchledger check name")
            validate_scorecard(entry["scorecard"])
            validate_catch_record(entry["catch_record"])
            validate_normalized_canary(entry["canaryfield_results"])
            packs.append(
                {
                    "format": CATCHLEDGER_PACK_FORMAT,
                    "repo": document["repo"],
                    "check": entry["name"],
                    "scorecard": entry["scorecard"],
                    "catch_record": entry["catch_record"],
                    "canaryfield_results": entry["canaryfield_results"],
                    "false_block_rate": entry["scorecard"]["false_block_rate"],
                    "pricing": document["pricing"],
                    "source": document["source"],
                    HISTORY_WINDOW_FIELD: ledger_window,
                }
            )
        return packs
    raise KeeporkillError(
        "the catchledger evidence carries an unknown format name"
    )


def validate_canary_document(document):
    """Refuse a malformed canaryfield catch table rather than reading it partially."""

    if not isinstance(document, dict) or set(document) != {"gates", "rows"}:
        raise KeeporkillError("the canaryfield document must carry a gates list and a rows list")
    gates = document["gates"]
    if (
        not isinstance(gates, list)
        or not gates
        or not all(isinstance(gate, str) and gate.strip() for gate in gates)
        or len(set(gates)) != len(gates)
    ):
        raise KeeporkillError("the canaryfield gates must be a list of distinct nonempty names")
    for gate in gates:
        _require_name(gate, "canaryfield gate name")
    if not isinstance(document["rows"], list):
        raise KeeporkillError("the canaryfield rows must be a list")
    seen_seeds = set()
    for row in document["rows"]:
        if not isinstance(row, dict):
            raise KeeporkillError("a canaryfield row must be an object")
        for field in ("seed", "name", "defect_class"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise KeeporkillError(f"a canaryfield row needs a nonempty {field}")
        if row["seed"] in seen_seeds:
            raise KeeporkillError("the canaryfield document repeats a seed")
        seen_seeds.add(row["seed"])
        row_gates = row.get("gates")
        if not isinstance(row_gates, dict) or set(row_gates) != set(gates):
            raise KeeporkillError("a canaryfield row must carry a result for each gate")
        for result in row_gates.values():
            if result not in RESULT_WORDS:
                raise KeeporkillError("a canaryfield result word is not a known result word")
        planted_files = row.get("planted_files")
        if planted_files is not None and (
            not isinstance(planted_files, list)
            or not all(isinstance(path, str) for path in planted_files)
        ):
            raise KeeporkillError("a canaryfield row carries malformed planted files")
        planted_file = row.get("planted_file")
        if planted_file is not None and not isinstance(planted_file, str):
            raise KeeporkillError("a canaryfield row carries a malformed planted file")
    return document


def normalize_canary_document(document, check):
    """Return normalized canaryfield evidence for one exact check name, or None."""

    if document is None:
        return None
    validate_canary_document(document)
    if check not in document["gates"]:
        return None
    counts = {word: 0 for word in RESULT_WORDS}
    results = []
    for row in document["rows"]:
        result = row["gates"][check]
        counts[result] += 1
        planted_files = row.get("planted_files")
        if isinstance(planted_files, list):
            normalized_files = list(planted_files)
        elif isinstance(row.get("planted_file"), str):
            normalized_files = [row["planted_file"]]
        elif row.get("planted_file") is None and planted_files is None:
            normalized_files = []
        else:
            raise KeeporkillError("a canaryfield row carries malformed planted files")
        results.append(
            {
                "seed": row["seed"],
                "name": row["name"],
                "defect_class": row["defect_class"],
                "result": result,
                "planted_files": normalized_files,
            }
        )
    results.sort(key=lambda item: item["seed"])
    return {
        "source_format": CANARY_SOURCE_FORMAT,
        "gate": check,
        "counts": counts,
        "results": results,
    }


def read_blindness_traces(document):
    """Return the blindness traces a document carries, grouped by check name."""

    if not isinstance(document, dict) or set(document) != {"format", "traces"}:
        raise KeeporkillError("the blindness evidence must carry a format name and a traces list")
    if document["format"] != BLINDNESS_FORMAT:
        raise KeeporkillError("the blindness evidence carries the wrong format name")
    if not isinstance(document["traces"], list):
        raise KeeporkillError("the blindness traces must be a list")
    traces_by_check = {}
    for trace in document["traces"]:
        _require_exact_fields(trace, _BLINDNESS_TRACE_FIELDS, "blindness trace")
        _require_name(trace["check"], "blindness trace check")
        for field in ("surface", "observation", "detail"):
            _require_text(trace[field], f"blindness trace {field}")
        traces_by_check.setdefault(trace["check"], []).append(trace)
    return traces_by_check
