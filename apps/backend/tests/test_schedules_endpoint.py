"""End-to-end tests of the SCH-2 schedule READ endpoints (OQ-SCH-2-7c).

The read exists for ONE ratified purpose: a burned month must be visible WHEN IT HAPPENS rather
than surfacing months later as an RM-1 alignment refusal. So the load-bearing assertions here are
the failure paths — ``?outcome=FAILED`` returns the burned tick with its reason, a pre-create
refusal (``calculation_run_id`` NULL) is distinguishable from a post-create FAILED run, and a
never-fired schedule is legible as such. The rest is the house contract: deny-by-default gating on
the SCH-1-minted ``schedule.view`` (no new mint), tenant scoping via the explicit predicate, and
silent-empty on a foreign id (no existence oracle).

SQLite has no RLS, so cross-tenant isolation proper is proven at the PG tier; what is proven here is
that the explicit ``tenant_id`` predicate in ``scheduling/queries.py`` alone already refuses.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from datetime import date as dt_date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_backend.api.schedules import router as schedules_router
from irp_backend.deps import get_db
from irp_shared.calc.models import CalculationRun
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
from irp_shared.model.models import Model, ModelVersion
from irp_shared.models import Base
from irp_shared.portfolio.models import Portfolio
from irp_shared.scheduling.events import (
    CADENCE_CALENDAR_MONTH_END,
    CADENCE_INTERVAL,
    OUTCOME_DISPATCHED,
    OUTCOME_FAILED,
    SCHEDULE_STATUS_PAUSED,
    TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
    TARGET_RUN_TYPE_VAR,
    SchedulingActor,
)
from irp_shared.scheduling.models import ScheduledRun
from irp_shared.scheduling.service import create_schedule

_ACTOR = SchedulingActor(actor_id="ops-1", actor_type="user")
_VIEW = ("schedule.view",)
_NO_VIEW = ("portfolio.view",)  # a real permission that is NOT the gate

#: The May-2026 month-end grid point: the 31st is a SUNDAY, so the tick is Friday the 29th.
_MAY_TICK = datetime(2026, 5, 29, 23, 59, 59, 999999, tzinfo=UTC)
_APR_TICK = datetime(2026, 4, 30, 23, 59, 59, 999999, tzinfo=UTC)


def _grant(db: Session, tenant: str, user_id: str, codes: tuple[str, ...]) -> None:
    role = Role(tenant_id=tenant, code=f"r-{uuid.uuid4().hex[:6]}", name="R")
    db.add(role)
    db.flush()
    for code in codes:
        perm = db.query(Permission).filter_by(code=code).one_or_none() or Permission(
            code=code, description="d"
        )
        db.add(perm)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.add(UserRole(tenant_id=tenant, user_id=user_id, role_id=role.id))


def _seed_portfolio(db: Session, tenant: str) -> str:
    p = Portfolio(
        tenant_id=tenant, code=f"pf-{uuid.uuid4().hex[:8]}", name="Book", node_type="BOOK"
    )
    db.add(p)
    db.flush()
    return str(p.id)


def _seed_calculation_run(db: Session, tenant: str, run_type: str) -> str:
    """A genuine parent for ``scheduled_run.calculation_run_id`` (FK → calculation_run.run_id)."""
    run = CalculationRun(
        tenant_id=tenant,
        run_type=run_type,
        status="SUCCEEDED",
        initiated_by="scheduler",
        code_version="v1",
        environment_id="ci",
    )
    db.add(run)
    db.flush()
    return str(run.run_id)


def _seed_model_version(db: Session, tenant: str) -> str:
    m = Model(tenant_id=tenant, code=f"m-{uuid.uuid4().hex[:8]}", name="VaR", model_type="RISK")
    db.add(m)
    db.flush()
    mv = ModelVersion(tenant_id=tenant, model_id=str(m.id), version_label="v1")
    db.add(mv)
    db.flush()
    return str(mv.id)


@pytest.fixture
def ctx() -> Iterator[dict[str, object]]:
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()

    tenant = str(uuid.uuid4())
    viewer = AppUser(tenant_id=tenant, display_name="Ops")
    blind = AppUser(tenant_id=tenant, display_name="NoView")
    db.add_all([viewer, blind])
    db.flush()
    _grant(db, tenant, viewer.id, _VIEW)
    _grant(db, tenant, blind.id, _NO_VIEW)

    # (1) A month-end EXPOSURE schedule that HAS fired — one good month, one burned month.
    fired = create_schedule(
        db,
        tenant_id=tenant,
        code="MONTH-END-EXPOSURE",
        name="Month-end exposure",
        target_run_type=TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
        scope_portfolio_id=_seed_portfolio(db, tenant),
        environment_id="ci",
        anchor_date=dt_date(2026, 3, 2),
        actor=_ACTOR,
        cadence_kind=CADENCE_CALENDAR_MONTH_END,
    )
    # April: a clean fire. May: BURNED — a pre-create refusal, so calculation_run_id is NULL.
    db.add(
        ScheduledRun(
            tenant_id=tenant,
            schedule_id=fired.id,
            scheduled_for=_APR_TICK,
            fired_at=datetime(2026, 5, 1, 6, 5, tzinfo=UTC),
            calculation_run_id=_seed_calculation_run(
                db, tenant, TARGET_RUN_TYPE_EXPOSURE_AGGREGATE
            ),
            outcome=OUTCOME_DISPATCHED,
        )
    )
    db.add(
        ScheduledRun(
            tenant_id=tenant,
            schedule_id=fired.id,
            scheduled_for=_MAY_TICK,
            fired_at=datetime(2026, 6, 1, 6, 5, tzinfo=UTC),
            calculation_run_id=None,  # refused BEFORE a run was created
            outcome=OUTCOME_FAILED,
            failure_reason="no marks for the month-end valuation date",
        )
    )

    # (2) An INTERVAL VaR schedule that has NEVER fired, and is PAUSED (for the status filter).
    never = create_schedule(
        db,
        tenant_id=tenant,
        code="AAA-DAILY-VAR",  # sorts FIRST by code — pins the ordering contract
        name="Daily VaR",
        target_run_type=TARGET_RUN_TYPE_VAR,
        scope_portfolio_id=_seed_portfolio(db, tenant),
        model_version_id=_seed_model_version(db, tenant),
        environment_id="ci",
        anchor_date=dt_date(2026, 1, 1),
        actor=_ACTOR,
        cadence_kind=CADENCE_INTERVAL,
        interval_days=1,
        status=SCHEDULE_STATUS_PAUSED,
    )

    # (3) A SECOND tenant with its own schedule — the explicit-predicate isolation control.
    tenant_b = str(uuid.uuid4())
    user_b = AppUser(tenant_id=tenant_b, display_name="B")
    db.add(user_b)
    db.flush()
    _grant(db, tenant_b, user_b.id, _VIEW)
    other = create_schedule(
        db,
        tenant_id=tenant_b,
        code="OTHER-TENANT",
        name="Other",
        target_run_type=TARGET_RUN_TYPE_EXPOSURE_AGGREGATE,
        scope_portfolio_id=_seed_portfolio(db, tenant_b),
        environment_id="ci",
        anchor_date=dt_date(2026, 3, 2),
        actor=_ACTOR,
        cadence_kind=CADENCE_CALENDAR_MONTH_END,
    )
    db.add(
        ScheduledRun(
            tenant_id=tenant_b,
            schedule_id=other.id,
            scheduled_for=_MAY_TICK,
            fired_at=datetime(2026, 6, 1, 6, 5, tzinfo=UTC),
            calculation_run_id=_seed_calculation_run(
                db, tenant_b, TARGET_RUN_TYPE_EXPOSURE_AGGREGATE
            ),
            outcome=OUTCOME_DISPATCHED,
        )
    )
    db.commit()

    def _override_db() -> Iterator[Session]:
        yield db

    app = FastAPI()
    app.include_router(schedules_router)
    app.dependency_overrides[get_db] = _override_db
    try:
        yield {
            "client": TestClient(app),
            "tenant": tenant,
            "viewer": viewer.id,
            "blind": blind.id,
            "fired": str(fired.id),
            "never": str(never.id),
            "tenant_b": tenant_b,
            "user_b": user_b.id,
            "other": str(other.id),
        }
    finally:
        db.close()
        engine.dispose()


def _hdr(user_id: str, tenant: str) -> dict[str, str]:
    return {"X-User-Id": user_id, "X-Tenant-Id": tenant}


def _get(c: dict, path: str, uid_key: str = "viewer", **params: object):  # noqa: ANN201
    return c["client"].get(path, params=params, headers=_hdr(c[uid_key], c["tenant"]))


# --- the ratified purpose: a burned month is visible when it happens ------------------------


def test_the_failed_outcome_filter_is_a_burned_month_feed(ctx) -> None:
    """The whole reason OQ-SCH-2-7c was ratified: one query surfaces every burned tick, with the
    reason attached, without knowing which schedule to look at."""
    rows = _get(ctx, "/schedules/runs", outcome=OUTCOME_FAILED).json()["items"]
    assert len(rows) == 1
    assert rows[0]["schedule_id"] == ctx["fired"]
    assert rows[0]["failure_reason"] == "no marks for the month-end valuation date"


def test_a_pre_create_refusal_is_distinguishable_from_a_failed_run(ctx) -> None:
    """``calculation_run_id`` NULL says "there is no run to inspect — only the reason". A
    post-create FAILED run would carry an id. Collapsing the two would send the operator hunting a
    run that was never minted."""
    rows = _get(ctx, "/schedules/runs", outcome=OUTCOME_FAILED).json()["items"]
    assert rows[0]["calculation_run_id"] is None
    dispatched = _get(ctx, "/schedules/runs", outcome=OUTCOME_DISPATCHED).json()["items"]
    assert all(r["calculation_run_id"] is not None for r in dispatched)


def test_the_head_carries_its_last_fire_so_a_missed_tick_is_legible(ctx) -> None:
    """A worker outage leaves NO ledger row at all, so the only signal is a stale last fire. The
    head must therefore stamp the newest tick — here May's burn, not April's success."""
    items = _get(ctx, "/schedules").json()["items"]
    head = next(i for i in items if i["id"] == ctx["fired"])
    assert head["last_scheduled_for"].startswith("2026-05-29T23:59:59")
    assert head["last_outcome"] == OUTCOME_FAILED
    assert head["last_failure_reason"] == "no marks for the month-end valuation date"


def test_a_never_fired_schedule_reports_null_rather_than_a_placeholder(ctx) -> None:
    items = _get(ctx, "/schedules").json()["items"]
    head = next(i for i in items if i["id"] == ctx["never"])
    assert head["last_scheduled_for"] is None
    assert head["last_fired_at"] is None
    assert head["last_outcome"] is None


# --- the SCH-2 nullability reaches the wire ------------------------------------------------


def test_both_sch2_nullable_columns_surface_as_null_not_as_placeholders(ctx) -> None:
    """EXPOSURE_AGGREGATE is model-less and month-end has no interval — the DTO mirrors the column
    nullability rather than inventing a zero or an empty string."""
    items = _get(ctx, "/schedules").json()["items"]
    head = next(i for i in items if i["id"] == ctx["fired"])
    assert head["model_version_id"] is None
    assert head["interval_days"] is None
    assert head["cadence_kind"] == CADENCE_CALENDAR_MONTH_END
    assert head["target_run_type"] == TARGET_RUN_TYPE_EXPOSURE_AGGREGATE

    interval = next(i for i in items if i["id"] == ctx["never"])
    assert interval["model_version_id"] is not None
    assert interval["interval_days"] == 1


# --- ordering, filters, pagination ----------------------------------------------------------


def test_heads_are_ordered_by_code_and_the_status_filter_narrows(ctx) -> None:
    items = _get(ctx, "/schedules").json()["items"]
    assert [i["code"] for i in items] == ["AAA-DAILY-VAR", "MONTH-END-EXPOSURE"]
    paused = _get(ctx, "/schedules", status=SCHEDULE_STATUS_PAUSED).json()["items"]
    assert [i["code"] for i in paused] == ["AAA-DAILY-VAR"]


def test_the_ledger_is_newest_first_and_bounded_by_the_grid_tick(ctx) -> None:
    """``since``/``until`` bound ``scheduled_for`` (the grid), NOT ``fired_at`` — the May burn was
    FIRED in June, so a June-onward ``since`` must exclude it."""
    rows = _get(ctx, "/schedules/runs", schedule_id=ctx["fired"]).json()["items"]
    assert [r["scheduled_for"][:10] for r in rows] == ["2026-05-29", "2026-04-30"]

    windowed = _get(
        ctx, "/schedules/runs", schedule_id=ctx["fired"], since="2026-06-01T00:00:00Z"
    ).json()["items"]
    assert windowed == []


def test_pagination_is_stable_across_offsets(ctx) -> None:
    first = _get(ctx, "/schedules/runs", schedule_id=ctx["fired"], limit=1).json()["items"]
    second = _get(ctx, "/schedules/runs", schedule_id=ctx["fired"], limit=1, offset=1).json()[
        "items"
    ]
    assert first[0]["scheduled_for"][:10] == "2026-05-29"
    assert second[0]["scheduled_for"][:10] == "2026-04-30"


# --- gating + tenant scoping ----------------------------------------------------------------


def test_both_reads_deny_by_default_without_schedule_view(ctx) -> None:
    assert _get(ctx, "/schedules", uid_key="blind").status_code == 403
    assert _get(ctx, "/schedules/runs", uid_key="blind").status_code == 403


def test_the_explicit_tenant_predicate_hides_another_tenants_rows(ctx) -> None:
    """SQLite has no RLS, so this proves the explicit predicate ALONE already refuses — the belt
    without the suspenders."""
    items = _get(ctx, "/schedules").json()["items"]
    assert ctx["other"] not in [i["id"] for i in items]
    rows = _get(ctx, "/schedules/runs").json()["items"]
    assert all(r["schedule_id"] != ctx["other"] for r in rows)


def test_a_foreign_schedule_id_filter_is_silently_empty_not_a_404(ctx) -> None:
    """No existence oracle: a foreign id and an unknown id are indistinguishable, both 200/empty."""
    foreign = _get(ctx, "/schedules/runs", schedule_id=ctx["other"])
    assert foreign.status_code == 200
    assert foreign.json()["items"] == []
    unknown = _get(ctx, "/schedules/runs", schedule_id=str(uuid.uuid4()))
    assert unknown.status_code == 200
    assert unknown.json()["items"] == []


def test_a_malformed_schedule_id_is_a_422_before_any_db_hit(ctx) -> None:
    assert _get(ctx, "/schedules/runs", schedule_id="not-a-uuid").status_code == 422


def test_the_read_surface_exposes_no_write_verb(ctx) -> None:
    """SCH-2 ships reads ONLY — ``schedule.manage`` has no HTTP consumer yet, and a create/pause API
    is its own slice with its own maker-checker question.

    RPT-2 fold (P10 — the fold applies to the class): the original walk filtered on
    ``hasattr(r, "methods")``, which the ``_IncludedRouter`` wrappers fail — so it censused ZERO
    routes and passed vacuously from the day it shipped. The platform census
    (``test_route_permission_census.py``) measured the trap; this walker now recurses and asserts
    it actually saw the schedules surface."""
    from fastapi.routing import APIRoute

    def _walk(routes):  # noqa: ANN001, ANN202
        for r in routes:
            if isinstance(r, APIRoute):
                yield r
            elif hasattr(r, "original_router"):
                yield from _walk(r.original_router.routes)

    methods = {
        (r.path, m) for r in _walk(ctx["client"].app.routes) for m in r.methods if m != "HEAD"
    }
    assert methods, "the walker censused ZERO routes — the vacuous-pass trap, again"
    assert all(m in {"GET", "OPTIONS"} for _, m in methods), sorted(methods)
