"""The ruling generator. It writes local artifacts only and deletes nothing."""

from __future__ import annotations

import re
from datetime import date, datetime

from .errors import FloorRefusal, TameshiError
from .ingest import (
    validate_catch_record,
    validate_history_window,
    validate_scorecard,
)
from .names import slugify_check
from .packs import PACK_FORMAT, floor_accounting, validate_canary_performance

RULING_FORMAT = "tameshi-ruling/1"

# The slice ruling set maps the caller's word to the verdict word the record
# carries and the lifecycle state the ruling puts the check in. Kill is not in
# the set in this slice.
RULINGS = {
    "keep": ("keep", "required"),
    "demote": ("demote-to-advisory", "advisory"),
    "quarantine": ("quarantine", "quarantined"),
}

_PACK_FIELDS = {
    "format",
    "repo",
    "check",
    "scorecard",
    "catch_record",
    "history_window",
    "false_block_rate",
    "cost_per_catch_usd",
    "canary_performance",
    "blindness_traces",
    "floor",
    "below_floor",
    "sources",
}


def ruling_slug(check):
    return slugify_check(check)


def _validate_pack_name(value, label):
    if not isinstance(value, str) or not value.strip():
        raise TameshiError(f"the evidence pack needs a {label}")
    if "\n" in value or "\r" in value:
        raise TameshiError(f"the evidence pack {label} must not carry a newline")


def _validate_pack(pack):
    if not isinstance(pack, dict):
        raise TameshiError("an evidence pack must be an object")
    if set(pack) != _PACK_FIELDS:
        raise TameshiError("the evidence pack has the wrong fields")
    if pack["format"] != PACK_FORMAT:
        raise TameshiError("the evidence pack carries the wrong format name")
    _validate_pack_name(pack["repo"], "repository label")
    _validate_pack_name(pack["check"], "check name")
    validate_scorecard(pack["scorecard"])
    validate_catch_record(pack["catch_record"])
    validate_history_window(pack["history_window"])
    if pack["false_block_rate"] != pack["scorecard"]["false_block_rate"]:
        raise TameshiError(
            "the evidence pack false block rate disagrees with its scorecard"
        )
    if pack["cost_per_catch_usd"] != pack["scorecard"]["cost_per_catch_usd"]:
        raise TameshiError(
            "the evidence pack cost per catch disagrees with its scorecard"
        )
    validate_canary_performance(pack["canary_performance"])
    if not isinstance(pack["blindness_traces"], list):
        raise TameshiError("the evidence pack blindness traces must be a list")
    if not isinstance(pack["floor"], dict):
        raise TameshiError("the evidence pack floor accounting must be an object")
    if not isinstance(pack["below_floor"], bool):
        raise TameshiError("the evidence pack below floor mark must be a boolean")
    if not isinstance(pack["sources"], dict):
        raise TameshiError("the evidence pack sources record must be an object")


def _floor_refusal(check, accounting):
    legs = []
    if accounting["canary_shortfall"] > 0:
        legs.append(
            "the canary evidence leg holds "
            f"{accounting['canary_defects']} of {accounting['required_canary_defects']} "
            "required scored planted defects and falls short by "
            f"{accounting['canary_shortfall']}"
        )
    if accounting["ci_history_shortfall"] > 0:
        legs.append(
            "the CI history leg holds "
            f"{accounting['ci_history_days']} of {accounting['required_ci_history_days']} "
            "required days and falls short by "
            f"{accounting['ci_history_shortfall']}"
        )
    return FloorRefusal(
        f"ruling refused for check {check} because the evidence is below the floor. "
        + " And ".join(legs)
        + "."
    )


def _number(value):
    if value is None:
        return "none"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def render_body(pack, record):
    """Render the ruling pull request body. Every number is read from the pack."""

    scorecard = pack["scorecard"]
    performance = pack["canary_performance"]
    accounting = pack["floor"]
    counts = performance["counts"] if performance is not None else None
    rows = [
        ("Repository", pack["repo"]),
        ("Check", pack["check"]),
        ("Ruling", record["ruling"]),
        ("State after ruling", record["state_after_ruling"]),
    ]
    if record["expiry"] is not None:
        rows.append(("Expiry", record["expiry"]))
    rows.extend(
        [
            ("Fires", _number(scorecard["fires"])),
            ("Blocks", _number(scorecard["blocks"])),
            ("Catches", _number(scorecard["catches"])),
            ("False blocks", _number(scorecard["false_blocks"])),
            ("Unattributed blocks", _number(scorecard["unattributed_blocks"])),
            ("False block rate", _number(pack["false_block_rate"])),
            ("Runtime seconds", _number(scorecard["runtime_seconds"])),
            ("Total cost USD", _number(scorecard["total_cost_usd"])),
            ("Cost per catch USD", _number(pack["cost_per_catch_usd"])),
            ("Canary scored defects", _number(performance["scored"]) if performance else "none"),
            ("Canary caught", _number(counts["caught"]) if counts else "none"),
            ("Canary waved through", _number(counts["waved-through"]) if counts else "none"),
            ("Canary gate broken", _number(counts["gate-broken"]) if counts else "none"),
            ("Canary not applicable", _number(counts["not-applicable"]) if counts else "none"),
            ("Canary catch rate", _number(performance["catch_rate"]) if performance else "none"),
            ("Canary defects held", _number(accounting["canary_defects"])),
            ("Canary defects required", _number(accounting["required_canary_defects"])),
            ("CI history days held", _number(accounting["ci_history_days"])),
            ("CI history days required", _number(accounting["required_ci_history_days"])),
            ("Blindness traces", _number(len(pack["blindness_traces"]))),
        ]
    )
    lines = [
        f"# Ruling for {pack['check']}",
        "",
        "The evidence pack for this check has been assembled and stands at or above "
        "the evidence floor on both legs. The ruling below is issued from that pack "
        "and every number in the receipts is read from it.",
        "",
        "This ruling is unsigned. A human signs it outside the tool before the "
        "pull request is submitted, and nothing is deleted by this ruling.",
        "",
        "| Evidence | Value |",
        "| --- | --- |",
    ]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    lines.append("")
    return "\n".join(lines) + "\n"


_HYPHENATED_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _calendar_date(value, label):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not _HYPHENATED_DATE.match(value):
        raise TameshiError(f"the {label} must be an ISO calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TameshiError(f"the {label} must be an ISO calendar date") from exc


def _current_date(today):
    if today is None:
        return date.today()
    return _calendar_date(today, "current date")


def generate_ruling(pack, ruling, expiry=None, today=None):
    """Generate the ruling record and body for a pack, or refuse.

    The generator recomputes the floor accounting from the pack's own canary
    performance rows and counts and from its catch record timestamps before
    honouring the pack's recorded accounting, refuses below the floor, and
    emits an unsigned record only. The current date is learned from the
    supplied today value when one stands and from the system date otherwise.
    """

    _validate_pack(pack)
    if ruling == "kill":
        raise TameshiError(
            "kill is outside the ruling set in this slice and waits for its own later rule"
        )
    if ruling not in RULINGS:
        raise TameshiError(f"an unknown ruling was requested ({ruling})")
    if ruling == "quarantine":
        if expiry is None:
            raise TameshiError("a quarantine ruling requires an expiry date")
        expiry_date = _calendar_date(expiry, "expiry")
        if expiry_date < _current_date(today):
            raise TameshiError("a quarantine expiry must not precede the current date")
    elif expiry is not None:
        raise TameshiError("an expiry date stands only on a quarantine ruling")
    recomputed = floor_accounting(pack["canary_performance"], pack["catch_record"])
    if pack["floor"] != recomputed:
        raise TameshiError(
            "the pack floor accounting disagrees with the accounting recomputed "
            "from the pack evidence"
        )
    if not recomputed["meets_floor"]:
        raise _floor_refusal(pack["check"], recomputed)
    verdict, state = RULINGS[ruling]
    record = {
        "format": RULING_FORMAT,
        "repo": pack["repo"],
        "check": pack["check"],
        "ruling": verdict,
        "state_after_ruling": state,
        "expiry": expiry,
        "floor": pack["floor"],
        "signature": {"status": "unsigned", "signed_by": None, "signed_at": None},
    }
    return record, render_body(pack, record)
