"""The reproduction engine (REPRO-1) — CTRL-018 made mechanical.

One sweep, per tenant, per night: for every family with a declared reproducer, take the most recent
COMPLETED run, **re-execute its binder over that run's own pinned snapshot**, compare the recomputed
content against the stored rows, and write a durable verdict.

**The one invariant everything else hangs off: a reproduction persists NOTHING of what it
recomputes.** The re-execution runs inside a nested transaction that is ALWAYS rolled back, so no
``calculation_run``, no result rows, no audit events and no lineage edges survive it. This is not
fastidiousness — every ``latest_*`` resolver in the platform picks runs by (tenant, run_type,
COMPLETED, recency), so a nightly reproduction that persisted its re-runs would silently become the
run that production consumers resolve as "latest". That is the PPF-2 defect class (reusing a shipped
result table activates every read that omits the run filter), reached by a different road.

The manoeuvre was proven by EXECUTION before it was adopted, not reasoned about: a probe re-ran
``run_var`` over an existing run's own ``input_snapshot_id`` inside ``session.begin_nested()``,
reproduced the stored values exactly, and left the run count, the result count and the tenant's
audit-event count unchanged with ``verify_chain`` still gapless — and its positive control, the same
manoeuvre committed instead of rolled back, moved all three. Both survive as tests.

**Why the alarm is a separate tick phase.** ``record_event`` takes the per-tenant audit-chain
advisory lock and holds it to top-level COMMIT, and the sweep runs in the tick's phases-1-2
transaction. Delivering to a network sink there would hold that lock across I/O — the API-2b
anti-pattern NOTIF-1 restructured itself to avoid. So the sweep records verdicts and stops;
``poll_tenant_reproduction_alarms`` delivers afterwards, in its own transactions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_RECORD
from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import record_event
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.classification.service import canonical_tenant_id
from irp_shared.notification.events import (
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SUPPRESSED,
    NO_RECIPIENT_SENTINEL,
    SOURCE_MODULE_NOTIFICATION,
)
from irp_shared.notification.sink import (
    ALERT_TYPE_REPRODUCTION,
    NotificationSink,
    NotificationMessage,
)
from irp_shared.reproduction.events import (
    ALARMING_VERDICTS,
    ALARM_RECIPIENT_PERMISSION,
    ENTITY_REPRODUCTION_CHECK,
    VERDICT_DIVERGED,
    VERDICT_MATCH,
    VERDICT_UNREPRODUCIBLE,
)
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck
from irp_shared.reproduction.registry import (
    REPRODUCIBLE_FAMILIES,
    ComparableRow,
    ReproducibleFamily,
    ReproductionUnsupported,
    normalize,
)

#: The redaction cap for operator-facing reason text — the ``redact_failure_reason`` bound, reused
#: so a driver's multi-kilobyte error cannot fill a governed evidence column.
_REASON_MAX = 2000


@dataclass(frozen=True)
class ReproductionOutcome:
    """What one sweep did. ``skipped`` names families that HAVE a reproducer but no COMPLETED run
    to reproduce — reported rather than silently absent, because "nothing to check" and "checked
    and fine" look identical from a verdict count alone."""

    run_id: str
    status: str
    failure_reason: str | None = None
    checks: list[ReproductionCheck] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _redact(text: str) -> str:
    """Cut a driver's statement/parameter dump off an operator-facing reason, then cap it.

    Mirrors ``scheduling.service.redact_failure_reason``: a DBAPI error string carries the failing
    statement AND its bound parameters, and PostgreSQL appends a ``DETAIL:`` line quoting the
    failing row's values — governed data that has no business in a control-plane evidence column.
    """
    cut = text
    for marker in ("\n[SQL:", "\n[parameters:", "\nDETAIL:", "\nCONTEXT:"):
        head = cut.split(marker, 1)[0]
        cut = head
    return cut[:_REASON_MAX]


def latest_completed_run(
    session: Session, *, acting_tenant: str, run_type: str
) -> CalculationRun | None:
    """The most recent COMPLETED run of a family for this tenant.

    Ordered by ``created_at`` then ``run_id`` — the tiebreak is not decoration: two runs created in
    the same transaction share a timestamp, and an unordered pick would make the sweep choose a
    different subject on different nights and turn a stable verdict history into noise.
    """
    return session.execute(
        select(CalculationRun)
        .where(
            CalculationRun.tenant_id == acting_tenant,
            CalculationRun.run_type == run_type,
            CalculationRun.status == RunStatus.COMPLETED.value,
        )
        .order_by(CalculationRun.created_at.desc(), CalculationRun.run_id.desc())
        .limit(1)
    ).scalar_one_or_none()


def compare_rows(
    stored: list[ComparableRow], recomputed: list[ComparableRow], family: ReproducibleFamily
) -> tuple[int, int, str | None]:
    """Compare two row sets by natural key. Returns ``(compared, diverged, first_divergence)``.

    ``compared`` counts the UNION of keys, not the stored side: a recompute that produced an EXTRA
    row has diverged just as surely as one that produced a wrong number, and counting only stored
    keys would make that invisible. A missing or extra row is reported as such rather than as a
    field mismatch, because the two call for different investigations.

    ``first_divergence`` names the key and the FIELD, never the two values — see the ENT-073 module
    docstring for why governed numbers do not belong in a control-plane evidence column.
    """
    stored_by_key = {row.key: row for row in stored}
    recomputed_by_key = {row.key: row for row in recomputed}
    compared = 0
    diverged = 0
    first: str | None = None
    for key in sorted(set(stored_by_key) | set(recomputed_by_key)):
        compared += 1
        left = stored_by_key.get(key)
        right = recomputed_by_key.get(key)
        label = "/".join(key)
        if left is None:
            diverged += 1
            first = first or f"{label} :: row PRESENT in the recompute but absent from the stored run"
            continue
        if right is None:
            diverged += 1
            first = first or f"{label} :: row MISSING from the recompute"
            continue
        for name in family.compared_fields:
            if normalize(left.values.get(name)) != normalize(right.values.get(name)):
                diverged += 1
                first = first or f"{label} :: {name}"
                break
    return compared, diverged, first


def check_one_family(
    session: Session,
    *,
    acting_tenant: str,
    family: ReproducibleFamily,
    subject: CalculationRun,
    code_version: str,
) -> tuple[str, int, int, str | None]:
    """Re-execute one family and judge it. Returns ``(verdict, compared, diverged, detail)``.

    The nested transaction is rolled back on EVERY path, including the exception paths — the
    ``finally`` is the whole point, and a rollback that only happened on success would leave a
    phantom run committed by the caller's next flush.
    """
    stored = family.read_stored(session, acting_tenant, subject)
    recomputed: list[ComparableRow] = []
    savepoint = session.begin_nested()
    try:
        recomputed = family.recompute(session, acting_tenant, subject, code_version)
    except ReproductionUnsupported as exc:
        return VERDICT_UNREPRODUCIBLE, 0, 0, _redact(str(exc))
    except Exception as exc:  # noqa: BLE001 - a family's own refusal is a verdict, not an outage
        return (
            VERDICT_UNREPRODUCIBLE,
            0,
            0,
            _redact(f"{type(exc).__name__}: {exc}"),
        )
    finally:
        # SQLAlchemy rolls a nested transaction back automatically when its block raises, so the
        # guard is not belt-and-braces — calling rollback() on an already-inactive SAVEPOINT is an
        # error. What matters is that there is NO path on which it stays open.
        if savepoint.is_active:
            savepoint.rollback()

    compared, diverged, first = compare_rows(stored, recomputed, family)
    if compared == 0:
        # A comparison that compared nothing has proven nothing. Reporting it as MATCH is precisely
        # how a control becomes decorative — the empty-set-passes-vacuously shape MG-2 had to fix.
        return (
            VERDICT_UNREPRODUCIBLE,
            0,
            0,
            f"neither the stored run nor the recompute produced any {family.family_key} rows to "
            "compare — a check that compared nothing is not a pass",
        )
    verdict = VERDICT_MATCH if diverged == 0 else VERDICT_DIVERGED
    return verdict, compared, diverged, first


def run_reproduction_sweep(
    session: Session,
    *,
    acting_tenant: str,
    actor_id: str,
    actor_type: str = "SYSTEM",
    code_version: str,
    environment_id: str,
    scope_portfolio_id: str | None = None,
) -> ReproductionOutcome:
    """Re-execute every registered family's most recent COMPLETED run and record the verdicts.

    The sweep is itself a ``calculation_run`` (run type ``REPRODUCTION``) so that the scheduler's
    ratified invariant holds — a schedule's ``target_run_type`` IS a real run type, not a parallel
    vocabulary — and so the sweep is audited by the same ``CALC.RUN_*`` events every other run is.
    Its ``input_snapshot_id`` is NULL and honestly so: one sweep consumes many subjects' snapshots,
    and each is named on its own verdict row rather than smeared into a single binding.

    **No alarm is delivered here** (module docstring): the sweep runs under the tick's audit
    advisory lock.
    """
    tenant = canonical_tenant_id(acting_tenant)
    run = create_run(
        session,
        tenant_id=tenant,
        run_type=RUN_TYPE_REPRODUCTION,
        initiated_by=actor_id,
        input_snapshot_id=None,
        model_version_id=None,
        code_version=code_version,
        environment_id=environment_id,
        scope_portfolio_id=scope_portfolio_id,
    )
    update_run_status(session, run, RunStatus.RUNNING, actor_id=actor_id)

    checks: list[ReproductionCheck] = []
    skipped: list[str] = []
    for family_key in sorted(REPRODUCIBLE_FAMILIES):
        family = REPRODUCIBLE_FAMILIES[family_key]
        subject = latest_completed_run(session, acting_tenant=tenant, run_type=family_key)
        if subject is None:
            skipped.append(family_key)
            continue
        verdict, compared, diverged, detail = check_one_family(
            session,
            acting_tenant=tenant,
            family=family,
            subject=subject,
            code_version=code_version,
        )
        row = ReproductionCheck(
            tenant_id=tenant,
            calculation_run_id=run.run_id,
            subject_run_id=subject.run_id,
            family_key=family_key,
            verdict=verdict,
            rows_compared=compared,
            rows_diverged=diverged,
            first_divergence=detail,
        )
        session.add(row)
        checks.append(row)
    session.flush()
    update_run_status(session, run, RunStatus.COMPLETED, actor_id=actor_id)
    return ReproductionOutcome(
        run_id=run.run_id,
        status=RunStatus.COMPLETED.value,
        checks=checks,
        skipped=skipped,
    )


# ------------------------------------------------------------------------------ the alarm phase ---
def unalarmed_verdicts(session: Session, *, acting_tenant: str) -> list[ReproductionCheck]:
    """Alarming verdicts with no ``NOTIFY.DISPATCH`` audit event yet.

    Deliberately an EXISTENCE test per verdict, not a high-water cursor over a sequence. NOTIF-1
    learned the difference the hard way: a derived ``MAX`` cursor cannot represent a gap, so one
    row that jumps ahead permanently hides every earlier unalarmed one. Existence has no such
    failure mode, and the population here is a handful of rows per night.
    """
    tenant = canonical_tenant_id(acting_tenant)
    alarmed = set(
        session.execute(
            select(AuditEvent.entity_id).where(
                AuditEvent.chain_id == tenant,
                AuditEvent.event_type == NOTIFY_DISPATCH_EVENT,
                AuditEvent.entity_type == ENTITY_REPRODUCTION_CHECK,
            )
        )
        .scalars()
        .all()
    )
    rows = (
        session.execute(
            select(ReproductionCheck)
            .where(
                ReproductionCheck.tenant_id == tenant,
                ReproductionCheck.verdict.in_(sorted(ALARMING_VERDICTS)),
            )
            .order_by(ReproductionCheck.system_from, ReproductionCheck.id)
        )
        .scalars()
        .all()
    )
    return [row for row in rows if str(row.id) not in alarmed]


def alarm_for_verdict(
    session: Session,
    *,
    check: ReproductionCheck,
    sink: NotificationSink,
    acting_tenant: str,
    now: datetime | None = None,
) -> str:
    """Deliver ONE divergence alarm and record the attempt. Returns the NOTIFY outcome.

    Delivery happens BEFORE the audit emit (the NOTIF-1 phase-A/phase-B order): the emit takes the
    per-tenant advisory lock and holds it to commit, so a sink called after it would run under the
    lock. A sink that raises is caught and recorded FAILED — a recipient must never be dropped
    without a row saying so.

    A zero-recipient tenant records a SUPPRESSED attempt rather than nothing. "Nobody was
    configured to hear this" is a fact an operator needs; silence would be indistinguishable from
    a healthy night.
    """
    from irp_shared.entitlement.service import holders_of_permission

    tenant = canonical_tenant_id(acting_tenant)
    recipients = holders_of_permission(
        session, permission_code=ALARM_RECIPIENT_PERMISSION, acting_tenant=tenant
    )
    if not recipients:
        _emit_dispatch(
            session,
            check=check,
            tenant=tenant,
            recipient_id=NO_RECIPIENT_SENTINEL,
            outcome=NOTIFY_OUTCOME_SUPPRESSED,
            channel=sink.channel,
            detail=f"no in-tenant holder of {ALARM_RECIPIENT_PERMISSION}",
            now=now,
        )
        return NOTIFY_OUTCOME_SUPPRESSED

    # PHASE A — every delivery first, no audit emit yet (nothing holds the advisory lock).
    attempts: list[tuple[str, str, str | None]] = []
    for recipient_id in recipients:
        message = NotificationMessage(
            tenant_id=tenant,
            recipient_id=recipient_id,
            subject_id=str(check.id),
            source_event_type=f"REPRODUCTION.{check.verdict}",
            severity="warning",
            alert_type=ALERT_TYPE_REPRODUCTION,
        )
        try:
            result = sink.deliver(message)
            outcome = NOTIFY_OUTCOME_SENT if result.ok else NOTIFY_OUTCOME_FAILED
            detail = None if result.ok else (result.detail or "delivery failed")
        except Exception as exc:  # noqa: BLE001 - a sink must never rowless-drop a recipient
            outcome = NOTIFY_OUTCOME_FAILED
            detail = _redact(f"{type(exc).__name__}: {exc}")
        attempts.append((recipient_id, outcome, detail))

    # PHASE B — the durable emits, all of them, after every delivery has a terminal outcome.
    for recipient_id, outcome, detail in attempts:
        _emit_dispatch(
            session,
            check=check,
            tenant=tenant,
            recipient_id=recipient_id,
            outcome=outcome,
            channel=sink.channel,
            detail=detail,
            now=now,
        )
    return NOTIFY_OUTCOME_SENT if any(o == NOTIFY_OUTCOME_SENT for _, o, _ in attempts) else (
        NOTIFY_OUTCOME_FAILED
    )


def _emit_dispatch(
    session: Session,
    *,
    check: ReproductionCheck,
    tenant: str,
    recipient_id: str,
    outcome: str,
    channel: str,
    detail: str | None,
    now: datetime | None,
) -> None:
    """One ``NOTIFY.DISPATCH`` per attempt, against ``entity_type='reproduction_check'``.

    The code is REUSED, not newly minted: ``NOTIFY.*`` was minted for "the alarm ABOUT something",
    and the verbs were parameterized on ``entity_type`` precisely so a second alarm class would not
    need a second code (the REF-1 precedent, which reused ``REFERENCE.*`` for the classification
    family). ``audit/service.py`` stays FROZEN. The taxonomy row is amended in the same slice —
    an unamended row would make the mint record wrong, which no test would catch.

    ``after_value`` is DC-2 metadata only. Note what is NOT here: the diverging values. They are
    absent for the same reason they are absent from the row itself.
    """
    record_event(
        session,
        tenant_id=tenant,
        event_type=NOTIFY_DISPATCH_EVENT,
        action=ACTION_RECORD,
        entity_type=ENTITY_REPRODUCTION_CHECK,
        entity_id=str(check.id),
        actor_id="reproduction-alarm",
        actor_type="SYSTEM",
        source_module=SOURCE_MODULE_NOTIFICATION,
        severity="warning",
        outcome="success" if outcome == NOTIFY_OUTCOME_SENT else "failure",
        after_value={
            "verdict": check.verdict,
            "family_key": check.family_key,
            "subject_run_id": str(check.subject_run_id),
            "rows_compared": check.rows_compared,
            "rows_diverged": check.rows_diverged,
            "recipient_id": recipient_id,
            "recipient_reason": ALARM_RECIPIENT_PERMISSION,
            "channel": channel,
            "outcome": outcome,
            "detail": detail,
        },
        event_time=now,
    )


__all__ = [
    "ReproductionOutcome",
    "alarm_for_verdict",
    "check_one_family",
    "compare_rows",
    "latest_completed_run",
    "run_reproduction_sweep",
    "unalarmed_verdicts",
]
