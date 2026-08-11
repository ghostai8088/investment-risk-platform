"""The reproduction coverage census, asserted against the REGISTERS that publish it.

**Why this file exists (Wave-17 close, BLOCKING 1).** REPRO-2 part 2 took CTRL-018 from three
governed families to nineteen and touched no register at all — ``git diff --name-only
80e6b9f..4908b65`` filtered to ``09_``/``02_`` is empty. For a day, the three documents a compliance
assessor reads first each said the platform's flagship detective control covered *three of
twenty-one*, and two of them additionally asserted that the schedule write API **did not exist** —
a route that ships in the generated OpenAPI contract.

The number lives in exactly one place that cannot lie: the registry itself. Everything else is a
hand-mirrored copy, and this project's own history is unambiguous about what happens to those —
the Wave-16 close found the same class in the migration-head pins (21 stale in one fold), and the
answer there was the same as the answer here: make the copies answerable to the source.

Two assertions, and they fail for different reasons on purpose:

1. the live census still equals the vocabulary (the registry's own invariant, restated at the
   boundary where the documents read it); and
2. no register still carries a SUPERSEDED claim. That list only ever grows, and each entry is a
   sentence that was true when written and false when read — which is the whole failure mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from irp_shared.reproduction.registry import REPRODUCIBLE_FAMILIES, UNREPRODUCIBLE_FAMILIES

ROOT = Path(__file__).resolve().parents[3]

#: The registers that publish the coverage number. Adding a fourth is a decision: it means one more
#: hand-mirrored copy of a fact that has exactly one source.
REGISTERS = (
    "09_compliance_controls/control_matrix_skeleton.md",
    "02_requirements/requirements_backbone.md",
    "02_requirements/requirements_traceability_matrix.md",
)

#: Claims that were TRUE when written and are FALSE at HEAD. A register carrying one of these is
#: telling an assessor something the code contradicts.
#:
#: Note what each of these has in common: none is a typo or an oversight in isolation. Each was an
#: accurate, carefully-worded sentence whose subject moved underneath it while the sentence stayed
#: still. That is why the guard is a denylist of retired sentences rather than a style rule.
SUPERSEDED_CLAIMS = (
    # The REPRO-1-era coverage census, superseded by REPRO-2 part 2 on 2026-08-10.
    "three families are registered",
    "MACHINE-CHECKABLE for three families",
    "MACHINE-CHECKABLE for exactly three families",
    # The pre-REPRO-2 startability claim. `POST /schedules` ships on `schedule.manage`.
    "there is no schedule WRITE API",
    "nothing outside the proof harness creates a REPRODUCTION schedule at all",
    "nothing outside the proof harness creates a schedule yet",
)


def test_the_live_census_still_partitions_the_whole_vocabulary() -> None:
    """The source of truth, restated where the documents read it.

    Asserted as a partition — disjoint AND covering — rather than as a count, because a count is
    the thing that silently stayed plausible while the registers went stale.
    """
    reproducible = set(REPRODUCIBLE_FAMILIES)
    unreproducible = set(UNREPRODUCIBLE_FAMILIES)
    assert not (reproducible & unreproducible), (
        "a family is declared BOTH reproducible and unreproducible — the census no longer "
        "partitions anything"
    )
    assert reproducible, "the reproducible set is empty; every coverage claim below is vacuous"
    assert unreproducible == {"CONCENTRATION", "LIQUIDITY"}, (
        "the UNREPRODUCIBLE set changed. That is a governed change: both remaining exclusions are "
        "STRUCTURAL (CONCENTRATION re-pins current-head classifications; LIQUIDITY has a wall "
        "clock in its compute) and both are named in the CTRL-018 row. Update the registers in "
        "the same commit — see SUPERSEDED_CLAIMS below for what happens when that is skipped."
    )


#: An occurrence of a retired claim is permitted only when it is QUOTED — that is how this project
#: records supersession, and forbidding the quote outright would push the history out of the
#: documents.
#:
#: **This is the rule's third version, and the first two are recorded because each PASSED while
#: being structurally unable to fire — the exact shape of every inert control this close review
#: found, reproduced twice inside the guard written to catch it:**
#:
#: 1. *a retirement marker anywhere on the line* — the CTRL-018 row is one ~9,000-character line, so
#:    the words "struck" and "read " hundreds of characters away in unrelated prose satisfied it;
#: 2. *a retirement marker within 260 characters* — mutant W-C1 reverted the row's census and the
#:    AMENDMENT NOTE that follows the corrected text ("…until the Wave-17 close on 2026-08-11")
#:    sat inside the window and exempted the very claim it was describing as retired.
#:
#: So the rule is now the project's actual supersession convention rather than a proxy for it: a
#: retired sentence appears in these documents QUOTED. An occurrence is permitted only when a quote
#: mark abuts it. Prose that reintroduces the claim as live text cannot satisfy that by accident.
_QUOTES = '"“”'
_ABUT = 2


@pytest.mark.parametrize("register", REGISTERS)
def test_no_register_still_carries_a_superseded_coverage_claim(register: str) -> None:
    """The guard that would have caught BLOCKING 1 the day REPRO-2 part 2 merged."""
    text = (ROOT / register).read_text(encoding="utf-8")
    offenders = []
    for claim in SUPERSEDED_CLAIMS:
        start = text.find(claim)
        while start != -1:
            end = start + len(claim)
            quoted = any(c in _QUOTES for c in text[max(0, start - _ABUT) : start]) or any(
                c in _QUOTES for c in text[end : end + _ABUT]
            )
            if not quoted:
                offenders.append(claim)
                break
            start = text.find(claim, end)
    assert not offenders, (
        f"{register} still asserts, as live text: {offenders}. Each of these was true when it was "
        f"written and is false at HEAD. Correct it, and correct the OTHER registers in the same "
        f"commit — the wording is near-identical across all three, so fixing one leaves two false."
    )
