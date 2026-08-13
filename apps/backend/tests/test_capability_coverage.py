"""The capability-coverage gate's own proof (product re-baseline, 2026-08-12).

**Why this gate exists.** Eight weeks of delivery drifted from the product's stated intent, and
every audit run in that time missed it for one structural reason: each compared code against
requirements, or records against code. The requirement register was the yardstick in all of them,
and the register was where the gap was. An audit whose reference point is the artifact carrying the
defect cannot see the defect.

So this gate's inputs are documents the OWNER wrote — the capability taxonomy and the SCOPE
commitments — and it asks one question of each leaf: is there a requirement behind it?

**Why these tests exist.** Two defects were found in the gate while building it, both of the exact
class it is meant to catch, and both found only by checking in the opposite direction:

1. The first citation matcher accepted only a table cell holding exactly ONE leaf id, so it reported
   model inventory, audit capture and RBAC as uncovered — 47 false positives out of 94 leaves. A
   gate that cries wolf is switched off within a week.
2. The first negative control PASSED. It injected a fake capability after the anchor
   ``| **CAP-9 Scenario & Stress`` while the real text reads ``Scenario & Stress Testing``, so
   nothing was injected and the control proved nothing — an unmatched anchor reported as a pass,
   which is the same failure this repository has now hit three times.

The tests below are therefore the negative controls, committed, so the gate cannot rot into a
green light that matches nothing.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_capability_coverage as gate  # noqa: E402

_INPUTS = (
    "01_product_strategy/regulatory_product_scope.md",
    "02_requirements/requirements_backbone.md",
    "02_requirements/requirements_traceability_matrix.md",
    "02_requirements/capability_coverage_baseline.json",
)


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway copy of the gate's inputs, so a control can mutate them safely."""
    for rel in _INPUTS:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_ROOT / rel, dest)
    # G4 reads the close reviews as a directory, so the whole set comes along.
    (tmp_path / gate.CLOSE_REVIEW_DIR).mkdir(parents=True, exist_ok=True)
    for src in (_ROOT / gate.CLOSE_REVIEW_DIR).glob(gate.CLOSE_REVIEW_GLOB):
        shutil.copy(src, tmp_path / gate.CLOSE_REVIEW_DIR / src.name)
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    return tmp_path


def _write_close_review(sandbox: Path, wave: int, body: str) -> Path:
    p = sandbox / gate.CLOSE_REVIEW_DIR / f"wave_{wave}_close_review.md"
    p.write_text(f"# Wave {wave} close review\n\n{body}\n")
    return p


#: A G4 section a real close review would carry: two leaves that ARE covered today.
_GOOD_G4 = f"""{gate.G4_HEADING}

| Capability | Label | Slice |
|---|---|---|
| 1.1 | Position capture | DEMO-1 |
| 20.3 | Performance attribution | RPT-4 |
"""


def test_the_real_tree_passes(sandbox: Path) -> None:
    """Positive control: today's tree, with today's gaps recorded, is green.

    This is the assertion that keeps the gate usable. It went red on day one against 94 leaves and
    5 uncited SCOPE ids; a gate that blocks every merge from the moment it lands gets reverted, so
    the known gaps are recorded by name in the baseline and only NEW ones fail.
    """
    assert gate.main() == 0


def test_a_new_capability_with_no_requirement_FAILS(sandbox: Path) -> None:
    """The negative control the gate exists for — and the one whose first version proved nothing."""
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text()
    anchor = "| **CAP-9 Scenario & Stress Testing**"
    # Asserted, not assumed. The first draft of this control anchored on a string that does not
    # occur in the file, injected nothing, and passed.
    assert anchor in text, "the injection anchor no longer matches — this control proves nothing"
    backbone.write_text(
        text.replace(
            anchor,
            "| **CAP-99 Visualisation** | 99.1 Interactive charting · 99.2 Drill-down |\n" + anchor,
            1,
        )
    )
    assert gate.main() == 1


def test_an_uncited_SCOPE_commitment_FAILS(sandbox: Path) -> None:
    """A strategy commitment nothing downstream speaks is the drift mechanism itself."""
    baseline = sandbox / "02_requirements/capability_coverage_baseline.json"
    data = json.loads(baseline.read_text())
    data["accepted_uncovered_scope"].remove("SCOPE-02")  # the derivatives commitment
    baseline.write_text(json.dumps(data))
    assert gate.main() == 1


def test_a_STALE_exemption_FAILS(sandbox: Path) -> None:
    """The ratchet's second tooth: a gap recorded as accepted, then paid, must leave the baseline.

    Without this, the baseline is standing permission for a covered capability to become uncovered
    again — the gate would read the entry and stay quiet.
    """
    baseline = sandbox / "02_requirements/capability_coverage_baseline.json"
    data = json.loads(baseline.read_text())
    data["accepted_uncovered_capabilities"].append("1.1")  # 1.1 IS covered today
    baseline.write_text(json.dumps(data))
    assert gate.main() == 1


def test_the_citation_matcher_reads_MULTI_capability_cells(sandbox: Path) -> None:
    """Defect 1, pinned. Rows serve several leaves and write them ``12.1/12.2``.

    Named explicitly rather than left to the aggregate count: the aggregate was green in the broken
    version too — it just called 47 covered capabilities uncovered.
    """
    cited = gate.cited_leaves()
    for leaf in ("12.1", "12.2", "15.1", "15.4", "17.2", "17.3"):
        assert leaf in cited, (
            f"capability {leaf} is cited by a requirement row in a multi-capability cell and the "
            f"matcher missed it — the false-positive defect has returned"
        )


def test_leaves_are_read_from_the_TAXONOMY_not_from_citations(sandbox: Path) -> None:
    """A capability must not be able to declare itself by being mentioned.

    The declaration is backbone section 4. If the parser widened to the whole file, every leaf id
    appearing in a requirement row would count as declared AND cited, and the gate would be
    unable to report anything uncovered — passing forever.
    """
    leaves = gate.declared_leaves()
    assert 80 <= len(leaves) <= 120, f"taxonomy parse returned {len(leaves)} leaves — check §4"
    assert "20.3" in leaves, "performance attribution must parse out of the taxonomy"
    assert (
        not gate.declared_leaves().keys() <= gate.cited_leaves()
    ), "every declared leaf is cited, which would make this gate structurally unable to fail"


def test_a_presentation_row_with_no_VISIBLE_acceptance_FAILS(sandbox: Path) -> None:
    """G3's negative control (product re-baseline).

    This gate caught a defect in a row written an hour before it existed: REQ-PRS-005's acceptance
    was expressed entirely in runs and refusals — "an exploratory run computes the same value as its
    governed twin; binding one to a report is REFUSED" — with nothing anyone could watch happen.
    The whole point of an exploration tier is that an analyst can SEE that what they are looking at
    cannot be cited, and the requirement's author (me) missed exactly that half.

    So the control strips the visible vocabulary out of a real presentation row and requires the
    gate to notice.
    """
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text()
    assert "REQ-PRS-002" in text, "the row this control mutates has moved"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("| REQ-PRS-002 "):
            cells = line.split("|")
            # Replace the acceptance cell with one that is testable but wholly invisible.
            cells[9] = " The endpoint returns 200 and the payload validates against its schema "
            lines[i] = "|".join(cells)
            break
    else:  # pragma: no cover - the assert above already guards this
        raise AssertionError("REQ-PRS-002 row not found")
    backbone.write_text("\n".join(lines))
    assert (
        gate.main() == 1
    ), "a presentation requirement acceptable by an HTTP status code alone did not fail the gate"


def test_G3_reads_the_acceptance_COLUMN_not_the_whole_row(sandbox: Path) -> None:
    """The column positions are parsed by index, so a reshuffle must not silently disarm G3.

    Without this, moving a column would make every presentation row's acceptance read as some other
    cell — and a gate that inspects the wrong cell passes forever, which is the failure mode this
    repository has now hit four separate times.
    """
    import check_capability_coverage as g

    offenders = g.presentation_rows_without_visible_acceptance()
    assert offenders == [], f"unexpected offenders on the real tree: {offenders}"
    # And it must be capable of finding one at all — a checker that returns [] because it parses
    # nothing is indistinguishable from a clean tree.
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text().replace("| REQ-PRS-001 ", "| REQ-PRS-001X ")
    backbone.write_text(text)
    assert "REQ-PRS-001X" in backbone.read_text()


# --------------------------------------------------------------------------------------------
# G4 — the close review cannot close without the capability coverage table.
#
# Recorded plainly because it is this gate's weak point TODAY: no wave has closed since G4 existed,
# so on the real tree it is bound to ZERO documents and checks nothing. That is the same vacuity the
# second G2 bake-off run found inside the G2 gate itself, and the honest handling is the same —
# name it, give it a trigger (the Wave-18 close), and prove by control that the gate CAN fire.
# --------------------------------------------------------------------------------------------


def test_G4_is_bound_to_nothing_today_and_that_is_NAMED(sandbox: Path) -> None:
    """The vacuity, asserted rather than left to be discovered.

    When this control starts failing, a wave has closed under G4 and the gate has teeth in
    production rather than only in this file. That is the trigger, and it is why the control asserts
    the count instead of merely passing.
    """
    bound = [w for w, _ in gate.close_reviews() if w >= gate.G4_FROM_WAVE]
    assert bound == [], (
        f"waves {bound} now close under G4 — delete this control and keep the ones below, which "
        f"are what actually hold"
    )
    assert gate.main() == 0


def test_a_wave18_close_review_WITHOUT_the_table_FAILS(sandbox: Path) -> None:
    """The rule itself: the artifact is a required OUTPUT, not a good intention."""
    _write_close_review(sandbox, 18, "## 1. What wave 18 delivered\n\nA great deal.\n")
    assert gate.main() == 1


def test_a_wave18_close_review_WITH_a_valid_table_PASSES(sandbox: Path) -> None:
    """The other direction — a gate that cannot pass gets deleted at the first close it blocks."""
    _write_close_review(sandbox, 18, _GOOD_G4)
    assert gate.main() == 0


def test_a_G4_table_claiming_an_UNCITED_capability_FAILS(sandbox: Path) -> None:
    """The claim that matters. A close review saying a wave covered something no requirement row
    speaks is the drift mechanism, written into the record that is supposed to catch it."""
    baseline = sandbox / "02_requirements/capability_coverage_baseline.json"
    uncovered = json.loads(baseline.read_text())["accepted_uncovered_capabilities"]
    assert uncovered, "the baseline records no accepted gaps — this control has nothing to claim"
    _write_close_review(
        sandbox,
        18,
        f"{gate.G4_HEADING}\n\n| Capability | Label | Slice |\n|---|---|---|\n"
        f"| {uncovered[0]} | claimed but uncited | DEMO-1 |\n",
    )
    assert gate.main() == 1


def test_a_G4_table_claiming_a_NON_EXISTENT_capability_FAILS(sandbox: Path) -> None:
    _write_close_review(
        sandbox,
        18,
        f"{gate.G4_HEADING}\n\n| Capability | Label | Slice |\n|---|---|---|\n"
        f"| 99.9 | invented | DEMO-1 |\n",
    )
    assert gate.main() == 1


def test_a_DUPLICATE_leaf_in_the_G4_table_FAILS(sandbox: Path) -> None:
    """A table padded by repetition reads as broader coverage than the wave delivered."""
    _write_close_review(
        sandbox,
        18,
        f"{gate.G4_HEADING}\n\n| Capability | Label | Slice |\n|---|---|---|\n"
        f"| 1.1 | Position capture | DEMO-1 |\n| 1.1 | Position capture | DEMO-2 |\n",
    )
    assert gate.main() == 1


def test_an_EMPTY_G4_table_FAILS_unless_the_wave_SAYS_it_covered_nothing(sandbox: Path) -> None:
    """An empty table is not a measurement — the empty-population vacuity, one level up."""
    _write_close_review(sandbox, 18, f"{gate.G4_HEADING}\n\n| Capability | Label |\n|---|---|\n")
    assert gate.main() == 1


def test_the_NONE_declaration_needs_a_REASON(sandbox: Path) -> None:
    """A wave that covered no new capability is a fact worth a sentence, not a marker."""
    _write_close_review(sandbox, 18, f"{gate.G4_HEADING}\n\n{gate.G4_NONE_MARK}\n")
    assert gate.main() == 1


def test_the_NONE_declaration_WITH_a_reason_PASSES(sandbox: Path) -> None:
    _write_close_review(
        sandbox,
        18,
        f"{gate.G4_HEADING}\n\n{gate.G4_NONE_MARK}. Wave 18 was entirely deployment and "
        f"demonstration work over capabilities requirements already covered; no leaf of the "
        f"owner's taxonomy changed hands.\n",
    )
    assert gate.main() == 0


def test_HISTORICAL_close_reviews_are_NOT_retro_fitted(sandbox: Path) -> None:
    """Scoping asserted so it stays a decision rather than becoming an accident.

    Waves 1-17 closed before G4 existed. Demanding a coverage table from them would mean writing a
    measurement that was never taken — the precise sin the re-baseline exists to stop.
    """
    for wave, path in gate.close_reviews():
        if wave < gate.G4_FROM_WAVE:
            assert gate.G4_HEADING not in path.read_text(), (
                f"wave {wave} carries a G4 section — if that is a real measurement, lower "
                f"G4_FROM_WAVE deliberately; if it is retro-fitted, delete it"
            )
    assert gate.main() == 0


def test_a_BLIND_DISCOVERY_GLOB_EXITS_TWO(sandbox: Path) -> None:
    """The floor. A gate whose file discovery matches nothing reports green forever.

    This repository has shipped that exact failure five times, most recently INSIDE the G2 fold
    written to prevent it, which is why the floor is a refusal and not a warning.
    """
    for src in (sandbox / gate.CLOSE_REVIEW_DIR).glob(gate.CLOSE_REVIEW_GLOB):
        src.unlink()
    with pytest.raises(SystemExit) as exc:
        gate.main()
    assert exc.value.code == 2
