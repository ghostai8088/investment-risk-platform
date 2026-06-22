"""SYSTEM_TENANT global reference seed catalog + governed seeder (P1B-1, OQ-P1B1-001/005).

A minimal representative global slice (a few ISO-4217 currencies, one market calendar, one agency
rating scale) — enough to make the *seeded-global*, *tenant-overridable*, and *no-context-read*
acceptance clauses end-to-end test-provable. Comprehensive catalogs are a deferred data-population
follow-up (REQ-SMR-005 stays In-Progress on the mechanism + representative slice).

``seed_system_reference`` writes the slice through the **governed** reference binders (MANUAL-source
lineage + ``REFERENCE.CREATE`` on the SYSTEM chain) — never a raw INSERT. The caller MUST have set
SYSTEM context (``set_config('app.current_tenant', SYSTEM_TENANT_ID, true)``) so rows satisfy the
hybrid ``WITH CHECK`` (single-tenant = SYSTEM), and owns the commit. This is the post-migrate seed
path (never the BYPASSRLS role); the CI reference RLS test invokes it to prove the SYSTEM chain.

``SYSTEM_TENANT_ID`` is imported from ``entitlement.bootstrap`` (one source of truth, used by the
0008 RLS policy literal).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.reference.calendar import HolidaySpec, create_calendar
from irp_shared.reference.currency import create_currency
from irp_shared.reference.models import Calendar, Currency, RatingScale
from irp_shared.reference.rating import GradeSpec, create_rating_scale
from irp_shared.reference.service import ReferenceActor

#: Representative global currency slice: (code, name, symbol, minor_units, numeric_code).
SYSTEM_CURRENCIES: list[tuple[str, str, str, int, str]] = [
    ("USD", "US Dollar", "$", 2, "840"),
    ("EUR", "Euro", "€", 2, "978"),
    ("GBP", "Pound Sterling", "£", 2, "826"),
    ("JPY", "Yen", "¥", 0, "392"),
]

#: Representative global calendar: (code, name, mic, [(holiday_date, name)]).
SYSTEM_CALENDAR_CODE = "XNYS"
SYSTEM_CALENDAR_HOLIDAYS: list[tuple[date, str]] = [
    (date(2026, 1, 1), "New Year's Day"),
    (date(2026, 12, 25), "Christmas Day"),
]

#: Representative global rating scale: code/agency + ordered grades (rank: lower = stronger).
SYSTEM_RATING_SCALE_CODE = "SP_LT"
SYSTEM_RATING_GRADES: list[tuple[str, int]] = [
    ("AAA", 1),
    ("AA", 2),
    ("A", 3),
    ("BBB", 4),
    ("BB", 5),
    ("B", 6),
    ("CCC", 7),
    ("D", 8),
]


def seed_system_reference(session: Session, *, actor_id: str = "system") -> None:
    """Seed the representative global slice under SYSTEM context (caller sets context + commits).

    Governed path only: each create roots a MANUAL-source origin edge and emits ``REFERENCE.CREATE``
    on the SYSTEM chain (``chain_id = SYSTEM_TENANT_ID``). Not idempotent — call once on a
    fresh database (re-seeding would violate ``UNIQUE(tenant_id, code)``)."""
    actor = ReferenceActor(actor_id=actor_id)

    for code, name, symbol, minor_units, numeric_code in SYSTEM_CURRENCIES:
        create_currency(
            session,
            tenant_id=SYSTEM_TENANT_ID,
            code=code,
            name=name,
            actor=actor,
            symbol=symbol,
            minor_units=minor_units,
            numeric_code=numeric_code,
        )

    create_calendar(
        session,
        tenant_id=SYSTEM_TENANT_ID,
        code=SYSTEM_CALENDAR_CODE,
        name="New York Stock Exchange",
        actor=actor,
        mic=SYSTEM_CALENDAR_CODE,
        holidays=[HolidaySpec(holiday_date=d, name=n) for d, n in SYSTEM_CALENDAR_HOLIDAYS],
    )

    create_rating_scale(
        session,
        tenant_id=SYSTEM_TENANT_ID,
        code=SYSTEM_RATING_SCALE_CODE,
        name="S&P Long-Term Issuer Rating",
        actor=actor,
        agency="SP",
        grades=[GradeSpec(code=c, rank=r) for c, r in SYSTEM_RATING_GRADES],
    )


def count_seeded(session: Session) -> dict[str, int]:
    """Return per-entity counts of SYSTEM_TENANT rows (a seed-verification helper for tests/ops)."""

    def _n(model: type[Currency] | type[Calendar] | type[RatingScale]) -> int:
        return session.execute(
            select(func.count()).select_from(model).where(model.tenant_id == SYSTEM_TENANT_ID)
        ).scalar_one()

    return {"currency": _n(Currency), "calendar": _n(Calendar), "rating_scale": _n(RatingScale)}
