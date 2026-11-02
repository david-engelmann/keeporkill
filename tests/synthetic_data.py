"""Synthetic evidence builders shared by the keeporkill tests.

Every fixture here is invented for this repo. No real check names, no real
traces, and no network anywhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

BASE_TIME = datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)

_EVIDENCE_BY_OUTCOME = {
    "catch": {
        "type": "flagged_fix_then_success",
        "fix_commits": ["f" * 40],
        "validating_run_id": "900",
        "reason": None,
    },
    "false_block": {
        "type": "same_commit_success_after_block",
        "fix_commits": [],
        "validating_run_id": "901",
        "reason": None,
    },
    "unattributed": {
        "type": "none",
        "fix_commits": [],
        "validating_run_id": None,
        "reason": "no_later_outcome",
    },
}


def make_catch_record(days=14, outcomes=("catch", "false_block", "unattributed")):
    """One catch record entry per day on distinct consecutive UTC dates."""

    entries = []
    for index in range(days):
        moment = BASE_TIME + timedelta(days=index, minutes=index)
        outcome = outcomes[index % len(outcomes)]
        entries.append(
            {
                "block_run_id": str(100 + index),
                "blocked_commit": format(index + 1, "040x"),
                "started_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "outcome": outcome,
                "flagged_paths": ["src/synthetic.py"],
                "evidence": dict(_EVIDENCE_BY_OUTCOME[outcome]),
            }
        )
    return entries


def make_scorecard(**overrides):
    scorecard = {
        "fires": 40,
        "blocks": 6,
        "judged_commits": 20,
        "flaky_commits": 1,
        "flake_rate": 0.05,
        "runtime_seconds": 900,
        "runtime_minutes": 15.0,
        "catches": 3,
        "false_blocks": 1,
        "unattributed_blocks": 2,
        "false_block_rate": 0.166667,
        "total_cost_usd": 0.12,
        "cost_per_catch_usd": 0.04,
    }
    scorecard.update(overrides)
    return scorecard


def make_embedded_canary(gate="unit checks", words=()):
    counts = {"caught": 0, "waved-through": 0, "not-applicable": 0, "gate-broken": 0}
    results = []
    for index, word in enumerate(words):
        counts[word] += 1
        results.append(
            {
                "seed": f"seed-{index:02d}",
                "name": f"synthetic defect {index}",
                "defect_class": "synthetic class",
                "result": word,
                "planted_files": ["src/synthetic.py"],
            }
        )
    return {
        "source_format": "canaryfield-catch-table",
        "gate": gate,
        "counts": counts,
        "results": results,
    }


def make_window(window_days):
    """A history window record spanning the given number of calendar days."""

    first = BASE_TIME
    last = BASE_TIME + timedelta(days=window_days - 1, hours=23, minutes=40)
    return {
        "first_run_started_at": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run_updated_at": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def make_cl_pack(
    check="unit checks",
    days=14,
    window_days=14,
    scorecard=None,
    canaryfield_results=None,
    repo="synthetic-repo",
):
    scorecard = make_scorecard() if scorecard is None else scorecard
    pack = {
        "format": "catchledger-pack/1",
        "repo": repo,
        "check": check,
        "scorecard": scorecard,
        "catch_record": make_catch_record(days=days),
        "canaryfield_results": canaryfield_results,
        "false_block_rate": scorecard["false_block_rate"],
        "pricing": {"currency": "USD", "cost_per_minute": "0.008"},
        "source": {
            "ci_history_sha256": "a" * 64,
            "git_history_sha256": "b" * 64,
            "canaryfield_results_sha256": "c" * 64 if canaryfield_results else None,
        },
    }
    if window_days == "absent":
        pass
    elif window_days is None:
        pack["history_window"] = None
    else:
        pack["history_window"] = make_window(window_days)
    return pack


def make_ledger(cl_packs):
    entries = []
    for index, pack in enumerate(
        sorted(cl_packs, key=lambda item: item["check"]), start=1
    ):
        entries.append(
            {
                "name": pack["check"],
                "scorecard": pack["scorecard"],
                "catch_record": pack["catch_record"],
                "canaryfield_results": pack["canaryfield_results"],
                "evidence_pack_file": f"{index:03d}-pack.json",
            }
        )
    first = cl_packs[0]
    ledger = {
        "format": "catchledger-ledger/1",
        "repo": first["repo"],
        "pricing": first["pricing"],
        "source": first["source"],
        "checks": entries,
        "totals": {},
    }
    if "history_window" in first:
        ledger["history_window"] = first["history_window"]
    return ledger


def make_canary_document(gate_words):
    """Build a catch table from a mapping of gate name to a list of result words."""

    gates = sorted(gate_words)
    longest = max((len(words) for words in gate_words.values()), default=0)
    rows = []
    for index in range(longest):
        row_gates = {}
        for gate in gates:
            words = gate_words[gate]
            row_gates[gate] = words[index] if index < len(words) else "not-applicable"
        rows.append(
            {
                "seed": f"seed-{index:02d}",
                "name": f"synthetic defect {index}",
                "defect_class": "synthetic class",
                "planted_file": "src/synthetic.py",
                "planted_files": ["src/synthetic.py"],
                "gates": row_gates,
            }
        )
    return {"gates": gates, "rows": rows}


def make_blindness_document(traces):
    return {"format": "blindgate-evidence/1", "traces": traces}


def make_trace(check, surface="settings file", observation="read", detail="synthetic trace"):
    return {
        "check": check,
        "surface": surface,
        "observation": observation,
        "detail": detail,
    }


AT_FLOOR_WORDS = ["caught"] * 20 + ["waved-through"] * 6 + ["gate-broken"] * 4


def at_floor_pack(blindness_document=None):
    """Assemble the single pack for a check standing exactly at the floor."""

    from keeporkill.packs import assemble_packs

    words = AT_FLOOR_WORDS + ["not-applicable"] * 3
    document = make_canary_document({"unit checks": words})
    packs = assemble_packs([make_cl_pack(days=14)], document, blindness_document)
    return next(iter(packs.values()))


def pack_with(scored_words, days, blindness_document=None):
    """Assemble one pack with the given canary words and own history span.

    The catchledger history window is deliberately forty days for every
    pack built here, so a floor reading taken from that global window
    cannot agree with the per check catch record span these packs carry.
    """

    from keeporkill.packs import assemble_packs

    document = make_canary_document({"unit checks": list(scored_words)})
    packs = assemble_packs(
        [make_cl_pack(days=days, window_days=40)],
        document,
        blindness_document,
    )
    return next(iter(packs.values()))
