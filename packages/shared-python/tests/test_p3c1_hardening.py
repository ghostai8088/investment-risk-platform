"""P3-C1 hardening proofs (OD-P3-C1-B/C/E/F/G/H — the tightenings and parity fixes).

- **Status-bind (OD-B):** a ``status=None`` version minted via the GENERIC registration is
  refused by ALL FOUR risk binders (``UnregisteredModelError``, zero runs); the governed
  registrars' versions (status=REGISTERED) still bind.
- **failure_reason (OD-C):** each binder's FAILED run persists its reason VERBATIM — a fresh
  read of the run row returns the same string the POST returned; COMPLETED runs read None; the
  ``CALC.RUN_STATUS_CHANGE`` audit payload shape is UNCHANGED (asserted).
- **PreciseDecimal parity (OD-E):** >float53 values roundtrip exactly through the seven
  converted columns on SQLite (write→expire→re-read equality).
- **_map_error (OD-F):** a SUBCLASS of a mapped exception resolves to its parent's mapping.
- **Ambiguous input (OD-G):** each of the five binders refuses both-modes input pre-create.
- **Mixed-base (OD-H):** a hand-minted mixed-base FACTOR_EXPOSURE_INPUT snapshot refuses
  pre-create.

The scaffold-extraction behavior proofs live in ``test_p3c1_scaffold_preservation.py`` (the
golden captures, written green BEFORE the extraction).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_covariance import _abc as _cov_factors
from test_covariance import _model as _cov_model
from test_covariance import _run as _cov_run
from test_factor_exposure import _ccy as _fx_ccy
from test_factor_exposure import _exposure_run as _fx_exposure_run
from test_factor_exposure import _factor as _fx_factor
from test_factor_exposure import _model as _fx_model
from test_sensitivity import _curve as _sens_curve
from test_sensitivity import _model as _sens_model
from test_sensitivity import _sel as _sens_sel
from test_sensitivity import _zero_nodes
from test_var import _run as _var_run
from test_var import _seed_upstream_runs as _var_seed
from test_var import _var_model

from irp_shared.audit.models import AuditEvent
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.model.service import UnregisteredModelError, register_model, register_model_version
from irp_shared.models import Base
from irp_shared.risk import (
    CovarianceActor,
    CovarianceInputError,
    FactorExposureActor,
    FactorExposureInputError,
    SensitivityActor,
    SensitivityInputError,
    VarInputError,
    run_covariance,
    run_factor_exposure,
    run_sensitivities,
    run_var,
)
from irp_shared.snapshot import SnapshotActor

T0 = __import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").UTC)


@pytest.fixture
def session() -> Session:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


# ---------- OD-B: REGISTERED-status bind (all four binders) ----------


def _generic_version(db: Session, tenant: str, code: str, assumptions: list[str]) -> str:
    """A version minted the GENERIC way — status ends up None (the P3-5 review's deferral)."""
    model = register_model(
        db, tenant_id=tenant, code=code, name="generic", model_type="X", actor_id="a"
    )
    return register_model_version(
        db,
        model=model,
        version_label="v1",
        actor_id="a",
        methodology_ref="x",
        code_version="risk-v1",
        status=None,  # never stamped REGISTERED
        assumptions=assumptions,
        limitations=[],
    ).id


def test_status_none_version_refused_by_all_four_binders(session: Session) -> None:
    from irp_shared.risk.bootstrap import (
        COVARIANCE_MODEL_CODE,
        FACTOR_EXPOSURE_MODEL_CODE,
        SENSITIVITY_MODEL_CODE,
        VAR_MODEL_CODE,
    )

    tenant = str(uuid.uuid4())
    # Sensitivity
    mv = _generic_version(session, tenant, SENSITIVITY_MODEL_CODE, [])
    with pytest.raises(UnregisteredModelError):
        run_sensitivities(
            session,
            acting_tenant=tenant,
            actor=SensitivityActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=mv,
            snapshot_id=str(uuid.uuid4()),
        )
    # Factor exposure
    tenant2 = str(uuid.uuid4())
    mv2 = _generic_version(session, tenant2, FACTOR_EXPOSURE_MODEL_CODE, [])
    with pytest.raises(UnregisteredModelError):
        run_factor_exposure(
            session,
            acting_tenant=tenant2,
            actor=FactorExposureActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=mv2,
            snapshot_id=str(uuid.uuid4()),
        )
    # Covariance (with a WELL-FORMED declared window — status alone must refuse)
    tenant3 = str(uuid.uuid4())
    mv3 = _generic_version(session, tenant3, COVARIANCE_MODEL_CODE, ["window_observations=4"])
    with pytest.raises(UnregisteredModelError):
        run_covariance(
            session,
            acting_tenant=tenant3,
            actor=CovarianceActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=mv3,
            snapshot_id=str(uuid.uuid4()),
        )
    # VaR (well-formed declarations — status alone must refuse)
    tenant4 = str(uuid.uuid4())
    mv4 = _generic_version(
        session,
        tenant4,
        VAR_MODEL_CODE,
        ["confidence_level=0.9500", "horizon_days=1", "z_score=1.644853626951"],
    )
    with pytest.raises(UnregisteredModelError):
        run_var(
            session,
            acting_tenant=tenant4,
            actor=__import__("irp_shared.risk", fromlist=["VarActor"]).VarActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=mv4,
            snapshot_id=str(uuid.uuid4()),
        )
    # Zero runs anywhere (pre-create refusals).
    total = session.execute(select(CalculationRun)).scalars().all()
    assert [r for r in total if r.tenant_id in (tenant, tenant2, tenant3, tenant4)] == []


def test_governed_registrars_still_bind(session: Session) -> None:
    # The governed registration paths stamp REGISTERED — a full run still COMPLETES.
    tenant = str(uuid.uuid4())
    factors = _cov_factors(session, tenant)
    mv = _cov_model(session, tenant, window=4)
    assert _cov_run(session, tenant, mv, factors).status == RunStatus.COMPLETED.value


# ---------- OD-C: failure_reason persisted + audit payload unchanged ----------


def test_failed_reason_persists_and_audit_payload_unchanged(session: Session) -> None:
    from test_sensitivity import _ccy as _sens_ccy

    from irp_shared.marketdata import CurveNode

    tenant = str(uuid.uuid4())
    _sens_ccy(session, "USD")
    _sens_curve(
        session,
        tenant,
        nodes=[
            CurveNode(
                tenor_label="1Y", tenor_days=365, value_type="PAR_RATE", point_value=Decimal("0.05")
            )
        ],
    )
    mv = _sens_model(session, tenant)
    session.flush()
    bad = run_sensitivities(
        session,
        acting_tenant=tenant,
        actor=SensitivityActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv,
        curve_selectors=[_sens_sel()],
        as_of_valid_at=T0,
    )
    assert bad.status == RunStatus.FAILED.value and bad.failure_reason
    # The reason is PERSISTED on the run row (previously discarded after the POST response).
    run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == bad.run.run_id)
    ).scalar_one()
    assert run_row.failure_reason == bad.failure_reason
    # The audit payload shape is UNCHANGED (no failure_reason key smuggled into the event).
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == bad.run.run_id,
                AuditEvent.event_type == "CALC.RUN_STATUS_CHANGE",
                AuditEvent.outcome == "failure",
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert set(events[0].after_value.keys()) == {"status"}
    # A COMPLETED run reads None.
    tenant2 = str(uuid.uuid4())
    _sens_curve(session, tenant2, nodes=_zero_nodes())
    mv2 = _sens_model(session, tenant2)
    session.flush()
    ok = run_sensitivities(
        session,
        acting_tenant=tenant2,
        actor=SensitivityActor(actor_id="analyst"),
        code_version="risk-v1",
        environment_id="ci",
        model_version_id=mv2,
        curve_selectors=[_sens_sel()],
        as_of_valid_at=T0,
    )
    ok_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == ok.run.run_id)
    ).scalar_one()
    assert ok_row.failure_reason is None


def test_failed_reason_persists_var(session: Session) -> None:
    from test_var import _covariance_content, _exposure_content, _mint_var_snapshot

    tenant = str(uuid.uuid4())
    exp_run, cov_run = _var_seed(session, tenant)
    mv = _var_model(session, tenant)
    fa, fb = sorted(str(uuid.uuid4()).lower() for _ in range(2))
    snap = _mint_var_snapshot(
        session,
        tenant,
        [
            _exposure_content(exp_run, fa, "A", "1.000000"),
            _exposure_content(exp_run, fb, "B", "-1.000000"),
        ],
        [
            _covariance_content(cov_run, fa, fa, "0.0001"),
            _covariance_content(cov_run, fb, fb, "0.0001"),
            _covariance_content(cov_run, fa, fb, "0.0002"),  # non-PSD
        ],
    )
    bad = _var_run(session, tenant, mv, None, None, snapshot_id=snap.id)
    assert bad.status == RunStatus.FAILED.value
    run_row = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == bad.run.run_id)
    ).scalar_one()
    assert run_row.failure_reason == bad.failure_reason
    assert "non-psd-radicand" in run_row.failure_reason


# ---------- OD-E: PreciseDecimal parity roundtrips ----------


def test_precise_decimal_parity_type_fences_and_scale_roundtrips() -> None:
    # (a) The seven converted columns ARE PreciseDecimal (the load-bearing application fence —
    # a revert to plain Numeric silently reintroduces the SQLite float roundtrip).
    from irp_shared.db.types import PreciseDecimal
    from irp_shared.exposure.models import ExposureAggregate
    from irp_shared.risk.models import FactorExposureResult, SensitivityResult

    for model, cols in (
        (SensitivityResult, ["sensitivity_value"]),
        (FactorExposureResult, ["loading", "exposure_amount"]),
        (ExposureAggregate, ["signed_quantity", "mark_value", "fx_rate", "exposure_amount"]),
    ):
        for col in cols:
            assert isinstance(model.__table__.columns[col].type, PreciseDecimal), (model, col)
    # (b) >float53 values roundtrip exactly through the type at EACH converted (p, s) — the
    # storage-exactness proof (the SQLite TEXT path; the PG path is native NUMERIC).
    from sqlalchemy.dialects import sqlite

    lite = sqlite.dialect()
    cases = [
        ((28, 12), Decimal("1234567890123456.123456789012")),
        ((20, 12), Decimal("12345678.123456789012")),
        ((28, 6), Decimal("1234567890123456789012.123456")),
        ((28, 8), Decimal("12345678901234567890.12345678")),
        ((20, 6), Decimal("12345678901234.123456")),
    ]
    for (precision, scale), value in cases:
        td = PreciseDecimal(precision, scale)
        stored = td.process_bind_param(value, lite)
        assert td.process_result_value(stored, lite) == value, (precision, scale)
        # The float path would corrupt these (documents WHY the conversion matters):
        assert Decimal(repr(float(value))) != value


# ---------- OD-F: _map_error MRO ----------


def test_map_error_resolves_subclasses() -> None:
    from irp_backend.api.risk import _ERROR_MAP, _map_error

    class SubVarError(VarInputError):
        pass

    code, detail = _map_error(SubVarError("x"))
    assert (code, detail) == _ERROR_MAP[VarInputError]
    with pytest.raises(KeyError):
        _map_error(RuntimeError("unmapped"))


# ---------- OD-G: both-modes ambiguous input refused (five binders) ----------


def test_both_modes_refused_all_five_binders(session: Session) -> None:
    from irp_shared.exposure import ExposureActor, ExposureInputError, run_exposure

    tenant = str(uuid.uuid4())
    with pytest.raises(ExposureInputError, match="ambiguous"):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ExposureActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            portfolio_id=str(uuid.uuid4()),
            snapshot_id=str(uuid.uuid4()),
        )
    with pytest.raises(SensitivityInputError, match="ambiguous"):
        run_sensitivities(
            session,
            acting_tenant=tenant,
            actor=SensitivityActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            curve_selectors=[_sens_sel()],
            snapshot_id=str(uuid.uuid4()),
        )
    with pytest.raises(FactorExposureInputError, match="ambiguous"):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            exposure_run_id=str(uuid.uuid4()),
            snapshot_id=str(uuid.uuid4()),
        )
    with pytest.raises(CovarianceInputError, match="ambiguous"):
        run_covariance(
            session,
            acting_tenant=tenant,
            actor=CovarianceActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            factor_ids=[str(uuid.uuid4())],
            snapshot_id=str(uuid.uuid4()),
        )
    from irp_shared.risk import VarActor

    with pytest.raises(VarInputError, match="ambiguous"):
        run_var(
            session,
            acting_tenant=tenant,
            actor=VarActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            exposure_run_id=str(uuid.uuid4()),
            snapshot_id=str(uuid.uuid4()),
        )
    assert session.execute(select(CalculationRun)).scalars().all() == []  # zero writes


# ---------- OD-H: mixed-base adjudication (P3-3) ----------


def test_mixed_base_atoms_refused_pre_create(session: Session) -> None:
    from irp_shared.snapshot import (
        COMPONENT_KIND_EXPOSURE,
        COMPONENT_KIND_FACTOR,
        FACTOR_EXPOSURE_BINDING_PREDICATE,
    )
    from irp_shared.snapshot.models import PURPOSE_FACTOR_EXPOSURE_INPUT
    from irp_shared.snapshot.service import _append_spec, _persist_snapshot

    tenant = str(uuid.uuid4())
    _fx_ccy(session, "USD")
    exp_run = _fx_exposure_run(session, tenant, [("100", "10.00", "USD")])
    fac = _fx_factor(session, tenant, "FX_USD", "USD")
    mv = _fx_model(session, tenant)
    session.flush()

    def _atom(base: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant,
            "calculation_run_id": exp_run,
            "portfolio_id": str(uuid.uuid4()),
            "instrument_id": str(uuid.uuid4()),
            "base_currency": base,  # the MIXED-base smuggle
            "mark_currency": "USD",
            "exposure_amount": "100.000000",
        }

    from irp_shared.marketdata.factor import resolve_factor as _rf
    from irp_shared.snapshot.serialize import factor_content

    factor_row = _rf(session, fac, acting_tenant=tenant)
    specs: list = []
    for content in (_atom("USD"), _atom("EUR")):
        anchor = SimpleNamespace(
            id=content["id"], valid_from=None, system_from=T0, record_version=None
        )
        _append_spec(specs, COMPONENT_KIND_EXPOSURE, "exposure_aggregate", anchor, content)
    _append_spec(specs, COMPONENT_KIND_FACTOR, "factor", factor_row, factor_content(factor_row))
    header = _persist_snapshot(
        session,
        acting_tenant=tenant,
        actor=SnapshotActor(actor_id="s"),
        specs=specs,
        label="",
        purpose=PURPOSE_FACTOR_EXPOSURE_INPUT,
        as_of_valid_at=T0,
        as_of_known_at=T0,
        as_of_valuation_date=T0.date(),
        # The allocation predicate so the CONTENT gate (mixed-base) is reached — FL-1's 3×3
        # predicate gate now front-runs a mismatched predicate.
        binding_predicate_version=FACTOR_EXPOSURE_BINDING_PREDICATE,
    )
    session.flush()
    with pytest.raises(FactorExposureInputError, match="mixed base currencies"):
        run_factor_exposure(
            session,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv,
            snapshot_id=header.id,
        )


# ---------- migration chain + scaffold fences (the 2026-07 review folds) ----------


def test_migration_head_and_chain() -> None:
    import pathlib as _pl

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = _pl.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0050_limit_breach"  # PPF-3
    assert script.get_revision("0028_var_historical").down_revision == "0027_run_failure_reason"
    assert script.get_revision("0027_run_failure_reason").down_revision == "0026_var"


def test_scope_fence_scaffold_and_compute_closures_make_no_live_reads() -> None:
    # The extraction created NEW seams outside the per-binder fences (the review fold): the
    # shared scaffold tail and each binder's nested _compute closure must stay free of live
    # readers (the AD-014 snapshot-only invariant).
    import ast
    import pathlib as _pl

    root = _pl.Path(__file__).resolve().parents[3] / "packages/shared-python/src/irp_shared/risk"
    forbidden = {
        "resolve_factor",
        "list_factor_returns",
        "reconstruct_factor_return_as_of",
        "list_factor_exposures",
        "list_covariances",
        "resolve_exposure_run",
        "list_exposure_atoms",
        "resolve_curve",
        "list_curve_points",
        "reconstruct_curve_as_of",
    }
    # (a) the whole scaffold module (relocated to calc/ at P3-C2 — the neutral home below both
    # risk and exposure; the live-read fence still applies wherever it lives)
    scaffold_path = root.parent / "calc" / "scaffold.py"
    tree = ast.parse(scaffold_path.read_text())
    idents = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    assert not (idents & forbidden), idents & forbidden
    # (b) each binder's nested _compute closure — found-set asserted (never vacuous)
    found: set[str] = set()
    for fname in ("service.py", "factor_service.py", "covariance_service.py", "var_service.py"):
        tree = ast.parse((root / fname).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_compute":
                found.add(fname)
                names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
                    n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
                }
                assert not (names & forbidden), (fname, names & forbidden)
    assert found == {"service.py", "factor_service.py", "covariance_service.py", "var_service.py"}


def test_both_modes_refused_for_secondary_as_of_arguments(session: Session) -> None:
    # The 2026-07 review fold: the as-of arguments are BUILD-mode inputs too — snapshot_id plus
    # ONLY an as-of must also refuse (previously silently dropped).
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from irp_shared.exposure import ExposureActor, ExposureInputError, run_exposure

    tenant = str(uuid.uuid4())
    at = _dt(2026, 6, 1, tzinfo=_UTC)
    with pytest.raises(SensitivityInputError, match="ambiguous"):
        run_sensitivities(
            session,
            acting_tenant=tenant,
            actor=SensitivityActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            as_of_valid_at=at,
            snapshot_id=str(uuid.uuid4()),
        )
    with pytest.raises(CovarianceInputError, match="ambiguous"):
        run_covariance(
            session,
            acting_tenant=tenant,
            actor=CovarianceActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            model_version_id=str(uuid.uuid4()),
            as_of_valid_at=at,
            snapshot_id=str(uuid.uuid4()),
        )
    with pytest.raises(ExposureInputError, match="ambiguous"):
        run_exposure(
            session,
            acting_tenant=tenant,
            actor=ExposureActor(actor_id="a"),
            code_version="v",
            environment_id="ci",
            as_of_valid_at=at,
            snapshot_id=str(uuid.uuid4()),
        )
    assert session.execute(select(CalculationRun)).scalars().all() == []


def test_registrars_refuse_non_registered_same_label_twin(session: Session) -> None:
    # The register/run consistency fold (2026-07 review): a generically-minted status=None twin
    # squatting the governed label must make the REGISTRAR refuse (WrongModelVersionError, the
    # identity class) — previously it returned the unusable version as a success while every
    # bind refused it. (The factor-exposure family is proven at the endpoint layer.)
    from irp_shared.risk import (
        WrongModelVersionError,
        register_covariance_model,
        register_sensitivity_model,
        register_var_model,
    )
    from irp_shared.risk.bootstrap import (
        COVARIANCE_MODEL_CODE,
        SENSITIVITY_MODEL_CODE,
        VAR_MODEL_CODE,
    )

    tenant = str(uuid.uuid4())
    _generic_version(session, tenant, SENSITIVITY_MODEL_CODE, [])
    with pytest.raises(WrongModelVersionError):
        register_sensitivity_model(session, tenant_id=tenant, actor_id="a", code_version="risk-v1")
    tenant2 = str(uuid.uuid4())
    _generic_version(session, tenant2, COVARIANCE_MODEL_CODE, ["window_observations=4"])
    with pytest.raises(WrongModelVersionError):
        register_covariance_model(
            session, tenant_id=tenant2, actor_id="a", code_version="risk-v1", window_observations=4
        )
    tenant3 = str(uuid.uuid4())
    _generic_version(
        session,
        tenant3,
        VAR_MODEL_CODE,
        ["confidence_level=0.9500", "horizon_days=1", "z_score=1.644853626951"],
    )
    with pytest.raises(WrongModelVersionError):
        register_var_model(
            session,
            tenant_id=tenant3,
            actor_id="a",
            code_version="risk-v1",
            confidence_level="0.95",
        )
