#!/usr/bin/env python3
"""Documentation-consistency check (placeholder, build-rule aligned).

Verifies that:
  1. Each code package/app has a README.md.
  2. The ratified governance standards carry a "Document Control" section.

Exits non-zero on failure so CI blocks, preventing code/doc drift. This is a
placeholder to be extended (e.g., code-change -> required doc-change checks).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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

    if errors:
        print("Documentation check FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("Documentation check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
