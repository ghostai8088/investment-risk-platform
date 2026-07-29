#!/usr/bin/env python3
"""Documentation-consistency check (placeholder, build-rule aligned).

Verifies that:
  1. Each code package/app has a README.md.
  2. The ratified governance standards carry a "Document Control" section.

Exits non-zero on failure so CI blocks, preventing code/doc drift. This is a
placeholder to be extended (e.g., code-change -> required doc-change checks).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The closure-discipline teeth (API-1b OQ-W9C-5, BROADENED at the Wave-10 close OQ-W10C): a
#: record whose slice is marked DONE in the roadmap must have its Status cell stamped CLOSED — NOT
#: left at any pre-close stamp ("DRAFT for ratification" / "RATIFIED" / "pending ratification"). The
#: class recurred at SIX consecutive closes; the pre-Wave-10 teeth had TWO blind spots the sixth
#: (PPF-3) slipped through: they matched only the literal "DRAFT for ratification" (PPF-3 sat at
#: "RATIFIED"), and the done-set keyed only on the leading `✅ **DONE**` row shape (the PPF arc row
#: marks each slice INLINE as `✅ **PPF-N**`, so all three arc slices were invisible). Both are now
#: covered. Filename-keyed + row-anchored so it does NOT false-fail when a slice-id appears only in
#: another row's PROSE (the verifier's CLAIM-6 trap: "API-1b" occurs inside two `✅ **DONE**` rows),
#: nor an in-flight planning DRAFT whose own roadmap row is not yet DONE. BROADENED AGAIN at the
#: Wave-12 close: the `**Status:**` PROSE shape (CAD-1/OPS-1's record form) is recognized alongside
#: the `| **Status** |` table row — the table-only matcher had silently exempted both newest
#: records. Records with NEITHER shape (old pre-cadence records) stay out of scope.
BACKLOG_DIR = "10_delivery_backlog"
ROADMAP = "10_delivery_backlog/delivery_roadmap.md"
_DONE_MARK = "✅ **DONE**"
_CLOSED_MARK = "CLOSED"  # the required TERMINAL Status stamp for a shipped slice
#: A bold slice-id token: `**API-1**`, `**PPF-3**`, … (row-anchored; upper-cased to match).
_LEAD_SLICE = re.compile(r"\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
#: A ✅-ADJACENT bold slice token: the arc row marks each slice INLINE (`✅ **PPF-1**`), not with
#: the leading `✅ **DONE**` row shape — Wave-10's PPF arc exposed this blind spot (OQ-W10C).
_TICK_SLICE = re.compile(r"✅\s*\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
#: Wave-13 close: the tick INSIDE the bold — `**✅ SR-1 — … DONE …**`. SR-1 and OPS-H1 both used
#: this shape and were therefore absent from the done-set entirely, so the gate could not have
#: flagged them however they were stamped.
_BOLD_TICK_SLICE = re.compile(r"\*\*\s*✅\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")


def _done_slice_ids(roadmap_text: str) -> set[str]:
    """The slice-ids marked done in the roadmap. Two shapes are recognized (the Wave-10 broadening,
    OQ-W10C): a normal row's leading bold title on a ``✅ **DONE**`` line, AND every ✅-adjacent
    bold token on any ``DONE`` line (the arc row's inline ``✅ **PPF-1**`` shape). Extra non-slice
    tokens (DONE/ALL) never match a decision-record filename, so they cannot false-flag."""
    done: set[str] = set()
    for line in roadmap_text.splitlines():
        if "✅" not in line or "DONE" not in line.upper():
            continue
        if _DONE_MARK in line:  # a normal `… **SLICE …** ✅ **DONE** …` row → leading title token
            m = _LEAD_SLICE.search(line)
            if m:
                done.add(m.group(1).upper())
        for m in _TICK_SLICE.finditer(line):  # arc-style inline `✅ **SLICE**` marks
            done.add(m.group(1).upper())
        # Wave-13 close fold: the tick INSIDE the bold — `**✅ SR-1 — … DONE + CLOSED …**`. Both
        # SR-1 and OPS-H1 wrote their roadmap rows this way, so neither slice was in the done-set
        # at all and neither could ever be flagged. `_TICK_SLICE` requires `✅` followed by `**`,
        # which is exactly inverted for this shape.
        for m in _BOLD_TICK_SLICE.finditer(line):
            done.add(m.group(1).upper())
    return done


#: Wave-13 close: the Status key with ANY emphasis — `| Status |`, `| **Status** |`, `| *Status* |`
#: — plus the prose `**Status:**` / `Status:` forms. Anchored, so prose merely QUOTING a Status line
#: is still not mistaken for one (the API-1b OD-API-1b-E case the anchoring was added for).
_STATUS_ROW = re.compile(r"^\|\s*\*{0,2}_?\s*Status\s*_?\*{0,2}\s*\|", re.IGNORECASE)
_STATUS_PROSE = re.compile(r"^\*{0,2}Status\*{0,2}\s*:", re.IGNORECASE)


def _status_lines(record_text: str) -> list[str]:
    """The record's actual Status line(s).

    **Wave-13 close fold — this matcher was the reason the gate saw NOTHING.** It recognized only
    the BOLDED table key ``| **Status** |`` and the prose ``**Status:**``. Every Wave-13 record
    writes the key UNBOLDED (``| Status |``), so ``_status_lines`` returned an empty list for all
    five, ``_is_unstamped_shipped`` short-circuited on ``not status_lines``, and the gate reported
    clean while FE-M1 actually shipped with its Status cell reading ``RATIFIED … Implementation
    next``. Measured at the close: 20 roadmap-DONE records were invisible to the gate this way.

    That is the SEVENTH recurrence of the closure-discipline class and the THIRD time the fix has
    been "broaden the matcher" (OQ-W9C-5 → OQ-W10C → Wave-12 close → here). Broadening alone has
    now failed three times because each broadening is only as good as the shapes someone thought to
    enumerate, so this fold also adds a NON-VACUITY FLOOR (see ``_closure_stamp_errors``): if the
    gate's in-scope population ever collapses again, the floor fails loudly instead of the gate
    silently guarding nothing.

    Each pattern is ANCHORED — prose that quotes or describes a Status line (as API-1b's own
    OD-API-1b-E does) must still not be mistaken for one.
    """
    return [
        ln
        for ln in record_text.splitlines()
        if _STATUS_ROW.match(ln.strip()) or _STATUS_PROSE.match(ln.strip())
    ]


def _is_unstamped_shipped(slice_id: str, status_lines: list[str], done: set[str]) -> bool:
    """The rule's TEETH (pure, unit-tested): a record is an unstamped-shipped miss iff its slice is
    DONE in the roadmap AND it HAS a Status cell NOT yet stamped CLOSED — catching a record stuck at
    ANY pre-close stamp (``DRAFT for ratification`` / ``RATIFIED`` / ``pending ratification``), not
    just the one literal the pre-Wave-10 gate matched (OQ-W10C: the class recurred a 6th time —
    PPF-3 sat at "RATIFIED", past the old teeth). Records with no Status cell stay out of scope."""
    if slice_id not in done or not status_lines:
        return False
    return not any(_CLOSED_MARK in ln for ln in status_lines)


#: Wave-13 close — the NON-VACUITY FLOORS. Measured at the fold: 61 records carry a recognized
#: Status line and 45 slice-ids are in the roadmap done-set. The floors sit deliberately BELOW the
#: measured values (records are only ever added) and exist to fail LOUDLY if a future shape drift
#: silently shrinks the gate's population again — which is exactly how this control reported clean
#: while guarding nothing for an entire wave. `test_ci_pg_coverage.py` uses the same pattern.
#:
#: The lesson these encode: three consecutive fixes to this gate were "broaden the matcher", and a
#: matcher is only as good as the shapes someone thought to enumerate. A floor does not need to
#: anticipate the next shape — it only needs to notice that coverage fell.
_MIN_RECORDS_WITH_STATUS = 50
_MIN_DONE_SLICES = 38

#: Decision records whose Status line the matcher does NOT recognize, enumerated EXACTLY.
#:
#: Added at REF-1 after the closure-stamp class recurred an EIGHTH time — in the REF-1 planning
#: record itself, whose status sat inside a blockquote so neither ``_STATUS_ROW`` nor
#: ``_STATUS_PROSE`` anchored after stripping. The two count floors above could never have caught
#: it: 61 of 62 records still had a recognized status, comfortably above the floor of 50. A MINIMUM
#: is blind to one record going dark; only an EXACT set is not.
#:
#: This is a grandfather list, not an allowlist to grow. A NEW record that the matcher cannot see
#: fails the gate by name. Removing entries (by giving those records a recognized Status line) is
#: always welcome; adding one requires explaining why a record may be invisible to the gate that
#: exists to read it.
_RECORDS_WITHOUT_RECOGNIZED_STATUS: frozenset[str] = frozenset(
    {
        "bt_1_decision_record.md",
        "md_h1_decision_record.md",
        "p3_6_decision_record.md",
        "pa_0_decision_record.md",
        "pa_1_decision_record.md",
        "pa_2_decision_record.md",
        "pa_3_decision_record.md",
        "pa_4_decision_record.md",
        "rd_1_decision_record.md",
        "rd_2_decision_record.md",
        "rd_3_decision_record.md",
    }
)


def _closure_stamp_errors() -> list[str]:
    roadmap_path = ROOT / ROADMAP
    if not roadmap_path.is_file():
        return [f"missing roadmap: {ROADMAP}"]
    done = _done_slice_ids(roadmap_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    with_status = 0
    for record in sorted((ROOT / BACKLOG_DIR).glob("*_decision_record.md")):
        slice_id = record.name.removesuffix("_decision_record.md").replace("_", "-").upper()
        status_lines = _status_lines(record.read_text(encoding="utf-8"))
        if status_lines:
            with_status += 1
        elif record.name not in _RECORDS_WITHOUT_RECOGNIZED_STATUS:
            errors.append(
                f"{record.name}: no Status line the closure-stamp gate can SEE. The gate "
                f"short-circuits on records it cannot read, so this record would ship unstamped "
                f"with the gate green (the eighth recurrence of that class, found at REF-1). "
                f"Use a `| Status | ... |` table row or an unprefixed `**Status:** ...` line — a "
                f"blockquote-prefixed status does not anchor."
            )
        if _is_unstamped_shipped(slice_id, status_lines, done):
            errors.append(
                f"{record.name}: slice {slice_id} is DONE in the roadmap but its Status cell is "
                f"not stamped CLOSED (the OQ-W9C-5 / OQ-W10C closure-discipline rule)"
            )
    if with_status < _MIN_RECORDS_WITH_STATUS:
        errors.append(
            f"closure-stamp gate NON-VACUITY: only {with_status} decision records have a "
            f"recognized Status line (floor {_MIN_RECORDS_WITH_STATUS}). The gate's matcher has "
            f"lost coverage — fix _status_lines rather than lowering this floor."
        )
    if len(done) < _MIN_DONE_SLICES:
        errors.append(
            f"closure-stamp gate NON-VACUITY: only {len(done)} slice-ids parsed from the roadmap "
            f"done-set (floor {_MIN_DONE_SLICES}). Fix _done_slice_ids rather than the floor."
        )
    return errors


PACKAGE_DIRS = [
    "apps/backend",
    "apps/frontend",
    "apps/worker",
    "packages/shared-python",
    "packages/shared-ts",
]

STANDARDS_REQUIRING_DOC_CONTROL = [
    "00_ai_operating_model/reconciled_agent_role_registry.md",
    "01_product_strategy/regulatory_product_scope.md",
    "03_architecture/architecture_baseline.md",
    "03_architecture/foundational_adrs.md",
    "03_architecture/foundation_slice.md",
    "04_data_model/canonical_data_model_standard.md",
    "04_data_model/temporal_reproducibility_standard.md",
    "04_data_model/audit_event_taxonomy.md",
    "05_analytics_methodologies/numerical_quant_standards.md",
    "06_security/entitlement_sod_model.md",
    "06_security/threat_model_initial.md",
    "07_model_governance/model_governance_independence_policy.md",
    "08_testing_qa/ci_enforcement_overview.md",
    "09_compliance_controls/control_matrix_skeleton.md",
]


def main() -> int:
    errors: list[str] = []

    for pkg in PACKAGE_DIRS:
        if not (ROOT / pkg / "README.md").is_file():
            errors.append(f"missing README.md in {pkg}")

    for doc in STANDARDS_REQUIRING_DOC_CONTROL:
        path = ROOT / doc
        if not path.is_file():
            errors.append(f"missing governance doc: {doc}")
        elif "Document Control" not in path.read_text(encoding="utf-8"):
            errors.append(f"missing Document Control header: {doc}")

    errors.extend(_closure_stamp_errors())

    if errors:
        print("Documentation check FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Documentation check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
