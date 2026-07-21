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

#: API-1b (OQ-W9C-5): the closure-discipline teeth — a decision record whose slice is marked DONE in
#: the roadmap must NOT still read "DRAFT for ratification" in its Status cell (the API-1-class miss
#: that recurred at FIVE consecutive wave closes). Filename-keyed + row-anchored so it does NOT
#: false-fail when a slice-id appears only in another row's PROSE (the verifier's CLAIM-6 trap:
#: "API-1b" occurs inside two `✅ **DONE**` rows), nor false-fail an in-flight planning DRAFT (whose
#: own roadmap row is not yet DONE). SCOPE (review finding B1): this guards the GO-FORWARD cadence —
#: any slice whose roadmap row leads with `**SLICE — …** ✅ **DONE**`. Pre-cadence rows without that
#: exact shape (or records with no `| **Status** |` cell — the old records that never had a Status
#: line and so cannot be "DRAFT") are out of scope; broadening is a future hygiene option, not a
#: silent guarantee.
BACKLOG_DIR = "10_delivery_backlog"
ROADMAP = "10_delivery_backlog/delivery_roadmap.md"
_DONE_MARK = "✅ **DONE**"
_DRAFT_MARK = "DRAFT for ratification"
#: The FIRST bold token on a line = that row's own slice-id (row-anchored; upper-cased to match).
_LEAD_SLICE = re.compile(r"\*\*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)")


def _done_slice_ids(roadmap_text: str) -> set[str]:
    """The slice-ids marked ``✅ **DONE**`` in the roadmap, keyed on each row's OWN leading bold
    title token (never a whole-line substring — a slice-id in prose is not counted)."""
    done: set[str] = set()
    for line in roadmap_text.splitlines():
        if _DONE_MARK in line:
            m = _LEAD_SLICE.search(line)
            if m:
                done.add(m.group(1).upper())
    return done


def _status_lines(record_text: str) -> list[str]:
    """The record's actual Status table row(s) — the line must START WITH the table-row pattern, not
    merely CONTAIN it, so prose that quotes/describes a Status line (as this very record's own OD-
    API-1b-E does) is not mistaken for one."""
    return [ln for ln in record_text.splitlines() if ln.strip().startswith("| **Status** |")]


def _is_unstamped_shipped(slice_id: str, status_lines: list[str], done: set[str]) -> bool:
    """The rule's TEETH (pure, unit-tested): a record is an unstamped-shipped miss iff its slice is
    DONE in the roadmap AND its Status cell still reads "DRAFT for ratification"."""
    return slice_id in done and any(_DRAFT_MARK in ln for ln in status_lines)


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
                f"{record.name}: slice {slice_id} is DONE in the roadmap but its Status cell still "
                f"reads '{_DRAFT_MARK}' — stamp it CLOSED (the OQ-W9C-5 closure-discipline rule)"
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
