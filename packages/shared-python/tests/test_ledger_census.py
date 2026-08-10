"""The mechanical ledger census (process fold, 2026-08-09) — build-time, not review-time.

Three slices running, the governance ledgers were paid at REVIEW rather than build (REF-1's SoD
row, LQ-1's, ONBOARD-1a's and 1b's rows — each recorded as "the register-omission class" in its
own slice record), and ONBOARD-1a's roadmap row escaped both passes entirely. Where a ledger
obligation became MECHANICAL (the ``DELIVERS`` gate, the stale-exemption twin, the §5C checklist)
it stopped being missed. This file generalizes that: the three ledgers whose completeness is a
computable set relation are asserted here, so an unpaid row fails the build that created the debt
instead of waiting for a reviewer.

The three census legs:

1. every ORM table -> a row in ``04_data_model/canonical_data_model_standard.md``;
2. every permission code (BOTH catalogs) -> a mention in ``06_security/entitlement_sod_model.md``;
3. every audit ``event_type`` minted as a constant or literal in source -> a mention in
   ``04_data_model/audit_event_taxonomy.md``.

What stays procedural (stated so silence is not read as coverage): the delivery-roadmap ledger
row per shipped slice (no computable "a slice shipped" predicate exists in the tree — the P1
seven-ledger sweep owns it), control-matrix STATUS moves (a status is a judgment on the P9 bar,
not a set relation), and prose QUALITY everywhere. Membership is what this file can prove.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

#: Tables deliberately absent from the canonical data model, each with the reason. EXACT set —
#: an entry whose table gains a doc row must be removed (the ``_DELIBERATELY_EMPTY`` pattern).
_TABLES_NOT_IN_CANONICAL_DOC: dict[str, str] = {}

#: Event types deliberately absent from the taxonomy, each with the reason. EXACT set.
_EVENTS_NOT_IN_TAXONOMY: dict[str, str] = {}


def _doc(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_every_ORM_table_has_a_canonical_data_model_row() -> None:
    from irp_shared.models import Base

    doc = _doc("04_data_model/canonical_data_model_standard.md")
    missing = sorted(
        t
        for t in Base.metadata.tables
        if f"`{t}`" not in doc and t not in _TABLES_NOT_IN_CANONICAL_DOC
    )
    assert not missing, (
        f"ORM tables with NO row in canonical_data_model_standard.md: {missing} — pay the ledger "
        "in the slice that mints the table, or list the table here with a reason"
    )
    stale = sorted(
        t
        for t in _TABLES_NOT_IN_CANONICAL_DOC
        if f"`{t}`" in _doc("04_data_model/canonical_data_model_standard.md")
    )
    assert not stale, f"exempted tables now documented — delete the entries: {stale}"


def test_every_permission_code_appears_in_the_sod_model() -> None:
    from irp_shared.entitlement.bootstrap import ALL_CODES
    from irp_shared.entitlement.platform_catalog import PLATFORM_PERMISSIONS

    doc = _doc("06_security/entitlement_sod_model.md")
    every = list(ALL_CODES) + [code for code, _ in PLATFORM_PERMISSIONS]
    missing = sorted(c for c in every if f"`{c}`" not in doc)
    assert not missing, (
        f"permission codes with NO mention in entitlement_sod_model.md: {missing} — §5C row 3 is "
        "part of the mint, not of the review"
    )


_EVENT_RE = re.compile(r"^[A-Z][A-Z_]*\.[A-Z][A-Z_]*$")


def _minted_event_types() -> set[str]:
    """Every audit event type the CODE can emit, collected from the AST.

    Two shapes: module constants named ``*_EVENT`` bound to a matching string, and literal
    ``event_type="X.Y"`` keywords at ``record_event`` call sites. Parameterized event types
    (f-strings, the REF-1 precedent) are invisible here by construction — their families are
    documented under wildcard rows and their literal halves still surface via the constants.
    """
    found: set[str] = set()
    src_roots = [
        ROOT / "packages" / "shared-python" / "src",
        ROOT / "apps" / "backend" / "src",
        ROOT / "apps" / "worker" / "src",
    ]
    for src in src_roots:
        for path in src.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id.endswith("_EVENT")
                            and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)
                            and _EVENT_RE.match(node.value.value)
                        ):
                            found.add(node.value.value)
                elif isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if (
                            kw.arg == "event_type"
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                            and _EVENT_RE.match(kw.value.value)
                        ):
                            found.add(kw.value.value)
    return found


def _taxonomy_covers(doc: str) -> tuple[set[str], list[str]]:
    """The taxonomy's own vocabulary: exact codes, plus its WILDCARD convention.

    The document has TWO compaction conventions of its own, and the census must honor both or its
    findings are artifacts: wildcards (``MARKET.CURVE_*`` / ``BREACH.*`` — a wildcard row is the
    mint record for its expansions, the REF-1 parameterized-verb precedent) and within-row
    ABBREVIATION (a `PRIVATE` family row writing ``.COMMITMENT_UPDATE`` for
    ``PRIVATE.COMMITMENT_UPDATE``). The first run of this census reported nine "undocumented"
    event types; all nine were the abbreviation convention, not debt — recorded here so the next
    reader knows the matcher earned its shape.
    """
    tokens = set(re.findall(r"`([A-Z][A-Z_]*\.[A-Z_*][A-Z_*]*)`", doc))
    exact = {t for t in tokens if "*" not in t}
    prefixes = [t[:-1] for t in tokens if t.endswith("*")]
    # Expand per-line abbreviations against every family named on the same line.
    for line in doc.splitlines():
        families = re.findall(r"`([A-Z][A-Z_]*)`", line)
        for suffix in re.findall(r"`(\.[A-Z_*][A-Z_*]*)`", line):
            for family in families:
                token = f"{family}{suffix}"
                if token.endswith("*"):
                    prefixes.append(token[:-1])
                else:
                    exact.add(token)
    return exact, prefixes


def test_every_minted_audit_event_type_appears_in_the_taxonomy() -> None:
    doc = _doc("04_data_model/audit_event_taxonomy.md")
    minted = _minted_event_types()
    assert minted, "the event-type collector found NOTHING — the census walked an empty population"
    exact, prefixes = _taxonomy_covers(doc)
    missing = sorted(
        e
        for e in minted
        if e not in exact
        and not any(e.startswith(p) for p in prefixes)
        and e not in _EVENTS_NOT_IN_TAXONOMY
    )
    assert not missing, (
        f"audit event types the code can emit with NO taxonomy mention: {missing} — the taxonomy "
        "row IS the R-07 mint record, so an undocumented emitter is an unminted code in use"
    )
    stale = sorted(e for e in _EVENTS_NOT_IN_TAXONOMY if e in doc)
    assert not stale, f"exempted event types now documented — delete the entries: {stale}"
