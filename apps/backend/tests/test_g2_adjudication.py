"""The G2 bookkeeping gate's own proof (product re-baseline, 2026-08-13).

**Why these controls, and why there are this many of them.**

G2 was specified as an automated detector and cannot be one. Six independent designs were built and
scored; all six caught the three known-bad rows and all six are unusable, because each was really
checking which words appear in the acceptance sentence. The decisive measurement, taken by hand on
the best performer: an acceptance criterion reading *"Exposure rollup across the hierarchy is NOT
implemented; the endpoint returns 501"* PASSED clean, the register's own 2026-08-12 repair was
FLAGGED as defective, and appending the six words *"; the hierarchy is recorded"* to the real defect
turned it green with nothing built.

So G2 is a human act, and this gate is the bookkeeping that makes the act unskippable and makes it
lapse when the text underneath it changes. The bookkeeping half is worth exactly as much as its
resistance to a cosmetic edit — and during the bake-off, each of the following was demonstrated to
turn one of the six candidate designs green while blind: a bolded id, a lettered id suffix, a
duplicate ledger line, a register the parser could not read at all. Four guards in this repository
have already shipped green while matching nothing (LQ-1 found three; the Wave-17 close found a
fourth that could not fire twice). The controls below are what stands between this gate and being
the fifth.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_g2_adjudication as gate  # noqa: E402

_INPUTS = (
    "02_requirements/requirements_backbone.md",
    "02_requirements/g2_adjudication_ledger.jsonl",
    "02_requirements/g2_adjudicators.json",
    "02_requirements/g2_slice_scope.json",
)

#: The requirement table's header row, verbatim — the gate reads its column positions from this.
_HEADER_ROW = (
    "| REQ | Title | CAP | Business purpose | Functional | Data | Calc | Test "
    "| Acceptance | Status |"
)

#: A row that exists in the register, used as the subject of the scope controls.
_SUBJECT = "REQ-PPM-004"
_REASONING = (
    "An implementation that aggregates a single node and ignores its children satisfies every "
    "clause of this criterion, because a one-element sum reproduces perfectly and binds lineage "
    "exactly as a real rollup would."
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


def _write_scope(sandbox: Path, **kw: object) -> None:
    p = sandbox / "02_requirements/g2_slice_scope.json"
    data = json.loads(p.read_text())
    data.update(kw)
    p.write_text(json.dumps(data))


def _entry(**kw: object) -> dict:
    e = {
        "req_id": _SUBJECT,
        "hash": "",
        "adjudicator": "ghostai8088",
        "disposition": "REBUTTED",
        "reasoning": _REASONING,
        "adjudicated_at": "2026-08-13",
    }
    e.update(kw)
    return e


def _write_ledger(sandbox: Path, *entries: dict) -> None:
    p = sandbox / "02_requirements/g2_adjudication_ledger.jsonl"
    p.write_text("// test ledger\n" + "\n".join(json.dumps(e) for e in entries) + "\n")


def _hash_of(sandbox: Path, req_id: str) -> str:
    text = (sandbox / "02_requirements/requirements_backbone.md").read_text()
    return gate.parse_rows(text)[req_id]


def test_the_real_tree_passes(sandbox: Path) -> None:
    """Positive control. An empty ledger with an empty slice scope is clean — by design.

    Recorded plainly because it is the gate's weakest moment: on the day it ships it blocks nothing,
    and the only reason that is acceptable is that the controls below prove it CAN block.
    """
    assert gate.main() == 0


def test_every_row_including_the_LETTERED_ones_is_parsed(sandbox: Path) -> None:
    """FOUR of the six bake-off scripts silently dropped REQ-MKT-002a and REQ-MKT-004a.

    Their id pattern did not allow a letter suffix, so they read 84 of 86 rows and said nothing —
    and those two are the newest, least-reviewed rows in the file, the amendment rows themselves.
    """
    rows = gate.parse_rows((sandbox / "02_requirements/requirements_backbone.md").read_text())
    for req in ("REQ-MKT-002a", "REQ-MKT-004a"):
        assert req in rows, f"{req} was silently dropped — the lettered-id defect has returned"


def test_a_row_entering_a_slice_UNADJUDICATED_FAILS(sandbox: Path) -> None:
    """The gate's whole reason for existing: rows entered build unexamined for seventeen waves."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    assert gate.main() == 1


def test_an_adjudicated_row_in_scope_PASSES(sandbox: Path) -> None:
    """The other direction — a gate that cannot pass is switched off as fast as one that cannot
    fail."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT)))
    assert gate.main() == 0


def test_EDITING_the_acceptance_cell_LAPSES_the_adjudication(sandbox: Path) -> None:
    """Trigger T2. Without this the ledger certifies text that no longer exists.

    Note what this control does NOT claim: the hash covers the business-purpose and acceptance cells
    only. A row can go stale in substance — Method, Test, Status, or the implementation drifting
    away from an unchanged criterion — with its hash perfectly current.
    """
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT)))
    assert gate.main() == 0, "precondition: the adjudication is current before the edit"

    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text()
    # The 2026-08-12 repair's falsifying case — the clause a degenerate rollup provably fails.
    # Asserted, not assumed: an anchor that no longer matches injects nothing and proves nothing,
    # which is how this repository's first capability-coverage negative control passed while blind.
    old = "a run scoped to a node whose subtree is empty REFUSES rather than returning zero"
    assert old in text, "the acceptance text this control edits has moved — it proves nothing"
    backbone.write_text(text.replace(old, "the subtree is handled appropriately", 1))
    assert gate.main() == 1


def test_COSMETIC_edits_do_NOT_lapse_an_adjudication(sandbox: Path) -> None:
    """The counterweight. A gate that lapses on whitespace trains people to re-stamp unread.

    Bolding is included deliberately: a bolded id was demonstrated to blind one of the six candidate
    designs entirely, so this asserts the row still parses AND that its hash is unmoved.
    """
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT)))
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text()
    assert f"| {_SUBJECT} |" in text
    backbone.write_text(text.replace(f"| {_SUBJECT} |", f"|  **{_SUBJECT}**  |", 1))
    assert _SUBJECT in gate.parse_rows(backbone.read_text()), "a bolded id stopped parsing"
    assert gate.main() == 0


def test_a_DUPLICATE_ledger_key_FAILS(sandbox: Path) -> None:
    """Appending a line must never erase a prior finding — so identical keys are rejected outright,
    rather than the last line winning."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    h = _hash_of(sandbox, _SUBJECT)
    _write_ledger(
        sandbox,
        _entry(hash=h, disposition="AMENDED", amendment_commit="deadbee", reasoning=_REASONING),
        _entry(hash=h),  # a second, contradicting adjudication of identical text
    )
    assert gate.main() == 1


def test_a_MODEL_adjudicator_FAILS(sandbox: Path) -> None:
    """The load-bearing refusal. G2 exists because the model authored the rows; letting the model
    adjudicate them reconstitutes the exact failure that cost eight weeks."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(
        sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT), adjudicator="MODEL:claude-opus-5")
    )
    assert gate.main() == 1


def test_an_ADJUDICATOR_OFF_THE_ROSTER_FAILS(sandbox: Path) -> None:
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT), adjudicator="someone-else"))
    assert gate.main() == 1


def test_a_THIRTY_CHARACTER_REBUTTAL_FAILS(sandbox: Path) -> None:
    """'Looks fine' is not a disposition. This is a deterrent, not a detector — a fluent WRONG
    rebuttal passes exactly as easily as a correct one, and the gate must never be described as if
    it caught that."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(
        sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT), reasoning="looks fine to me, shipping")
    )
    assert gate.main() == 1


def test_AMENDED_without_the_repair_commit_FAILS(sandbox: Path) -> None:
    """An exploit was found and nothing records the repair — the most valuable half, unrecorded."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT), disposition="AMENDED"))
    assert gate.main() == 1


def test_an_INVALID_disposition_FAILS(sandbox: Path) -> None:
    _write_scope(sandbox, slice="TEST-1", slice_scope=[_SUBJECT])
    _write_ledger(sandbox, _entry(hash=_hash_of(sandbox, _SUBJECT), disposition="OK"))
    assert gate.main() == 1


def test_a_SCOPE_ROW_THAT_IS_NOT_IN_THE_REGISTER_FAILS(sandbox: Path) -> None:
    """A slice cannot declare scope the register does not contain — that is a typo silently
    exempting a real row from the gate."""
    _write_scope(sandbox, slice="TEST-1", slice_scope=["REQ-XXX-999"])
    assert gate.main() == 1


def test_a_REGISTER_WITH_NO_PARSEABLE_ROWS_EXITS_TWO(sandbox: Path) -> None:
    """Structural, never a pass. This is the failure mode the repository has hit four times: a
    guard that matches nothing and reports green forever."""
    (sandbox / "02_requirements/requirements_backbone.md").write_text(_HEADER_ROW + "\n")
    assert gate.main() == 2


def test_a_COLUMN_RESHUFFLE_EXITS_TWO(sandbox: Path) -> None:
    """The columns are read from the header, and a header the gate cannot recognise must stop it.

    Without this, moving a column would make the gate hash some other pair of cells — and it would
    keep reporting current adjudications for text it was never shown.
    """
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text()
    assert _HEADER_ROW in text
    broken = _HEADER_ROW.replace("| Acceptance |", "| Accept |")
    backbone.write_text(text.replace(_HEADER_ROW, broken, 1))
    assert gate.main() == 2


def test_a_DECLARED_SLICE_WITH_AN_EMPTY_SCOPE_EXITS_TWO(sandbox: Path) -> None:
    """The vacuity interlock — and the one control here that was written because the gate FAILED it.

    The first version of this gate exited 0 with an empty slice scope, having adjudicated nothing.
    A second, independent bake-off run found it within the hour and called the interlock mandatory:
    the empty-population vacuity, sitting inside the gate whose entire subject is checks that pass
    while checking nothing. Four guards in this repository have already shipped green while matching
    nothing. This one nearly made five, in the fold written to prevent it.
    """
    _write_scope(sandbox, slice="TEST-1", slice_scope=[])
    assert gate.main() == 2


def test_AN_UNDECLARED_EMPTY_SCOPE_EXITS_TWO(sandbox: Path) -> None:
    """The other half: no slice, no reason, no thought. The default that rots.

    What this buys is attribution, not detection — someone must write down why nothing is in scope.
    Deciding whether a slice is REALLY in flight would mean parsing the roadmap, which carries no
    machine-readable active-slice marker, and a fragile parse fails open. Named as an accepted
    residual with its trigger: at the first planning gate that sets ``slice``, the interlock above
    becomes load-bearing on its own.
    """
    _write_scope(sandbox, slice=None, slice_scope=[], no_scope_reason="none")
    assert gate.main() == 2


def test_a_REGISTER_TOO_SMALL_TO_BE_REAL_EXITS_TWO(sandbox: Path) -> None:
    """A floor, not "more than zero". The register has only ever grown, 74 rows to 86.

    A parse that suddenly returns three rows is a broken parser wearing a pass — and the scoped rows
    would all read as "not in the register" rather than as unadjudicated.
    """
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    lines = backbone.read_text().splitlines()
    kept, dropped = [], 0
    for line in lines:
        if line.startswith("| REQ-") and dropped < 80:
            dropped += 1
            continue
        kept.append(line)
    assert dropped >= 80, "fewer rows were dropped than intended — this control proves nothing"
    backbone.write_text("\n".join(kept))
    assert gate.main() == 2


def test_a_LEDGER_ENTRY_FOR_A_ROW_THAT_NO_LONGER_EXISTS_FAILS(sandbox: Path) -> None:
    """A renumbering or deletion leaving an adjudication pointing at text nobody can read."""
    _write_ledger(sandbox, _entry(req_id="REQ-ZZZ-001", hash="0" * 64))
    assert gate.main() == 1


def test_a_row_OUTSIDE_the_slice_scope_is_REPORTED_not_BLOCKED(sandbox: Path) -> None:
    """The accepted trade, asserted so it stays a decision rather than becoming an accident.

    Gating at slice entry means Draft and Deferred rows accumulate unexamined. An unbuilt row has
    driven nothing, so that is correct — but it means the register as a whole is never certified,
    only the parts entering build, and a wave that pulls in ten rows pays the whole review cost at
    its planning gate.
    """
    _write_scope(sandbox, slice=None, slice_scope=[])
    assert gate.main() == 0
    rows = gate.parse_rows((sandbox / "02_requirements/requirements_backbone.md").read_text())
    assert (
        len(rows) > 80
    ), "the register is full of unadjudicated rows and the gate is silent — by design"


def test_a_SECOND_header_shape_EXITS_TWO(sandbox: Path) -> None:
    """The repair, pinned (2026-08-13, found while writing re-baseline part 2).

    The first version of this gate matched headers by the prefix ``| REQ | Title |`` and was
    therefore blind to the CAP-21 table, whose header read ``| ID | Requirement | Cap | ...`` — a
    second shape, in the section written the day before, sitting inside the file the "exactly one
    header" assertion claimed to cover. Nothing was mis-hashed only because the two happened to
    order their columns identically. That is luck, not a control.

    Headers are now recognised by content, so a variant cannot hide behind a different first cell.
    """
    backbone = sandbox / "02_requirements/requirements_backbone.md"
    text = backbone.read_text()
    assert _HEADER_ROW in text
    variant = (
        "| ID | Requirement | Cap | Business purpose | What it does | Inputs | Method | Test "
        "| Acceptance | Status |"
    )
    backbone.write_text(text.replace(_HEADER_ROW, variant, 1))
    assert gate.main() == 2
