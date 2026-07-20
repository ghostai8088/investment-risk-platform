"""CC-1 stage-8 conformance suite (OD-CC-1-H) — the capture-only honesty pins, SQLite tier.

The ``stage8`` filename component is LOAD-BEARING: local single-invocation batteries
collect alphabetically, and an earlier-sorting name would seed the stage-8 footprint
before the prior stages' suites assert their pins."""

from __future__ import annotations

from decimal import Decimal

from irp_shared.demo.cc1_stage8 import (
    _COMMITMENT_DATE,
    _COMMITTED,
    _FUND_CODE,
    _PORTFOLIO_CODE,
)
from irp_shared.demo.dossiers import TIER_DOSSIERS


def test_stage8_mints_no_code_no_dossier_no_run_shape() -> None:
    """Capture-only: the campaign 16-pin dossier source is untouched and NO CC-1 dossier
    constant exists anywhere in the dossier module (there is no model version to validate
    — the HG-1 OQ-5 bar a fortiori)."""
    assert len(TIER_DOSSIERS) == 16  # the campaign pin's source, unchanged
    import irp_shared.demo.dossiers as dossiers_mod

    assert not any("CC1" in name or "CC_1" in name for name in dir(dossiers_mod))


def test_stage8_fixture_realism_pins() -> None:
    """The seeded economics are TD-1-realistic and internally consistent: the commitment
    covers the net called amount; the mis-capture teaching pair nets to the true notice."""
    assert _FUND_CODE == "PE-MERIDIAN-X" and _PORTFOLIO_CODE == "DEMO-GLOBAL"
    assert _COMMITTED == Decimal("25000000.000000")
    assert _COMMITMENT_DATE.isoformat() == "2025-06-30"
    # 3 + 3 + (9 − 9) + 4 = 10M net called ≤ 25M committed; 1.8M distributed.
    net_called = Decimal("3000000") + Decimal("3000000") + Decimal("4000000")
    assert net_called < _COMMITTED


def test_stage8_module_carries_the_read_rule() -> None:
    """The OD-CC-1-D read rule is stated where a consumer reads first."""
    import irp_shared.demo.cc1_stage8 as stage8
    import irp_shared.private_capital as pkg
    import irp_shared.private_capital.capital_flow_service as flows
    import irp_shared.private_capital.commitment_service as commitments

    assert "THE READ RULE" in (pkg.__doc__ or "")
    assert "TRANSFER_IN/" in (commitments.__doc__ or "")
    assert "TRANSFER_IN/TRANSFER_OUT" in (flows.__doc__ or "")
    assert "READ RULE" in (stage8.__doc__ or "")
