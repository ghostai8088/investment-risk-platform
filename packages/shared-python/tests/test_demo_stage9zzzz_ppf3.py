"""PPF-3 stage-13 conformance suite (OD-PPF-3) — the governed-number structural pins, SQLite tier.
The live full-chain seed + count/read/headline assertions are the PG twin (``_pg``); this tier pins
the module's own contract without the heavy chain.

The ``stage9zzzz`` filename component is LOAD-BEARING (the PPF-1/PPF-2 zero-pad hazard): it collates
immediately AFTER ``test_demo_stage9zzz_ppf2*`` — last among the demo stage suites — which is where
a runs-adding stage must run so the earlier stages assert their exact count pins first."""

from __future__ import annotations

from irp_shared.demo.dossiers import PPF3_UNIFIED_VAR_INITIAL, PPF3_UNIFIED_VAR_TIER
from irp_shared.demo.ppf3_stage13 import (
    _FUNDS,
    _UNION_FACTOR_CODES,
    Ppf3Stage13Summary,
)


def test_stage13_is_a_governed_number_in_its_story() -> None:
    """The demo's own contrast — a NEW governed number moves codes+records+runs (the CC-2 shape) —
    is stated where the runner reads first."""
    import irp_shared.demo.ppf3_stage13 as stage13

    doc = stage13.__doc__ or ""
    assert "GOVERNED-NUMBER stage" in doc
    assert "22/37/104 → 23/38/" in doc
    assert "TWENTIETH governed number" in doc


def test_stage13_targets_the_two_seeded_private_funds() -> None:
    """The two funds are exactly the PPF-1/HG-1-seeded PRIVATE_EQUITY + PRIVATE_CREDIT funds (zero
    new instruments); the union factor set is their combined promoted-proxy factors."""
    assert tuple(code for code, _q, _m in _FUNDS) == ("PE-HARBOR-IV", "PC-BRIDGEWATER-II")
    assert _UNION_FACTOR_CODES == ("FX_USD", "MF_RATES_GOV", "MF_CRSPD_IG")


def test_stage13_dossiers_are_high_high_awc() -> None:
    """The tier is HIGH materiality (the flagship public+private VaR — exposure+purpose, aligning
    with the sibling VaR flagships) / HIGH complexity (the genuinely-new repartition math) and the
    INITIAL is APPROVED_WITH_CONDITIONS; its finding keys are the ratified unified-VaR limitation
    substrings (block-diagonal, single-member/thin, unlevered, tail)."""
    assert PPF3_UNIFIED_VAR_TIER.materiality_rating == "HIGH"
    assert PPF3_UNIFIED_VAR_TIER.complexity_rating == "HIGH"
    assert PPF3_UNIFIED_VAR_INITIAL.outcome == "APPROVED_WITH_CONDITIONS"
    assert PPF3_UNIFIED_VAR_INITIAL.finding_keys == (
        "Block-diagonal ONLY",
        "Single-member / thin pure-private segments",
        "UNLEVERED (leverage held at the strategy-bucket average",
        "the VaR TAIL degrades under jumps/fat tails",
    )


def test_stage13_finding_keys_match_the_registered_limitations_exactly_once() -> None:
    """Fail-loud drift guard: each dossier finding key must be a substring of exactly one REGISTERED
    unified-VaR limitation row (the runner's own resolver refuses otherwise)."""
    from irp_shared.risk.bootstrap import VAR_UNIFIED_LIMITATIONS

    for key in PPF3_UNIFIED_VAR_INITIAL.finding_keys:
        assert sum(key in text for text in VAR_UNIFIED_LIMITATIONS) == 1, key


def test_stage13_summary_surfaces_the_headline_and_provenance() -> None:
    fields = set(Ppf3Stage13Summary.__dataclass_fields__)
    assert {
        "tenant_id",
        "portfolio_id",
        "unified_model_version_id",
        "unified_run_id",
        "total_run_id",
        "exposure_run_id",
        "factor_exposure_run_id",
        "covariance_run_id",
        "private_covariance_run_id",
        "sigma_unified",
        "sigma_total",
        "private_variance",
        "variance_delta",
        "initials_filed",
    } <= fields
