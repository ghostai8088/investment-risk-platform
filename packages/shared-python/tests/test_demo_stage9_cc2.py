"""CC-2 stage-9 conformance suite (OD-CC-2-G) — the governed-projection pins, SQLite tier.

The ``stage9`` filename component is LOAD-BEARING: local single-invocation batteries collect
alphabetically, and an earlier-sorting name would seed the stage-9 footprint before the prior
stages' suites assert their pins. (**stage10 zero-pad hazard**: ``stage10`` sorts BEFORE ``stage2``
lexically — a tenth stage MUST zero-pad its suite filename.)"""

from __future__ import annotations

from decimal import Decimal

from irp_shared.demo.cc2_stage9 import (
    _BOW,
    _FUND_LIFE,
    _GROWTH,
    _MARK_DATE,
    _MARK_VALUE,
    _RC_SCHEDULE,
    _YIELD_FLOOR,
)
from irp_shared.demo.dossiers import (
    CC2_PACING_INITIAL,
    CC2_PACING_TIER,
    TIER_DOSSIERS,
)


def test_stage9_dossiers_are_separate_constants_not_in_the_campaign_map() -> None:
    """The 20th code's dossiers are SEPARATE module constants — the campaign 16-pin dossier
    source is untouched (the ES_HS_TIER/BT3_ES_BACKTEST_TIER discipline)."""
    assert len(TIER_DOSSIERS) == 16
    assert "pacing" not in TIER_DOSSIERS
    assert CC2_PACING_TIER.materiality_rating == "MEDIUM"
    assert CC2_PACING_TIER.complexity_rating == "MEDIUM"
    assert CC2_PACING_INITIAL.outcome == "APPROVED_WITH_CONDITIONS"


def test_stage9_finding_keys_uniquely_match_registered_limitations() -> None:
    """Every INITIAL finding key resolves to exactly one REGISTERED pacing limitation row —
    the fail-loud key discipline, checked against the source of truth (the registrar's
    ``PACING_LIMITATIONS``) so a drift is caught before the live filing loop."""
    from irp_shared.pacing.bootstrap import PACING_LIMITATIONS

    for key in CC2_PACING_INITIAL.finding_keys:
        matches = [t for t in PACING_LIMITATIONS if key in t]
        assert len(matches) == 1, f"key {key!r} matched {len(matches)} limitation rows"


def test_stage9_fixture_realism_pins() -> None:
    """The declared parameters + the NAV anchor are TD-1-realistic and PE-shaped (our own
    choices, not TA's un-routed paper examples)."""
    assert _RC_SCHEDULE == [Decimal("0.25"), Decimal("0.333"), Decimal("0.5")]
    assert len(_RC_SCHEDULE) <= _FUND_LIFE
    assert _FUND_LIFE == 12 and _BOW == Decimal("2.5") and _GROWTH == Decimal("0.13")
    assert _YIELD_FLOOR == Decimal("0")
    # The mark is the mid-life NAV anchor, one anniversary after the 2025-06-30 vintage.
    assert _MARK_VALUE == Decimal("11200000.000000")
    assert _MARK_DATE.isoformat() == "2026-06-30"


def test_stage9_module_carries_the_capture_vs_governed_story() -> None:
    """The demo's own story — capture mints nothing, a projection is governed — is stated
    where the runner reads first (OD-CC-2-G)."""
    import irp_shared.demo.cc2_stage9 as stage9

    doc = stage9.__doc__ or ""
    assert "SEVENTEENTH governed number" in doc
    assert "20 codes / 35 records / 96 runs" in doc
    assert "NO constant minted" in doc
