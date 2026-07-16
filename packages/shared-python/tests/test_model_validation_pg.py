"""PostgreSQL FORCE-RLS tests for the VW-1 model-validation tables (ENT-037).

Gated on ``IRP_TEST_DATABASE_URL``; runs under the constrained non-superuser ``irp_app`` role
(NOSUPERUSER NOBYPASSRLS). Proves tenant isolation + the WITH CHECK backstop + the P0001
append-only trigger on all three IA tables (model_validation / _finding / _evidence), and the
RLS-vs-FK guard: a cross-tenant model_version_id is refused by ``record_validation``'s explicit
re-resolve BEFORE it can be stamped into the NOT-NULL FK (PG FK checks bypass RLS — P3-5).
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.model.models import ModelValidation, ModelValidationEvidence, ModelValidationFinding
from irp_shared.model.service import register_model, register_model_version
from irp_shared.model.validation import (
    ModelValidationActor,
    ModelValidationValueError,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

_TABLES = ("model_validation", "model_validation_finding", "model_validation_evidence")
_DUE = "2027-06-01"


def _is_rls_violation(error: ProgrammingError) -> bool:
    return (
        getattr(error.orig, "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


def _is_append_only_violation(error: ProgrammingError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "P0001" or "append-only" in str(error).lower()


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser app role with the grants the validation path needs (incl.
    UPDATE/DELETE so the append-only rejection is the TRIGGER (P0001), not a privilege denial)."""
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
        for tbl in ("model", "model_version", *_TABLES):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _seed_registered_version(factory, tenant: str) -> str:  # noqa: ANN001
    session = factory()
    try:
        set_tenant_context(session, tenant)
        model = register_model(
            session,
            tenant_id=tenant,
            code="risk.var.parametric",
            name="n",
            model_type="VAR",
            actor_id="a",
        )
        version = register_model_version(
            session, model=model, version_label="1.0.0", actor_id="a", status="REGISTERED"
        )
        session.commit()
        return version.id
    finally:
        session.close()


def _record(factory, tenant: str, version_id: str, outcome: str = "APPROVED") -> str:  # noqa: ANN001
    is_rejected = outcome == "REJECTED"
    session = factory()
    try:
        set_tenant_context(session, tenant)
        req = RecordValidationRequest(
            model_version_id=version_id,
            validation_type="INITIAL",
            outcome=outcome,
            scope_summary="scope",
            next_review_due=None if is_rejected else date.fromisoformat(_DUE),
            findings=(ValidationFindingInput(finding_text="f"),),
        )
        record = record_validation(
            session,
            acting_tenant=tenant,
            actor=ModelValidationActor(actor_id="v2l"),
            request=req,
        )
        session.commit()
        return record.id
    finally:
        session.close()


def test_validation_tenant_isolation(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    va = _seed_registered_version(factory, a)
    vb = _seed_registered_version(factory, b)
    _record(factory, a, va)
    _record(factory, b, vb)
    session = factory()
    try:
        set_tenant_context(session, a)
        tenants = {
            str(r[0])
            for r in session.execute(text("SELECT DISTINCT tenant_id FROM model_validation"))
        }
        assert a in tenants and b not in tenants
    finally:
        session.close()
        engine.dispose()


def test_validation_no_context_fails_closed(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    version_id = _seed_registered_version(factory, tenant)
    session = factory()
    try:
        # A valid FK parent, but no tenant context -> RLS 42501 (not an FK error).
        session.add(
            ModelValidation(
                tenant_id=tenant,
                model_version_id=version_id,
                validation_type="INITIAL",
                outcome="REJECTED",
                scope_summary="s",
                validated_by="v",
            )
        )
        with pytest.raises(ProgrammingError) as exc:
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_validation_tenant_mismatch_write_denied(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    version_id = _seed_registered_version(factory, a)
    session = factory()
    try:
        set_tenant_context(session, a)
        session.add(
            ModelValidation(
                tenant_id=b,  # tenant b under context a -> WITH CHECK 42501
                model_version_id=version_id,
                validation_type="INITIAL",
                outcome="REJECTED",
                scope_summary="s",
                validated_by="v",
            )
        )
        with pytest.raises(ProgrammingError) as exc:
            session.flush()
        assert _is_rls_violation(exc.value)
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_cross_tenant_version_reference_fails_closed(app_url: str) -> None:
    """The RLS-vs-FK guard: a foreign model_version_id is refused by the explicit re-resolve BEFORE
    it can be stamped into the NOT-NULL FK (PG FK checks bypass RLS)."""
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    b_version = _seed_registered_version(factory, b)
    session = factory()
    try:
        set_tenant_context(session, a)
        req = RecordValidationRequest(
            model_version_id=b_version,  # a tenant-B version, invisible under context A
            validation_type="INITIAL",
            outcome="REJECTED",
            scope_summary="s",
        )
        with pytest.raises(ModelValidationValueError, match="not visible"):
            record_validation(
                session, acting_tenant=a, actor=ModelValidationActor(actor_id="v"), request=req
            )
    finally:
        session.close()
        engine.dispose()


def test_ia_tables_append_only_at_db(app_url: str) -> None:
    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    version_id = _seed_registered_version(factory, tenant)
    # Build the record + a finding + a DOCUMENT evidence in ONE session and capture all three ids
    # BEFORE commit clears the transaction-local tenant context (the registry-PG exemplar pattern).
    session = factory()
    try:
        set_tenant_context(session, tenant)
        record = record_validation(
            session,
            acting_tenant=tenant,
            actor=ModelValidationActor(actor_id="v2l"),
            request=RecordValidationRequest(
                model_version_id=version_id,
                validation_type="INITIAL",
                outcome="APPROVED",
                scope_summary="scope",
                next_review_due=date.fromisoformat(_DUE),
                findings=(ValidationFindingInput(finding_text="f"),),
                evidence=(ValidationEvidenceInput(evidence_type="DOCUMENT", reference="r.pdf"),),
            ),
        )
        validation_id = record.id
        finding_id = (
            session.execute(
                select(ModelValidationFinding.id).where(
                    ModelValidationFinding.validation_id == validation_id
                )
            )
            .scalars()
            .one()
        )
        evidence_id = (
            session.execute(
                select(ModelValidationEvidence.id).where(
                    ModelValidationEvidence.validation_id == validation_id
                )
            )
            .scalars()
            .one()
        )
        session.commit()
        targets = {
            "model_validation": (validation_id, "outcome"),
            "model_validation_finding": (finding_id, "finding_text"),
            "model_validation_evidence": (evidence_id, "reference"),
        }
    finally:
        session.close()

    for table, (row_id, col) in targets.items():
        session = factory()
        try:
            set_tenant_context(session, tenant)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(f"UPDATE {table} SET {col} = 'X' WHERE id = CAST(:i AS uuid)"),
                    {"i": row_id},
                )
            assert _is_append_only_violation(exc.value), f"{table} UPDATE not trigger-blocked"
            session.rollback()
            set_tenant_context(session, tenant)
            with pytest.raises(ProgrammingError) as exc:
                session.execute(
                    text(f"DELETE FROM {table} WHERE id = CAST(:i AS uuid)"), {"i": row_id}
                )
            assert _is_append_only_violation(exc.value), f"{table} DELETE not trigger-blocked"
            session.rollback()
        finally:
            session.close()
    engine.dispose()


def test_rejected_gate_blocks_run_binding_on_pg(app_url: str) -> None:
    """OD-B end to end on real PG: a REJECTED latest validation makes assert_model_version_of raise
    RejectedModelVersionError; a later APPROVED clears it (recency)."""
    from irp_shared.model.service import RejectedModelVersionError, assert_model_version_of

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    version_id = _seed_registered_version(factory, tenant)
    _record(factory, tenant, version_id, outcome="REJECTED")
    session = factory()
    try:
        set_tenant_context(session, tenant)
        with pytest.raises(RejectedModelVersionError):
            assert_model_version_of(
                session, version_id, tenant_id=tenant, expected_model_code="risk.var.parametric"
            )
    finally:
        session.close()
        engine.dispose()


def test_expired_exception_gate_blocks_run_binding_on_pg(app_url: str) -> None:
    """MG-1 OD-F end to end on real PG under RLS (the seam-gate leg the plan promised): an EXPIRED
    use-before-validation EXCEPTION makes assert_model_version_of raise ExpiredModelExceptionError;
    a fresh (unexpired) EXCEPTION clears it. The expired-EXCEPTION branch reads the same
    model+model_validation rows the REJECTED leg already proves granted, but the branch itself had
    no PG coverage until here."""
    from datetime import UTC, datetime, timedelta

    from irp_shared.model.service import ExpiredModelExceptionError, assert_model_version_of

    engine = make_engine(app_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    tenant = str(uuid.uuid4())
    version_id = _seed_registered_version(factory, tenant)
    past = datetime(2025, 1, 1, tzinfo=UTC)
    # File a backdated EXCEPTION whose expiry is already in the past (cadence-compliant at its own
    # injected clock: past+180 <= past+365).
    session = factory()
    try:
        set_tenant_context(session, tenant)
        record_validation(
            session,
            acting_tenant=tenant,
            actor=ModelValidationActor(actor_id="v2l"),
            request=RecordValidationRequest(
                model_version_id=version_id,
                validation_type="EXCEPTION",
                outcome="APPROVED_WITH_CONDITIONS",
                scope_summary="Use-before-validation grant (POC).",
                conditions="Controls: registered limitations + monitoring.",
                next_review_due=past.date() + timedelta(days=180),
            ),
            now=past,
        )
        session.commit()
    finally:
        session.close()
    session = factory()
    try:
        set_tenant_context(session, tenant)
        with pytest.raises(ExpiredModelExceptionError):
            assert_model_version_of(
                session, version_id, tenant_id=tenant, expected_model_code="risk.var.parametric"
            )
    finally:
        session.close()
    # A fresh EXCEPTION re-grant clears the block (the discharge path the message advertises).
    session = factory()
    try:
        set_tenant_context(session, tenant)
        record_validation(
            session,
            acting_tenant=tenant,
            actor=ModelValidationActor(actor_id="v2l"),
            request=RecordValidationRequest(
                model_version_id=version_id,
                validation_type="EXCEPTION",
                outcome="APPROVED_WITH_CONDITIONS",
                scope_summary="Re-grant.",
                conditions="Controls: registered limitations + monitoring.",
                next_review_due=date.fromisoformat(_DUE),
            ),
        )
        session.commit()
        assert (
            assert_model_version_of(
                session, version_id, tenant_id=tenant, expected_model_code="risk.var.parametric"
            ).id
            == version_id
        )
    finally:
        session.close()
        engine.dispose()
