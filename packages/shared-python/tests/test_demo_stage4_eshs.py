"""ES-HS-1 stage-4 unit tier: the conformance fence for the NEW searched set + the dossier
placement rules (OD-ES-HS-1-F). The ``stage4`` filename component is LOAD-BEARING: local
full-PG runs collect alphabetically, and an earlier-sorting name would seed the 18th code
before the multifamily suite asserts its EXACTLY-17 pin (the planning verifier's catch)."""

from __future__ import annotations

from irp_shared.demo.dossiers import ES_HS_INITIAL, ES_HS_TIER, TIER_DOSSIERS
from irp_shared.model.models import derive_model_tier
from irp_shared.risk.bootstrap import ES_HS_ASSUMPTIONS_BASE, ES_HS_LIMITATIONS


def test_es_hs_finding_keys_resolve_exactly_once_in_the_new_searched_set() -> None:
    """The HG-1 fence rules for the NEW set: each dossier key matches exactly ONE registered
    row; no key is a duplicate substring; the existing 6-code _SEARCHED_SETS map is untouched
    (this module carries the NEW set's mirror — no existing pin moves)."""
    for key in ES_HS_INITIAL.finding_keys:
        matches = [t for t in ES_HS_LIMITATIONS if key in t]
        assert len(matches) == 1, (key, len(matches))


def test_no_new_constant_carries_the_flywheel_token() -> None:
    for rows in (ES_HS_ASSUMPTIONS_BASE, ES_HS_LIMITATIONS):
        for t in rows:
            assert "FL-1" not in t
    for text in (ES_HS_INITIAL.scope_note, ES_HS_INITIAL.conditions or ""):
        assert "FL-1" not in text
    assert "FL-1" not in ES_HS_TIER.rationale


def test_es_hs_tier_dossier_is_a_separate_constant_never_in_tier_dossiers() -> None:
    """The campaign PG suite derives its exactly-16 pin from TIER_DOSSIERS itself — the
    stage-4 dossier MUST stay a separate module constant (the MF1_LOADINGS_TIER shape)."""
    assert "risk.var.historical_es" not in TIER_DOSSIERS
    assert len(TIER_DOSSIERS) == 16  # the campaign pin's source, unchanged


def test_es_hs_ratings_derive_tier_1() -> None:
    """HIGH/MEDIUM ⇒ TIER_1 under the ratified MG-1 matrix — stated at ratification
    (OQ-ES-HS-1-5) so the 365-day ceiling lands with the ratings, not by surprise."""
    assert (ES_HS_TIER.materiality_rating, ES_HS_TIER.complexity_rating) == ("HIGH", "MEDIUM")
    assert derive_model_tier("HIGH", "MEDIUM") == "TIER_1"
