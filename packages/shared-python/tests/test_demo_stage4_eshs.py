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


def test_latest_flagship_hs_row_tie_break_is_time_ordered_not_uuid(session) -> None:
    """BT-3 (the OQ-W7C-2 fold): two flagship rows at the SAME window_end must order by the
    IA write instant (``system_from``), never by uuid draw — the run ids here are chosen so
    the RETIRED uuid tie-break would pick the WRONG (earlier) row."""
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from irp_shared.demo.campaign import DEMO_TENANT_ID
    from irp_shared.demo.eshs_stage4 import _latest_flagship_hs_row
    from irp_shared.model.models import Model, ModelVersion
    from irp_shared.risk.bootstrap import VAR_HS_MODEL_CODE
    from irp_shared.risk.models import VarResult

    model = Model(tenant_id=DEMO_TENANT_ID, code=VAR_HS_MODEL_CODE, name="hs", model_type="RISK")
    session.add(model)
    session.flush()
    version = ModelVersion(
        tenant_id=DEMO_TENANT_ID,
        model_id=model.id,
        version_label="v1",
        code_version="demo-mg1",
    )
    session.add(version)
    session.flush()

    def _row(run_id: str, written: datetime, value: str) -> VarResult:
        return VarResult(
            tenant_id=DEMO_TENANT_ID,
            calculation_run_id=run_id,
            input_snapshot_id="11111111-1111-1111-1111-111111111111",
            model_version_id=version.id,
            exposure_run_id="22222222-2222-2222-2222-222222222222",
            metric_type="VAR_HISTORICAL",
            base_currency="USD",
            confidence_level=Decimal("0.9500"),
            horizon_days=1,
            var_value=Decimal(value),
            n_factors=3,
            n_observations=21,
            window_start=date(2026, 5, 1),
            window_end=date(2026, 6, 19),
            system_from=written,
        )

    # The EARLIER write carries the LARGER uuid; the LATER write the SMALLER — the retired
    # uuid tie-break would return the earlier row.
    session.add(
        _row(
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
            datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC),
            "112.042694",
        )
    )
    session.add(
        _row(
            "00000000-0000-0000-0000-000000000001",
            datetime(2026, 7, 19, 12, 0, 5, tzinfo=UTC),
            "113.239146",
        )
    )
    session.flush()

    assert _latest_flagship_hs_row(session).var_value == Decimal("113.239146")
