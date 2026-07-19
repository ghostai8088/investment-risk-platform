"""DS-2 stage-6 constants-conformance suite (OD-DS-2-E) — the HG-1 fence mirrored for the new
searched sets + the no-new-code/no-TRIGGERED discipline. The ``stage6`` filename component is
LOAD-BEARING: local single-invocation batteries collect alphabetically, and an earlier-sorting
name would seed the stage-6 footprint before the prior stages' suites assert their pins."""

from __future__ import annotations

from decimal import Decimal

from irp_shared.demo.dossiers import DS2_AR1_INITIAL, DS2_OW_INITIAL, TIER_DOSSIERS
from irp_shared.demo.ds2_stage6 import _ALPHA_HAT_BAND, _DS2_MARK_VALUES
from irp_shared.perf.bootstrap import (
    DESMOOTHING_AR1_ESTIMATED_LIMITATIONS,
    DESMOOTHING_OKUNEV_WHITE_LIMITATIONS,
)


def test_initial_finding_keys_resolve_exactly_once_in_their_new_searched_sets() -> None:
    for key in DS2_AR1_INITIAL.finding_keys:
        assert sum(key in t for t in DESMOOTHING_AR1_ESTIMATED_LIMITATIONS) == 1, key
    for key in DS2_OW_INITIAL.finding_keys:
        assert sum(key in t for t in DESMOOTHING_OKUNEV_WHITE_LIMITATIONS) == 1, key


def test_no_stale_tokens_and_the_honest_claims() -> None:
    """No flywheel token; the AR1 dossier claims estimation-not-recovery (the R1 reframe) and
    the OW dossier carries the transcription-grade condition."""
    for text in (
        DS2_AR1_INITIAL.scope_note, DS2_AR1_INITIAL.conditions or "",
        DS2_OW_INITIAL.scope_note, DS2_OW_INITIAL.conditions or "",
    ):  # fmt: skip
        assert "FL-1" not in text and "hostage to the PA-3" not in text
    assert "NOT a recovery claim" in DS2_AR1_INITIAL.scope_note
    assert "UPWARD bias" in DS2_AR1_INITIAL.scope_note
    assert "re-verify" in (DS2_OW_INITIAL.conditions or "")


def test_stage6_mints_no_new_code_and_the_fixture_is_stable() -> None:
    """Stage 6 registers VERSIONS of an existing code (the campaign 16-pin source untouched);
    the frozen mark literals reproduce the planning-verified alpha-hat inside the tripwire
    band (the deterministic-draw honesty)."""
    from irp_shared.perf.desmoothing_kernel import estimate_ar1_alpha, observed_returns

    assert len(TIER_DOSSIERS) == 16  # the campaign pin's source, unchanged
    est = estimate_ar1_alpha(observed_returns([Decimal(v) for v in _DS2_MARK_VALUES]))
    lo, hi = _ALPHA_HAT_BAND
    assert lo < est.alpha_hat < hi
    # the specific planning-verified draw (documentation-grade pin, 4dp)
    assert est.alpha_hat.quantize(Decimal("0.0001")) == Decimal("0.4962")
