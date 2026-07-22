"""PPF-1 stage-11 conformance suite (OD-PPF-1-F) — the governed-number structural pins, SQLite tier.
The live full-chain seed + count/read assertions are the PG twin (``_pg``); this tier pins the
module's own contract without the heavy chain.

The ``stage9zz`` filename component is LOAD-BEARING (the CC-2/stage10 zero-pad hazard): a two-digit
``stage11`` suite sorts lexically BEFORE ``stage2``/``stage4``, so a single-invocation local PG
battery would seed the two extra runs before the earlier stages assert their exact count pins.
``stage9zz`` collates immediately AFTER ``test_demo_stage9z_api1_reads*`` — last among the demo
stage suites — which is where a runs-adding stage must run."""

from __future__ import annotations

from irp_shared.demo.dossiers import PPF1_PURE_PRIVATE_INITIAL, PPF1_PURE_PRIVATE_TIER
from irp_shared.demo.ppf1_stage11 import _SEGMENTS, Ppf1Stage11Summary


def test_stage11_is_a_governed_number_in_its_story() -> None:
    """The demo's own contrast — a NEW governed number moves codes+records+runs (the CC-2 shape,
    NOT stage 10's runs-only) — is stated where the runner reads first."""
    import irp_shared.demo.ppf1_stage11 as stage11

    doc = stage11.__doc__ or ""
    assert "GOVERNED-NUMBER stage" in doc
    assert "20/35/101 → **21/36/103**" in doc
    assert "EIGHTEENTH governed number" in doc


def test_stage11_targets_the_two_seeded_single_member_segments() -> None:
    """The two segments are exactly the seeded PRIVATE_EQUITY + PRIVATE_CREDIT members with both a
    desmoothing run AND a promoted REGRESSION blend (the verifier census — zero new seeding)."""
    assert _SEGMENTS == (
        ("PPF_PRIVATE_EQUITY_GLOBAL", "PE-HARBOR-IV"),
        ("PPF_PRIVATE_CREDIT_GLOBAL", "PC-BRIDGEWATER-II"),
    )


def test_stage11_dossiers_are_tier2_awc_with_registry_matching_keys() -> None:
    """The tier is MEDIUM/MEDIUM (TIER_2, the CC-2 precedent) and the INITIAL is APPROVED_WITH_
    CONDITIONS; its finding keys are the ratified pure-private limitation substrings."""
    assert PPF1_PURE_PRIVATE_TIER.materiality_rating == "MEDIUM"
    assert PPF1_PURE_PRIVATE_TIER.complexity_rating == "MEDIUM"
    assert PPF1_PURE_PRIVATE_INITIAL.outcome == "APPROVED_WITH_CONDITIONS"
    assert PPF1_PURE_PRIVATE_INITIAL.finding_keys == (
        "covariance block Omega_pp",
        "regresses MODEL OUTPUT",
        "named-gap refusal",
    )


def test_stage11_finding_keys_match_the_registered_limitations_exactly_once() -> None:
    """Fail-loud drift guard: each dossier finding key must be a substring of exactly one REGISTERED
    pure-private limitation row (the runner's own resolver refuses otherwise)."""
    from irp_shared.risk.bootstrap import PURE_PRIVATE_LIMITATIONS

    for key in PPF1_PURE_PRIVATE_INITIAL.finding_keys:
        assert sum(key in text for text in PURE_PRIVATE_LIMITATIONS) == 1, key


def test_stage11_summary_surfaces_both_run_ids() -> None:
    fields = set(Ppf1Stage11Summary.__dataclass_fields__)
    assert {
        "tenant_id",
        "pure_private_model_version_id",
        "run_ids",
        "segment_factor_ids",
        "total_period_rows",
        "initials_filed",
    } <= fields
