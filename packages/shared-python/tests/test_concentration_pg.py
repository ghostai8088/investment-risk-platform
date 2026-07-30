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
            # NO-DRIFT control: an excluded-field edit leaves the content byte-identical.
            update_instrument(session, inst, actor=actor, name="renamed — must not drift")
            session.flush()
            assert issuer_edge_content(inst) == pinned, "a rename moved the narrow pin"
            # DRIFT control: moving the EDGE changes the content.
            update_instrument(session, inst, actor=actor, issuer_id=str(issuer2.id))
            session.flush()
            assert issuer_edge_content(inst) != pinned, "an issuer move did NOT move the pin"
        finally:
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
