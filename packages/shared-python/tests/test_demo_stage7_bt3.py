"""BT-3 stage-7 unit tier: the conformance fence for the NEW dossier constants + the placement
rules (OD-BT-3-F). The ``stage7`` filename component is LOAD-BEARING: local full-PG runs collect
alphabetically, and this suite must run AFTER every prior stage's (the recurring discipline)."""

from __future__ import annotations

from irp_shared.demo.dossiers import (
    BT3_ES_BACKTEST_INITIAL,
    BT3_ES_BACKTEST_TIER,
    BT3_ESHS_C975_INITIAL,
    BT3_VARHS_C975_INITIAL,
    BT3_VB_V2_INITIAL,
    TIER_DOSSIERS,
)
from irp_shared.model.models import derive_model_tier
from irp_shared.risk.bootstrap import (
    ES_BACKTEST_ASSUMPTIONS_BASE,
    ES_BACKTEST_LIMITATIONS,
    ES_HS_LIMITATIONS,
    VAR_BACKTEST_V2_ASSUMPTIONS_EXTRA,
    VAR_BACKTEST_V2_LIMITATIONS,
    VAR_HS_LIMITATIONS,
)


def test_bt3_finding_keys_resolve_exactly_once_in_their_searched_sets() -> None:
    """Each dossier key matches exactly ONE row of ITS version's registered constant set —
    the fail-loud fence, mirrored per set (the HG-1 discipline)."""
    for dossier, rows in (
        (BT3_ES_BACKTEST_INITIAL, ES_BACKTEST_LIMITATIONS),
        (BT3_VB_V2_INITIAL, VAR_BACKTEST_V2_LIMITATIONS),
        (BT3_VARHS_C975_INITIAL, VAR_HS_LIMITATIONS),
        (BT3_ESHS_C975_INITIAL, ES_HS_LIMITATIONS),
    ):
        for key in dossier.finding_keys:
            matches = [t for t in rows if key in t]
            assert len(matches) == 1, (key, len(matches))


def test_es_backtest_tier_is_a_separate_constant_never_in_tier_dossiers() -> None:
    """The campaign PG suite derives its exactly-16 pin from TIER_DOSSIERS itself — the BT-3
    dossier MUST stay a separate module constant (the ES_HS_TIER shape; the Wave-7-close
    verifier's pin-arithmetic fold)."""
    assert "risk.es_backtest" not in TIER_DOSSIERS
    assert len(TIER_DOSSIERS) == 16  # the campaign pin's source, unchanged


def test_es_backtest_ratings_derive_tier_2() -> None:
    """MEDIUM/MEDIUM ⇒ TIER_2 under the ratified MG-1 matrix (the BT-1 var_backtest twin —
    outcomes-analysis machinery gates no capital)."""
    assert (
        BT3_ES_BACKTEST_TIER.materiality_rating,
        BT3_ES_BACKTEST_TIER.complexity_rating,
    ) == ("MEDIUM", "MEDIUM")
    assert derive_model_tier("MEDIUM", "MEDIUM") == "TIER_2"


def test_no_new_constant_carries_a_stale_flywheel_token() -> None:
    for rows in (
        ES_BACKTEST_ASSUMPTIONS_BASE,
        ES_BACKTEST_LIMITATIONS,
        VAR_BACKTEST_V2_ASSUMPTIONS_EXTRA,
        VAR_BACKTEST_V2_LIMITATIONS,
    ):
        for t in rows:
            assert "FL-1" not in t
    for d in (
        BT3_ES_BACKTEST_INITIAL,
        BT3_VB_V2_INITIAL,
        BT3_VARHS_C975_INITIAL,
        BT3_ESHS_C975_INITIAL,
    ):
        assert "FL-1" not in d.scope_note and "FL-1" not in (d.conditions or "")


def test_the_tee_reword_preserves_the_key_substring_exactly_once() -> None:
    """The BT3-V-2 invariant: the fresh-seed key-match re-runs against the REWORDED ES-HS
    constant, so 'DELIBERATELY not backtestable v1' must survive as a unique substring."""
    matches = [t for t in ES_HS_LIMITATIONS if "DELIBERATELY not backtestable v1" in t]
    assert len(matches) == 1
    assert "risk.es_backtest" in matches[0]  # the reword names the shipping home
