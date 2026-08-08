"""RPT-1 end to end: generate a report, then regenerate it byte-identically (I2, BR-9).

The identity tests in ``test_report_identity.py`` prove the RENDERER is deterministic. These prove
the whole path: real family rows → a pinned REPORT_INPUT snapshot → a persisted ENT-072 row →
regeneration from the pin alone. That distinction matters, because a deterministic renderer over a
non-deterministic PIN would still fail BR-9, and only this level can see it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.concentration.bootstrap import (
    CONCENTRATION_METHODOLOGY_REF,
    CONCENTRATION_MODEL_CODE,
)
from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.model.models import Model, ModelVersion
from irp_shared.models import Base
from irp_shared.perf.bootstrap import (
    ROLLING_RISK_METHODOLOGY_REF,
    ROLLING_RISK_MODEL_CODE,
)
from irp_shared.perf.events import RUN_TYPE_ROLLING_RISK
from irp_shared.report.families import VAR_REGISTERED_METHODOLOGIES, ReportProvenanceError
from irp_shared.report.models import ReportGeneration
from irp_shared.report.service import (
    ReportIdentityError,
    ReportInputError,
    generate_report,
    regenerate_report,
)
from irp_shared.risk.bootstrap import (
    VAR_METHODOLOGY_REF,
    VAR_UNIFIED_METHODOLOGY_REF,
    VAR_UNIFIED_MODEL_CODE,
)
from irp_shared.risk.events import RUN_TYPE_VAR
from irp_shared.risk.models import VarResult
from irp_shared.snapshot.models import DatasetSnapshot


@pytest.fixture
def session() -> Iterator[Session]:
    """This suite's engine — FK enforcement now comes from the FACTORY, not from here.

    This fixture used to carry its own ``PRAGMA foreign_keys=ON`` listener, installed at RPT-1 when
    the restore-cycle proof caught eighteen tests generating reports against a ``portfolio_id``
    resolving to nothing, and the global flip was carried as a measured 115-failure slice of its
    own. FK-1 paid that carry: ``make_engine`` enforces the pragma on every SQLite engine it
    builds, so the local listener became a SECOND mechanism for the same property — and two
    mechanisms is how the next reader trusts the wrong one (removing the factory's would have left
    this suite green while every other suite went blind again). Retired here; the enforcement is
    pinned by ``test_db_foreign_keys.py`` against the factory itself.
    """
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TENANT = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
_AS_OF = date(2026, 6, 30)
_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _assert_nothing_persisted(session: Session) -> None:
    """N1 (audit): a refusal leaves NO report row, NO REPORT run, NO REPORT_INPUT snapshot.

    The original assertions checked only ``ReportGeneration.count() == 0``. The remit demands "the
    absence of state", and `generate_report` creates a snapshot and a run BEFORE the report row —
    so counting only the last of the three artifacts is exactly the vacuity that would let a
    half-completed generation pass as a clean refusal.
    """
    from irp_shared.calc.models import CalculationRun
    from irp_shared.report.models import RUN_TYPE_REPORT

    assert session.query(ReportGeneration).count() == 0, "a report row survived a refusal"
    runs = (
        session.execute(select(CalculationRun).where(CalculationRun.run_type == RUN_TYPE_REPORT))
        .scalars()
        .all()
    )
    assert not runs, f"a refusal left {len(runs)} REPORT run(s) behind"
    snaps = (
        session.execute(select(DatasetSnapshot).where(DatasetSnapshot.purpose == "REPORT_INPUT"))
        .scalars()
        .all()
    )
    assert not snaps, f"a refusal left {len(snaps)} REPORT_INPUT snapshot(s) behind"


def _seed_portfolio(session: Session, *, tenant: str, portfolio_id: str | None = None) -> str:
    """A REAL portfolio row, resolve-or-create.

    ``report_generation.portfolio_id`` carries an FK to ``portfolio``. With the shared fixture's
    foreign keys OFF this was invisible; with them ON (see the ``session`` fixture) it is the
    difference between a report bound to a book and a report bound to a UUID nobody issued.
    """
    from irp_shared.portfolio.models import Portfolio

    if portfolio_id is not None:
        existing = session.get(Portfolio, portfolio_id)
        if existing is not None:
            return str(existing.id)
    pf = Portfolio(
        tenant_id=tenant,
        code=f"PF-{uuid.uuid4().hex[:8]}",
        name="Report fixture book",
        node_type="ACCOUNT",
        status="ACTIVE",
        record_version=1,
    )
    if portfolio_id is not None:
        pf.id = portfolio_id
    session.add(pf)
    session.flush()
    return str(pf.id)


def _seed_model_version(session: Session, *, tenant: str, code: str, ref: str | None) -> str:
    """A REAL registered model + version, because provenance is resolved from the row.

    The first version of this helper did not exist: the fixture stamped ``model_version_id=uuid4()``
    on the result rows, so no model version was bound at all. Under the old registry that was
    invisible — the section's methodology came from a static constant, so a report over a run whose
    model version DID NOT EXIST rendered a full, plausible provenance line. Resolving provenance
    from the row turned that into a refusal, and this fixture into a requirement.
    """
    # Resolve-or-create: `uq_model_tenant_code` is real, and the I3 proof seeds a SECOND run of the
    # same family in the same tenant. A helper that always INSERTed made that test fail on a
    # constraint violation rather than on what it was testing.
    model = session.execute(
        select(Model).where(Model.tenant_id == tenant, Model.code == code)
    ).scalar_one_or_none()
    if model is None:
        model = Model(
            tenant_id=tenant,
            code=code,
            name="seeded",
            model_type="RISK",
            is_active=True,
        )
        session.add(model)
        session.flush()
    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.tenant_id == tenant,
            ModelVersion.model_id == str(model.id),
            ModelVersion.version_label == "v1",
        )
    ).scalar_one_or_none()
    if version is None:
        version = ModelVersion(
            tenant_id=tenant,
            model_id=str(model.id),
            version_label="v1",
            methodology_ref=ref,
            status="REGISTERED",
        )
        session.add(version)
        session.flush()
    return str(version.id)


def _seed_concentration_run(
    session: Session,
    *,
    tenant: str = TENANT,
    portfolio_id: str | None = None,
    methodology_ref: str | None = CONCENTRATION_METHODOLOGY_REF,
) -> tuple[str, str]:
    """A COMPLETED concentration run with real result rows. Returns (run_id, portfolio_id)."""
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status

    pf = _seed_portfolio(session, tenant=tenant, portfolio_id=portfolio_id)
    version_id = _seed_model_version(
        session, tenant=tenant, code=CONCENTRATION_MODEL_CODE, ref=methodology_ref
    )
    snap = DatasetSnapshot(
        tenant_id=tenant,
        label="src",
        purpose="CONCENTRATION_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    run = create_run(
        session,
        tenant_id=tenant,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=pf,
    )
    session.flush()
    scheme = str(uuid.uuid4())
    # Both CHECKs read the same way for a CLASSIFICATION dimension: a non-ISSUER DETAIL row and a
    # classification SUMMARY metric each require scheme_id NOT NULL. Read off the constraints
    # rather than discovered by repeated failure.
    # DETAIL carries share_invested_long; SUMMARY carries metric_value. The shapes differ, which is
    # exactly the split that broke the first version of the family readers.
    for bucket, value in (("FINANCIALS", "0.412300"), ("__SUMMARY__", "0.412300")):
        session.add(
            ConcentrationResult(
                tenant_id=tenant,
                calculation_run_id=run.run_id,
                input_snapshot_id=snap.id,
                model_version_id=version_id,
                portfolio_id=pf,
                row_kind="DETAIL" if bucket != "__SUMMARY__" else "SUMMARY",
                dimension_kind="SECTOR_INDUSTRY",
                bucket_code=bucket,
                # The summary metric name is DIMENSION-QUALIFIED (MAX_SHARE_SECTOR_INDUSTRY);
                # a bare "MAX_SHARE" is refused by ck_concentration_result_summary_shape.
                metric_type=("SHARE" if bucket != "__SUMMARY__" else "MAX_SHARE_SECTOR_INDUSTRY"),
                share_invested_long=Decimal(value) if bucket != "__SUMMARY__" else None,
                metric_value=None if bucket != "__SUMMARY__" else Decimal(value),
                scheme_id=scheme,
                basis="NOT_APPLICABLE",
                # Every non-nullable column enumerated from the model rather than
                # discovered one IntegrityError at a time.
                gross_amount=Decimal("1000.000000"),
                long_amount=Decimal("1000.000000"),
                short_amount=Decimal("0.000000"),
                net_amount=Decimal("1000.000000"),
                denominator_basis="INVESTED_LONG",
            )
        )
    update_run_status(session, run, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()
    return str(run.run_id), pf


def _generate(session: Session, run_id: str, pf: str) -> tuple[ReportGeneration, str]:
    row, rendered = generate_report(
        session,
        acting_tenant=TENANT,
        actor_id="analyst",
        portfolio_id=pf,
        portfolio_code="P-RPT",
        as_of_date=_AS_OF,
        family_runs={"concentration": run_id},
        generated_at=_NOW,
    )
    return row, rendered.content_hash


def test_generate_then_regenerate_is_BYTE_IDENTICAL(session: Session) -> None:
    """I2 end to end — the slice's central claim, over the whole path rather than the renderer."""
    run_id, pf = _seed_concentration_run(session)
    row, first_hash = _generate(session, run_id, pf)
    session.flush()

    again = regenerate_report(session, report_id=str(row.id), acting_tenant=TENANT)
    assert again.content_hash == first_hash
    assert again.content_hash == row.content_hash


def test_the_report_is_run_bound_and_snapshot_gated(session: Session) -> None:
    """The governed-artifact contract: a report that cannot name its run and its pinned inputs is
    not reproducible, so both FKs are populated and the snapshot is a REPORT_INPUT."""
    run_id, pf = _seed_concentration_run(session)
    row, _ = _generate(session, run_id, pf)
    assert row.calculation_run_id is not None
    assert row.input_snapshot_id is not None
    snap = session.get(DatasetSnapshot, row.input_snapshot_id)
    assert snap is not None and snap.purpose == "REPORT_INPUT"


def test_generation_EMITS_the_governed_run_audit_events(session: Session) -> None:
    """The gap this test exists for: the FIRST draft of ``generate_report`` constructed
    ``CalculationRun(...)`` directly and emitted NO audit event — a governed evidence artifact with
    no record of its own creation. RPT-1 mints no audit code (CON-1's precedent); it rides
    CALC.RUN_CREATE + CALC.RUN_STATUS_CHANGE, and this asserts they are actually there."""
    run_id, pf = _seed_concentration_run(session)
    before = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "CALC.RUN_CREATE")
    ).all()
    _generate(session, run_id, pf)
    session.flush()
    after = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "CALC.RUN_CREATE")
    ).all()
    assert len(after) == len(before) + 1, "the report run emitted no CALC.RUN_CREATE"
    statuses = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "CALC.RUN_STATUS_CHANGE")
    ).all()
    assert statuses, "the report run emitted no CALC.RUN_STATUS_CHANGE"


def test_a_TAMPERED_stored_hash_makes_regeneration_REFUSE(session: Session) -> None:
    """The identity check made to FIRE (P9). Without this the regeneration path could compare
    nothing and still pass every happy-path test above.

    The stored hash is edited by a raw UPDATE deliberately — ``report_generation`` is IA
    append-only, so the ORM refuses; this reaches past that to simulate the only thing that could
    realistically diverge, and proves the comparison is live rather than decorative.
    """
    run_id, pf = _seed_concentration_run(session)
    row, _ = _generate(session, run_id, pf)
    session.flush()
    session.execute(
        ReportGeneration.__table__.update()
        .where(ReportGeneration.__table__.c.id == row.id)
        .values(content_hash="0" * 64)
    )
    session.expire_all()
    with pytest.raises(ReportIdentityError, match="did not regenerate identically"):
        regenerate_report(session, report_id=str(row.id), acting_tenant=TENANT)


def test_ANOTHER_TENANTS_report_is_refused(session: Session) -> None:
    """The tenant fence against the LIKELY hostile input — a REAL report owned by someone else, not
    a random UUID. The DEP-1 lesson: a nonexistent id refuses whether or not a fence exists."""
    run_id, pf = _seed_concentration_run(session)
    row, _ = _generate(session, run_id, pf)
    session.flush()
    with pytest.raises(ReportInputError, match="not visible"):
        regenerate_report(session, report_id=str(row.id), acting_tenant=OTHER_TENANT)


def test_a_run_from_ANOTHER_TENANT_cannot_be_bound(session: Session) -> None:
    """PostgreSQL FK checks bypass RLS, so a caller-supplied cross-tenant run id would otherwise be
    durably referenced by a governed artifact (the P3-5 doctrine). Refused pre-persist."""
    foreign_run, _ = _seed_concentration_run(session, tenant=OTHER_TENANT)
    # ATTRIBUTED, not just raised (pre-merge audit): build_report_snapshot now raises the SAME
    # ReportInputError from THREE consecutive fences (tenant+run_type, attribution, zero
    # values), so a bare-class assertion passes whichever one fires — and the cross-tenant
    # leg is precisely the one test_report_pg.py says lives in the application. Match the
    # message so the test proves WHICH fence refused.
    with pytest.raises(ReportInputError, match="not a visible"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=str(uuid.uuid4()),
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"concentration": foreign_run},
            generated_at=_NOW,
        )


def test_a_family_with_ZERO_values_is_REFUSED_with_nothing_persisted(session: Session) -> None:
    """The load-bearing refusal: an empty section reads as 'no risk' to a board, and is
    indistinguishable from a family that silently returned nothing. Asserts the ABSENCE of state —
    a refusal that half-persisted would be worse than none (the DATA-1 dangling-savepoint class)."""
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status

    snap = DatasetSnapshot(
        tenant_id=TENANT,
        label="empty",
        purpose="CONCENTRATION_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    # SCOPED to the portfolio the report will name: the RPT-2 attribution fence runs BEFORE the
    # zero-values check (an unscoped or mismatched run is refused earlier), so an unscoped fixture
    # would make this test pass on the WRONG refusal — the vacuity class, one layer up.
    zero_pf = _seed_portfolio(session, tenant=TENANT)
    empty = create_run(
        session,
        tenant_id=TENANT,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=zero_pf,
    )
    update_run_status(session, empty, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()

    before_reports = session.execute(select(ReportGeneration)).all()
    before_snaps = session.execute(
        select(DatasetSnapshot).where(DatasetSnapshot.purpose == "REPORT_INPUT")
    ).all()
    with pytest.raises(ReportInputError, match="ZERO values"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=zero_pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"concentration": str(empty.run_id)},
            generated_at=_NOW,
        )
    session.rollback()
    assert len(session.execute(select(ReportGeneration)).all()) == len(before_reports)
    assert len(
        session.execute(
            select(DatasetSnapshot).where(DatasetSnapshot.purpose == "REPORT_INPUT")
        ).all()
    ) == len(before_snaps)


def test_a_row_with_NO_VALUE_IN_EITHER_COLUMN_is_REFUSED_not_rendered_as_None(
    session: Session,
) -> None:
    """The NULL refusal, made to FIRE (P9) — added because a mutation proved it VACUOUS.

    Both value columns are NULLABLE and no CHECK requires either, so a row carrying neither is
    SCHEMA-LEGAL. Without this refusal such a row renders the string "None" where a governed number
    belongs — a placeholder in a board document, indistinguishable from a real figure to anyone not
    reading closely. The mutation that removed the refusal killed no test until this one existed.
    """
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status

    pf = _seed_portfolio(session, tenant=TENANT)
    version_id = _seed_model_version(
        session, tenant=TENANT, code=CONCENTRATION_MODEL_CODE, ref=CONCENTRATION_METHODOLOGY_REF
    )
    snap = DatasetSnapshot(
        tenant_id=TENANT,
        label="src",
        purpose="CONCENTRATION_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    run = create_run(
        session,
        tenant_id=TENANT,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=pf,
    )
    session.flush()
    session.add(
        ConcentrationResult(
            tenant_id=TENANT,
            calculation_run_id=run.run_id,
            input_snapshot_id=snap.id,
            model_version_id=version_id,
            portfolio_id=pf,
            row_kind="DETAIL",
            dimension_kind="SECTOR_INDUSTRY",
            bucket_code="FINANCIALS",
            metric_type="SHARE",
            scheme_id=str(uuid.uuid4()),
            basis="NOT_APPLICABLE",
            gross_amount=Decimal("1000.000000"),
            long_amount=Decimal("1000.000000"),
            short_amount=Decimal("0.000000"),
            net_amount=Decimal("1000.000000"),
            share_invested_long=None,  # the hostile case: schema-legal, valueless
            metric_value=None,
            denominator_basis="INVESTED_LONG",
        )
    )
    update_run_status(session, run, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()

    with pytest.raises(ValueError, match="no value in either column"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"concentration": str(run.run_id)},
            generated_at=_NOW,
        )


# --- I5: provenance resolved FROM THE BOUND RUN, and the allowlist that makes it non-forgeable ----


def _seed_var_run(
    session: Session,
    *,
    tenant: str = TENANT,
    model_code: str = VAR_UNIFIED_MODEL_CODE,
    methodology_ref: str | None = VAR_UNIFIED_METHODOLOGY_REF,
    portfolio_id: str | None = None,
) -> tuple[str, str]:
    """A COMPLETED VaR run with one real ``var_result`` row. Returns (run_id, portfolio_id)."""
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status

    pf = _seed_portfolio(session, tenant=tenant, portfolio_id=portfolio_id)
    version_id = _seed_model_version(session, tenant=tenant, code=model_code, ref=methodology_ref)
    snap = DatasetSnapshot(
        tenant_id=tenant,
        label="src",
        purpose="VAR_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    upstream = create_run(
        session, tenant_id=tenant, run_type="FACTOR_EXPOSURE", initiated_by="analyst"
    )
    run = create_run(
        session,
        tenant_id=tenant,
        run_type=RUN_TYPE_VAR,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=pf,
    )
    session.flush()
    session.add(
        VarResult(
            tenant_id=tenant,
            calculation_run_id=run.run_id,
            input_snapshot_id=snap.id,
            model_version_id=version_id,
            exposure_run_id=upstream.run_id,
            covariance_run_id=upstream.run_id,
            metric_type="VAR_PARAMETRIC_UNIFIED",
            base_currency="USD",
            confidence_level=Decimal("0.9750"),
            horizon_days=1,
            z_score=Decimal("1.959963984540"),
            sigma=Decimal("1250000.000000"),
            var_value=Decimal("2449954.980675"),
            n_factors=6,
            n_observations=252,
            window_start=date(2025, 7, 1),
            window_end=_AS_OF,
        )
    )
    update_run_status(session, run, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()
    return str(run.run_id), pf


def test_the_VAR_family_cites_the_model_ITS_OWN_RUN_bound(session: Session) -> None:
    """The test the static-pair design could not have passed.

    Seven registered models write into ``var_result`` under the single ``VAR`` run_type. A registry
    declaring one ``methodology_ref`` for the family would have cited the PLAIN parametric document
    on a UNIFIED run — a false provenance line on a governed number, rendered with full confidence.
    """
    run_id, pf = _seed_var_run(session)
    _row, rendered = generate_report(
        session,
        acting_tenant=TENANT,
        actor_id="analyst",
        portfolio_id=pf,
        portfolio_code="P-RPT",
        as_of_date=_AS_OF,
        family_runs={"var": run_id},
        generated_at=_NOW,
    )
    assert VAR_UNIFIED_MODEL_CODE in rendered.body
    assert VAR_UNIFIED_METHODOLOGY_REF in rendered.body
    assert (
        VAR_METHODOLOGY_REF not in rendered.body
    ), "cited the PLAIN parametric doc on a unified run"
    # The metric key names WHICH VaR and in what currency — "VaR: 2,449,954" alone is a disclosure
    # defect when one table holds parametric, total, unified, historical and both ES families.
    assert "VAR_PARAMETRIC_UNIFIED:USD" in rendered.body
    assert "2449954.980675" in rendered.body


def test_a_TENANT_STAMPED_methodology_ref_is_REFUSED_not_cited(session: Session) -> None:
    """``model_version.methodology_ref`` is tenant-supplied — ``POST /models`` can stamp any string.

    Without the registered-reference check, a tenant could make a board report cite a document of
    their own choosing while the number itself stayed genuine. The refusal fires on a REGISTERED
    model code with a SUBSTITUTED reference, which is the input that discriminates: an unregistered
    code is refused by a different branch entirely.
    """
    run_id, pf = _seed_var_run(
        session, methodology_ref="05_analytics_methodologies/chosen_by_the_tenant.md"
    )
    with pytest.raises(ReportProvenanceError, match="registered reference"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"var": run_id},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)


def test_an_UNREGISTERED_model_is_REFUSED(session: Session) -> None:
    """A VaR run bound to a model the report registry does not know. Fail-closed: a new VaR family
    must be added to the allowlist DELIBERATELY before a report can cite it."""
    run_id, pf = _seed_var_run(
        session,
        model_code="risk.var.experimental",
        methodology_ref="05_analytics_methodologies/x.md",
    )
    with pytest.raises(ReportProvenanceError, match="UNREGISTERED model"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"var": run_id},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)


def test_a_run_binding_NO_RESOLVABLE_MODEL_VERSION_is_REFUSED(session: Session) -> None:
    """The defect this suite's own fixture carried until provenance moved onto the row — and then a
    SECOND defect, which only the stronger version of this test could see.

    The result rows stamped a ``model_version_id`` that resolved to nothing. Under the static-pair
    registry that was INVISIBLE: the methodology came from a constant, so the report rendered a
    complete, plausible provenance line for a number whose model version did not exist.

    Rewriting the input from a random UUID to a REAL model version owned by ANOTHER TENANT then
    showed the reader resolving it happily — a report could have cited a model somebody else
    registered. PostgreSQL's RLS would have hidden it in production, which is exactly why the tenant
    check now lives in the query: a control that only works on one engine is a control whose absence
    no unit test can see.
    """
    run_id, pf = _seed_var_run(session)
    # A REAL model version owned by ANOTHER TENANT, not a random UUID. Two reasons, and the second
    # is the one that matters: the FK refuses a dangling id outright now that this suite enforces
    # foreign keys, and — the LIM-2 lesson — a nonexistent id is refused whether or not a tenant
    # fence exists, so it discriminates nothing. A real foreign-owned row is the input that does.
    foreign_version = _seed_model_version(
        session,
        tenant=OTHER_TENANT,
        code=VAR_UNIFIED_MODEL_CODE,
        ref=VAR_UNIFIED_METHODOLOGY_REF,
    )
    session.query(VarResult).filter(VarResult.calculation_run_id == run_id).update(
        {"model_version_id": foreign_version}
    )
    session.flush()
    with pytest.raises(ReportProvenanceError, match="no resolvable model version"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"var": run_id},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)


def test_a_NON_VAR_run_cannot_be_bound_to_the_VAR_family(session: Session) -> None:
    """The run_type filter (the PPF-2 defect class): ``var_result`` is shared across run families,
    so a read that does not fence the run_type activates every other family's rows."""
    run_id, pf = _seed_concentration_run(session)
    with pytest.raises(ReportInputError, match="not a visible VAR run"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"var": run_id},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)


def test_the_VAR_ALLOWLIST_covers_EVERY_registered_var_model(session: Session) -> None:
    """A census, not an enumeration: discovered from the risk bootstrap's own source.

    The allowlist is what stops a report citing a tenant-chosen document — which makes it exactly
    the kind of hand-written list that goes stale the moment an eighth VaR family ships. Discovery
    means the NEXT VaR model fails this test on the day it lands, instead of being silently
    un-reportable (fail-closed, but silently) or silently mis-cited.

    ``risk.var.`` with the trailing dot is deliberate: ``risk.var_backtest`` is a different family
    that does not write into ``var_result``, and a prefix without the dot would have swept it in.
    """
    import pathlib
    import re

    src = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "irp_shared" / "risk" / "bootstrap.py"
    ).read_text(encoding="utf8")
    discovered = set(re.findall(r'^[A-Z_]+_MODEL_CODE = "(risk\.var\.[a-z_]+)"', src, re.MULTILINE))
    assert discovered, "the discovery regex matched nothing — it has gone stale, not the allowlist"
    assert set(VAR_REGISTERED_METHODOLOGIES) == discovered, (
        "the report's VaR allowlist and the registered risk.var.* models have diverged: "
        f"missing {sorted(discovered - set(VAR_REGISTERED_METHODOLOGIES))}, "
        f"extra {sorted(set(VAR_REGISTERED_METHODOLOGIES) - discovered)}"
    )


def test_a_SUPPRESSED_rolling_risk_window_renders_its_SUPPRESSION_not_None(
    session: Session,
) -> None:
    """The third instance of the render-None defect, found by reading the schema rather than by a
    failing test.

    ``rolling_risk_result`` suppresses a window with too few observations and carries NULL. The
    reader's first version called ``str(metric_value)`` unconditionally, so a board reader would
    have seen "None" where the platform meant "deliberately not computed, and here is why".
    """
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status
    from irp_shared.perf.models import RollingRiskResult
    from irp_shared.report.families import _read_rolling_risk

    pf = _seed_portfolio(session, tenant=TENANT)
    version_id = _seed_model_version(
        session, tenant=TENANT, code=ROLLING_RISK_MODEL_CODE, ref=ROLLING_RISK_METHODOLOGY_REF
    )
    snap = DatasetSnapshot(
        tenant_id=TENANT,
        label="src",
        purpose="ROLLING_RISK_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    upstream = create_run(
        session, tenant_id=TENANT, run_type="PORTFOLIO_RETURN", initiated_by="analyst"
    )
    run = create_run(
        session,
        tenant_id=TENANT,
        run_type=RUN_TYPE_ROLLING_RISK,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=pf,
    )
    session.flush()
    for months, value, suppressed, reason in (
        (12, Decimal("0.142300000000"), False, None),
        (36, None, True, "insufficient observations"),
    ):
        session.add(
            RollingRiskResult(
                tenant_id=TENANT,
                calculation_run_id=run.run_id,
                input_snapshot_id=snap.id,
                model_version_id=version_id,
                portfolio_id=pf,
                portfolio_return_run_id=upstream.run_id,
                metric_type="VOLATILITY",
                window_months=months,
                period_start=date(2025, 7, 1),
                period_end=_AS_OF,
                metric_value=value,
                suppressed=suppressed,
                suppression_reason=reason,
                annualization_basis="MONTHLY_12",
                sampling_frequency="MONTHLY",
                n_observations=None if suppressed else months,
            )
        )
    update_run_status(session, run, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()

    values = dict(_read_rolling_risk(session, str(run.run_id), TENANT))
    assert values["VOLATILITY:12m:2026-06-30"] == "0.142300000000"
    suppressed_value = values["VOLATILITY:36m:2026-06-30"]
    assert "None" not in suppressed_value, "a suppressed window rendered as the string None"
    assert "SUPPRESSED" in suppressed_value
    assert "insufficient observations" in suppressed_value


# --- I3: a superseded input regenerates the ORIGINAL, and the report SAYS as-of-when -------------


def test_a_SUPERSEDING_correction_does_not_reach_a_historical_report(session: Session) -> None:
    """I3, executed rather than argued from the append-only property.

    **What a "correction" actually is here, stated because the honest answer is not obvious.** NO
    governed result family on this platform has an in-place correction path — every result table is
    IMMUTABLE_APPEND_ONLY, so a corrected number is a NEW COMPLETED run that supersedes the old one.
    That is what this test applies, and it is the only correction shape the platform admits.

    The report survives it because it pins VALUES, not run ids. Had it pinned only "which runs this
    bound" and re-read at render time — which looks sufficient, since those tables are append-only —
    the superseding run would not have reached it either, but only until the first family gained a
    correction path. Pinning the value makes the property STRUCTURAL rather than inherited.
    """
    run_id, pf = _seed_concentration_run(session)
    row, original_hash = _generate(session, run_id, pf)
    session.flush()

    # The correction: a SECOND completed run for the same portfolio, carrying a different number.
    corrected_run_id, _ = _seed_concentration_run(session, portfolio_id=pf)
    session.query(ConcentrationResult).filter(
        ConcentrationResult.calculation_run_id == corrected_run_id,
        ConcentrationResult.row_kind == "SUMMARY",
    ).update({"metric_value": Decimal("0.987600")})
    session.flush()
    assert corrected_run_id != run_id

    again = regenerate_report(session, report_id=str(row.id), acting_tenant=TENANT)
    assert again.content_hash == original_hash, "a later correction changed a historical report"
    assert "0.412300" in again.body, "the ORIGINAL value is no longer rendered"
    assert "0.987600" not in again.body, "the corrected value leaked into a historical report"


def test_the_report_SAYS_as_of_when_its_inputs_were_KNOWN(session: Session) -> None:
    """I3's second half — "and SAYS so".

    Byte-identical regeneration of a historical report is only honest if the reader can tell it IS
    historical. The as-of date says what period the numbers describe; the knowledge time says when
    they were known. A report carrying only the first is indistinguishable, on the page, from a
    current view of the same period.
    """
    run_id, pf = _seed_concentration_run(session)
    _row, rendered = generate_report(
        session,
        acting_tenant=TENANT,
        actor_id="analyst",
        portfolio_id=pf,
        portfolio_code="P-RPT",
        as_of_date=_AS_OF,
        family_runs={"concentration": run_id},
        generated_at=_NOW,
    )
    assert "As of 2026-06-30" in rendered.body, "the economic as-of is missing"
    assert "as known at" in rendered.body, "the KNOWLEDGE time is missing — I3 is not stated"
    assert _NOW.isoformat() in rendered.body


def test_the_report_does_NOT_RE_READ_the_source_rows_even_if_they_MOVE(session: Session) -> None:
    """I1's discriminating control — and it exists because the obvious I3 test did NOT discriminate.

    Mutation N10 replaced the renderer's pinned read with a LIVE re-read of the bound run, and
    ``test_a_SUPERSEDING_correction_does_not_reach_a_historical_report`` did not notice: a
    supersession creates a NEW run, so a live re-read of the ORIGINAL run still returns the original
    numbers. The supersession test proves the realistic correction path and nothing about where the
    renderer gets its values.

    The input that discriminates is the source rows of the BOUND run moving. That is something the
    schema forbids — ``concentration_result`` is IA append-only — and it is applied here through a
    bulk UPDATE that bypasses the ORM guards ON PURPOSE. The point is not that the rows can move; it
    is that the report's reproducibility must not DEPEND on their not moving, because that guarantee
    lives in a different table's constraints and a restore, a migration or a future correction path
    could each put it in question.
    """
    run_id, pf = _seed_concentration_run(session)
    row, original_hash = _generate(session, run_id, pf)
    session.flush()

    moved = (
        session.query(ConcentrationResult)
        .filter(
            ConcentrationResult.calculation_run_id == run_id,
            ConcentrationResult.row_kind == "SUMMARY",
        )
        .update({"metric_value": Decimal("0.999900")}, synchronize_session=False)
    )
    session.flush()
    session.expire_all()
    assert moved == 1, "the mutation did not land — this control would pass vacuously"

    again = regenerate_report(session, report_id=str(row.id), acting_tenant=TENANT)
    assert again.content_hash == original_hash, "the renderer re-read the live source rows"
    assert "0.412300" in again.body
    assert "0.999900" not in again.body, "a moved source row reached a pinned report"


# --- B1 (pre-merge audit): the report regenerates from the REPORT ID ALONE ------------------------


def test_regeneration_takes_NO_caller_supplied_render_input(session: Session) -> None:
    """The audit finding, made mechanical: `regenerate_report` accepts only ids.

    Asserted against the SIGNATURE rather than by passing a bad value, because the defect was not a
    wrong value — it was the parameter EXISTING. Anything a caller can vary is something the stored
    artifact does not pin, and every such parameter is a way for two "identical" regenerations to
    differ.
    """
    import inspect

    params = set(inspect.signature(regenerate_report).parameters)
    assert params == {"session", "report_id", "acting_tenant"}, (
        f"regenerate_report accepts caller-supplied render input: {sorted(params)} — every "
        "parameter beyond the ids is an unpinned degree of freedom in a reproducibility claim"
    )


def test_a_RENAMED_portfolio_still_regenerates_its_HISTORICAL_report(session: Session) -> None:
    """The input that DISCRIMINATES, which the original I2 proof could not reach.

    `portfolio.code` is effective-dated and mutable. It is rendered into the `<h1>` and therefore
    into the hashed bytes. While the code was a regeneration PARAMETER, a report stayed reproducible
    only for a caller who remembered the string the book had at generation time — so a rename made
    every historical report of that book unreproducible in practice, and the failure surfaced as a
    hash mismatch blamed on "a RENDERER change".

    Neither the unit proof nor the deployed restore proof could see it: both re-supplied the same
    constant. Renaming the book between generation and regeneration is what tells the two designs
    apart.
    """
    from irp_shared.portfolio.models import Portfolio

    run_id, pf = _seed_concentration_run(session)
    row, first_hash = _generate(session, run_id, pf)
    session.flush()

    book = session.get(Portfolio, pf)
    assert book is not None
    assert book.code != "RENAMED-AFTER-THE-FACT"
    book.code = "RENAMED-AFTER-THE-FACT"
    session.flush()

    again = regenerate_report(session, report_id=str(row.id), acting_tenant=TENANT)
    assert again.content_hash == first_hash, "a portfolio rename broke a historical report"
    assert row.portfolio_code in again.body, "the report did not render its PINNED code"
    assert (
        "RENAMED-AFTER-THE-FACT" not in again.body
    ), "the live code leaked into a historical report — the value is being re-read, not pinned"


# --- N2 (pre-merge audit): the GOVERNED_VALUE verify branch, BOTH arms ----------------------------


def test_verify_snapshot_REDDENS_when_a_report_s_source_rows_MOVE(session: Session) -> None:
    """The branch's stated purpose, executed — and it had no committed test until the audit.

    `_reresolve_content`'s GOVERNED_VALUE arm re-derives each family's values LIVE precisely so that
    `verify_snapshot` has something to compare against. The tempting implementation returns the
    pinned content unchanged and calls the component "immutable by construction" — which is the
    vacuous verification the component-kind census exists to prevent, because a branch that returns
    its input can never disagree with it.

    Both arms are asserted. Arm 1 alone would pass for a branch that always reports ``ok``; arm 2
    alone would pass for one that always reports drift. Only the pair shows discrimination.

    Note this does NOT weaken I1: the REPORT still regenerates byte-identically after such a move
    (`test_the_report_does_NOT_RE_READ_the_source_rows_even_if_they_MOVE`). The two are different
    questions — "is this artifact reproducible?" and "have its inputs been disturbed since?" — and a
    governed platform owes an honest answer to both.
    """
    from irp_shared.snapshot.service import verify_snapshot

    run_id, pf = _seed_concentration_run(session)
    row, _ = _generate(session, run_id, pf)
    session.flush()

    before = verify_snapshot(session, snapshot_id=str(row.input_snapshot_id), acting_tenant=TENANT)
    assert before.ok is True, f"an untouched report snapshot did not verify: {before}"
    assert before.component_count >= 1, "the snapshot pinned nothing — the check is vacuous"

    moved = (
        session.query(ConcentrationResult)
        .filter(
            ConcentrationResult.calculation_run_id == run_id,
            ConcentrationResult.row_kind == "SUMMARY",
        )
        .update({"metric_value": Decimal("0.999999")}, synchronize_session=False)
    )
    assert moved == 1, "the mutation did not land — arm 2 would pass vacuously"
    session.flush()
    session.expire_all()

    after = verify_snapshot(session, snapshot_id=str(row.input_snapshot_id), acting_tenant=TENANT)
    assert after.ok is False, "a MOVED source row did not redden the snapshot — the branch is blind"
    assert after.drifted_components, "reported not-ok while naming no drifted component"


def test_a_run_for_ANOTHER_PORTFOLIO_is_refused_by_NAME(session: Session) -> None:
    """The attribution fence's message, asserted where it is raised (the HTTP layer's detail is
    deliberately opaque, so the specific refusal belongs here).

    Found by the RPT-2 adversarial review, and it is the defect the whole review earned its cost
    on: the portfolio was tenant-fenced, each run was tenant-and-type fenced, and NOTHING related
    the two. Same tenant throughout — no cross-tenant control could ever have fired.
    """
    named_run, named_pf = _seed_concentration_run(session)
    other_pf = _seed_portfolio(session, tenant=TENANT)
    other_run, _ = _seed_concentration_run(session, portfolio_id=other_pf)
    assert named_pf != other_pf

    with pytest.raises(ReportInputError, match="was computed for portfolio"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=named_pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"concentration": other_run},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)
    assert named_run != other_run


def test_an_UNSCOPED_run_is_refused_rather_than_admitted(session: Session) -> None:
    """ "Unscoped" is not "matches". A run with no `scope_portfolio_id` cannot be shown to belong to
    the book the report names, and admitting it would leave the fence open to exactly the runs
    whose provenance is weakest."""
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status

    pf = _seed_portfolio(session, tenant=TENANT)
    snap = DatasetSnapshot(
        tenant_id=TENANT,
        label="src",
        purpose="CONCENTRATION_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    unscoped = create_run(
        session,
        tenant_id=TENANT,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
    )
    update_run_status(session, unscoped, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()

    # Its OWN message, not the mismatch one: the pre-merge audit found the two conflated, and a
    # caller told "computed for portfolio None" learns nothing about the real cause (a root
    # exposure run built through the snapshot-consume path, which records an honest NULL scope).
    with pytest.raises(ReportInputError, match="is UNSCOPED"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=_AS_OF,
            family_runs={"concentration": str(unscoped.run_id)},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)


def test_a_run_valued_at_ANOTHER_DATE_cannot_be_dated_as_this_one(session: Session) -> None:
    """The DATE half of the attribution class (pre-merge audit).

    The review's fold closed the run↔PORTFOLIO relation and left run↔DATE open: `as_of_date` is
    caller-asserted and renders as "As of {date}" at the head of a board artifact, while the bound
    run carries its own economic date on the snapshot it pinned. A report headed with one quarter's
    date carrying another quarter's numbers is the same misattribution one axis over — equally
    hashed, equally reproducible, equally audited, and equally wrong.
    """
    run_id, pf = _seed_concentration_run(session)  # its snapshot is valued at _AS_OF

    with pytest.raises(ReportInputError, match="refusing to date one period"):
        generate_report(
            session,
            acting_tenant=TENANT,
            actor_id="analyst",
            portfolio_id=pf,
            portfolio_code="P-RPT",
            as_of_date=date(2025, 12, 31),  # a DIFFERENT quarter
            family_runs={"concentration": run_id},
            generated_at=_NOW,
        )
    _assert_nothing_persisted(session)


def test_ISSUER_identity_rows_NEVER_reach_the_report(session: Session) -> None:
    """The pre-merge audit's CONFIRMED disclosure, closed and made to FIRE.

    `concentration.issuer.view` exists solely to withhold issuer identity from auditor_3l — the
    split three prior mints made and REF-1 shipped a BLOCKING defect by collapsing. `report.view`
    IS held by auditor_3l, so a reader taking every row of a concentration run handed the 3L
    auditor exactly that read through a new door, with every per-code holder pin still passing.

    Mutation H1 (delete the exclusion) killed NOTHING until this test existed — the same shape as
    G5 in the review fold, one layer up: the fix was written and believed, and nothing made it fire.
    """
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status
    from irp_shared.concentration.models import DIMENSION_KIND_ISSUER
    from irp_shared.reference.models import Issuer, LegalEntity

    # A REAL issuer behind a REAL legal entity: `concentration_result.issuer_id` carries an FK and
    # this suite enforces foreign keys (the RPT-1 lesson), so a random UUID would fail the INSERT
    # for the wrong reason and the test would never reach what it is testing.
    le = LegalEntity(
        tenant_id=TENANT, code=f"LE-{uuid.uuid4().hex[:8]}", name="Acme Holdings", is_active=True
    )
    session.add(le)
    session.flush()
    issuer = Issuer(tenant_id=TENANT, legal_entity_id=str(le.id), is_active=True)
    session.add(issuer)
    session.flush()

    pf = _seed_portfolio(session, tenant=TENANT)
    version_id = _seed_model_version(
        session, tenant=TENANT, code=CONCENTRATION_MODEL_CODE, ref=CONCENTRATION_METHODOLOGY_REF
    )
    snap = DatasetSnapshot(
        tenant_id=TENANT,
        label="src",
        purpose="CONCENTRATION_INPUT",
        as_of_valid_at=_NOW,
        as_of_known_at=_NOW,
        as_of_valuation_date=_AS_OF,
        binding_predicate_version="v1",
        component_count=0,
        manifest_hash="h",
    )
    session.add(snap)
    session.flush()
    run = create_run(
        session,
        tenant_id=TENANT,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
        scope_portfolio_id=pf,
    )
    session.flush()
    issuer_uuid = str(issuer.id)
    # A SUMMARY row (reportable) and an ISSUER DETAIL row (must never render).
    session.add(
        ConcentrationResult(
            tenant_id=TENANT,
            calculation_run_id=run.run_id,
            input_snapshot_id=snap.id,
            model_version_id=version_id,
            portfolio_id=pf,
            row_kind="SUMMARY",
            dimension_kind="SECTOR_INDUSTRY",
            bucket_code="__SUMMARY__",
            metric_type="MAX_SHARE_SECTOR_INDUSTRY",
            metric_value=Decimal("0.412300"),
            share_invested_long=None,
            scheme_id=str(uuid.uuid4()),
            basis="NOT_APPLICABLE",
            gross_amount=Decimal("1000.000000"),
            long_amount=Decimal("1000.000000"),
            short_amount=Decimal("0.000000"),
            net_amount=Decimal("1000.000000"),
            denominator_basis="INVESTED_LONG",
        )
    )
    session.add(
        ConcentrationResult(
            tenant_id=TENANT,
            calculation_run_id=run.run_id,
            input_snapshot_id=snap.id,
            model_version_id=version_id,
            portfolio_id=pf,
            row_kind="DETAIL",
            dimension_kind=DIMENSION_KIND_ISSUER,
            bucket_code="ACME-CORP-ISSUER",
            metric_type="SHARE",
            share_invested_long=Decimal("0.777700"),
            metric_value=None,
            issuer_id=issuer_uuid,
            basis="NOT_APPLICABLE",
            gross_amount=Decimal("1000.000000"),
            long_amount=Decimal("1000.000000"),
            short_amount=Decimal("0.000000"),
            net_amount=Decimal("1000.000000"),
            denominator_basis="INVESTED_LONG",
        )
    )
    update_run_status(session, run, RunStatus.COMPLETED, actor_id="analyst")
    session.flush()

    _row, rendered = generate_report(
        session,
        acting_tenant=TENANT,
        actor_id="analyst",
        portfolio_id=pf,
        portfolio_code="P-RPT",
        as_of_date=_AS_OF,
        family_runs={"concentration": str(run.run_id)},
        generated_at=_NOW,
    )
    assert "0.412300" in rendered.body, "the reportable summary metric did not render"
    assert "ACME-CORP-ISSUER" not in rendered.body, "an ISSUER bucket reached the report"
    assert issuer_uuid not in rendered.body, "issuer IDENTITY reached the report"
    assert "0.777700" not in rendered.body, "the issuer row's share reached the report"
