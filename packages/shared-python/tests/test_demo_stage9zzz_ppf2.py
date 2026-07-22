"""PPF-2 stage-12 conformance suite (OD-PPF-2-F) — the governed-number structural pins, SQLite tier.
The live full-chain seed + count/read assertions are the PG twin (``_pg``); this tier pins the
module's own contract without the heavy chain.

The ``stage9zzz`` filename component is LOAD-BEARING (the PPF-1/stage10 zero-pad hazard): it
collates immediately AFTER ``test_demo_stage9zz_ppf1*`` — last among the demo stage suites — which
is where a runs-adding stage must run so the earlier stages assert their exact count pins first."""

from __future__ import annotations

from irp_shared.demo.dossiers import PPF2_PRIVATE_COVARIANCE_INITIAL, PPF2_PRIVATE_COVARIANCE_TIER
from irp_shared.demo.ppf2_stage12 import _SEGMENT_CODES, Ppf2Stage12Summary


def test_stage12_is_a_governed_number_in_its_story() -> None:
    """The demo's own contrast — a NEW governed number moves codes+records+runs (the CC-2 shape) —
    is stated where the runner reads first."""
    import irp_shared.demo.ppf2_stage12 as stage12

    doc = stage12.__doc__ or ""
    assert "GOVERNED-NUMBER stage" in doc
    assert "21/36/103 → **22/37/104**" in doc
    assert "NINETEENTH governed number" in doc


def test_stage12_targets_the_two_seeded_private_segments() -> None:
    """The two segments are exactly the PPF-1-seeded PRIVATE_EQUITY + PRIVATE_CREDIT segments (the
    verifier census — zero new seeding)."""
    assert _SEGMENT_CODES == ("PPF_PRIVATE_EQUITY_GLOBAL", "PPF_PRIVATE_CREDIT_GLOBAL")


def test_stage12_dossiers_are_medium_awc_with_registry_matching_keys() -> None:
    """The tier is MEDIUM/MEDIUM (the pure-private substrate tier) and the INITIAL is
    APPROVED_WITH_CONDITIONS; its finding keys are the ratified private-covariance limitation
    substrings (block-diagonal approx, thin-N, no-shrinkage)."""
    assert PPF2_PRIVATE_COVARIANCE_TIER.materiality_rating == "MEDIUM"
    assert PPF2_PRIVATE_COVARIANCE_TIER.complexity_rating == "MEDIUM"
    assert PPF2_PRIVATE_COVARIANCE_INITIAL.outcome == "APPROVED_WITH_CONDITIONS"
    assert PPF2_PRIVATE_COVARIANCE_INITIAL.finding_keys == (
        "Block-diagonal APPROXIMATION",
        "no shrinkage (Vasicek/Ledoit-Wolf)",
        "Thin window by nature",
    )


def test_stage12_finding_keys_match_the_registered_limitations_exactly_once() -> None:
    """Fail-loud drift guard: each dossier finding key must be a substring of exactly one REGISTERED
    private-covariance limitation row (the runner's own resolver refuses otherwise)."""
    from irp_shared.risk.bootstrap import PRIVATE_COVARIANCE_LIMITATIONS

    for key in PPF2_PRIVATE_COVARIANCE_INITIAL.finding_keys:
        assert sum(key in text for text in PRIVATE_COVARIANCE_LIMITATIONS) == 1, key


def test_stage12_summary_surfaces_the_run_and_window() -> None:
    fields = set(Ppf2Stage12Summary.__dataclass_fields__)
    assert {
        "tenant_id",
        "private_covariance_model_version_id",
        "run_id",
        "segment_factor_ids",
        "window_observations",
        "matrix_rows",
        "initials_filed",
    } <= fields
