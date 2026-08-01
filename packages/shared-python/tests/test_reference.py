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
from irp_shared.reference.bootstrap import (
    SYSTEM_CALENDAR_CODE,
    SYSTEM_CALENDAR_HOLIDAYS,
    count_seeded,
    seed_system_reference,
)
from irp_shared.reference.calendar import (
    HolidaySpec,
    create_calendar,
    refresh_calendar_holidays,
    update_calendar,
)
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
from irp_shared.reference.xnys_holidays import XNYS_HOLIDAYS, XNYS_RULE_72_OPEN_FRIDAYS
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


def test_scope_fence_hybrid_set_is_exactly_seven_tables() -> None:
    """EXTENDED AT REF-1 (AD-013-R2, user-ratified): five P1B-1 vocabularies + two classification
    vocabulary tables. The five P1B-1 models still account for exactly their own five, so this
    package's own contribution to the set cannot drift while the total grows."""
    assert set(HYBRID_TABLES) == {
        "currency",
        "calendar",
        "calendar_holiday",
        "rating_scale",
        "rating_grade",
        "classification_scheme",
        "classification_node",
    }
    p1b1 = {
        m.__tablename__ for m in (Currency, Calendar, CalendarHoliday, RatingScale, RatingGrade)
    }
    assert p1b1 <= set(HYBRID_TABLES)
    assert set(HYBRID_TABLES) - p1b1 == {"classification_scheme", "classification_node"}


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
        "irp_shared.market_data",  # deferred downstream packages (explicit; allowlist also blocks)
        "irp_shared.calc",
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


# --- CAL-1a: the ADD-ONLY holiday refresh + the XNYS dataset censuses (OQ-CAL-1-8/-11) ---


def test_refresh_calendar_holidays_adds_the_diff_once_and_is_idempotent(session: Session) -> None:
    tenant = _tenant()
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XTST",
        name="Refresh target",
        actor=_actor(),
        holidays=[
            HolidaySpec(holiday_date=date(2026, 1, 1), name="NY"),
            HolidaySpec(holiday_date=date(2026, 12, 25), name="Xmas"),
        ],
    )
    version_before = cal.record_version
    updates_before = _events(session, REFERENCE_UPDATE_EVENT)

    added = refresh_calendar_holidays(
        session,
        cal,
        actor=_actor(),
        holidays=[
            HolidaySpec(holiday_date=date(2026, 1, 1), name="NY"),  # already present
            HolidaySpec(holiday_date=date(2026, 5, 25), name="Memorial Day"),
            HolidaySpec(holiday_date=date(2026, 7, 3), name="Independence Day (observed)"),
        ],
    )
    assert added == 2
    dates = set(
        session.execute(
            select(CalendarHoliday.holiday_date).where(CalendarHoliday.calendar_id == cal.id)
        ).scalars()
    )
    assert dates == {date(2026, 1, 1), date(2026, 12, 25), date(2026, 5, 25), date(2026, 7, 3)}
    assert cal.record_version == version_before + 1
    assert _events(session, REFERENCE_UPDATE_EVENT) == updates_before + 1
    ev = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == REFERENCE_UPDATE_EVENT, AuditEvent.entity_id == cal.id)
            .order_by(AuditEvent.sequence_no.desc())
        )
        .scalars()
        .first()
    )
    assert ev is not None
    assert ev.before_value == {"holiday_count": 2}
    assert ev.after_value == {
        "holiday_count": 4,
        "holidays_added": 2,
        "added_from": "2026-05-25",
        "added_through": "2026-07-03",
    }

    # Idempotent re-run: nothing added, no version bump, NO event.
    added_again = refresh_calendar_holidays(
        session,
        cal,
        actor=_actor(),
        holidays=[
            HolidaySpec(holiday_date=date(2026, 5, 25), name="Memorial Day"),
            HolidaySpec(holiday_date=date(2026, 7, 3), name="Independence Day (observed)"),
        ],
    )
    assert added_again == 0
    assert cal.record_version == version_before + 1
    assert _events(session, REFERENCE_UPDATE_EVENT) == updates_before + 1


def test_refresh_is_add_only_a_subset_input_deletes_nothing(session: Session) -> None:
    # The negative control on the verb's central claim: absence from the input is NOT removal.
    tenant = _tenant()
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XSUB",
        name="Subset target",
        actor=_actor(),
        holidays=[
            HolidaySpec(holiday_date=date(2026, 1, 1), name="NY"),
            HolidaySpec(holiday_date=date(2026, 12, 25), name="Xmas"),
        ],
    )
    added = refresh_calendar_holidays(
        session, cal, actor=_actor(), holidays=[HolidaySpec(holiday_date=date(2026, 1, 1))]
    )
    assert added == 0
    remaining = set(
        session.execute(
            select(CalendarHoliday.holiday_date).where(CalendarHoliday.calendar_id == cal.id)
        ).scalars()
    )
    assert remaining == {date(2026, 1, 1), date(2026, 12, 25)}


def test_refresh_never_mutates_an_existing_child(session: Session) -> None:
    # An already-present date wins AS STORED: a differing name in the input is ignored.
    tenant = _tenant()
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XMUT",
        name="Mutation target",
        actor=_actor(),
        holidays=[HolidaySpec(holiday_date=date(2026, 1, 1), name="New Year's Day")],
    )
    version_before = cal.record_version
    updates_before = _events(session, REFERENCE_UPDATE_EVENT)
    added = refresh_calendar_holidays(
        session,
        cal,
        actor=_actor(),
        holidays=[HolidaySpec(holiday_date=date(2026, 1, 1), name="RENAMED")],
    )
    row = session.execute(
        select(CalendarHoliday).where(CalendarHoliday.calendar_id == cal.id)
    ).scalar_one()
    assert row.name == "New Year's Day"
    assert row.record_version == 1
    # A rename-ignored refresh that still emitted an event would be an audit lie (review fold).
    assert added == 0
    assert cal.record_version == version_before
    assert _events(session, REFERENCE_UPDATE_EVENT) == updates_before


def test_the_xnys_dataset_census(session: Session) -> None:
    """The DOUBLE census (OQ-CAL-1-8): structure + anchor pins AND the Rule 7.2 negatives.

    The set is hand-encoded literals. This census pins per-year COUNTS, the tricky observance
    ANCHORS, and the negatives; FULL membership is pinned by the independent rule re-derivation
    test below — the review fold executed a mutation check proving the pair is needed (the census
    alone missed 5 of 6 single-date perturbations; the derivation caught all 6)."""
    dates = [d for d, _ in XNYS_HOLIDAYS]
    dset = set(dates)
    assert len(dates) == len(dset) == 118  # no duplicates; the full 2024-2035 count
    per_year = {y: sum(1 for d in dates if d.year == y) for y in range(2024, 2036)}
    # 2028 and 2033 carry NINE: Saturday New Year's unobserved (NYSE Rule 7.2).
    assert per_year == {
        2024: 10,
        2025: 10,
        2026: 10,
        2027: 10,
        2028: 9,
        2029: 10,
        2030: 10,
        2031: 10,
        2032: 10,
        2033: 9,
        2034: 10,
        2035: 10,
    }
    # Every observed closure is a weekday (Sat/Sun holidays are substituted or unobserved).
    assert all(d.weekday() < 5 for d in dates)
    # The four last-weekday month-end collisions the scheduler's recorded limitation quantifies.
    assert {date(2024, 3, 29), date(2027, 5, 31), date(2029, 3, 30), date(2032, 5, 31)} <= dset
    # The Rule 7.2 NEGATIVES: these Fridays are TRADING days; a naive observance rule adds them.
    assert XNYS_RULE_72_OPEN_FRIDAYS == (date(2027, 12, 31), date(2032, 12, 31))
    assert dset.isdisjoint(XNYS_RULE_72_OPEN_FRIDAYS)
    # The two token seed dates are members, so the seed's refresh is idempotent over them.
    assert {d for d, _ in SYSTEM_CALENDAR_HOLIDAYS} <= dset
    # Anchor pins (review fold): the observance dates a wrong rule plausibly gets wrong -- known
    # published Good Fridays, Sat->Fri and Sun->Mon substitutions near month/year boundaries.
    assert {
        date(2025, 4, 18),  # Good Friday 2025 (published)
        date(2026, 4, 3),  # Good Friday 2026 (published)
        date(2026, 7, 3),  # Independence Day observed (Jul 4 Saturday)
        date(2027, 7, 5),  # Independence Day observed (Jul 4 Sunday)
        date(2027, 12, 24),  # Christmas observed (Dec 25 Saturday; NOT a month-end Friday)
        date(2032, 6, 18),  # Juneteenth observed (Jun 19 Saturday)
        date(2033, 6, 20),  # Juneteenth observed (Jun 19 Sunday)
        date(2033, 12, 26),  # Christmas observed (Dec 25 Sunday; stays in-month)
        date(2034, 1, 2),  # New Year observed (Jan 1 Sunday; stays in-year)
    } <= dset
    # The exact 9-member sets for the two Rule 7.2 years (New Year's Day unobserved).
    assert {d for d in dates if d.year == 2028} == {
        date(2028, 1, 17),
        date(2028, 2, 21),
        date(2028, 4, 14),
        date(2028, 5, 29),
        date(2028, 6, 19),
        date(2028, 7, 4),
        date(2028, 9, 4),
        date(2028, 11, 23),
        date(2028, 12, 25),
    }
    assert {d for d in dates if d.year == 2033} == {
        date(2033, 1, 17),
        date(2033, 2, 21),
        date(2033, 4, 15),
        date(2033, 5, 30),
        date(2033, 6, 20),
        date(2033, 7, 4),
        date(2033, 9, 5),
        date(2033, 11, 24),
        date(2033, 12, 26),
    }


def test_the_xnys_dataset_agrees_with_an_independent_rule_derivation(session: Session) -> None:
    """Cross-check the hand-encoded literals against an INDEPENDENT in-test derivation
    (statutory definitions + observance incl. the Rule 7.2 year-end exception). Two encodings
    agreeing is the strongest offline check available; the published-calendar citation lives in
    the diligence checklist (Execution 1) and the decision record's Part 5."""
    from datetime import timedelta

    def easter_sunday(year: int) -> date:
        a = year % 19
        century, rem = divmod(year, 100)
        d_, e_ = divmod(century, 4)
        f_ = (century + 8) // 25
        g_ = (century - f_ + 1) // 3
        h_ = (19 * a + century - d_ - g_ + 15) % 30
        i_, k_ = divmod(rem, 4)
        l_ = (32 + 2 * e_ + 2 * i_ - h_ - k_) % 7
        m_ = (a + 11 * h_ + 22 * l_) // 451
        month, day = divmod(h_ + l_ - 7 * m_ + 114, 31)
        return date(year, month, day + 1)

    def nth_monday(year: int, month: int, n: int) -> date:
        first = date(year, month, 1)
        return first + timedelta(days=(0 - first.weekday()) % 7, weeks=n - 1)

    def last_monday_of_may(year: int) -> date:
        d = date(year, 5, 31)
        return d - timedelta(days=(d.weekday() - 0) % 7)

    def fourth_thursday_of_november(year: int) -> date:
        first = date(year, 11, 1)
        return first + timedelta(days=(3 - first.weekday()) % 7, weeks=3)

    expected: set[date] = set()
    for year in range(2024, 2036):
        for nominal in (
            date(year, 1, 1),
            nth_monday(year, 1, 3),
            nth_monday(year, 2, 3),
            easter_sunday(year) - timedelta(days=2),
            last_monday_of_may(year),
            date(year, 6, 19),
            date(year, 7, 4),
            nth_monday(year, 9, 1),
            fourth_thursday_of_november(year),
            date(year, 12, 25),
        ):
            if nominal.weekday() == 5:
                substitute = nominal - timedelta(days=1)
                if substitute.month != (substitute + timedelta(days=1)).month:
                    # Rule 7.2: the substitute Friday is a month-end -> exchange OPEN.
                    # (Last-CALENDAR-day check == last-BUSINESS-day here: the only
                    # triggering case is Saturday Jan 1, whose substitute is Dec 31.)
                    continue
                expected.add(substitute)
            elif nominal.weekday() == 6:
                expected.add(nominal + timedelta(days=1))
            else:
                expected.add(nominal)
    assert {d for d, _ in XNYS_HOLIDAYS} == expected


def test_seed_system_reference_loads_the_full_xnys_set(session: Session) -> None:
    seed_system_reference(session, actor_id="system")
    xnys = session.execute(
        select(Calendar).where(
            Calendar.tenant_id == SYSTEM_TENANT_ID, Calendar.code == SYSTEM_CALENDAR_CODE
        )
    ).scalar_one()
    n = session.execute(
        select(func.count())
        .select_from(CalendarHoliday)
        .where(CalendarHoliday.calendar_id == xnys.id)
    ).scalar_one()
    assert n == len(XNYS_HOLIDAYS) == 118
    # Exactly ONE REFERENCE.UPDATE on the SYSTEM chain: the refresh's single parent event.
    updates = session.execute(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.event_type == REFERENCE_UPDATE_EVENT,
            AuditEvent.tenant_id == SYSTEM_TENANT_ID,
        )
    ).scalar_one()
    assert updates == 1
    assert verify_chain(session, SYSTEM_TENANT_ID).ok is True


def test_refresh_dedupes_duplicate_specs_first_wins(session: Session) -> None:
    """Duplicate specs for one NEW date in ONE input dedupe first-spec-wins (review fold: the
    pre-fold verb inserted both and crashed on the child UNIQUE mid-flush)."""
    tenant = _tenant()
    cal = create_calendar(session, tenant_id=tenant, code="XDUP", name="Dup target", actor=_actor())
    added = refresh_calendar_holidays(
        session,
        cal,
        actor=_actor(),
        holidays=[
            HolidaySpec(holiday_date=date(2026, 5, 25), name="Memorial Day"),
            HolidaySpec(holiday_date=date(2026, 5, 25), name="DUPLICATE-LOSES"),
        ],
    )
    assert added == 1
    row = session.execute(
        select(CalendarHoliday).where(CalendarHoliday.calendar_id == cal.id)
    ).scalar_one()
    assert row.name == "Memorial Day"


def test_refresh_with_an_empty_input_is_a_no_op(session: Session) -> None:
    tenant = _tenant()
    cal = create_calendar(
        session, tenant_id=tenant, code="XEMP", name="Empty target", actor=_actor()
    )
    version_before = cal.record_version
    updates_before = _events(session, REFERENCE_UPDATE_EVENT)
    assert refresh_calendar_holidays(session, cal, actor=_actor(), holidays=[]) == 0
    assert cal.record_version == version_before
    assert _events(session, REFERENCE_UPDATE_EVENT) == updates_before


def test_a_second_effective_refresh_recounts_and_a_mixed_input_counts_only_new(
    session: Session,
) -> None:
    """The event's before/after recount from the live child set on EACH refresh, and a mixed
    rename-plus-addition input counts ONLY the new dates (the rename stays ignored)."""
    tenant = _tenant()
    cal = create_calendar(
        session,
        tenant_id=tenant,
        code="XSEQ",
        name="Sequence target",
        actor=_actor(),
        holidays=[HolidaySpec(holiday_date=date(2026, 1, 1), name="New Year's Day")],
    )
    refresh_calendar_holidays(
        session, cal, actor=_actor(), holidays=[HolidaySpec(holiday_date=date(2026, 5, 25))]
    )
    added = refresh_calendar_holidays(
        session,
        cal,
        actor=_actor(),
        holidays=[
            HolidaySpec(holiday_date=date(2026, 1, 1), name="RENAMED-IGNORED"),
            HolidaySpec(holiday_date=date(2026, 12, 25), name="Christmas Day"),
        ],
    )
    assert added == 1
    ev = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.event_type == REFERENCE_UPDATE_EVENT, AuditEvent.entity_id == cal.id)
            .order_by(AuditEvent.sequence_no.desc())
        )
        .scalars()
        .first()
    )
    assert ev is not None
    assert ev.before_value == {"holiday_count": 2}
    assert ev.after_value == {
        "holiday_count": 3,
        "holidays_added": 1,
        "added_from": "2026-12-25",
        "added_through": "2026-12-25",
    }


def test_refresh_rolls_back_children_and_version_when_audit_fails(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refresh verb's OWN fail-closed pin (review fold: it was inherited from the create
    path, not pinned per-verb): an audit failure discards the children AND the version bump."""
    import irp_shared.reference.service as reference_service

    tenant = _tenant()
    cal = create_calendar(
        session, tenant_id=tenant, code="XAUD", name="Audit-fail target", actor=_actor()
    )
    version_before = cal.record_version

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit capture failed")

    monkeypatch.setattr(reference_service, "record_event", _boom)
    nested = session.begin_nested()  # the caller-owned rollback unit; the setup calendar survives
    with pytest.raises(RuntimeError):
        refresh_calendar_holidays(
            session,
            cal,
            actor=_actor(),
            holidays=[HolidaySpec(holiday_date=date(2026, 5, 25), name="Memorial Day")],
        )
    nested.rollback()
    session.expire_all()
    assert (
        session.execute(
            select(func.count())
            .select_from(CalendarHoliday)
            .where(CalendarHoliday.calendar_id == cal.id)
        ).scalar_one()
        == 0
    )
    refreshed = session.execute(select(Calendar).where(Calendar.id == cal.id)).scalar_one()
    assert refreshed.record_version == version_before
