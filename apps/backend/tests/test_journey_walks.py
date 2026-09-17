"""The G5 bookkeeping gate's own proof (product re-baseline, 2026-09-17, DP-RB2-2).

**Why these controls.** G5 is the G2 shape applied to the product: a human walks a journey line on
the deployed stack and names the decision the persona would take; the script proves the act
happened, lapses it when the line's text moves, and refuses to merge a slice whose declared lines
nobody walked. The first draft asked the walker to describe the screen and a different engine broke
it in one pass (a description of five tables of strings passed). Every control below is one of the
ways this gate could go green while checking nothing, each demonstrated against the script before
the control was kept: a walk by a model, a walk off the roster, a WALKABLE row with no decision, a
walk of a line whose text has since changed, a walk on a build that is not an ancestor of the
commit, a walk followed by a rewrite of the screen, an empty scope nobody declared, a parser floor,
a blind discovery glob, and a close review that claims a line the ledger never saw walked.

Every control goes through ``gate.main()``, the real entry point, because helper tests prove the
logic and not that it is reachable (the 2026-08-14 lesson: one deleted line in ``main()`` left
20/20 helper tests green while the gate exited 0 over its own defect).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))

import check_journey_walks as gate  # noqa: E402

_INPUTS = (
    "02_requirements/personas_and_user_journeys.md",
    "02_requirements/journey_walk_ledger.jsonl",
    "02_requirements/g2_adjudicators.json",
    "02_requirements/journey_slice_scope.json",
)
_SUBJECT = "J-CRO-2"
_SOURCE_DIR = "apps/frontend/src/views/funds"
_REASONING = (
    "The headline row showed total exposure 412,300,000 USD, VaR 99/1d 3,110,000 USD and ES "
    "3,900,000 USD as of 2026-10-02 with provenance links; appetite is 3,500,000 so today's "
    "VaR is inside it."
)


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway git repository holding copies of the gate's inputs and the close reviews."""
    for rel in _INPUTS:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_ROOT / rel, dest)
    reviews = tmp_path / gate.CLOSE_REVIEW_DIR
    reviews.mkdir(parents=True, exist_ok=True)
    for p in (_ROOT / gate.CLOSE_REVIEW_DIR).glob(gate.CLOSE_REVIEW_GLOB):
        shutil.copy(p, reviews / p.name)
    (tmp_path / _SOURCE_DIR).mkdir(parents=True)
    (tmp_path / _SOURCE_DIR / "FundOverview.tsx").write_text("export const v = 1;\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "deployed")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    return tmp_path


def _commit(sandbox: Path, msg: str = "next") -> str:
    _git(sandbox, "add", "-A")
    _git(sandbox, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(sandbox, "rev-parse", "HEAD")


def _write_scope(sandbox: Path, **kw: object) -> None:
    p = sandbox / "02_requirements/journey_slice_scope.json"
    data = json.loads(p.read_text())
    data.update(kw)
    p.write_text(json.dumps(data))


def _declare(sandbox: Path, *lines: str) -> None:
    _write_scope(sandbox, slice="CRO-1", journey_lines=list(lines), source_dirs=[_SOURCE_DIR])


def _hash_of(sandbox: Path, line: str) -> str:
    return gate.parse_lines(
        (sandbox / "02_requirements/personas_and_user_journeys.md").read_text()
    )[line]


def _row(sandbox: Path, **kw: object) -> dict:
    e = {
        "line": _SUBJECT,
        "line_hash": _hash_of(sandbox, _SUBJECT),
        "persona": "P-CRO",
        "walked_by": "ghostai8088",
        "deployed_head": _git(sandbox, "rev-parse", "HEAD"),
        "route": "/funds/global-multi-asset",
        "verdict": "WALKABLE",
        "decision": "Today's risk is inside appetite; no action before the 2L review.",
        "driving_value": "VaR 99/1d 3,110,000 USD against appetite 3,500,000 USD",
        "reasoning": _REASONING,
        "walked_at": "2026-10-02",
    }
    e.update(kw)
    return e


def _write_ledger(sandbox: Path, *rows: dict) -> None:
    p = sandbox / "02_requirements/journey_walk_ledger.jsonl"
    p.write_text("// test ledger\n" + "\n".join(json.dumps(r) for r in rows) + "\n")


# --- the real tree -------------------------------------------------------------------------


def test_the_real_tree_passes(sandbox: Path) -> None:
    """Positive control: an empty ledger with a declared no-scope is clean, by design."""
    assert gate.main() == 0


def test_the_ledger_is_EMPTY_at_birth_and_this_control_deletes_itself_at_the_first_walk() -> None:
    """The gate's weakest moment, recorded rather than hidden.

    On the day it ships G5 blocks nothing, because no slice has declared a line and no line has
    been walked. The controls below prove it CAN block. This control asserts the birth state so the
    first real walk is a deliberate act: when the first WALKABLE row lands in the real ledger, this
    test goes red and its instruction is to DELETE it in that same commit (the G4 precedent, whose
    zero-bindings control was deleted at the Wave-18 close per its own instruction).
    """
    rows = [
        ln
        for ln in (_ROOT / gate.LEDGER).read_text().splitlines()
        if ln.strip() and not ln.startswith("//")
    ]
    assert rows == [], "the first walk has landed — delete this control in the same commit"


def test_all_twelve_birth_lines_parse_and_the_floor_is_below_them() -> None:
    lines = gate.parse_lines((_ROOT / gate.JOURNEYS).read_text())
    assert {f"J-CRO-{i}" for i in range(1, 9)} <= set(lines)
    assert {f"J-PM-{i}" for i in range(1, 5)} <= set(lines)
    assert gate.MIN_JOURNEY_LINES <= len(lines)


# --- the slice gate ------------------------------------------------------------------------


def test_a_declared_line_NOBODY_walked_FAILS(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    assert gate.main() == 1


def test_a_declared_line_walked_WALKABLE_on_an_ancestor_PASSES(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox))
    _commit(sandbox, "the fold, touching nothing under the source dirs")
    assert gate.main() == 0


def test_a_NOT_WALKABLE_verdict_does_not_accept_the_line(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, verdict="NOT WALKABLE", decision="", driving_value=""))
    assert gate.main() == 1


def test_WALKABLE_without_a_DECISION_FAILS(sandbox: Path) -> None:
    """The exploit the different engine found: describing the screen is not using it."""
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, decision="   "))
    assert gate.main() == 1


def test_WALKABLE_without_a_DRIVING_VALUE_FAILS(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, driving_value=""))
    assert gate.main() == 1


def test_EDITING_the_line_text_LAPSES_the_walk(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox))
    p = sandbox / "02_requirements/personas_and_user_journeys.md"
    text = p.read_text()
    edited = re.sub(
        r"^(\| J-CRO-2 \|)(.*)(\|\s*)$",
        r"\1\2 and the fund's leverage ratio \3",
        text,
        count=1,
        flags=re.M,
    )
    assert edited != text, "the edit did not land on the subject line"
    p.write_text(edited)
    assert gate.main() == 1


def test_COSMETIC_edits_do_NOT_lapse_a_walk(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox))
    p = sandbox / "02_requirements/personas_and_user_journeys.md"
    text = p.read_text()
    cosmetic = text.replace("| J-CRO-2 | Headline row", "| **J-CRO-2** |  Headline   row", 1)
    assert cosmetic != text
    p.write_text(cosmetic)
    _commit(sandbox)
    assert gate.main() == 0


def test_a_walk_by_a_MODEL_FAILS(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, walked_by="MODEL:claude-opus-5"))
    assert gate.main() == 1


def test_a_MODEL_on_the_roster_STILL_FAILS(sandbox: Path) -> None:
    """The roster check alone caught the first version of this control, which meant the MODEL
    rule was untested (mutant M-G5-7 survived its removal). A model added to the roster is the
    case the rule exists for: the roster is a file the builder can edit."""
    roster = sandbox / "02_requirements/g2_adjudicators.json"
    data = json.loads(roster.read_text())
    data["adjudicators"].append("MODEL:claude-opus-5")
    roster.write_text(json.dumps(data))
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, walked_by="MODEL:claude-opus-5"))
    assert gate.main() == 1
    # And the row is invalid ANYWHERE in the ledger, not only when its line is in scope: the
    # slice filter in main() would silently skip it, and a ledger holding a model's walk of an
    # out-of-scope line is a ledger that will accept it the day that line enters scope.
    _write_scope(sandbox, slice=None, journey_lines=[], source_dirs=[])
    _write_ledger(
        sandbox,
        _row(
            sandbox,
            line="J-PM-3",
            line_hash=_hash_of(sandbox, "J-PM-3"),
            walked_by="MODEL:claude-opus-5",
        ),
    )
    assert gate.main() == 1


def test_a_walker_OFF_the_roster_FAILS(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, walked_by="someone-else"))
    assert gate.main() == 1


def test_a_short_REASONING_FAILS(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, reasoning="Looked fine to me."))
    assert gate.main() == 1


def test_a_walk_on_a_build_that_is_NOT_an_ancestor_FAILS(sandbox: Path) -> None:
    """A walk on some other branch's build is not a walk of this commit's lineage."""
    base = _git(sandbox, "rev-parse", "HEAD")
    _git(sandbox, "checkout", "-q", "-b", "elsewhere")
    (sandbox / "elsewhere.txt").write_text("x")
    other = _commit(sandbox, "elsewhere")
    _git(sandbox, "checkout", "-q", "-")
    assert _git(sandbox, "rev-parse", "HEAD") == base
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox, deployed_head=other))
    assert gate.main() == 1


def test_a_REWRITE_of_the_screen_after_the_walk_is_STALE_and_FAILS(sandbox: Path) -> None:
    """The lapse the first draft did not have: the walked build must still be the screen."""
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox))
    (sandbox / _SOURCE_DIR / "FundOverview.tsx").write_text("export const v = 2;\n")
    _commit(sandbox, "rewrote the screen after the walk")
    assert gate.main() == 1


def test_a_change_OUTSIDE_the_source_dirs_after_the_walk_is_NOT_stale(sandbox: Path) -> None:
    _declare(sandbox, _SUBJECT)
    _write_ledger(sandbox, _row(sandbox))
    (sandbox / "README.md").write_text("docs only\n")
    _commit(sandbox, "docs")
    assert gate.main() == 0


def test_a_scoped_line_that_is_NOT_a_journey_line_FAILS(sandbox: Path) -> None:
    _declare(sandbox, "J-CRO-99")
    assert gate.main() == 1


def test_a_line_OUTSIDE_the_scope_is_never_blocking(sandbox: Path) -> None:
    _write_scope(sandbox, slice=None, journey_lines=[], source_dirs=[])
    _write_ledger(sandbox, _row(sandbox, line="J-PM-3", line_hash=_hash_of(sandbox, "J-PM-3")))
    assert gate.main() == 0


# --- structural refusals -------------------------------------------------------------------


def test_a_DECLARED_slice_with_an_EMPTY_scope_EXITS_TWO(sandbox: Path) -> None:
    _write_scope(sandbox, slice="CRO-1", journey_lines=[], source_dirs=[_SOURCE_DIR])
    assert gate.main() == 2


def test_a_DECLARED_slice_with_NO_source_dirs_EXITS_TWO(sandbox: Path) -> None:
    _write_scope(sandbox, slice="CRO-1", journey_lines=[_SUBJECT], source_dirs=[])
    assert gate.main() == 2


def test_an_UNDECLARED_empty_scope_EXITS_TWO(sandbox: Path) -> None:
    _write_scope(sandbox, slice=None, journey_lines=[], source_dirs=[], no_scope_reason="")
    assert gate.main() == 2


def test_a_journeys_document_with_TOO_FEW_lines_EXITS_TWO(sandbox: Path) -> None:
    p = sandbox / "02_requirements/personas_and_user_journeys.md"
    text = p.read_text()
    thinned = "\n".join(ln for ln in text.splitlines() if not ln.startswith("| J-PM-"))
    p.write_text(thinned)
    assert gate.main() == 2


def test_a_DUPLICATE_journey_line_id_EXITS_TWO(sandbox: Path) -> None:
    p = sandbox / "02_requirements/personas_and_user_journeys.md"
    text = p.read_text()
    donor = next(ln for ln in text.splitlines() if ln.startswith("| J-CRO-2 |"))
    p.write_text(text.replace(donor, donor + "\n" + donor, 1))
    assert gate.main() == 2


def test_a_BLIND_discovery_glob_EXITS_TWO(sandbox: Path) -> None:
    for p in (sandbox / gate.CLOSE_REVIEW_DIR).glob(gate.CLOSE_REVIEW_GLOB):
        p.unlink()
    assert gate.main() == 2


def test_an_INVALID_ledger_line_EXITS_TWO(sandbox: Path) -> None:
    (sandbox / "02_requirements/journey_walk_ledger.jsonl").write_text("// x\n{not json\n")
    assert gate.main() == 2


# --- the wave-close section ---------------------------------------------------------------


def _write_close(sandbox: Path, wave: int, body: str) -> None:
    (sandbox / gate.CLOSE_REVIEW_DIR / f"wave_{wave}_close_review.md").write_text(
        f"# Wave {wave} close\n\n{body}\n\n## Next\n"
    )


def test_a_wave20_close_review_WITHOUT_the_section_FAILS(sandbox: Path) -> None:
    _write_close(sandbox, 20, "## 1. Delivered\n\nthings")
    assert gate.main() == 1


def test_a_wave20_close_review_claiming_an_UNWALKED_line_FAILS(sandbox: Path) -> None:
    _write_close(
        sandbox, 20, f"{gate.G5_HEADING}\n\n| Line | Slice |\n|---|---|\n| {_SUBJECT} | CRO-1 |"
    )
    assert gate.main() == 1


def test_a_wave20_close_review_claiming_a_WALKED_line_PASSES(sandbox: Path) -> None:
    _write_ledger(sandbox, _row(sandbox))
    _write_close(
        sandbox, 20, f"{gate.G5_HEADING}\n\n| Line | Slice |\n|---|---|\n| {_SUBJECT} | CRO-1 |"
    )
    _commit(sandbox)
    assert gate.main() == 0


def test_a_wave20_close_review_claiming_a_NON_EXISTENT_line_FAILS(sandbox: Path) -> None:
    _write_close(
        sandbox, 20, f"{gate.G5_HEADING}\n\n| Line | Slice |\n|---|---|\n| J-CRO-77 | CRO-1 |"
    )
    assert gate.main() == 1


def test_an_EMPTY_G5_table_FAILS_unless_the_wave_SAYS_it_covered_nothing(sandbox: Path) -> None:
    _write_close(sandbox, 20, f"{gate.G5_HEADING}\n\nnothing to see here")
    assert gate.main() == 1


def test_the_NONE_declaration_needs_a_REASON(sandbox: Path) -> None:
    _write_close(sandbox, 20, f"{gate.G5_HEADING}\n\n{gate.G5_NONE_MARK}.")
    assert gate.main() == 1


def test_the_NONE_declaration_WITH_a_reason_PASSES(sandbox: Path) -> None:
    _write_close(
        sandbox,
        20,
        f"{gate.G5_HEADING}\n\n{gate.G5_NONE_MARK} — this wave delivered the demo tenant only; no "
        f"screen entered build and no journey line was declared by any of its slices.",
    )
    assert gate.main() == 0


def test_HISTORICAL_close_reviews_are_NOT_retro_fitted(sandbox: Path) -> None:
    """Waves 1-19 carry no G5 section and must not be asked for one."""
    for wave, path in gate.close_reviews():
        if wave < gate.G5_FROM_WAVE:
            assert gate.G5_HEADING not in path.read_text()
    assert gate.main() == 0
