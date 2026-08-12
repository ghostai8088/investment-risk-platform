#!/usr/bin/env python3
"""Capability coverage gate — does every capability the STRATEGY commits to have a requirement?

**Why this exists, and why its input is deliberately not a document Claude generated.**

Eight weeks of delivery drifted from the product's stated intent, and every audit run in that time
missed it for one structural reason: each audit compared code against requirements, or records
against code, and the requirement register was the reference point in all of them. An audit whose
yardstick is the artifact that carries the gap cannot see the gap.

So this gate's inputs are the two documents the OWNER wrote and owns:

  * ``01_product_strategy/capability_map.md``      — the CAP-nn / nn.m capability tree
  * ``01_product_strategy/regulatory_product_scope.md`` — the SCOPE-nn commitments

and it asks one question of each leaf: **is there a requirement behind it?**

Measured at the moment of writing: SCOPE-01..05 — including SCOPE-02's "public and private, both
first-class" — are cited in exactly ONE file, their own. Nothing downstream speaks that vocabulary,
so a commitment could be made and never converted with nothing registering the gap.

**Ratchet, not a wall.** The known gaps are recorded in a baseline file, visibly and by name. The
gate fails when a NEW uncovered capability appears, or when the baseline is edited to hide one
rather than to pay it. The gaps can shrink without touching this file; they cannot grow quietly.
That is deliberate: a gate that goes red on day one and blocks a security fix gets switched off,
and this project has already learned that a control everyone routes around is worse than no control.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The AUTHORITATIVE capability taxonomy. `capability_map.md` says so in its own header — "the
#: authoritative capability taxonomy is requirements_backbone.md §4 (CAP-1 … CAP-19) … where this
#: map and the backbone differ, the backbone governs" — so §4 is the declaration and the map is the
#: business view. The gate reads the declaration.
CAPABILITY_MAP = "02_requirements/requirements_backbone.md"
SCOPE_DOC = "01_product_strategy/regulatory_product_scope.md"
BACKBONE = "02_requirements/requirements_backbone.md"
RTM = "02_requirements/requirements_traceability_matrix.md"
BASELINE = "02_requirements/capability_coverage_baseline.json"

#: A leaf capability inside a capability-map table cell: "14.3 Lineage query/visualization".
#: The map writes several per cell separated by "·", so this matches the ID and its label.
_LEAF = re.compile(r"\b(\d{1,2}\.\d{1,2}[a-z]?)\s+([A-Za-z][^·|]*)")
#: The backbone's Cap column. A row may serve SEVERAL leaves and writes them "12.1/12.2" — the
#: first version of this matcher accepted only a cell holding exactly one id and therefore reported
#: model inventory, audit capture and RBAC as uncovered when all three have requirements. Checked in
#: the opposite direction before being trusted, which is the only reason it was caught.
_CAP_CELL = re.compile(
    r"\|\s*((?:\d{1,2}\.\d{1,2}[a-z]?)(?:\s*[/,]\s*\d{1,2}\.\d{1,2}[a-z]?)*)\s*\|"
)
_LEAF_ID = re.compile(r"\d{1,2}\.\d{1,2}[a-z]?")
_SCOPE = re.compile(r"\b(SCOPE-\d{2,3})\b")


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        print(f"capability-coverage: missing input {rel}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def declared_leaves() -> dict[str, str]:
    """Every leaf capability the strategy declares, id -> label."""
    text = _read(CAPABILITY_MAP)
    # Section 4 ONLY — the taxonomy table. Leaf ids elsewhere in the file are citations, not
    # declarations, and conflating them would let a capability declare itself by being referenced.
    m = re.search(r"^## 4\..*?$(.*?)^## 5\.", text, re.S | re.M)
    if not m:
        print(
            "capability-coverage: backbone section 4 (capability taxonomy) not found",
            file=sys.stderr,
        )
        sys.exit(2)
    out: dict[str, str] = {}
    for cap_id, label in _LEAF.findall(m.group(1)):
        out.setdefault(cap_id, " ".join(label.split())[:80])
    return out


def cited_leaves() -> set[str]:
    """Every leaf capability a requirement row claims to serve."""
    text = _read(BACKBONE) + "\n" + _read(RTM)
    out: set[str] = set()
    for cell in _CAP_CELL.findall(text):
        out |= set(_LEAF_ID.findall(cell))
    return out


def scope_coverage() -> tuple[set[str], set[str]]:
    """SCOPE ids declared, and those cited anywhere outside the scope document itself."""
    declared = set(_SCOPE.findall(_read(SCOPE_DOC)))
    cited: set[str] = set()
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("node_modules", "CC-Session-Logs")) or rel == SCOPE_DOC:
            continue
        cited |= set(_SCOPE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return declared, cited


def main() -> int:
    leaves = declared_leaves()
    cited = cited_leaves()
    uncovered_caps = {k: v for k, v in sorted(leaves.items()) if k not in cited}

    scope_declared, scope_cited = scope_coverage()
    uncovered_scope = sorted(scope_declared - scope_cited)

    baseline_path = ROOT / BASELINE
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    else:
        baseline = {"accepted_uncovered_capabilities": [], "accepted_uncovered_scope": []}

    accepted_caps = set(baseline.get("accepted_uncovered_capabilities", []))
    accepted_scope = set(baseline.get("accepted_uncovered_scope", []))

    new_caps = {k: v for k, v in uncovered_caps.items() if k not in accepted_caps}
    new_scope = [s for s in uncovered_scope if s not in accepted_scope]

    # The ratchet's other tooth: an accepted gap that is now COVERED must leave the baseline, or the
    # file silently grants permission for it to regress. Paying a debt updates the ledger.
    stale_caps = sorted(accepted_caps - set(uncovered_caps))
    stale_scope = sorted(accepted_scope - set(uncovered_scope))

    print(f"capability leaves declared : {len(leaves)}")
    print(f"  covered by a requirement : {len(leaves) - len(uncovered_caps)}")
    print(f"  uncovered (accepted)     : {len(uncovered_caps) - len(new_caps)}")
    print(f"  uncovered (NEW)          : {len(new_caps)}")
    print(f"SCOPE ids declared         : {len(scope_declared)}")
    print(f"  cited downstream         : {len(scope_declared & scope_cited)}")
    print(f"  uncited (NEW)            : {len(new_scope)}")

    errors: list[str] = []
    for cap_id, label in new_caps.items():
        errors.append(
            f"capability {cap_id} ({label}) is declared in the capability map and NO requirement "
            f"row cites it. Write the requirement, or record it in {BASELINE} with a reason."
        )
    for s in new_scope:
        errors.append(
            f"{s} is committed in the scope document and is cited in NO other document. A "
            f"commitment nothing downstream speaks is how the Wave 1-17 drift happened."
        )
    for cap_id in stale_caps:
        errors.append(
            f"capability {cap_id} is listed as an accepted gap but IS now covered — remove it from "
            f"{BASELINE}. A stale exemption is standing permission to regress."
        )
    for s in stale_scope:
        errors.append(
            f"{s} is listed as an accepted gap but IS now cited — remove it from {BASELINE}."
        )

    if errors:
        print("\ncapability-coverage FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\ncapability-coverage passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
