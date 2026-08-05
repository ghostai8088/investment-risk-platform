"""RPT-1 end to end: generate a report, then regenerate it byte-identically (I2, BR-9).

The identity tests in ``test_report_identity.py`` prove the RENDERER is deterministic. These prove
the whole path: real family rows → a pinned REPORT_INPUT snapshot → a persisted ENT-072 row →
regeneration from the pin alone. That distinction matters, because a deterministic renderer over a
non-deterministic PIN would still fail BR-9, and only this level can see it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.report.models import ReportGeneration
from irp_shared.report.service import (
    ReportIdentityError,
    ReportInputError,
    generate_report,
    regenerate_report,
)
from irp_shared.snapshot.models import DatasetSnapshot

TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TENANT = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
_AS_OF = date(2026, 6, 30)
_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _seed_concentration_run(
    session: Session, *, tenant: str = TENANT, portfolio_id: str | None = None
) -> tuple[str, str]:
    """A COMPLETED concentration run with real result rows. Returns (run_id, portfolio_id)."""
    from irp_shared.calc.models import RunStatus
    from irp_shared.calc.service import create_run, update_run_status

    pf = portfolio_id or str(uuid.uuid4())
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
                model_version_id=str(uuid.uuid4()),
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

    again = regenerate_report(
        session, report_id=str(row.id), acting_tenant=TENANT, portfolio_code="P-RPT"
    )
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
        regenerate_report(
            session, report_id=str(row.id), acting_tenant=TENANT, portfolio_code="P-RPT"
        )


def test_ANOTHER_TENANTS_report_is_refused(session: Session) -> None:
    """The tenant fence against the LIKELY hostile input — a REAL report owned by someone else, not
    a random UUID. The DEP-1 lesson: a nonexistent id refuses whether or not a fence exists."""
    run_id, pf = _seed_concentration_run(session)
    row, _ = _generate(session, run_id, pf)
    session.flush()
    with pytest.raises(ReportInputError, match="not visible"):
        regenerate_report(
            session, report_id=str(row.id), acting_tenant=OTHER_TENANT, portfolio_code="P-RPT"
        )


def test_a_run_from_ANOTHER_TENANT_cannot_be_bound(session: Session) -> None:
    """PostgreSQL FK checks bypass RLS, so a caller-supplied cross-tenant run id would otherwise be
    durably referenced by a governed artifact (the P3-5 doctrine). Refused pre-persist."""
    foreign_run, _ = _seed_concentration_run(session, tenant=OTHER_TENANT)
    with pytest.raises(ReportInputError):
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
    empty = create_run(
        session,
        tenant_id=TENANT,
        run_type=RUN_TYPE_CONCENTRATION,
        initiated_by="analyst",
        input_snapshot_id=str(snap.id),
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
            portfolio_id=str(uuid.uuid4()),
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

    pf = str(uuid.uuid4())
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
            model_version_id=str(uuid.uuid4()),
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
