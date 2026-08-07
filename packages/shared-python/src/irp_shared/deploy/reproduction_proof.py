"""REPRO-1's deployed-stack harness — the OBSERVED scheduled green CTRL-018 moves on.

**Why a deployed proof and not another unit test.** ``test_reproduction`` proves the sweep in one
process against one in-memory SQLite file. CTRL-018's claim is different in kind: *every night, on
the real deployment, a machine re-derives the platform's governed numbers and says whether they
came back the same.* Everything in that sentence crosses a boundary the unit tier never touches —
a container, a real PostgreSQL with RLS forced, the scheduler's due-tick arithmetic, and the WORKER
process itself.

**And the worker's database path has never executed anywhere.** ``.env.example`` ships
``IRP_TENANT_IDS`` empty, ``deploy.sh`` deliberately deploys it empty, and the supervisor fails
closed at startup on an empty list — so ``deploy.sh``'s worker step proves only that the refusal
fires. RPT-2 recorded that gap as a carry and named REPRO-1 as its natural host. This harness is
where the deployed worker finally connects to a database and does governed work.

The seeded subject is the REPORT family, and that is not a shortcut: ``regenerate_report``
re-renders from the pinned snapshot and re-hashes, so a REPORT verdict is a genuine end-to-end
reproduction of a governed artifact — the same check RPT-1 proved by hand, now made to happen on a
schedule.

Every entry point refuses to touch a database unless ``IRP_ALLOW_PROOF_SEED`` is set: this module
writes governed rows, and it must never do that to whatever ``DATABASE_URL`` happens to name
because someone imported it.
"""

from __future__ import annotations

import os
import sys
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context

#: The tenant the seeded subject actually lives in.
#:
#: **Imported, not re-declared, and the first deployed run is why.** This module originally minted
#: its own tenant id while seeding its subject through ``report_identity_proof.seed_and_generate``
#: — which writes under ITS tenant. The result was a sweep that ran perfectly, found no subjects
#: because it was looking in a different tenant, produced ZERO verdicts, and still left a
#: ``DISPATCHED`` scheduled_run. It looked exactly like a healthy night; only the assertion on the
#: verdicts caught it. (The product-side fix is separate and larger: a sweep that checks NOTHING
#: now reports a FAILED dispatch with a reason, instead of a silent green.)
from irp_shared.deploy.report_identity_proof import PROOF_TENANT

#: The schedule grid anchor, comfortably in the past so the first tick is immediately due.
_ANCHOR = date(2026, 1, 1)
_ENV = "reproduction-proof"


def _require_arming() -> None:
    if not os.environ.get("IRP_ALLOW_PROOF_SEED"):
        raise RuntimeError(
            "IRP_ALLOW_PROOF_SEED is not set — refusing to write governed rows into the database "
            "named by DATABASE_URL"
        )


def _session_factory():  # noqa: ANN202
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set — refusing to guess a database")
    return make_session_factory(make_engine(url))


def _create_repro_schedule(session: Session, code: str) -> str:
    """One nightly reproduction schedule. Both per-family declarations are exercised for real: the
    tenant-wide family names NO portfolio and NO model version, and migration 0065's two DB CHECKs
    are what admit the row at all."""
    from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION
    from irp_shared.scheduling.events import CADENCE_INTERVAL, SchedulingActor
    from irp_shared.scheduling.service import create_schedule

    schedule = create_schedule(
        session,
        tenant_id=PROOF_TENANT,
        code=code,
        name=f"Nightly reproduction ({code})",
        target_run_type=RUN_TYPE_REPRODUCTION,
        scope_portfolio_id=None,
        model_version_id=None,
        environment_id=_ENV,
        anchor_date=_ANCHOR,
        cadence_kind=CADENCE_INTERVAL,
        interval_days=1,
        actor=SchedulingActor(actor_id="reproduction-proof", actor_type="SYSTEM"),
    )
    return str(schedule.id)


def seed(session: Session) -> dict[str, str]:
    """Seed a governed REPORT run plus the nightly schedule that will re-verify it."""
    from irp_shared.deploy.report_identity_proof import seed_and_generate, seed_principals

    set_tenant_context(session, PROOF_TENANT)
    report_id, content_hash = seed_and_generate(session)
    # **A REAL recipient, and the review found out why.** Without one,
    # `holders_of_permission("breach.review")` returns [] and `alarm_for_verdict` short-circuits to
    # SUPPRESSED before touching the sink — so the proof's "the alarm fires" arm passed while the
    # DELIVERY path had never executed. `ALARM_EVENTS >= 1` was satisfied by the no-recipient
    # sentinel row, which is the opposite of what the arm claims to show.
    seed_principals(session)
    recipient_id = _seed_alarm_recipient(session)
    schedule_id = _create_repro_schedule(session, "repro-nightly-a")
    session.commit()
    return {
        "REPORT_ID": report_id,
        "CONTENT_HASH": content_hash,
        "SCHEDULE_A": schedule_id,
        "ALARM_RECIPIENT_ID": recipient_id,
    }


def _seed_alarm_recipient(session: Session) -> str:
    """One in-tenant principal holding ``breach.review`` — the reproduction alarm's audience.

    ``seed_principals`` grants ``report.*`` and nothing else, so on its own the proof tenant has NO
    holder of the alarm permission and ``alarm_for_verdict`` short-circuits to SUPPRESSED before it
    ever touches the sink. The review caught the arm passing on exactly that: ``ALARM_EVENTS >= 1``
    was satisfied by the no-recipient sentinel row, so the DELIVERY path — the thing the arm claims
    to prove — had never executed on the deployed stack.
    """
    from sqlalchemy import select as _select

    from irp_shared.entitlement.models import AppUser, Permission, Role, RolePermission, UserRole
    from irp_shared.reproduction.events import ALARM_RECIPIENT_PERMISSION

    perm = session.execute(
        _select(Permission).where(Permission.code == ALARM_RECIPIENT_PERMISSION)
    ).scalar_one_or_none()
    if perm is None:
        raise RuntimeError(
            f"permission {ALARM_RECIPIENT_PERMISSION!r} is ABSENT from the deployed catalog — the "
            "reproduction alarm would have nobody to address and the proof would be vacuous"
        )
    user = AppUser(tenant_id=PROOF_TENANT, display_name="proof-repro-reviewer")
    role = Role(tenant_id=PROOF_TENANT, code="proof-repro-reviewer", name="repro reviewer")
    session.add_all([user, role])
    session.flush()
    session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    session.add(UserRole(tenant_id=PROOF_TENANT, user_id=user.id, role_id=role.id))
    session.flush()
    return str(user.id)


def plant_divergence(session: Session) -> dict[str, str]:
    """Corrupt the stored report hash, then create the SECOND schedule that will catch it.

    **The second schedule is created HERE, not at seed time, and the first run of this proof is
    why.**
    Both schedules were originally seeded together — and because ``interval_days=1`` puts every
    schedule on the same UTC-midnight grid, the first tick fired BOTH (``fired=2`` in the log). The
    negative arm's tick bucket was consumed before the divergence was even planted, so the second
    tick would have fired nothing and the arm would have proven nothing while looking fine.
    Creating it after the plant gives it an unused bucket.

    Raw SQL for the corruption, because ``report_generation`` is IA append-only: the ORM listener
    refuses the UPDATE and so does the P0001 trigger. The trigger is suspended for the duration —
    which is that control working, and the reason this lives in a proof harness and not in an
    application path. The script asserts the trigger is back afterwards.

    **The UPDATE is TENANT-QUALIFIED, and the review found out why that matters.** The first draft
    ran `UPDATE report_generation SET content_hash = '000…'` with NO predicate, relying on RLS to
    fence it — but this harness connects as the migrate role, which is a superuser, and RLS does
    not apply to a BYPASSRLS role. Pointed at a shared database (a staging host, or a `.env` whose
    DATABASE_URL was never repointed — the mistake this module's own docstring anticipates) it
    would have silently corrupted the stored hash of EVERY tenant's every report, with the
    append-only trigger disabled at the time. A proof harness that can destroy governed evidence in
    tenants it was never pointed at is not a proof harness.
    """
    set_tenant_context(session, PROOF_TENANT)
    session.execute(
        text("ALTER TABLE report_generation DISABLE TRIGGER report_generation_append_only")
    )
    try:
        result = session.execute(
            text(
                "UPDATE report_generation SET content_hash = "
                "'0000000000000000000000000000000000000000000000000000000000000000' "
                "WHERE tenant_id = CAST(:t AS uuid) "
                "RETURNING id"
            ).bindparams(t=PROOF_TENANT)
        )
        # RETURNING rather than `.rowcount`: the typed Result has no rowcount attribute (mypy
        # caught it), and counting the returned ids is the more direct statement of the fact the
        # assertion below needs.
        updated = len(result.fetchall())
    finally:
        # ALWAYS restore the fence, including on the failure path. Leaving a governed evidence
        # table freely mutable because an UPDATE raised would be the worse outcome by far.
        session.execute(
            text("ALTER TABLE report_generation ENABLE TRIGGER report_generation_append_only")
        )
    if updated != 1:
        raise RuntimeError(
            f"the plant touched {updated} rows, expected exactly 1 — the negative arm would be "
            "vacuous (nothing corrupted) or over-broad (something else corrupted)"
        )
    schedule_id = _create_repro_schedule(session, "repro-nightly-b")
    session.commit()
    return {"PLANT": "PLANTED", "PLANTED_ROWS": str(updated), "SCHEDULE_B": schedule_id}


def _json_outcome(value: object) -> str:
    """The ``outcome`` out of a NOTIFY.DISPATCH ``after_value``, whatever shape the driver returns.

    SENT vs SUPPRESSED is the distinction the proof's alarm arm rests on, so it is read explicitly
    rather than inferred from a row count — a count cannot tell "delivered to a human" from
    "recorded that nobody was listening".
    """
    import json

    if value is None:
        return "NONE"
    if isinstance(value, str):
        try:
            return str(json.loads(value).get("outcome"))
        except (ValueError, AttributeError):
            return "UNPARSEABLE"
    return "UNKNOWN"


def report(session: Session) -> dict[str, str]:
    """Read back what the deployed tick actually did. Values only — the script does the judging."""
    from irp_shared.audit.models import AuditEvent
    from irp_shared.calc.models import CalculationRun
    from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck
    from irp_shared.scheduling.models import ScheduledRun

    set_tenant_context(session, PROOF_TENANT)
    checks = list(
        session.execute(
            select(ReproductionCheck)
            .where(ReproductionCheck.tenant_id == PROOF_TENANT)
            .order_by(ReproductionCheck.system_from, ReproductionCheck.id)
        )
        .scalars()
        .all()
    )
    runs = list(
        session.execute(
            select(ScheduledRun)
            .where(ScheduledRun.tenant_id == PROOF_TENANT)
            .order_by(ScheduledRun.fired_at)
        )
        .scalars()
        .all()
    )
    # Counted through the ORM, not raw SQL: ``calculation_run.tenant_id`` is a native ``uuid`` on
    # PostgreSQL, and a text bind against it fails with "operator does not exist: uuid = character
    # varying" — which the first run of this proof produced. The ORM's GUID type does the cast.
    sweeps = session.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == PROOF_TENANT,
            CalculationRun.run_type == RUN_TYPE_REPRODUCTION,
        )
    ).scalar_one()
    # What the sweep could SEE. Added after the first deployed run reported a DISPATCHED tick with
    # zero verdicts: "the sweep ran" and "the sweep checked something" are different facts, and
    # without this the log could not tell them apart.
    subjects = session.execute(
        select(CalculationRun.run_type, func.count())
        .where(
            CalculationRun.tenant_id == PROOF_TENANT,
            CalculationRun.status == "COMPLETED",
        )
        .group_by(CalculationRun.run_type)
        .order_by(CalculationRun.run_type)
    ).all()
    out = {
        "COMPLETED_RUNS": ",".join(f"{rt}:{n}" for rt, n in subjects),
        "CHECK_COUNT": str(len(checks)),
        "SCHEDULED_RUN_COUNT": str(len(runs)),
        "SWEEP_RUN_COUNT": str(sweeps),
        "VERDICTS": ",".join(f"{c.family_key}:{c.verdict}" for c in checks),
        "OUTCOMES": ",".join(r.outcome for r in runs),
        # Phase 5's own evidence. The proof tenant has no `breach.review` holder, so a delivered
        # alarm records SUPPRESSED — which is the point: "nobody was configured to hear this" is a
        # durable fact, and its ABSENCE would mean the alarm phase never ran at all.
        "ALARM_OUTCOMES": ",".join(
            sorted(
                {
                    str((e.after_value or {}).get("outcome"))
                    if isinstance(e.after_value, dict)
                    else _json_outcome(e.after_value)
                    for e in session.execute(
                        select(AuditEvent).where(
                            AuditEvent.chain_id == PROOF_TENANT,
                            AuditEvent.event_type == "NOTIFY.DISPATCH",
                            AuditEvent.entity_type == "reproduction_check",
                        )
                    )
                    .scalars()
                    .all()
                }
            )
        ),
        "ALARM_EVENTS": str(
            session.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.chain_id == PROOF_TENANT,
                    AuditEvent.event_type == "NOTIFY.DISPATCH",
                    AuditEvent.entity_type == "reproduction_check",
                )
            ).scalar_one()
        ),
        # `tgenabled = 'O'` (origin), NOT merely "a row exists in pg_trigger". The review's HIGH:
        # a DISABLED trigger still has a catalog row, so the first draft's count(*) would have
        # returned 1 for a table left permanently mutable — the assertion could not fail for the
        # condition it existed to detect. 'D' (disabled) and 'R' (replica-only, which does not fire
        # for ordinary sessions) both read as "not fencing".
        "TRIGGER_ENABLED": str(
            session.execute(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgname = "
                    "'report_generation_append_only' AND NOT tgisinternal AND tgenabled = 'O'"
                )
            ).scalar_one()
        ),
    }
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: reproduction_proof <seed|plant|report>", file=sys.stderr)
        return 2
    command = argv[0]
    if command in {"seed", "plant"}:
        _require_arming()
    factory = _session_factory()
    session = factory()
    try:
        if command == "seed":
            for key, value in seed(session).items():
                print(f"{key}={value}")
        elif command == "plant":
            for key, value in plant_divergence(session).items():
                print(f"{key}={value}")
        elif command == "report":
            for key, value in report(session).items():
                print(f"{key}={value}")
        else:
            print(f"unknown command {command!r}", file=sys.stderr)
            return 2
    finally:
        session.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - a container entrypoint
    raise SystemExit(main(sys.argv[1:]))
