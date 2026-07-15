"""PostgreSQL-only proofs for PA-4 ``var_result.residual_variance`` (ENT-027 total-family
realization, additive migration 0038), run as the constrained NOSUPERUSER/NOBYPASSRLS ``irp_app``
role (the CI/pipeline posture) — the ``test_var_pg.py`` twin.

``var_result`` already carries the symmetric FORCE-RLS policy + the P0001 append-only trigger
(proven for the plain family in ``test_var_pg.py``; migration 0038 adds ONE additive nullable
column, no new table/policy). Here we prove the NEW surface only: the ``residual_variance``
column round-trips its FULL 20dp precision under PG (``PreciseDecimal`` on a native ``NUMERIC``
column vs SQLite's fixed-scale TEXT emulation); a total-family run is tenant-isolated exactly like
a plain one; and the append-only trigger still blocks UPDATE/DELETE on a row that carries a
non-NULL ``residual_variance``.

The FULL upstream chain (portfolio -> holdings -> exposure run -> factors + returns ->
factor-exposure run + covariance run -> a hand-minted PROXY_WEIGHT_ESTIMATE run + its
ESTIMATION_SUMMARY row -> a promoted REGRESSION proxy_mapping -> a total-VaR run) executes through
the binders under ``set_tenant_context``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.exposure import ExposureActor, run_exposure
from irp_shared.marketdata import FxRateActor, ProxyMappingActor, capture_fx_rate
from irp_shared.marketdata.factor import (
    FactorActor,
    capture_factor,
    capture_factor_return,
    resolve_factor,
)
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk import (
    METRIC_TYPE_ESTIMATION_SUMMARY,
    RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
    CovarianceActor,
    FactorExposureActor,
    ProxyWeightEstimateResult,
    VarActor,
    promote_proxy_weight_estimate,
    register_covariance_model,
    register_factor_exposure_model,
    register_var_parametric_es_total_model,
    register_var_parametric_total_model,
    run_covariance,
    run_factor_exposure,
    run_var,
)
from irp_shared.snapshot import SnapshotActor
from irp_shared.snapshot.models import PURPOSE_PROXY_WEIGHT_INPUT
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_PA_4 = ("var_result",)
_DEPS = (
    "portfolio",
    "position",
    "valuation",
    "instrument",
    "legal_entity",
    "issuer",
    "currency",
    "fx_rate",
    "exposure_aggregate",
    "factor",
    "factor_return",
    "factor_exposure_result",
    "covariance_result",
    "proxy_mapping",
    "proxy_weight_estimate_result",
    "model",
    "model_version",
    # VW-1: every binder bind now reads the latest model_validation (the OD-B REJECTED gate).
    "model_validation",
    "model_assumption",
    "model_limitation",
)
_SNAP = ("dataset_snapshot", "dataset_snapshot_component")
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")
_RUN = ("calculation_run",)
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_VALID_AT = datetime(2026, 6, 1, tzinfo=UTC)
_KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
_VD = date(2026, 6, 1)
_D = (date(2026, 5, 26), date(2026, 5, 27), date(2026, 5, 28), date(2026, 5, 29))
_ACT = VarActor(actor_id="a")
_APPRAISAL_DAYS = 91
_MAX_ESTIMATE_AGE_DAYS = 400  # BT-2: the declared staleness policy (see test_var_total.py)
#: The 20dp-precision residual stdev — deliberately carries the FULL PreciseDecimal(20,12) scale
#: (not a round decimal) so a SQLite/PG divergence in the round-trip would be caught.
_RESIDUAL_STDEV = Decimal("0.040000000001")


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


@pytest.fixture(scope="module")
def app_url() -> str:
    superuser = make_engine(URL, poolclass=NullPool)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'irp_app') "
                "THEN CREATE ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "ELSE ALTER ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO irp_app"))
        for table in (*_PA_4, *_RUN, *_SNAP, *_DEPS, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _currency(tenant: str, code: str):  # noqa: ANN201
    from irp_shared.reference.models import Currency

    return Currency(tenant_id=tenant, code=code, name=code, valid_from=_T0)


def _seed_and_run_total(factory, tenant: str, *, es: bool = False):  # noqa: ANN001, ANN201
    """The FULL chain incl. the PA-4 idiosyncratic leg: holdings -> exposure run -> factor-
    exposure + covariance runs -> a hand-minted PROXY_WEIGHT_ESTIMATE run + ESTIMATION_SUMMARY ->
    a promoted REGRESSION proxy_mapping -> a COMPLETED total run. Returns the run's
    (calculation_run_id, residual_variance).

    ``es=True`` binds the ES-TOTAL family instead of total-VaR (ES-1) over the IDENTICAL chain —
    parameterized rather than duplicated, so the two families are provably exercised against the
    same seeded evidence."""
    session = factory()
    try:
        set_tenant_context(session, tenant)
        session.add(_currency(tenant, "USD"))
        session.add(_currency(tenant, "EUR"))
        session.flush()
        pf = create_portfolio(
            session,
            tenant_id=tenant,
            code=f"ACCT-{uuid.uuid4().hex[:6]}",
            name="acct",
            node_type="ACCOUNT",
            actor=PortfolioActor(actor_id="s"),
        ).id
        instrument_ids: dict[str, str] = {}
        for code, mark, ccy in (("I-USD", "300.00", "USD"), ("I-EUR", "400.00", "EUR")):
            inst = create_instrument(
                session,
                tenant_id=tenant,
                code=f"{code}-{uuid.uuid4().hex[:6]}",
                name="i",
                asset_class="BOND",
                actor=ReferenceActor(actor_id="s"),
            ).id
            instrument_ids[code] = inst
            create_position(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                acting_tenant=tenant,
                actor=PositionActor(actor_id="s"),
                quantity=Decimal("100"),
                valid_from=_T0,
            )
            create_valuation(
                session,
                portfolio_id=pf,
                instrument_id=inst,
                valuation_date=_VD,
                acting_tenant=tenant,
                actor=ValuationActor(actor_id="s"),
                mark_value=Decimal(mark),
                currency_code=ccy,
                valid_from=_T0,
            )
        capture_fx_rate(
            session,
            base_currency="EUR",
            quote_currency="USD",
            rate_date=_VD,
            rate=Decimal("1.000000000000"),
            acting_tenant=tenant,
            actor=FxRateActor(actor_id="s"),
            valid_from=_T0,
        )
        exposure = run_exposure(
            session,
            acting_tenant=tenant,
            actor=ExposureActor(actor_id="a"),
            code_version="v1",
            environment_id="ci",
            portfolio_id=pf,
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
            base_currency="USD",
        )
        factor_ids: list[str] = []
        for code, ccy, values in (
            (f"FX_USD_{uuid.uuid4().hex[:6]}", "USD", ("0.01", "0.02", "0.03", "0.04")),
            (f"FX_EUR_{uuid.uuid4().hex[:6]}", "EUR", ("0.04", "0.03", "0.02", "0.01")),
        ):
            fid = capture_factor(
                session,
                factor_code=code,
                factor_source="VENDOR_F",
                factor_family="CURRENCY",
                currency_code=ccy,
                acting_tenant=tenant,
                actor=FactorActor(actor_id="s"),
                valid_from=_T0,
            ).id
            factor = resolve_factor(session, fid, acting_tenant=tenant)
            for d, v in zip(_D, values, strict=True):
                capture_factor_return(
                    session,
                    factor,
                    return_date=d,
                    return_value=Decimal(v),
                    acting_tenant=tenant,
                    actor=FactorActor(actor_id="s"),
                    valid_from=_T0,
                )
            factor_ids.append(fid)
        fx_mv = register_factor_exposure_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1"
        )
        fx_run = run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=fx_mv.id,
            exposure_run_id=exposure.run.run_id,
            factor_ids=factor_ids,
        )
        cov_mv = register_covariance_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", window_observations=4
        )
        cov_run = run_covariance(
            session,
            acting_tenant=tenant,
            actor=CovarianceActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=cov_mv.id,
            factor_ids=factor_ids,
            as_of_valid_at=_VALID_AT,
        )

        # PA-4: proxy-map I-USD via a REGRESSION mapping citing a completed proxy-weight estimate
        # (a hand-minted ESTIMATION_SUMMARY — every FK target is a REAL row, PG-enforced).
        from irp_shared.risk.bootstrap import register_proxy_weight_regression_model

        # BT-2 fixture realism: the estimate's input snapshot is what the REAL chain persists —
        # a PROXY_WEIGHT_INPUT header whose as_of_valuation_date is the regression SPAN END (the
        # two fields the staleness gate reads). Span end = 30 days before the covariance window
        # end -> a fresh estimate that passes the declared policy.
        from irp_shared.snapshot.service import _persist_snapshot

        snap = _persist_snapshot(
            session,
            acting_tenant=tenant,
            actor=SnapshotActor(actor_id="a"),
            specs=[],
            label="",
            purpose=PURPOSE_PROXY_WEIGHT_INPUT,
            as_of_valid_at=_VALID_AT,
            as_of_known_at=_KNOWN_AT,
            as_of_valuation_date=_D[3] - timedelta(days=30),
            binding_predicate_version="v1:test",
        )
        pw_mv = register_proxy_weight_regression_model(
            session, tenant_id=tenant, actor_id="a", code_version="risk-v1", min_observations=4
        )
        est_run = create_run(
            session,
            tenant_id=tenant,
            run_type=RUN_TYPE_PROXY_WEIGHT_ESTIMATE,
            initiated_by="a",
            input_snapshot_id=snap.id,
            model_version_id=pw_mv.id,
            code_version="risk-v1",
            environment_id="ci",
        )
        update_run_status(session, est_run, RunStatus.RUNNING, actor_id="a")
        session.add(
            ProxyWeightEstimateResult(
                tenant_id=tenant,
                calculation_run_id=est_run.run_id,
                input_snapshot_id=snap.id,
                model_version_id=pw_mv.id,
                portfolio_id=pf,
                instrument_id=instrument_ids["I-USD"],
                source_desmoothed_run_id=fx_run.run.run_id,
                metric_type=METRIC_TYPE_ESTIMATION_SUMMARY,
                factor_id=None,
                metric_value=Decimal("0.8"),
                std_error=None,
                n_observations=6,
                n_regressors=1,
                residual_stdev=_RESIDUAL_STDEV,
                min_observations=4,
                series_currency="USD",
            )
        )
        session.flush()
        update_run_status(session, est_run, RunStatus.COMPLETED, actor_id="a")
        promote_proxy_weight_estimate(
            session,
            private_instrument_id=instrument_ids["I-USD"],
            factor_id=factor_ids[0],
            weight=Decimal("0.5"),
            acting_tenant=tenant,
            actor=ProxyMappingActor(actor_id="a"),
            source_calculation_run_id=est_run.run_id,
        )

        register = (
            register_var_parametric_es_total_model if es else register_var_parametric_total_model
        )
        total_mv = register(
            session,
            tenant_id=tenant,
            actor_id="a",
            code_version="risk-v1",
            confidence_level="0.95",
            appraisal_days=_APPRAISAL_DAYS,
            max_estimate_age_days=_MAX_ESTIMATE_AGE_DAYS,
        )
        session.flush()
        result = run_var(
            session,
            acting_tenant=tenant,
            actor=_ACT,
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=total_mv.id,
            exposure_run_id=fx_run.run.run_id,
            covariance_run_id=cov_run.run.run_id,
        )
        assert result.status == "COMPLETED" and len(result.rows) == 1
        row = result.rows[0]
        assert row.metric_type == ("ES_PARAMETRIC" if es else "VAR_PARAMETRIC_TOTAL")
        assert row.residual_variance is not None and row.residual_variance > 0
        session.commit()
        return result.run.run_id, row.residual_variance
    finally:
        session.close()


def test_residual_variance_round_trips_full_precision(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    run_id, residual_variance = _seed_and_run_total(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        db_value = session.execute(
            text(
                "SELECT residual_variance, metric_type FROM var_result "
                "WHERE calculation_run_id = :r"
            ),
            {"r": run_id},
        ).one()
        # The full 20dp scale round-trips EXACTLY (a native PG NUMERIC(38,20), not SQLite's
        # fixed-scale TEXT emulation — the P3-4 covariance precision lesson, applied here).
        assert Decimal(db_value[0]) == residual_variance
        assert db_value[1] == "VAR_PARAMETRIC_TOTAL"
    finally:
        session.close()
        engine.dispose()


def test_tenant_isolation_total_family(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    run1, _rv1 = _seed_and_run_total(factory, t1)
    _seed_and_run_total(factory, t2)

    session = factory()
    try:
        set_tenant_context(session, t1)
        rows = session.execute(
            text(
                "SELECT calculation_run_id FROM var_result "
                "WHERE metric_type = 'VAR_PARAMETRIC_TOTAL'"
            )
        ).fetchall()
        assert rows and all(str(r[0]) == run1 for r in rows)  # only t1's row visible
    finally:
        session.close()
        engine.dispose()


def test_append_only_trigger_blocks_update_and_delete_on_total_row(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    _seed_and_run_total(factory, tenant)

    session = factory()
    try:
        set_tenant_context(session, tenant)
        # irp_app HAS UPDATE/DELETE grants -> a rejection is the P0001 trigger, not 42501. The
        # trigger fires regardless of WHICH column is touched — probe residual_variance itself.
        with pytest.raises(ProgrammingError) as upd:
            session.execute(
                text(
                    "UPDATE var_result SET residual_variance = 0 "
                    "WHERE metric_type = 'VAR_PARAMETRIC_TOTAL'"
                )
            )
        assert _is_append_only_violation(upd.value)
        session.rollback()
        set_tenant_context(session, tenant)
        with pytest.raises(ProgrammingError) as dele:  # the plain-twin's DELETE leg (review fold)
            session.execute(
                text("DELETE FROM var_result WHERE metric_type = 'VAR_PARAMETRIC_TOTAL'")
            )
        assert _is_append_only_violation(dele.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


# ---------- ES-1 + the BT-2 trigger (both halves) ----------


def test_es_total_row_satisfies_the_live_check_constraint(app_url: str) -> None:
    """ES-1: the ES row's compliance with ``ck_var_result_parametric_not_null`` is provable ONLY
    here. That CHECK (0028) exempts just ``VAR_HISTORICAL`` and forces z_score+sigma+
    covariance_run_id non-NULL on everything else — and it is **absent from the ORM**, so the
    entire SQLite battery is blind to it. An ES row that NULLed its (arithmetically unused)
    z_score would pass every other test in this repo and fail only in production."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    run_id, residual_variance = _seed_and_run_total(factory, tenant, es=True)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = session.execute(
            text(
                "SELECT metric_type, z_score, sigma, covariance_run_id, var_value, "
                "residual_variance, estimate_age_days FROM var_result "
                "WHERE calculation_run_id = :r"
            ),
            {"r": run_id},
        ).one()
        assert row[0] == "ES_PARAMETRIC"
        # The three columns the CHECK forces — the INSERT above proves the constraint holds.
        assert row[1] is not None and row[2] is not None and row[3] is not None
        # ...and the ES row genuinely does NOT reconcile against them: var_value = k*sigma, not
        # z*sigma. The multiplier lives in the model_version, never on the row (a registered
        # limitation — this is the recorded cost of ES-1 needing no migration).
        assert Decimal(row[1]) * Decimal(row[2]) != Decimal(row[4])
        assert Decimal(row[5]) == residual_variance  # PA-4's 20dp leg round-trips on ES too
        assert row[6] is not None  # BT-2's age echo rides the ES-total row
    finally:
        session.close()
        engine.dispose()


def test_estimate_age_days_round_trips_on_pg(app_url: str) -> None:
    """BT-2's recorded residual coverage gap ('no PG leg for the age column'), PAID — its trigger
    was 'the next slice touching var_result's PG suite', and ES-1 is that slice.

    The column landed in migration 0040 as an additive nullable Integer; nothing had yet proven it
    survives a real PG round-trip under RLS (SQLite's type affinity would mask a type error)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    run_id, _rv = _seed_and_run_total(factory, tenant)
    session = factory()
    try:
        set_tenant_context(session, tenant)
        row = session.execute(
            text(
                "SELECT estimate_age_days, pg_typeof(estimate_age_days)::text, metric_type "
                "FROM var_result WHERE calculation_run_id = :r"
            ),
            {"r": run_id},
        ).one()
        assert row[2] == "VAR_PARAMETRIC_TOTAL"
        assert row[0] is not None and isinstance(row[0], int)
        assert row[1] == "integer"  # a real PG integer, not a text/numeric affinity accident
        assert row[0] >= 0
    finally:
        session.close()
        engine.dispose()


def test_tenant_isolation_es_total_family(app_url: str) -> None:
    """The ES families inherit the SAME symmetric FORCE-RLS isolation — proven, not assumed."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    run1, _ = _seed_and_run_total(factory, t1, es=True)
    _seed_and_run_total(factory, t2, es=True)
    session = factory()
    try:
        set_tenant_context(session, t2)  # t2 must NOT see t1's ES row
        assert (
            session.execute(
                text("SELECT count(*) FROM var_result WHERE calculation_run_id = :r"),
                {"r": run1},
            ).scalar_one()
            == 0
        )
        set_tenant_context(session, t1)
        assert (
            session.execute(
                text("SELECT count(*) FROM var_result WHERE calculation_run_id = :r"),
                {"r": run1},
            ).scalar_one()
            == 1
        )
    finally:
        session.close()
        engine.dispose()
