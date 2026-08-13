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
    """A throwaway copy of the gate's four inputs, so a control can mutate them safely."""
    for rel in _INPUTS:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_ROOT / rel, dest)
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    return tmp_path


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
