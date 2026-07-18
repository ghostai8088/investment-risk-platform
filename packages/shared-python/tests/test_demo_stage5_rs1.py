"""RS-1 stage-5 constants-conformance suite (OD-RS-1-E) — the HG-1 fence mirrored for the new
searched sets + the closure-token discipline. The ``stage5`` filename component is LOAD-BEARING:
local single-invocation batteries collect alphabetically, and an earlier-sorting name would seed
the stage-5 footprint before the campaign/hg1/multifamily/stage4 suites assert their pins."""

from __future__ import annotations

from irp_shared.demo.dossiers import (
    RS1_CLOSURE_FINDING,
    RS1_EWMA_INITIAL,
    RS1_SHRINKAGE_INITIAL,
    RS1_TRIGGERED_DOSSIERS,
    TIER_DOSSIERS,
)
from irp_shared.risk.bootstrap import (
    ES_TOTAL_LIMITATIONS,
    PROXY_WEIGHT_EWMA_ASSUMPTIONS_BASE,
    PROXY_WEIGHT_EWMA_LIMITATIONS,
    PROXY_WEIGHT_SHRINKAGE_EB_ASSUMPTIONS_BASE,
    PROXY_WEIGHT_SHRINKAGE_EB_LIMITATIONS,
    VAR_TOTAL_LIMITATIONS,
)

_RS1_TEXT_SURFACES: tuple[str, ...] = (
    RS1_CLOSURE_FINDING,
    *(d.scope_note for d in RS1_TRIGGERED_DOSSIERS.values()),
    *(d.conditions or "" for d in RS1_TRIGGERED_DOSSIERS.values()),
    RS1_EWMA_INITIAL.scope_note,
    RS1_EWMA_INITIAL.conditions or "",
    RS1_SHRINKAGE_INITIAL.scope_note,
    RS1_SHRINKAGE_INITIAL.conditions or "",
    *PROXY_WEIGHT_EWMA_ASSUMPTIONS_BASE,
    *PROXY_WEIGHT_EWMA_LIMITATIONS,
    *PROXY_WEIGHT_SHRINKAGE_EB_ASSUMPTIONS_BASE,
    *PROXY_WEIGHT_SHRINKAGE_EB_LIMITATIONS,
)


def test_initial_finding_keys_resolve_exactly_once_in_their_new_searched_sets() -> None:
    """Each INITIAL dossier key must match exactly ONE row of ITS version's registered
    limitation tuple (the fail-loud lookup executes at every re-seed; this pins it statically)."""
    for key in RS1_EWMA_INITIAL.finding_keys:
        assert sum(key in t for t in PROXY_WEIGHT_EWMA_LIMITATIONS) == 1, key
    for key in RS1_SHRINKAGE_INITIAL.finding_keys:
        assert sum(key in t for t in PROXY_WEIGHT_SHRINKAGE_EB_LIMITATIONS) == 1, key


def test_triggered_finding_keys_resolve_exactly_once_against_the_reworded_tuples() -> None:
    """The TRIGGERED keys resolve against the (RS-1 reworded) TOTAL-family tuples a FRESH
    campaign registers — and the SUPERSEDED key ('hostage…') still resolves for the historical
    MF-1 record's sake while being ABSENT from every RS-1 key set (the flip's static half)."""
    searched = {
        "risk.var.parametric_total": VAR_TOTAL_LIMITATIONS,
        "risk.var.parametric_es_total": ES_TOTAL_LIMITATIONS,
    }
    for code, dossier in RS1_TRIGGERED_DOSSIERS.items():
        for key in dossier.finding_keys:
            assert sum(key in t for t in searched[code]) == 1, (code, key)
        assert "hostage to the PA-3 estimate quality" not in dossier.finding_keys
    # the superseded key itself still matches exactly one registered row (MF-1's key resolves
    # on a fresh tenant; RS-1 closes the FINDING, not the registered limitation row).
    assert sum("hostage to the PA-3 estimate quality" in t for t in VAR_TOTAL_LIMITATIONS) == 1


def test_the_reworded_rows_realize_rs1_and_preserve_the_calendar_clause() -> None:
    """The verifier's doctrine hazard, pinned: the ES_TOTAL reword discharges ONLY the
    shrinkage/EWMA clause — the still-open calendar-aware v2 clause survives."""
    assert any("REALIZED" in t and "RS-1" in t for t in VAR_TOTAL_LIMITATIONS)
    assert any("REALIZED" in t and "RS-1" in t for t in ES_TOTAL_LIMITATIONS)
    assert any(
        "calendar-aware per-period trading-day counts remain" in t for t in ES_TOTAL_LIMITATIONS
    )


def test_no_rs1_text_carries_the_closed_rider_or_the_flywheel_token() -> None:
    """The closure-token discipline (the MF-1 'FL-1' precedent): the CLOSED rider token appears
    in NO fresh RS-1 conditions/scope text (it survives only in historical records + the
    registered limitation row), and no RS-1 text carries the MF-1 flywheel token."""
    for text in _RS1_TEXT_SURFACES:
        assert "hostage to the PA-3" not in text
        assert "FL-1" not in text


def test_stage5_mints_no_new_code_and_no_new_tier_dossier() -> None:
    """Stage 5 registers VERSIONS of an existing code — the campaign's 16-pin source is
    untouched and no RS1 tier dossier exists (the model keeps its campaign tier)."""
    assert len(TIER_DOSSIERS) == 16  # the campaign pin's source, unchanged
