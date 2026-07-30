"""PostgreSQL tests for CON-1 (ENT-069) — the grain, the tenancy, and the pin drift doors.

Gated on ``IRP_TEST_DATABASE_URL``. Three families of proof that the unit tier is structurally
blind to:

- **The partial-index grain** (both row kinds, including the ratified duplicate-``__UNCLASSIFIED__``
  control) — declared for both dialects, but PG is the authoritative gate.
- **Symmetric FORCE RLS** on ``concentration_result`` (cross-tenant invisibility + the 42501
  write refusal under the constrained ``irp_app`` role).
- **The OQ-CON-1-7/9 drift doors**: the narrow issuer-edge pin drifts on an issuer move and does
  NOT drift on excluded fields; a tenant LEAF override changes the code-first closure content
  (the by-id idiom would never see it — the whole reason the CLASSIFICATION branch deviates).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from irp_shared.classification.service import (
    ClassificationActor,
    create_node,
    create_scheme,
    resolve_ancestors,
    resolve_node,
)
from irp_shared.concentration.models import (
    BUCKET_SUMMARY,
    BUCKET_UNCLASSIFIED,
    ConcentrationResult,
)
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.snapshot.service import (
    classification_assignment_closure_content,
    issuer_edge_content,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _is_rls_violation(exc: Exception) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == "42501"


@pytest.fixture(scope="module")
def app_url() -> str:
    """The constrained ``irp_app`` role with grants on this module's tables (the
    test_classification_pg convention)."""
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
        for table in ("concentration_result",):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _session(url: str, tenant: str):  # noqa: ANN202
    engine = make_engine(url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    set_tenant_context(session, tenant)
    return engine, session


def _stage_parents(session, tenant: str) -> tuple[str, str, str]:  # noqa: ANN001
    """A minimal (run, snapshot, model_version) FK chain for grain-control rows — superuser
    staging (RLS bypassed is irrelevant: the subject is the CONSTRAINT, not the policy)."""
    from irp_shared.calc.models import CalculationRun
    from irp_shared.model.models import Model, ModelVersion
    from irp_shared.snapshot.models import DatasetSnapshot

    now = datetime.now(UTC)
    model = Model(
        tenant_id=tenant,
        code=f"pgtest.concentration.{uuid.uuid4().hex[:8]}",
        name="pg grain fixture",
        model_type="CONCENTRATION",
        owner="pgtest",
        valid_from=now,
        record_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(model)
    session.flush()
    version = ModelVersion(
        tenant_id=tenant,
        model_id=model.id,
        version_label="v1",
        status="REGISTERED",
        system_from=now,
    )
    session.add(version)
    session.flush()
    snapshot = DatasetSnapshot(
        tenant_id=tenant,
        label="pg grain fixture",
        purpose="TEST",
        as_of_valid_at=now,
        as_of_known_at=now,
        as_of_valuation_date=now.date(),
        binding_predicate_version="v1:test",
        component_count=0,
        manifest_hash="0" * 64,
        system_from=now,
        created_at=now,
        updated_at=now,
    )
    session.add(snapshot)
    session.flush()
    run = CalculationRun(
        tenant_id=tenant,
        run_id=str(uuid.uuid4()),
        run_type="CONCENTRATION",
        status="COMPLETED",
        initiated_by="pgtest",
        input_snapshot_id=snapshot.id,
        model_version_id=version.id,
        system_from=now,
        created_at=now,
    )
    session.add(run)
    session.flush()
    return str(run.run_id), str(snapshot.id), str(version.id)


def _row(run_id: str, snapshot_id: str, version_id: str, tenant: str, **overrides):  # noqa: ANN003, ANN202
    base = dict(
        tenant_id=tenant,
        calculation_run_id=run_id,
        input_snapshot_id=snapshot_id,
        model_version_id=version_id,
        portfolio_id=str(uuid.uuid4()),
        row_kind="DETAIL",
        dimension_kind="SECTOR_INDUSTRY",
        metric_type="SHARE",
        bucket_code="C",
        issuer_id=None,
        scheme_id=str(uuid.uuid4()),
        basis="NOT_APPLICABLE",
        denominator_basis="INVESTED_LONG",
        gross_amount=Decimal("1"),
        long_amount=Decimal("1"),
        short_amount=Decimal("0"),
        net_amount=Decimal("1"),
        share_invested_long=Decimal("1.000000"),
        metric_value=None,
        coverage_ratio=None,
        coverage_classifiable=None,
        system_from=datetime.now(UTC),
    )
    base.update(overrides)
    return ConcentrationResult(**base)


class TestGrainConstraints:
    """The two PARTIAL unique indexes, proven on the authoritative engine — including the
    ratified duplicate-``__UNCLASSIFIED__`` control (the NULL-vacuity class the v3 grain died of
    is structurally gone: every key column is NOT NULL)."""

    def test_duplicate_summary_row_refused_and_detail_coexists(self) -> None:
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            run_id, snap_id, ver_id = _stage_parents(session, tenant)
            session.add(
                _row(
                    run_id,
                    snap_id,
                    ver_id,
                    tenant,
                    row_kind="SUMMARY",
                    metric_type="HHI_SECTOR_INDUSTRY",
                    bucket_code=BUCKET_SUMMARY,
                    share_invested_long=None,
                    metric_value=Decimal("0.36"),
                    coverage_ratio=Decimal("1"),
                    coverage_classifiable=Decimal("1"),
                )
            )
            # POSITIVE control: a DETAIL row sharing the run inserts alongside.
            session.add(_row(run_id, snap_id, ver_id, tenant))
            session.flush()
            # The duplicate SUMMARY (same run + metric_type) refuses.
            session.add(
                _row(
                    run_id,
                    snap_id,
                    ver_id,
                    tenant,
                    row_kind="SUMMARY",
                    metric_type="HHI_SECTOR_INDUSTRY",
                    bucket_code=BUCKET_SUMMARY,
                    share_invested_long=None,
                    metric_value=Decimal("0.37"),
                    coverage_ratio=Decimal("1"),
                    coverage_classifiable=Decimal("1"),
                )
            )
            with pytest.raises(IntegrityError, match="uq_concentration_summary"):
                session.flush()
        finally:
            session.close()
            engine.dispose()

    def test_duplicate_detail_and_duplicate_unclassified_refused(self) -> None:
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            run_id, snap_id, ver_id = _stage_parents(session, tenant)
            session.add(_row(run_id, snap_id, ver_id, tenant, bucket_code="C"))
            session.add(_row(run_id, snap_id, ver_id, tenant, bucket_code=BUCKET_UNCLASSIFIED))
            session.flush()
            session.add(_row(run_id, snap_id, ver_id, tenant, bucket_code="C"))
            with pytest.raises(IntegrityError, match="uq_concentration_detail"):
                session.flush()
            session.rollback()
            # THE RATIFIED CONTROL: a duplicate residual row refuses too (v3's NULL-keyed grain
            # was vacuous for exactly this row class).
            run_id, snap_id, ver_id = _stage_parents(session, tenant)
            session.add(_row(run_id, snap_id, ver_id, tenant, bucket_code=BUCKET_UNCLASSIFIED))
            session.flush()
            session.add(_row(run_id, snap_id, ver_id, tenant, bucket_code=BUCKET_UNCLASSIFIED))
            with pytest.raises(IntegrityError, match="uq_concentration_detail"):
                session.flush()
        finally:
            session.close()
            engine.dispose()

    def test_summary_shape_check_refuses_a_junk_SHARE_summary(self) -> None:
        """The v6 CHECK: metric_type='SHARE' on a SUMMARY row is refused BY THE DB."""
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            run_id, snap_id, ver_id = _stage_parents(session, tenant)
            session.add(
                _row(
                    run_id,
                    snap_id,
                    ver_id,
                    tenant,
                    row_kind="SUMMARY",
                    metric_type="SHARE",
                    bucket_code=BUCKET_SUMMARY,
                    share_invested_long=None,
                    metric_value=Decimal("1"),
                )
            )
            with pytest.raises(IntegrityError, match="summary_shape"):
                session.flush()
        finally:
            session.close()
            engine.dispose()

    def test_live_constraint_names_match_the_ORM_exactly(self) -> None:
        """Migration-vs-ORM parity read from the LIVE CATALOG, not from the two sources' text.

        The shipped 0057 passed FULL constraint names into ``op.create_table``, but the metadata
        naming convention prepends ``ck_<table>_`` itself — so every CHECK landed double-prefixed
        (``ck_concentration_result_ck_concentration_result_row_kind``) and the longest was
        TRUNCATED by PostgreSQL to 63 chars. A text-vs-text comparison of migration and ORM cannot
        see this; three independent review lanes read both files and missed it. Only the database
        knows the name it actually created, which is why this assertion asks the database.

        The `match=` substring in the sibling refusal tests hid it too: 'summary_shape' is a
        substring of the double-prefixed name, so those tests passed either way."""
        engine = make_engine(URL, poolclass=NullPool)
        try:
            with engine.begin() as conn:
                live = set(
                    conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conrelid = 'concentration_result'::regclass AND contype = 'c'"
                        )
                    ).scalars()
                )
            declared = {
                c.name
                for c in ConcentrationResult.__table__.constraints
                if type(c).__name__ == "CheckConstraint"
            }
            assert live == declared, (
                f"live CHECK names diverge from the ORM's.\nonly in DB: {sorted(live - declared)}"
                f"\nonly in ORM: {sorted(declared - live)}"
            )
            assert all(len(n) <= 63 for n in live), "a constraint name was truncated by PG"
        finally:
            engine.dispose()

    def test_issuer_identity_is_refused_on_a_NON_issuer_row(self) -> None:
        """The disclosure fence. Before it, a SECTOR_INDUSTRY DETAIL row carrying ``issuer_id``
        was schema-legal, and the ``concentration.view`` exclusion — which keys on
        (ISSUER, DETAIL) — would have handed that issuer identity to a caller holding no
        ``concentration.issuer.view``. Only binder discipline stood in the way."""
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            run_id, snap_id, ver_id = _stage_parents(session, tenant)
            session.add(
                _row(
                    run_id,
                    snap_id,
                    ver_id,
                    tenant,
                    dimension_kind="SECTOR_INDUSTRY",
                    bucket_code="C",
                    issuer_id=str(uuid.uuid4()),
                )
            )
            with pytest.raises(IntegrityError, match="issuer_only_on_issuer_rows"):
                session.flush()
        finally:
            session.close()
            engine.dispose()


class TestTenancy:
    """Symmetric FORCE RLS under the constrained role: invisible cross-tenant; 42501 on a
    cross-tenant write."""

    def test_rows_invisible_cross_tenant_and_write_refused(self, app_url: str) -> None:
        tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
        # Stage under superuser (parents + one row) for tenant A.
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        stage = factory()
        set_tenant_context(stage, tenant_a)
        run_id, snap_id, ver_id = _stage_parents(stage, tenant_a)
        stage.add(_row(run_id, snap_id, ver_id, tenant_a))
        stage.commit()
        stage.close()
        engine.dispose()

        # Tenant B under irp_app sees NOTHING.
        engine_b, session_b = _session(app_url, tenant_b)
        try:
            rows = list(
                session_b.execute(
                    select(ConcentrationResult).where(
                        ConcentrationResult.calculation_run_id == run_id
                    )
                ).scalars()
            )
            assert rows == [], "a foreign tenant read concentration rows through FORCE RLS"
            # And a write STAMPED for tenant A from B's context refuses with 42501.
            session_b.add(_row(run_id, snap_id, ver_id, tenant_a, bucket_code="K"))
            with pytest.raises(Exception) as excinfo:
                session_b.flush()
            assert _is_rls_violation(
                excinfo.value
            ), f"expected SQLSTATE 42501, got {excinfo.value!r}"
        finally:
            session_b.close()
            engine_b.dispose()

        # POSITIVE control: tenant A sees its own row under the same constrained role.
        engine_a, session_a = _session(app_url, tenant_a)
        try:
            own = list(
                session_a.execute(
                    select(ConcentrationResult).where(
                        ConcentrationResult.calculation_run_id == run_id
                    )
                ).scalars()
            )
            assert len(own) == 1
        finally:
            session_a.close()
            engine_a.dispose()


class TestAppendOnly:
    """ENT-069 is IA: the ``0057`` P0001 trigger must REFUSE both mutations.

    The review found this control shipped un-executed — the vacuous-guard class (SCH-2). A trigger
    created against a typo'd table name, or lost in a merge, would leave every assertion here
    silently passing on an ordinary UPDATE, so the proof must be the SQLSTATE itself."""

    @staticmethod
    def _staged() -> tuple[object, object, str]:  # noqa: ANN401
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        run_id, snap_id, ver_id = _stage_parents(session, tenant)
        session.add(_row(run_id, snap_id, ver_id, tenant))
        session.commit()
        return engine, session, run_id

    def test_update_is_refused_with_P0001(self) -> None:
        engine, session, run_id = self._staged()
        try:
            with pytest.raises(Exception) as excinfo:
                session.execute(
                    text(
                        "UPDATE concentration_result SET share_invested_long = 0.5 "
                        "WHERE calculation_run_id = :r"
                    ),
                    {"r": run_id},
                )
            assert (
                getattr(getattr(excinfo.value, "orig", None), "sqlstate", None) == "P0001"
            ), f"expected the append-only trigger's P0001, got {excinfo.value!r}"
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_delete_is_refused_with_P0001(self) -> None:
        engine, session, run_id = self._staged()
        try:
            with pytest.raises(Exception) as excinfo:
                session.execute(
                    text("DELETE FROM concentration_result WHERE calculation_run_id = :r"),
                    {"r": run_id},
                )
            assert (
                getattr(getattr(excinfo.value, "orig", None), "sqlstate", None) == "P0001"
            ), f"expected the append-only trigger's P0001, got {excinfo.value!r}"
        finally:
            session.rollback()
            session.close()
            engine.dispose()


def _stage_book(session, tenant: str, *, n_instruments: int = 2):  # noqa: ANN001, ANN202
    """A minimal priced book with issuer edges + a COMPLETED exposure run.

    Returns ``(portfolio_id, exposure_run_id, [instrument_id, ...])``."""
    from irp_shared.exposure import ExposureActor, run_exposure
    from irp_shared.portfolio import PortfolioActor, create_portfolio
    from irp_shared.position import create_position
    from irp_shared.position.service import PositionActor
    from irp_shared.reference.instrument import create_instrument, update_instrument
    from irp_shared.reference.issuer import create_issuer
    from irp_shared.reference.legal_entity import create_legal_entity
    from irp_shared.reference.service import ReferenceActor
    from irp_shared.valuation import create_valuation
    from irp_shared.valuation.service import ValuationActor

    t0 = datetime(2024, 6, 1, tzinfo=UTC)
    as_of = datetime(2026, 1, 2, tzinfo=UTC)
    mark_date = as_of.date()  # the completeness gate demands a SAME-as-of mark per bound position
    ref_actor = ReferenceActor(actor_id="pgtest")
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"PGCON-{uuid.uuid4().hex[:6]}",
        name="pg refusal fixture",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="pgtest"),
    ).id
    instrument_ids: list[str] = []
    for i in range(n_instruments):
        core = create_legal_entity(
            session,
            tenant_id=tenant,
            code=f"PGLE-{uuid.uuid4().hex[:6]}",
            name=f"pg refusal issuer {i}",
            jurisdiction="US",
            actor=ref_actor,
        )
        issuer = create_issuer(
            session,
            tenant_id=tenant,
            legal_entity_id=core.id,
            issuer_type="CORPORATE",
            actor=ref_actor,
        )
        inst = create_instrument(
            session,
            tenant_id=tenant,
            code=f"PGIN-{uuid.uuid4().hex[:6]}",
            name=f"pg refusal instrument {i}",
            asset_class="EQUITY",
            actor=ref_actor,
        )
        update_instrument(session, inst, actor=ref_actor, issuer_id=str(issuer.id))
        create_position(
            session,
            portfolio_id=pf,
            instrument_id=inst.id,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="pgtest"),
            quantity=Decimal("100"),
            valid_from=t0,
        )
        create_valuation(
            session,
            portfolio_id=pf,
            instrument_id=inst.id,
            valuation_date=mark_date,
            acting_tenant=tenant,
            actor=ValuationActor(actor_id="pgtest"),
            mark_value=Decimal("1000"),
            currency_code="USD",
            valid_from=t0,
        )
        instrument_ids.append(str(inst.id))
    session.flush()
    exposure = run_exposure(
        session,
        acting_tenant=tenant,
        actor=ExposureActor(actor_id="pgtest"),
        code_version="pgtest-con1",
        environment_id="test",
        portfolio_id=pf,
        as_of_valid_at=as_of,
        base_currency="USD",
    )
    assert exposure.status == "COMPLETED", "the fixture exposure run did not COMPLETE"
    return str(pf), str(exposure.run.run_id), instrument_ids


def _short_position(session, *, tenant: str, portfolio_id: str):  # noqa: ANN001, ANN202
    """Add ONE short (negative-quantity) instrument to a staged book, with a same-as-of mark."""
    from irp_shared.position import create_position
    from irp_shared.position.service import PositionActor
    from irp_shared.reference.instrument import create_instrument, update_instrument
    from irp_shared.reference.issuer import create_issuer
    from irp_shared.reference.legal_entity import create_legal_entity
    from irp_shared.reference.service import ReferenceActor
    from irp_shared.valuation import create_valuation
    from irp_shared.valuation.service import ValuationActor

    t0 = datetime(2024, 6, 1, tzinfo=UTC)
    mark_date = datetime(2026, 1, 2, tzinfo=UTC).date()
    ref_actor = ReferenceActor(actor_id="pgtest")
    core = create_legal_entity(
        session,
        tenant_id=tenant,
        code=f"PGSH-{uuid.uuid4().hex[:6]}",
        name="pg short issuer",
        jurisdiction="US",
        actor=ref_actor,
    )
    issuer = create_issuer(
        session,
        tenant_id=tenant,
        legal_entity_id=core.id,
        issuer_type="CORPORATE",
        actor=ref_actor,
    )
    inst = create_instrument(
        session,
        tenant_id=tenant,
        code=f"PGSH-{uuid.uuid4().hex[:6]}",
        name="pg short instrument",
        asset_class="EQUITY",
        actor=ref_actor,
    )
    update_instrument(session, inst, actor=ref_actor, issuer_id=str(issuer.id))
    create_position(
        session,
        portfolio_id=portfolio_id,
        instrument_id=inst.id,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="pgtest"),
        quantity=Decimal("-50"),
        valid_from=t0,
    )
    create_valuation(
        session,
        portfolio_id=portfolio_id,
        instrument_id=inst.id,
        valuation_date=mark_date,
        acting_tenant=tenant,
        actor=ValuationActor(actor_id="pgtest"),
        # A POSITIVE per-unit mark against a NEGATIVE quantity: exposure is quantity x mark, so
        # a negative mark here would multiply back to a LONG (the first draft's fixture bug).
        mark_value=Decimal("500"),
        currency_code="USD",
        valid_from=t0,
    )
    session.flush()
    return str(issuer.id)


def _scheme(session, *, family: str, dimension_kind: str, tenant: str, codes=("C", "C26")):  # noqa: ANN001, ANN202
    """A tenant-owned scheme with a two-level chain (root ``codes[0]`` → leaf ``codes[1]``)."""
    actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family=family,
        version_label=f"pgtest-{uuid.uuid4().hex[:8]}",
        name=f"{family} refusal fixture",
        dimension_kind=dimension_kind,
        authority="pgtest",
    )
    create_node(session, actor=actor, scheme_id=scheme.id, code=codes[0], name="Root", level=1)
    create_node(
        session,
        actor=actor,
        scheme_id=scheme.id,
        code=codes[1],
        name="Leaf",
        level=2,
        parent_code=codes[0],
    )
    session.flush()
    return scheme


def _system_scheme(factory, *, family: str, dimension_kind: str, codes=("C", "C26")):  # noqa: ANN001, ANN202
    """A SYSTEM-owned scheme (the normal case: the vocabulary is hybrid). Returns its id.

    A tenant can only LEAF-OVERRIDE a node it does not already own, so the drift-door controls
    need the SYSTEM row to shadow — a tenant-owned scheme would collide on
    ``uq_classification_node_tenant_scheme_code`` instead."""
    session = factory()
    set_tenant_context(session, SYSTEM_TENANT_ID)
    actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id="pgtest")
    try:
        scheme = create_scheme(
            session,
            actor=actor,
            scheme_family=family,
            version_label=f"pgtest-{uuid.uuid4().hex[:8]}",
            name=f"{family} system fixture",
            dimension_kind=dimension_kind,
            authority="pgtest",
        )
        create_node(session, actor=actor, scheme_id=scheme.id, code=codes[0], name="Root", level=1)
        create_node(
            session,
            actor=actor,
            scheme_id=scheme.id,
            code=codes[1],
            name="Leaf",
            level=2,
            parent_code=codes[0],
        )
        session.commit()
        return str(scheme.id)
    finally:
        session.close()


class TestPreBuildRefusals:
    """The PRE-BUILD / pre-create refusals, each with an executed negative control.

    The review found EVERY one of these shipped with zero controls while the record claimed them
    "negative-controlled" — and the SCH-2 lesson is that an unexecuted guard is routinely a vacuous
    one. Each test asserts the refusal AND (where the refusal is pre-create) that no governance
    row survives: zero ``calculation_run``, zero ``dataset_snapshot``."""

    @staticmethod
    def _fresh():  # noqa: ANN205
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        return engine, session, tenant

    def test_mixed_live_scheme_VERSIONS_of_one_family_refuse(self) -> None:
        """OQ-CON-1-24 (i). As RATIFIED this discriminator read "the pinned assignments" — which
        the review proved unfireable, because the pinned set is filtered to the requested scheme
        and can never hold the second version. It now reads the LIVE current heads."""
        from irp_shared.classification.service import capture_assignment
        from irp_shared.snapshot.events import SnapshotActor
        from irp_shared.snapshot.service import (
            ConcentrationSnapshotError,
            build_concentration_snapshot,
        )

        engine, session, tenant = self._fresh()
        try:
            _pf, exposure_run_id, instrument_ids = _stage_book(session, tenant, n_instruments=2)
            rev5 = _scheme(session, family="ISIC", dimension_kind="SECTOR_INDUSTRY", tenant=tenant)
            rev6 = _scheme(session, family="ISIC", dimension_kind="SECTOR_INDUSTRY", tenant=tenant)
            actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
            capture_assignment(
                session,
                actor=actor,
                entity_type="instrument",
                entity_id=instrument_ids[0],
                scheme_id=str(rev5.id),
                dimension_kind="SECTOR_INDUSTRY",
                node_code="C26",
                basis="NOT_APPLICABLE",
            )
            capture_assignment(
                session,
                actor=actor,
                entity_type="instrument",
                entity_id=instrument_ids[1],
                scheme_id=str(rev6.id),
                dimension_kind="SECTOR_INDUSTRY",
                node_code="C26",
                basis="NOT_APPLICABLE",
            )
            session.flush()
            with pytest.raises(ConcentrationSnapshotError, match="mixed live scheme VERSIONS"):
                build_concentration_snapshot(
                    session,
                    acting_tenant=tenant,
                    actor=SnapshotActor(actor_id="pgtest"),
                    exposure_run_id=exposure_run_id,
                    scheme_by_dimension={"SECTOR_INDUSTRY": str(rev6.id)},
                )
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_co_existing_DIFFERENT_families_still_build(self) -> None:
        """The POSITIVE control clause (i)'s own rationale demands: ISIC + NACE co-existing on one
        instrument is a permanent legal state and must NOT refuse (clause iii — simply not
        consumed). Without this, the refusal above could be a blanket over-refusal."""
        from irp_shared.classification.service import capture_assignment
        from irp_shared.snapshot.events import SnapshotActor
        from irp_shared.snapshot.service import build_concentration_snapshot

        engine, session, tenant = self._fresh()
        try:
            _pf, exposure_run_id, instrument_ids = _stage_book(session, tenant, n_instruments=1)
            isic = _scheme(session, family="ISIC", dimension_kind="SECTOR_INDUSTRY", tenant=tenant)
            nace = _scheme(session, family="NACE", dimension_kind="SECTOR_INDUSTRY", tenant=tenant)
            actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
            for scheme in (isic, nace):
                capture_assignment(
                    session,
                    actor=actor,
                    entity_type="instrument",
                    entity_id=instrument_ids[0],
                    scheme_id=str(scheme.id),
                    dimension_kind="SECTOR_INDUSTRY",
                    node_code="C26",
                    basis="NOT_APPLICABLE",
                )
            session.flush()
            snapshot = build_concentration_snapshot(
                session,
                acting_tenant=tenant,
                actor=SnapshotActor(actor_id="pgtest"),
                exposure_run_id=exposure_run_id,
                scheme_by_dimension={"SECTOR_INDUSTRY": str(isic.id)},
            )
            assert snapshot is not None
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_mixed_basis_within_one_dimension_refuses(self) -> None:
        """OQ-CON-1-26 (ii): aggregating two bases in one dimension is meaningless, so it fails
        closed BEFORE any write."""
        from irp_shared.classification.service import capture_assignment
        from irp_shared.snapshot.events import SnapshotActor
        from irp_shared.snapshot.service import (
            ConcentrationSnapshotError,
            build_concentration_snapshot,
        )

        engine, session, tenant = self._fresh()
        try:
            _pf, exposure_run_id, instrument_ids = _stage_book(session, tenant, n_instruments=2)
            countries = _scheme(
                session,
                family="ISO_3166_1",
                dimension_kind="COUNTRY_OF_RISK",
                tenant=tenant,
                codes=("US", "US-CA"),
            )
            actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
            for instrument_id, basis in (
                (instrument_ids[0], "IMMEDIATE_ISSUER_RESIDENCE"),
                (instrument_ids[1], "ULTIMATE_RISK"),
            ):
                capture_assignment(
                    session,
                    actor=actor,
                    entity_type="instrument",
                    entity_id=instrument_id,
                    scheme_id=str(countries.id),
                    dimension_kind="COUNTRY_OF_RISK",
                    node_code="US-CA",
                    basis=basis,
                )
            session.flush()
            with pytest.raises(ConcentrationSnapshotError, match="mixed basis"):
                build_concentration_snapshot(
                    session,
                    acting_tenant=tenant,
                    actor=SnapshotActor(actor_id="pgtest"),
                    exposure_run_id=exposure_run_id,
                    scheme_by_dimension={"COUNTRY_OF_RISK": str(countries.id)},
                )
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_scheme_dimension_mismatch_refuses(self) -> None:
        """A COUNTRY scheme requested for the SECTOR dimension: the run would silently bucket by
        the wrong taxonomy."""
        from irp_shared.snapshot.events import SnapshotActor
        from irp_shared.snapshot.service import (
            ConcentrationSnapshotError,
            build_concentration_snapshot,
        )

        engine, session, tenant = self._fresh()
        try:
            _pf, exposure_run_id, _ids = _stage_book(session, tenant, n_instruments=1)
            countries = _scheme(
                session,
                family="ISO_3166_1",
                dimension_kind="COUNTRY_OF_RISK",
                tenant=tenant,
                codes=("US", "US-CA"),
            )
            with pytest.raises(ConcentrationSnapshotError, match="requested for"):
                build_concentration_snapshot(
                    session,
                    acting_tenant=tenant,
                    actor=SnapshotActor(actor_id="pgtest"),
                    exposure_run_id=exposure_run_id,
                    scheme_by_dimension={"SECTOR_INDUSTRY": str(countries.id)},
                )
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_null_scope_upstream_run_refused_PRE_CREATE_with_zero_governance_rows(self) -> None:
        """The OD-API-1b-D honest NULL. The record says "refused from the run head" — so the proof
        is not only the raise but that NOTHING was minted: the ENT-069 scope identity
        ``portfolio_id == scope_portfolio_id`` is uncomputable, and a run is unwithdrawable."""
        from irp_shared.calc.models import CalculationRun
        from irp_shared.concentration.bootstrap import register_concentration_model
        from irp_shared.concentration.events import ConcentrationActor
        from irp_shared.concentration.service import (
            ConcentrationInputError,
            run_concentration,
        )
        from irp_shared.snapshot.models import DatasetSnapshot

        engine, session, tenant = self._fresh()
        try:
            _pf, exposure_run_id, _ids = _stage_book(session, tenant, n_instruments=1)
            isic = _scheme(session, family="ISIC", dimension_kind="SECTOR_INDUSTRY", tenant=tenant)
            version = register_concentration_model(
                session,
                tenant_id=tenant,
                actor_id="pgtest",
                code_version="pgtest-con1",
                coverage_floor=Decimal("0.5"),
            )
            # Force the honest NULL onto the upstream run head.
            session.execute(
                text("UPDATE calculation_run SET scope_portfolio_id = NULL WHERE run_id = :r"),
                {"r": exposure_run_id},
            )
            session.flush()
            runs_before = session.execute(
                select(CalculationRun).where(
                    CalculationRun.tenant_id == tenant,
                    CalculationRun.run_type == "CONCENTRATION",
                )
            ).all()
            snaps_before = session.execute(
                select(DatasetSnapshot).where(
                    DatasetSnapshot.tenant_id == tenant,
                    DatasetSnapshot.purpose == "CONCENTRATION_INPUT",
                )
            ).all()
            with pytest.raises(ConcentrationInputError, match="NULL scope_portfolio_id"):
                run_concentration(
                    session,
                    acting_tenant=tenant,
                    actor=ConcentrationActor(actor_id="pgtest"),
                    code_version="pgtest-con1",
                    environment_id="test",
                    model_version_id=str(version.id),
                    exposure_run_id=exposure_run_id,
                    scheme_by_dimension={"SECTOR_INDUSTRY": str(isic.id)},
                )
            runs_after = session.execute(
                select(CalculationRun).where(
                    CalculationRun.tenant_id == tenant,
                    CalculationRun.run_type == "CONCENTRATION",
                )
            ).all()
            snaps_after = session.execute(
                select(DatasetSnapshot).where(
                    DatasetSnapshot.tenant_id == tenant,
                    DatasetSnapshot.purpose == "CONCENTRATION_INPUT",
                )
            ).all()
            assert len(runs_after) == len(runs_before) == 0, "a run was minted before the refusal"
            assert (
                len(snaps_after) == len(snaps_before) == 0
            ), "a snapshot was minted before the refusal"
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_coverage_floor_must_be_strictly_positive(self) -> None:
        """A ZERO floor is not a permissive setting but a broken one: an all-UNCLASSIFIED
        dimension has classifiable coverage 0, which clears a zero floor, so the run COMPLETES and
        writes immutable MAX/HHI/CR-5 rows of 0.000000 over an EMPTY classified set — values with
        no defined meaning. Registration refuses it, and the error is a DEDICATED type so the API
        map cannot relabel an unrelated server-side ValueError as a client 422."""
        from irp_shared.concentration.bootstrap import (
            ConcentrationModelParameterError,
            register_concentration_model,
        )

        engine, session, tenant = self._fresh()
        try:
            for bad in (Decimal("0"), Decimal("1.5"), Decimal("-0.1")):
                with pytest.raises(ConcentrationModelParameterError, match="coverage_floor"):
                    register_concentration_model(
                        session,
                        tenant_id=tenant,
                        actor_id="pgtest",
                        code_version="pgtest-con1",
                        coverage_floor=bad,
                    )
            # POSITIVE control: the boundary value 1 and an ordinary floor both register.
            assert register_concentration_model(
                session,
                tenant_id=tenant,
                actor_id="pgtest",
                code_version="pgtest-con1",
                coverage_floor=Decimal("1"),
            )
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_empty_atom_set_refuses(self) -> None:
        """An exposure run with no visible atoms pins nothing — a snapshot over an empty book is
        governance garbage, so the build refuses."""
        from irp_shared.calc.models import CalculationRun
        from irp_shared.snapshot.events import SnapshotActor
        from irp_shared.snapshot.service import (
            ConcentrationSnapshotError,
            build_concentration_snapshot,
        )

        engine, session, tenant = self._fresh()
        try:
            _pf, seed_run_id, _ids = _stage_book(session, tenant, n_instruments=1)
            isic = _scheme(session, family="ISIC", dimension_kind="SECTOR_INDUSTRY", tenant=tenant)
            # A COMPLETED exposure run head carrying NO atoms. The atoms are append-only, so the
            # book cannot be emptied by deletion — the honest fixture is a run that produced none.
            seed = session.execute(
                select(CalculationRun).where(CalculationRun.run_id == seed_run_id)
            ).scalar_one()
            empty_run_id = str(uuid.uuid4())
            session.add(
                CalculationRun(
                    tenant_id=tenant,
                    run_id=empty_run_id,
                    run_type=seed.run_type,
                    status="COMPLETED",
                    initiated_by="pgtest",
                    input_snapshot_id=seed.input_snapshot_id,
                    model_version_id=seed.model_version_id,
                    scope_portfolio_id=seed.scope_portfolio_id,
                    system_from=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()
            exposure_run_id = empty_run_id
            with pytest.raises(ConcentrationSnapshotError, match="no visible atoms"):
                build_concentration_snapshot(
                    session,
                    acting_tenant=tenant,
                    actor=SnapshotActor(actor_id="pgtest"),
                    exposure_run_id=exposure_run_id,
                    scheme_by_dimension={"SECTOR_INDUSTRY": str(isic.id)},
                )
        finally:
            session.rollback()
            session.close()
            engine.dispose()


class TestPinDriftDoors:
    """OQ-CON-1-7/9: the serializer-level drift controls, on the real engine."""

    def test_issuer_edge_pin_drifts_on_the_edge_and_not_on_excluded_fields(self) -> None:
        from irp_shared.reference.instrument import create_instrument, update_instrument
        from irp_shared.reference.issuer import create_issuer
        from irp_shared.reference.legal_entity import create_legal_entity
        from irp_shared.reference.service import ReferenceActor

        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        actor = ReferenceActor(actor_id="pgtest")
        try:
            core = create_legal_entity(
                session,
                tenant_id=tenant,
                code=f"PGT-{uuid.uuid4().hex[:6]}",
                name="pg drift fixture",
                jurisdiction="US",
                actor=actor,
            )
            issuer = create_issuer(
                session,
                tenant_id=tenant,
                legal_entity_id=core.id,
                issuer_type="CORPORATE",
                actor=actor,
            )
            core2 = create_legal_entity(
                session,
                tenant_id=tenant,
                code=f"PGT2-{uuid.uuid4().hex[:6]}",
                name="pg drift fixture 2",
                jurisdiction="US",
                actor=actor,
            )
            issuer2 = create_issuer(
                session,
                tenant_id=tenant,
                legal_entity_id=core2.id,
                issuer_type="CORPORATE",
                actor=actor,
            )
            inst = create_instrument(
                session,
                tenant_id=tenant,
                code=f"PGI-{uuid.uuid4().hex[:6]}",
                name="pg drift instrument",
                asset_class="EQUITY",
                actor=actor,
            )
            update_instrument(session, inst, actor=actor, issuer_id=str(issuer.id))
            session.flush()
            pinned = issuer_edge_content(inst)
            # NO-DRIFT control on EVERY excluded field, not just ``name``. OQ-CON-1-7 requires
            # "a test that it does not drift on EACH excluded field"; testing one of four left
            # three fields free to leak into the pin and redden historical runs on a data fix.
            from irp_shared.reference.instrument import _UPDATABLE

            excluded = [f for f in _UPDATABLE if f != "issuer_id"]
            assert set(excluded) == {"name", "instrument_type", "currency_code", "is_active"}, (
                f"the instrument's updatable set changed to {_UPDATABLE} — decide, per new field, "
                "whether it belongs in the narrow issuer-edge pin, then update this census"
            )
            for field, value in (
                ("name", "renamed — must not drift"),
                ("instrument_type", "COMMON_STOCK"),
                ("currency_code", "EUR"),
                ("is_active", False),
            ):
                update_instrument(session, inst, actor=actor, **{field: value})
                session.flush()
                assert issuer_edge_content(inst) == pinned, f"{field} moved the narrow pin"
            # DRIFT control: moving the EDGE changes the content.
            update_instrument(session, inst, actor=actor, issuer_id=str(issuer2.id))
            session.flush()
            assert issuer_edge_content(inst) != pinned, "an issuer move did NOT move the pin"
        finally:
            session.close()
            engine.dispose()

    def test_verify_snapshot_REDDENS_on_a_tenant_leaf_override(self) -> None:
        """OQ-CON-1-9 through the REAL verify path, on a real CONCENTRATION_INPUT snapshot.

        Its sibling below proves the serializer's content changes, but computes that content by
        calling ``resolve_node``/``classification_assignment_closure_content`` directly — so the
        CLASSIFICATION ``_reresolve_content`` branch, the platform's FIRST code-first re-derive and
        this slice's headline deviation from the by-id idiom, was executed by no test at all. A
        by-id re-read would sit exactly here, green, while the number silently drifted."""
        from irp_shared.classification.service import capture_assignment
        from irp_shared.snapshot.events import SnapshotActor
        from irp_shared.snapshot.service import build_concentration_snapshot, verify_snapshot

        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        scheme_id = _system_scheme(factory, family="ISIC", dimension_kind="SECTOR_INDUSTRY")
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            _pf, exposure_run_id, instrument_ids = _stage_book(session, tenant, n_instruments=1)
            actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
            capture_assignment(
                session,
                actor=actor,
                entity_type="instrument",
                entity_id=instrument_ids[0],
                scheme_id=scheme_id,
                dimension_kind="SECTOR_INDUSTRY",
                node_code="C26",
                basis="NOT_APPLICABLE",
            )
            session.flush()
            snapshot = build_concentration_snapshot(
                session,
                acting_tenant=tenant,
                actor=SnapshotActor(actor_id="pgtest"),
                exposure_run_id=exposure_run_id,
                scheme_by_dimension={"SECTOR_INDUSTRY": scheme_id},
            )
            session.flush()
            # POSITIVE control first: an untouched book must verify clean, or the negative below
            # proves nothing.
            before = verify_snapshot(session, snapshot_id=str(snapshot.id), acting_tenant=tenant)
            assert (
                before.ok
            ), f"a freshly built snapshot did not verify: {before.drifted_components}"
            # The LEAF override: shadow C26 with a different parentage. Only a CODE-FIRST
            # re-resolve can see this.
            create_node(
                session,
                actor=actor,
                scheme_id=scheme_id,
                code="C26",
                name="House override",
                level=1,
            )
            session.flush()
            after = verify_snapshot(session, snapshot_id=str(snapshot.id), acting_tenant=tenant)
            assert not after.ok, (
                "verify_snapshot stayed GREEN after a tenant leaf override — the CLASSIFICATION "
                "branch is re-resolving by id, not code-first"
            )
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_a_tenant_leaf_override_changes_the_code_first_closure_content(self) -> None:
        """The OQ-CON-1-9 mandatory negative control: a LEAF override MUST redden the pin — under
        the shipped by-id re-resolve idiom it never would, which is why the CLASSIFICATION branch
        re-resolves code-first."""
        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        sys_session = factory()
        set_tenant_context(sys_session, SYSTEM_TENANT_ID)
        tenant = str(uuid.uuid4())
        sys_actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id="pgtest")
        try:
            scheme = create_scheme(
                sys_session,
                actor=sys_actor,
                scheme_family="ISIC",
                version_label=f"pgtest-{uuid.uuid4().hex[:8]}",
                name="closure drift fixture",
                dimension_kind="SECTOR_INDUSTRY",
                authority="UNSD",
            )
            create_node(
                sys_session,
                actor=sys_actor,
                scheme_id=scheme.id,
                code="C",
                name="Manufacturing",
                level=1,
            )
            create_node(
                sys_session,
                actor=sys_actor,
                scheme_id=scheme.id,
                code="C26",
                name="Electronics",
                level=2,
                parent_code="C",
            )
            sys_session.commit()
            scheme_id = str(scheme.id)
        finally:
            sys_session.close()

        session = factory()
        set_tenant_context(session, tenant)
        actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
        try:
            node = resolve_node(session, scheme_id=scheme_id, code="C26", acting_tenant=tenant)
            chain = resolve_ancestors(session, node=node, acting_tenant=tenant)
            fake_assignment = type(
                "A",
                (),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant,
                    "entity_type": "instrument",
                    "entity_id": str(uuid.uuid4()),
                    "scheme_id": scheme_id,
                    "dimension_kind": "SECTOR_INDUSTRY",
                    "node_code": "C26",
                    "basis": "NOT_APPLICABLE",
                },
            )()
            pinned = classification_assignment_closure_content(fake_assignment, [*chain, node])
            # The LEAF override: the tenant shadows C26 with a DIFFERENT parentage (level 1, no
            # parent) — resolve_node now prefers the tenant row, so the closure changes.
            create_node(
                session,
                actor=actor,
                scheme_id=scheme_id,
                code="C26",
                name="House override",
                level=1,
            )
            session.flush()
            node2 = resolve_node(session, scheme_id=scheme_id, code="C26", acting_tenant=tenant)
            chain2 = resolve_ancestors(session, node=node2, acting_tenant=tenant)
            live = classification_assignment_closure_content(fake_assignment, [*chain2, node2])
            assert live != pinned, (
                "a tenant LEAF override did not change the closure content — the code-first "
                "re-resolve is broken (a by-id re-read would sit exactly here, green)"
            )
        finally:
            session.close()
            engine.dispose()


class TestGovernedRunReads:
    """A REAL end-to-end run on the authoritative engine, covering three Part-3 claims that
    shipped with no test: the issuer bucket-code invariant, the non-String read filter pins, and
    a SHORT-BEARING book (which existed only in the unit kernel tier)."""

    @staticmethod
    def _run(session, tenant: str, *, factory, with_short: bool):  # noqa: ANN001, ANN205
        from irp_shared.classification.service import capture_assignment
        from irp_shared.concentration.bootstrap import register_concentration_model
        from irp_shared.concentration.events import ConcentrationActor
        from irp_shared.concentration.service import run_concentration
        from irp_shared.exposure import ExposureActor, run_exposure

        portfolio_id, exposure_run_id, instrument_ids = _stage_book(
            session, tenant, n_instruments=2
        )
        scheme_id = _system_scheme(factory, family="ISIC", dimension_kind="SECTOR_INDUSTRY")
        if with_short:
            short_instrument_id = _short_position(session, tenant=tenant, portfolio_id=portfolio_id)
            instrument_ids = [*instrument_ids, short_instrument_id]
            # Re-run exposure so the short lands in the atoms the snapshot pins.
            exposure = run_exposure(
                session,
                acting_tenant=tenant,
                actor=ExposureActor(actor_id="pgtest"),
                code_version="pgtest-con1",
                environment_id="test",
                portfolio_id=portfolio_id,
                as_of_valid_at=datetime(2026, 1, 2, tzinfo=UTC),
                base_currency="USD",
            )
            assert exposure.status == "COMPLETED"
            exposure_run_id = str(exposure.run.run_id)
        # Classify EVERY instrument: an unclassified book fails the coverage floor, and a gap in
        # ANY dimension discards the whole run's rows (the scaffold's all-or-nothing contract).
        cls_actor = ClassificationActor(tenant_id=tenant, actor_id="pgtest")
        for instrument_id in instrument_ids:
            capture_assignment(
                session,
                actor=cls_actor,
                entity_type="instrument",
                entity_id=instrument_id,
                scheme_id=scheme_id,
                dimension_kind="SECTOR_INDUSTRY",
                node_code="C26",
                basis="NOT_APPLICABLE",
            )
        session.flush()
        version = register_concentration_model(
            session,
            tenant_id=tenant,
            actor_id="pgtest",
            code_version="pgtest-con1",
            coverage_floor=Decimal("0.5"),
        )
        session.flush()
        result = run_concentration(
            session,
            acting_tenant=tenant,
            actor=ConcentrationActor(actor_id="pgtest"),
            code_version="pgtest-con1",
            environment_id="test",
            model_version_id=str(version.id),
            exposure_run_id=exposure_run_id,
            scheme_by_dimension={"SECTOR_INDUSTRY": scheme_id},
        )
        session.flush()
        return portfolio_id, result

    def test_issuer_bucket_code_is_the_issuer_id_and_reads_filter(self) -> None:
        """``bucket_code == str(issuer_id)`` on real ISSUER DETAIL rows — the record calls this a
        service invariant "with its own PG-tier test", and had none; the demo test could not
        supply one because it compares the share MULTISET (ids are run-local)."""
        from irp_shared.concentration.service import (
            concentration_rows_for_run,
            list_concentration_issuer_detail,
            list_concentration_results,
        )

        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            portfolio_id, _result = self._run(session, tenant, factory=factory, with_short=False)
            issuer_rows = list_concentration_issuer_detail(
                session, acting_tenant=tenant, portfolio_id=portfolio_id
            )
            real = [
                r
                for r in issuer_rows
                if r.bucket_code not in (BUCKET_UNCLASSIFIED, "__UNCLASSIFIABLE__")
            ]
            assert real, "no real ISSUER buckets were produced"
            for row in real:
                assert row.issuer_id is not None
                assert row.bucket_code == str(row.issuer_id), (
                    f"ISSUER bucket_code {row.bucket_code!r} is not str(issuer_id) "
                    f"{str(row.issuer_id)!r} — the join key the read surface resolves names by"
                )
            # The .view shape must NOT carry those rows.
            view_rows = list_concentration_results(
                session, acting_tenant=tenant, portfolio_id=portfolio_id
            )
            assert not [
                r for r in view_rows if r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL"
            ], "an ISSUER DETAIL row reached the concentration.view payload"
            # NON-STRING FILTER PINS (record Part 3: "PG-tier pins for every non-String filter").
            assert (
                list_concentration_results(
                    session, acting_tenant=tenant, portfolio_id=str(uuid.uuid4())
                )
                == []
            ), "a foreign portfolio_id was not silent-empty"
            assert (
                list_concentration_results(
                    session,
                    acting_tenant=tenant,
                    portfolio_id=portfolio_id,
                    as_of=datetime(2020, 1, 1, tzinfo=UTC),
                )
                == []
            ), "an as_of cutoff BEFORE the run still returned rows"
            assert list_concentration_results(
                session,
                acting_tenant=tenant,
                portfolio_id=portfolio_id,
                as_of=datetime.now(UTC),
            ), "an as_of cutoff AFTER the run returned nothing"
            assert (
                concentration_rows_for_run(session, acting_tenant=tenant, run_id=str(uuid.uuid4()))
                == []
            ), "a foreign run id was not silent-empty"
        finally:
            session.rollback()
            session.close()
            engine.dispose()

    def test_short_bearing_book_end_to_end(self) -> None:
        """OQ-CON-1-1's distinguishing case ratified for "the unit + PG tiers" — it shipped only
        in the unit tier. Shares are over INVESTED LONG, so a short contributes to gross/short/net
        but NEVER to the denominator, and the long-only buckets still sum to 1.000000."""
        from irp_shared.concentration.service import concentration_rows_for_run

        engine = make_engine(URL, poolclass=NullPool)
        factory = make_session_factory(engine)
        session = factory()
        tenant = str(uuid.uuid4())
        set_tenant_context(session, tenant)
        try:
            _portfolio_id, result = self._run(session, tenant, factory=factory, with_short=True)
            rows = concentration_rows_for_run(
                session,
                acting_tenant=tenant,
                run_id=str(result.run.run_id),
                include_issuer_detail=True,
            )
            detail = [r for r in rows if r.dimension_kind == "ISSUER" and r.row_kind == "DETAIL"]
            assert detail, "no ISSUER detail rows"
            shares = sum((r.share_invested_long for r in detail), Decimal("0"))
            assert shares == Decimal("1.000000"), f"long-only shares summed to {shares}"
            shorts = [r for r in detail if r.short_amount != 0]
            assert shorts, "the short leg never reached a result row"
            for row in shorts:
                assert row.share_invested_long == Decimal("0.000000"), (
                    "a SHORT-only bucket carries a non-zero invested-long share — the denominator "
                    "is not long-only"
                )
        finally:
            session.rollback()
            session.close()
            engine.dispose()
