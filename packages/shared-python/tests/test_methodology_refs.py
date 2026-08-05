"""ONE census over EVERY registered `*_METHODOLOGY_REF` (RPT-1 pre-work, ratified OQ-W15P-2).

**DEVIATION FROM THE REMIT, recorded rather than silently followed.** The RPT-1 remit said this
census would REPLACE the ~14 hand-copied per-family doc tests. Executing it showed that premise was
wrong: those tests assert SEVEN sections *plus family-specific content a generic census cannot
express* — exact hand-reference values (`0.007211102551`), honesty-gap phrases ("EX-ANTE",
"Specific/idiosyncratic active risk = 0"). Deleting them would have been a coverage LOSS dressed as
consolidation. They stay; this census ADDS the universal layer none of them had.

**What was actually missing.** Methodology-doc existence was checked by those per-family tests, each
naming one constant it happened to know about — the defect the P6 rule describes: it covers only the
families someone remembered to write a test for. It missed
`PURE_PRIVATE_METHODOLOGY_REF` entirely — which pointed at
`05_analytics_methodologies/pure_private_factor_v1.md`, **a file that never existed** (`git log
--diff-filter=A` over the directory does not list it) — while CTRL-002 ("every calculation has a
methodology doc") was stamped *Operational*. Two further constants carried PROSE strings rather than
paths, which no reader can follow and no report can render.

**The form is a DISCOVERY census, not an enumeration.** It walks the source tree for every
constant matching `*METHODOLOGY_REF` and requires each to RESOLVE. A family added tomorrow with a
dangling ref fails without anyone remembering to extend a list — the whole difference between this
and what it replaces (P7's hierarchy: exact census > coverage floor > enumerating matcher).

**Two tiers, and the second one is a declared set — stated plainly rather than implied.** The
universal tier (resolves / is a path / is not prose) covers EVERY registered ref with no exceptions,
and is the gap that motivated this census. The full-form tier (8 sections + source grades) covers a
DECLARED set, because building this census measured the corpus and found only 5 of 30 docs carry
that form: the two RM-1/SR-1 wrote, plus the three written here. Requiring it of the other 25 would
declare shipped governed documents non-compliant on this test's own authority — a ratification-gate
decision, not a pre-work test's. See `_FULL_FORM_DOCS` for the recorded gap and its trigger.
"""

from __future__ import annotations

import pathlib
import re

#: The eight sections the house form requires (the shape the per-family tests asserted).
REQUIRED_SECTIONS: tuple[str, ...] = (
    "Purpose & applicability",
    "Inputs & data policy",
    "Formulas & numerical standards",
    "Assumptions",
    "Validation / reproduction tests",
    "Governed-number contract",
    "Known limitations",
    "External benchmarks",
)

#: Rule 6: every external source carries a grade — [V] verified against the primary source,
#: [C] cited, [U] uncited/unverified. A doc with no [U] anywhere is usually a doc that has not
#: admitted what it cannot support.
REQUIRED_GRADES: tuple[str, ...] = ("[V]", "[C]", "[U]")

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "packages" / "shared-python" / "src" / "irp_shared"


def _discovered_refs() -> dict[str, tuple[str, str]]:
    """Every `*_METHODOLOGY_REF` constant in the shared source tree -> (value, defining file)."""
    found: dict[str, tuple[str, str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r'^([A-Z][A-Z0-9_]*METHODOLOGY_REF)(?:\s*:\s*[^=]+)?\s*=\s*"([^"]+)"',
            text,
            re.MULTILINE,
        ):
            found[match.group(1)] = (match.group(2), str(path.relative_to(_REPO_ROOT)))
    return found


def test_the_census_finds_a_plausible_population() -> None:
    """The non-vacuity floor (P6). Without it, a regex that silently stopped matching would make
    every assertion below pass over an EMPTY set — a green census proving nothing, which is exactly
    the failure mode the enumerating tests this replaces already had."""
    refs = _discovered_refs()
    assert len(refs) >= 25, (
        f"the methodology-ref census found only {len(refs)} constants — the discovery regex has "
        "gone blind, or the population collapsed. Either way this census is not covering what it "
        "claims to."
    )


def test_EVERY_registered_methodology_ref_RESOLVES_to_a_real_file() -> None:
    """The finding that motivated this census: a registered pointer to a missing file is a
    governance gap, not a broken link. It survived because nothing looked at ALL of them."""
    dangling: list[str] = []
    for name, (value, source) in sorted(_discovered_refs().items()):
        if not value.startswith("05_analytics_methodologies/"):
            dangling.append(f"{name} = {value!r} ({source}) — not a path at all")
        elif not (_REPO_ROOT / value).is_file():
            dangling.append(f"{name} -> {value} ({source}) — path does not exist")
    assert not dangling, "registered methodology refs that do not resolve:\n  " + "\n  ".join(
        dangling
    )


#: The docs held to the FULL house form (8 sections + the three source grades).
#:
#: **Why this is a declared set and not "all of them", stated honestly.** Building this census
#: MEASURED the corpus: of 30 methodology docs, only FIVE carry the full form — the two the
#: RM-1/SR-1 slices wrote (which is where the convention was introduced, and the only two that ever
#: had a per-family test asserting it) and the three written here at RPT-1. The other 25 predate the
#: convention. Requiring it universally would declare 25 SHIPPED governed documents non-compliant on
#: this test's own authority, which is a governance decision for a ratification gate, not something
#: a pre-work test should assert unilaterally.
#:
#: So: the UNIVERSAL checks (resolves, is a path, not prose) apply to every registered ref and are
#: the gap that motivated this census. The FULL-FORM check applies to exactly the set that already
#: carried it, plus every doc written from RPT-1 onward. **RECORDED GAP:** retrofitting the other 25
#: to the full form is a real, un-done piece of work — named here rather than hidden by a weaker
#: assertion. Trigger: the next methodology-touching gate.
_FULL_FORM_DOCS: frozenset[str] = frozenset(
    {
        "05_analytics_methodologies/rolling_risk_v1.md",
        "05_analytics_methodologies/sharpe_v1.md",
        "05_analytics_methodologies/pure_private_factor_v1.md",
        "05_analytics_methodologies/concentration_dimensional_v1.md",
        "05_analytics_methodologies/liquidity_tiers_v1.md",
    }
)


def test_the_full_form_set_never_shrinks() -> None:
    """A coverage floor on the declared set (P6). Without it, the cheapest way to make a failing
    full-form check pass would be to quietly DROP the doc from the set — turning a real regression
    into a green run. The set may only grow."""
    assert len(_FULL_FORM_DOCS) >= 5, (
        "the full-form set has shrunk — a doc was removed rather than fixed, which is the "
        "enumeration-guard failure mode this floor exists to catch"
    )


def test_the_FULL_FORM_docs_carry_every_required_section_and_grade() -> None:
    """A resolving path is necessary and not sufficient: an empty file resolves. For the docs held
    to the full form, *Known limitations* is the section a governed report must render, and the
    [V]/[C]/[U] grades are Rule 6 — a doc with no [U] has usually not admitted what it cannot
    support."""
    problems: list[str] = []
    for name, (value, _source) in sorted(_discovered_refs().items()):
        if value not in _FULL_FORM_DOCS:
            continue
        doc = _REPO_ROOT / value
        if not doc.is_file():
            continue  # already reported by the resolution test; do not double-count
        text = doc.read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                problems.append(f"{name} ({value}): missing section {section!r}")
        for grade in REQUIRED_GRADES:
            if grade not in text:
                problems.append(f"{name} ({value}): missing source grade {grade}")
    assert not problems, "full-form methodology docs failing the form:\n  " + "\n  ".join(problems)


def test_every_full_form_doc_is_actually_registered() -> None:
    """The set must not accumulate entries for docs no model version points at — a stale name in
    the set is coverage that looks real and guards nothing."""
    registered = {value for value, _s in _discovered_refs().values()}
    orphans = sorted(_FULL_FORM_DOCS - registered)
    assert not orphans, f"full-form entries no registered ref points at: {orphans}"


def test_no_methodology_ref_is_PROSE() -> None:
    """Two constants carried prose ("docs: CON-1 decision record Parts 1-2 …") until RPT-1. Prose
    is unfollowable by a reader and unrenderable by a report, and it silently satisfied any test
    that only asked whether the constant was non-empty."""
    prose = [
        f"{name} = {value!r}"
        for name, (value, _s) in sorted(_discovered_refs().items())
        if not value.endswith(".md")
    ]
    assert not prose, (
        "methodology refs that are prose rather than document paths:\n  " + "\n  ".join(prose)
    )
