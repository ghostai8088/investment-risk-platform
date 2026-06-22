"""SQLite-local unit/behavior tests for reference data (P1B-1, REQ-SMR-005 + REQ-SMR-004 calendar).

RLS is a no-op on SQLite, so the hybrid-tenancy isolation/asymmetry proofs live in
``test_reference_pg.py``; here we prove the governed-write contract (one MANUAL-source ORIGIN edge +
``REFERENCE.CREATE``), child fold-in (no extra events), the **application-layer** tenant-wins dedup,
EV mutability (``REFERENCE.UPDATE`` succeeds + bumps ``record_version``), the fail-closed audit
rollback (parent + children + edge), the import-direction guard, and the scope fence (taxonomy only,
no assignments, no reserved events).
"""

from __future__ import annotations

import json
import pathlib
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.entitlement.bootstrap import ALL_CODES, SYSTEM_TENANT_ID
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.reference.bootstrap import count_seeded, seed_system_reference
from irp_shared.reference.calendar import HolidaySpec, create_calendar, update_calendar
from irp_shared.reference.currency import create_currency, update_currency
from irp_shared.reference.events import (
    REFERENCE_CORRECTION_EVENT,
    REFERENCE_CREATE_EVENT,
    REFERENCE_STATUS_CHANGE_EVENT,
    REFERENCE_UPDATE_EVENT,
)
from irp_shared.reference.models import (
    HYBRID_TABLES,
    Calendar,
    CalendarHoliday,
    Currency,
    RatingGrade,
    RatingScale,
)
from irp_shared.reference.rating import GradeSpec, create_rating_scale, update_rating_scale
from irp_shared.reference.service import ReferenceActor, dedupe_tenant_wins
from irp_shared.temporal import TemporalClass


def _tenant() -> str:
    return str(uuid.uuid4())


def _actor() -> ReferenceActor:
    return ReferenceActor(actor_id="steward")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


# --- temporal classes: all five EV ---


def test_all_five_are_effective_dated() -> None:
    for model in (Currency, Calendar, CalendarHoliday, RatingScale, RatingGrade):
        assert model.__temporal_class__ == TemporalClass.EFFECTIVE_DATED
        assert hasattr(model, "valid_from") and hasattr(model, "record_version")


# --- governed create: lineage + REFERENCE.CREATE (literal codes) ---


def test_create_currency_records_lineage_and_audit(session: Session) -> None:
    tenant = _tenant()
    currency = create_currency(
        session, tenant_id=tenant, code="USD", name="US Dollar", actor=_actor(), minor_units=2
    )
    # Exactly one ORIGIN edge from a MANUAL data_source.
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == currency.id)
    ).scalar_one()
    assert edge.target_entity_type == "currency" and edge.edge_kind == "ORIGIN"
    source = session.get(DataSource, edge.source_id)
    assert source is not None and source.source_type == "MANUAL" and source.code == "MANUAL"
    assert_has_lineage(session, "currency", currency.id, tenant_id=tenant)
    # REFERENCE.CREATE emitted with the literal code + correct entity_type/action (CTRL-012).
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == currency.id)).scalar_one()
    assert ev.event_type == "REFERENCE.CREATE" == REFERENCE_CREATE_EVENT
    assert ev.entity_type == "currency" and ev.action == "create"
    assert ev.after_value == {
        "code": "USD",
        "name": "US Dollar",
        "is_active": True,
        "minor_units": 2,
    }
    assert verify_chain(session, tenant).ok is True


def test_manual_source_is_reused_across_writes(session: Session) -> None:
    tenant = _tenant()
    create_currency(session, tenant_id=tenant, code="USD", name="USD", actor=_actor())
    create_currency(session, tenant_id=tenant, code="EUR", name="EUR", actor=_actor())
    # One lazy MANUAL source per tenant, reused (not one per write).
    sources = session.execute(
        select(func.count()).select_from(DataSource).where(DataSource.tenant_id == tenant)
    ).scalar_one()
    assert sources == 1


# --- child fold-in: no extra events, one parent edge ---


def test_calendar_children_fold_into_parent_event(session: Session) -> None:
    tenant = _tenant()
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XNYS",
        name="NYSE",
        actor=_actor(),
        mic="XNYS",
        holidays=[
            HolidaySpec(holiday_date=date(2026, 1, 1), name="New Year"),
            HolidaySpec(holiday_date=date(2026, 12, 25), name="Christmas"),
        ],
    )
    holidays = (
        session.execute(select(CalendarHoliday).where(CalendarHoliday.calendar_id == cal.id))
        .scalars()
        .all()
    )
    assert len(holidays) == 2 and all(h.tenant_id == tenant for h in holidays)
    # Exactly ONE REFERENCE.CREATE for the whole calendar (children emit none); zero UPDATE events.
    assert _events(session, REFERENCE_CREATE_EVENT) == 1
    assert _events(session, REFERENCE_UPDATE_EVENT) == 0  # create path emits no spurious UPDATE
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == cal.id)).scalar_one()
    assert ev.after_value["holiday_count"] == 2
    # One ORIGIN edge at the parent level only (no per-holiday lineage).
    assert session.execute(select(func.count()).select_from(LineageEdge)).scalar_one() == 1


def test_rating_scale_children_fold_in(session: Session) -> None:
    tenant = _tenant()
    scale = create_rating_scale(
        session,
        tenant_id=tenant,
        code="SP",
        name="S&P",
        actor=_actor(),
        agency="SP",
        grades=[GradeSpec(code="AAA", rank=1), GradeSpec(code="AA", rank=2)],
    )
    grades = (
        session.execute(select(RatingGrade).where(RatingGrade.rating_scale_id == scale.id))
        .scalars()
        .all()
    )
    assert len(grades) == 2
    assert _events(session, REFERENCE_CREATE_EVENT) == 1
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == scale.id)).scalar_one()
    assert ev.after_value["grade_count"] == 2 and ev.entity_type == "rating_scale"


# --- EV mutability: REFERENCE.UPDATE succeeds, bumps record_version ---


def test_update_currency_is_mutable_and_audited(session: Session) -> None:
    tenant = _tenant()
    currency = create_currency(
        session, tenant_id=tenant, code="USD", name="US Dollar", actor=_actor()
    )
    update_currency(session, currency, actor=_actor(), name="United States Dollar", is_active=False)
    assert currency.record_version == 2 and currency.name == "United States Dollar"
    ev = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == REFERENCE_UPDATE_EVENT)
            .order_by(AuditEvent.sequence_no.desc())
        )
        .scalars()
        .first()
    )
    assert ev is not None and ev.event_type == "REFERENCE.UPDATE" and ev.action == "update"
    assert ev.before_value == {"name": "US Dollar", "is_active": True}
    assert ev.after_value == {"name": "United States Dollar", "is_active": False}


def test_update_keeps_exactly_one_origin_edge(session: Session) -> None:
    # The single-origin invariant: an UPDATE must NOT add a second ORIGIN edge (lineage is
    # CREATE-only; an entity keeps the one edge rooted at creation).
    tenant = _tenant()
    currency = create_currency(
        session, tenant_id=tenant, code="USD", name="US Dollar", actor=_actor()
    )
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == currency.id)
    ).scalar_one()
    before_source = edge.source_id
    update_currency(session, currency, actor=_actor(), name="Renamed")
    update_currency(session, currency, actor=_actor(), is_active=False)
    edges = (
        session.execute(select(LineageEdge).where(LineageEdge.target_entity_id == currency.id))
        .scalars()
        .all()
    )
    assert len(edges) == 1  # still exactly one
    assert edges[0].source_id == before_source and edges[0].edge_kind == "ORIGIN"


def test_calendar_and_rating_updates_emit_update_event(session: Session) -> None:
    tenant = _tenant()
    cal = create_calendar(session, tenant_id=tenant, code="C", name="C", actor=_actor())
    update_calendar(session, cal, actor=_actor(), name="C2")
    scale = create_rating_scale(session, tenant_id=tenant, code="S", name="S", actor=_actor())
    update_rating_scale(session, scale, actor=_actor(), agency="MOODYS")
    assert _events(session, REFERENCE_UPDATE_EVENT) == 2
    assert cal.record_version == 2 and scale.record_version == 2


def test_update_rejects_unknown_attribute(session: Session) -> None:
    tenant = _tenant()
    currency = create_currency(session, tenant_id=tenant, code="USD", name="USD", actor=_actor())
    with pytest.raises(ValueError, match="non-updatable currency"):
        update_currency(
            session, currency, actor=_actor(), code="EUR"
        )  # code is identity, not editable


# --- tenant override wins (application-layer dedup) ---


def test_dedupe_tenant_wins_over_system(session: Session) -> None:
    tenant = _tenant()
    create_currency(session, tenant_id=tenant, code="USD", name="Tenant USD", actor=_actor())
    # A coexisting SYSTEM row of the same code (no RLS on SQLite, so add directly).
    session.add(
        Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="Global USD", record_version=1)
    )
    session.flush()
    rows = session.execute(select(Currency)).scalars().all()
    winners = dedupe_tenant_wins(rows, tenant)
    assert len(winners) == 1 and winners[0].tenant_id == tenant and winners[0].name == "Tenant USD"


def test_dedupe_returns_system_when_no_override(session: Session) -> None:
    tenant = _tenant()
    session.add(
        Currency(tenant_id=SYSTEM_TENANT_ID, code="JPY", name="Global JPY", record_version=1)
    )
    session.flush()
    rows = session.execute(select(Currency)).scalars().all()
    winners = dedupe_tenant_wins(rows, tenant)
    assert len(winners) == 1 and winners[0].tenant_id == SYSTEM_TENANT_ID


# --- fail-closed audit (AUD-04 / CTRL-032): parent + children + edge roll back together ---


def _raise_audit(*_a: object, **_k: object) -> None:
    raise RuntimeError("audit capture failed")


def test_create_rolls_back_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import irp_shared.reference.service as svc

    tenant = _tenant()
    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        create_calendar(
            session,
            tenant_id=tenant,
            code="X",
            name="X",
            actor=_actor(),
            holidays=[HolidaySpec(holiday_date=date(2026, 1, 1))],
        )
    session.rollback()
    # The WHOLE governed unit-of-work rolled back — no orphan of ANY side-effect. Crucially this
    # includes the lazily-created provenance objects: record_reference_create calls
    # ensure_manual_source FIRST (which registers the MANUAL data_source + emits its
    # DATA.SOURCE_REGISTER via the lineage module's record_event — NOT the patched one) and
    # record_lineage BEFORE the patched REFERENCE.CREATE raises. Asserting DataSource==0 and
    # AuditEvent==0 proves a leaked provenance root would be caught (AUD-04/CTRL-032).
    assert session.execute(select(func.count()).select_from(Calendar)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(CalendarHoliday)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(LineageEdge)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(DataSource)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(AuditEvent)).scalar_one() == 0


# --- SYSTEM seed catalog (governed path) ---


def test_seed_system_reference_creates_governed_global_slice(session: Session) -> None:
    seed_system_reference(session, actor_id="system")
    counts = count_seeded(session)
    assert counts["currency"] >= 1 and counts["calendar"] >= 1 and counts["rating_scale"] >= 1
    # The seed is governed: REFERENCE.CREATE on the SYSTEM chain + a MANUAL SYSTEM source + lineage.
    sys_events = session.execute(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.event_type == REFERENCE_CREATE_EVENT,
            AuditEvent.tenant_id == SYSTEM_TENANT_ID,
        )
    ).scalar_one()
    assert sys_events == counts["currency"] + counts["calendar"] + counts["rating_scale"]
    assert verify_chain(session, SYSTEM_TENANT_ID).ok is True
    sys_source = session.execute(
        select(DataSource).where(
            DataSource.tenant_id == SYSTEM_TENANT_ID, DataSource.source_type == "MANUAL"
        )
    ).scalar_one()
    assert sys_source.code == "MANUAL"
    # ensure_manual_source is idempotent under SYSTEM context: exactly ONE MANUAL source for the
    # whole seed, registered exactly ONCE (one DATA.SOURCE_REGISTER on the SYSTEM chain) — reused
    # across every seeded currency/calendar/rating_scale, not re-created per write.
    manual_sources = session.execute(
        select(func.count())
        .select_from(DataSource)
        .where(DataSource.tenant_id == SYSTEM_TENANT_ID, DataSource.source_type == "MANUAL")
    ).scalar_one()
    assert manual_sources == 1
    source_registers = session.execute(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.event_type == "DATA.SOURCE_REGISTER",
            AuditEvent.tenant_id == SYSTEM_TENANT_ID,
        )
    ).scalar_one()
    assert source_registers == 1


# --- scope fence (negative) ---


def test_scope_fence_exactly_five_tables() -> None:
    assert set(HYBRID_TABLES) == {
        "currency",
        "calendar",
        "calendar_holiday",
        "rating_scale",
        "rating_grade",
    }
    assert {
        m.__tablename__ for m in (Currency, Calendar, CalendarHoliday, RatingScale, RatingGrade)
    } == set(HYBRID_TABLES)


def test_rating_is_taxonomy_only_no_assignment_columns() -> None:
    # rating_scale / rating_grade are EV taxonomy: NO rated-entity FK / as-of / outlook / watch.
    scale_cols = set(RatingScale.__table__.columns.keys())
    grade_cols = set(RatingGrade.__table__.columns.keys())
    forbidden = {"instrument_id", "issuer_id", "rated_entity", "as_of", "outlook", "watch"}
    assert not (forbidden & scale_cols) and not (forbidden & grade_cols)
    # The only FK on a grade is its parent scale (no rated-entity FK).
    grade_fk_targets = {fk.column.table.name for fk in RatingGrade.__table__.foreign_keys}
    assert grade_fk_targets == {"rating_scale"}
    assert not RatingScale.__table__.foreign_keys  # head has no FK


def test_calendar_holiday_fk_only_to_calendar() -> None:
    fk_targets = {fk.column.table.name for fk in CalendarHoliday.__table__.foreign_keys}
    assert fk_targets == {"calendar"}


def test_no_unique_on_code_alone() -> None:
    # The override pattern requires UNIQUE(tenant_id, code) — a bare UNIQUE(code) would collapse it.
    for model in (Currency, Calendar, RatingScale):
        for uc in model.__table__.constraints:
            cols = getattr(uc, "columns", None)
            if cols is not None and {c.name for c in cols} == {"code"}:
                raise AssertionError(f"{model.__tablename__} has a forbidden UNIQUE(code)")


def test_reserved_events_not_emitted_and_rating_perm_reserved(session: Session) -> None:
    tenant = _tenant()
    create_currency(session, tenant_id=tenant, code="USD", name="USD", actor=_actor())
    create_calendar(session, tenant_id=tenant, code="C", name="C", actor=_actor())
    create_rating_scale(session, tenant_id=tenant, code="S", name="S", actor=_actor())
    # The reserved taxonomy codes are declared but NEVER emitted in P1B-1.
    assert _events(session, REFERENCE_CORRECTION_EVENT) == 0
    assert _events(session, REFERENCE_STATUS_CHANGE_EVENT) == 0
    # reference.rating.* is RESERVED, not minted (future FR assignment domain).
    assert not any(code.startswith("reference.rating.") for code in ALL_CODES)
    # The activated reference permissions exist.
    for code in (
        "reference.currency.view",
        "reference.currency.edit",
        "reference.rating_scale.view",
        "reference.rating_scale.edit",
        "reference.calendar.view",
    ):
        assert code in ALL_CODES


# --- import direction (static text scanner, mirrors test_ingestion) ---


def test_reference_import_direction() -> None:
    import irp_shared.reference as ref_pkg

    forbidden = (
        "irp_backend",
        "irp_shared.models",  # the plural aggregator (cycle vector)
        "irp_shared.ingestion",
        "irp_shared.risk",
        "irp_shared.portfolio",
        "irp_shared.reporting",
    )
    # Allowlist (the "imports only" spec): any first-party irp_shared.* import must land in exactly
    # these subpackages. This fails CLOSED on a NEW cross-layer import (e.g. irp_shared.calc/model)
    # that a denylist would silently admit. ``reference`` = intra-package; ``temporal`` is a module.
    allowed_subpackages = {"lineage", "dq", "audit", "entitlement", "db", "temporal", "reference"}
    ref_dir = pathlib.Path(ref_pkg.__file__).parent
    for py in sorted(ref_dir.glob("*.py")):
        for line in py.read_text().splitlines():
            stripped = line.strip()
            mods: list[str] = []
            if stripped.startswith("from "):
                base = stripped.split()[1]
                mods.append(base)
                if " import " in stripped:
                    for name in stripped.split(" import ", 1)[1].replace("(", "").split(","):
                        token = name.strip().split(" as ")[0].strip()
                        if token and token != "*":
                            mods.append(f"{base}.{token}")
            elif stripped.startswith("import "):
                mods.append(stripped.split()[1].split(",")[0])
            else:
                continue
            for mod in mods:
                for root in forbidden:
                    assert mod != root and not mod.startswith(
                        root + "."
                    ), f"{py.name} imports forbidden {mod}"
                # Allowlist enforcement for first-party imports (denylist alone is not enough).
                if mod.startswith("irp_shared."):
                    segments = mod.split(".")
                    assert (
                        segments[1] in allowed_subpackages
                    ), f"{py.name} imports non-allowlisted {mod} (irp_shared.{segments[1]})"


def test_rails_do_not_import_reference() -> None:
    # Every rail reference depends on (lineage/dq/audit/entitlement) must NOT import it back —
    # entitlement is a real cycle vector (reference.bootstrap imports entitlement.bootstrap). db is
    # swept too for completeness; temporal is a single module (no package dir) handled separately.
    import irp_shared.audit as audit_pkg
    import irp_shared.db as db_pkg
    import irp_shared.dq as dq_pkg
    import irp_shared.entitlement as ent_pkg
    import irp_shared.lineage as lin_pkg
    import irp_shared.temporal as temporal_mod

    for pkg in (dq_pkg, lin_pkg, audit_pkg, ent_pkg, db_pkg):
        pkg_dir = pathlib.Path(pkg.__file__).parent
        for py in sorted(pkg_dir.glob("*.py")):
            assert "irp_shared.reference" not in py.read_text(), f"{pkg.__name__}/{py.name}"
    assert "irp_shared.reference" not in pathlib.Path(temporal_mod.__file__).read_text()


def test_audit_after_value_is_metadata_only(session: Session) -> None:
    # DC-2: REFERENCE.* after_value carries identifying/controlled-vocab fields + counts only —
    # never full child collections or raw input. (A holiday's name is metadata, not a smuggled row.)
    tenant = _tenant()
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XNYS",
        name="NYSE",
        actor=_actor(),
        holidays=[HolidaySpec(holiday_date=date(2026, 1, 1), name="NY")],
    )
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == cal.id)).scalar_one()
    body = json.dumps(ev.after_value)
    assert set(ev.after_value) == {"code", "name", "is_active", "mic", "holiday_count"}
    assert "2026-01-01" not in body  # no serialized child rows
