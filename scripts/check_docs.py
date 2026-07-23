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
#: nor an in-flight planning DRAFT whose own roadmap row is not yet DONE. Records with no
#: `| **Status** |` cell (old records that never had one) stay out of scope.
BACKLOG_DIR = "10_delivery_backlog"
ROADMAP = "10_delivery_backlog/delivery_roadmap.md"
_DONE_MARK = "✅ **DONE**"
_CLOSED_MARK = "CLOSED"  # the required TERMINAL Status stamp for a shipped slice
#: A bold slice-id token: `**API-1**`, `**PPF-3**`, … (row-anchored; upper-cased to match).
_LEAD_SLICE = re.compile(r"\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")
#: A ✅-ADJACENT bold slice token: the arc row marks each slice INLINE (`✅ **PPF-1**`), not with
#: the leading `✅ **DONE**` row shape — Wave-10's PPF arc exposed this blind spot (OQ-W10C).
_TICK_SLICE = re.compile(r"✅\s*\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")


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
    return done


def _status_lines(record_text: str) -> list[str]:
    """The record's actual Status table row(s) — the line must START WITH the table-row pattern, not
    merely CONTAIN it, so prose that quotes/describes a Status line (as this very record's own OD-
    API-1b-E does) is not mistaken for one."""
    return [ln for ln in record_text.splitlines() if ln.strip().startswith("| **Status** |")]


def _is_unstamped_shipped(slice_id: str, status_lines: list[str], done: set[str]) -> bool:
    """The rule's TEETH (pure, unit-tested): a record is an unstamped-shipped miss iff its slice is
    DONE in the roadmap AND it HAS a Status cell NOT yet stamped CLOSED — catching a record stuck at
    ANY pre-close stamp (``DRAFT for ratification`` / ``RATIFIED`` / ``pending ratification``), not
    just the one literal the pre-Wave-10 gate matched (OQ-W10C: the class recurred a 6th time —
    PPF-3 sat at "RATIFIED", past the old teeth). Records with no Status cell stay out of scope."""
    if slice_id not in done or not status_lines:
        return False
    return not any(_CLOSED_MARK in ln for ln in status_lines)


def _closure_stamp_errors() -> list[str]:
    roadmap_path = ROOT / ROADMAP
    if not roadmap_path.is_file():
        return [f"missing roadmap: {ROADMAP}"]
    done = _done_slice_ids(roadmap_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for record in sorted((ROOT / BACKLOG_DIR).glob("*_decision_record.md")):
        slice_id = record.name.removesuffix("_decision_record.md").replace("_", "-").upper()
        status_lines = _status_lines(record.read_text(encoding="utf-8"))
        if _is_unstamped_shipped(slice_id, status_lines, done):
            errors.append(
                f"{record.name}: slice {slice_id} is DONE in the roadmap but its Status cell is "
                f"not stamped CLOSED (the OQ-W9C-5 / OQ-W10C closure-discipline rule)"
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
