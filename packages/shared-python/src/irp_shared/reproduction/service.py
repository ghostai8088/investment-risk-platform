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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.audit.actions import ACTION_RECORD
from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import record_event
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.service import create_run, update_run_status
from irp_shared.classification.service import canonical_tenant_id
from irp_shared.notification.events import (
    NO_RECIPIENT_SENTINEL,
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SUPPRESSED,
    SOURCE_MODULE_NOTIFICATION,
)
from irp_shared.notification.sink import (
    ALERT_TYPE_REPRODUCTION,
    NotificationMessage,
    NotificationSink,
)
from irp_shared.reproduction.events import (
    ALARM_RECIPIENT_PERMISSION,
    ALARMING_VERDICTS,
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

#: How many times a FAILED delivery is re-attempted before the verdict is left alone.
#:
#: Bounded on purpose. Unbounded retry was a HIGH the re-audit executed: at the supervisor's 300s
#: cadence an un-deliverable verdict wrote ~288 hash-chained audit rows a day, forever. Five
#: attempts spans roughly 25 minutes of ticking, which covers a transient outage; past that the
#: five durable FAILED attempts ARE the evidence an operator needs, and continuing to POST adds
#: nothing but volume.
MAX_ALARM_ATTEMPTS = 5


class _Discard(Exception):
    """Raised to unwind ``begin_nested()`` so the recompute is ALWAYS rolled back.

    A ``with session.begin_nested():`` block that returns normally COMMITS its savepoint, which
    would persist exactly the phantom run and result rows invariant I1 exists to prevent. Raising
    is how the context manager is told to discard — and it makes the discard structural: there is
    no code path out of that block that commits.
    """


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
    #: Families whose SUBJECT could not even be resolved (the lookup itself failed). Distinct from
    #: ``skipped``, which means "nothing to reproduce yet" — a distinction an operator needs,
    #: because one is a quiet tenant and the other is a broken read.
    unresolved: list[str] = field(default_factory=list)


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
    # A duplicate key would COLLAPSE rows into one dict entry and produce a confident MATCH over a
    # single survivor (the review's MEDIUM). Registering a multi-row family with too narrow a key
    # is the obvious next-slice mistake — eight of the eighteen unregistered families have
    # multi-row grains — so it fails LOUDLY here rather than passing quietly.
    for label, rows in (("stored", stored), ("recomputed", recomputed)):
        keys = [row.key for row in rows]
        if len(keys) != len(set(keys)):
            duplicated = sorted({k for k in keys if keys.count(k) > 1})
            raise ValueError(
                f"family {family.family_key!r}: the declared natural key {family.key_fields} does "
                f"not uniquely identify a {label} row within a run — duplicates {duplicated}. "
                "Comparing would collapse them and report a pass over one survivor."
            )
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
            first = (
                first or f"{label} :: row PRESENT in the recompute but absent from the stored run"
            )
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

    The recompute is discarded on EVERY path. That is enforced STRUCTURALLY by the
    ``with session.begin_nested():`` block plus the ``_Discard`` unwind below — there is no
    ``finally`` and deliberately no guard, because the guarded form was the BLOCKING defect the
    adversarial review found (see the comment on the block itself).
    """
    # GUARDED too. The previous fold moved only the `compare_rows` call inside a guard, because
    # that was the call the audit named — and the re-audit correctly pointed out that fixing the
    # reported instance is not fixing the class. `read_stored` runs arbitrary per-family SQL and can
    # raise for exactly the reasons the recompute can; if it escapes, the night's other verdicts go
    # with it. Every per-family call in this function is now inside a guard that turns a family's
    # failure into that family's verdict.
    try:
        stored = family.read_stored(session, acting_tenant, subject)
    except Exception as exc:  # noqa: BLE001 - a family's own failure is a verdict, not an outage
        return VERDICT_UNREPRODUCIBLE, 0, 0, _redact(f"{type(exc).__name__}: {exc}")
    recomputed: list[ComparableRow] = []
    # The rollback is UNCONDITIONAL, and the first draft's `if savepoint.is_active:` guard was a
    # BLOCKING defect found at the adversarial review and reproduced by execution.
    #
    # When a `session.flush()` inside the recompute raises — a 40P01 deadlock (which the tick's own
    # docstring documents as reachable in phases 1-2, and which this slice materially widens by
    # running full binders there), a lock timeout, an FK violation, a dropped connection —
    # SQLAlchemy DEACTIVATES the savepoint but leaves the Session poisoned. The guard then skipped
    # the rollback, and the sweep's next statement raised `PendingRollbackError`, which the
    # per-schedule SAVEPOINT in `poll_tenant_schedules` rolled back: **the night's ENTIRE sweep was
    # lost, including verdicts for families computed minutes earlier — a DIVERGED among them if the
    # platform's promise really had broken.** Executed both ways: bombing the first family and
    # bombing the last both produced `PendingRollbackError` and zero persisted verdicts; removing
    # the guard produced the correct two verdicts and a clean COMMIT.
    #
    # The comment that justified the guard claimed calling `rollback()` on an inactive SAVEPOINT is
    # an error. **That was simply wrong** — and the proof was already in this repository:
    # `dq/gates.ensure_presence_rule` and `db/integrity.resolve_or_insert` use
    # `with session.begin_nested():`, whose `__exit__` calls `rollback()` unconditionally, which is
    # exactly why neither has this bug. The context-manager form is used here for the same reason:
    # it makes the unconditional rollback structural rather than a thing a later edit can re-guard.
    try:
        with session.begin_nested():
            recomputed = family.recompute(session, acting_tenant, subject, code_version)
            # Raised to force the rollback — the recompute must NEVER be committed, and returning
            # normally from this block would commit the savepoint. `_Discard` is caught immediately
            # below and is not an error condition.
            raise _Discard
    except _Discard:
        pass
    except ReproductionUnsupported as exc:
        return VERDICT_UNREPRODUCIBLE, 0, 0, _redact(str(exc))
    except Exception as exc:  # noqa: BLE001 - a family's own refusal is a verdict, not an outage
        return (
            VERDICT_UNREPRODUCIBLE,
            0,
            0,
            _redact(f"{type(exc).__name__}: {exc}"),
        )

    # INSIDE its own guard, because the fold that added `compare_rows`'s duplicate-key refusal put
    # the call AFTER the try above — and the pre-merge audit found (three lenses independently)
    # that this re-created the exact blast radius the BLOCKING savepoint fix had just removed: a
    # ValueError here escaped the sweep entirely, the per-schedule SAVEPOINT rolled back, and the
    # night's other verdicts were discarded. A comparison that cannot be performed is this family's
    # verdict, not the tenant's outage — the same doctrine as the recompute guard.
    try:
        compared, diverged, first = compare_rows(stored, recomputed, family)
    except Exception as exc:  # noqa: BLE001 - a comparison refusal is a verdict, not an outage
        return VERDICT_UNREPRODUCIBLE, 0, 0, _redact(f"{type(exc).__name__}: {exc}")
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
    unresolved: list[str] = []
    for family_key in sorted(REPRODUCIBLE_FAMILIES):
        family = REPRODUCIBLE_FAMILIES[family_key]
        try:
            subject = latest_completed_run(session, acting_tenant=tenant, run_type=family_key)
        except Exception as exc:  # noqa: BLE001 - one family's lookup must not end the sweep
            # NO verdict row: `subject_run_id` is a NOT NULL FK and there is no subject to bind
            # one to, so a verdict here would be a claim about a run we could not identify. It is
            # reported as UNRESOLVED instead — visible in the outcome and distinct from `skipped`,
            # which means "this family has nothing to reproduce yet" rather than "we could not
            # find out".
            unresolved.append(f"{family_key}: {_redact(f'{type(exc).__name__}: {exc}')}")
            continue
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

    # A sweep that checked NOTHING is not a healthy night, and it must not be recorded as one.
    #
    # This is the strongest thing REPRO-1's deployed proof found. The first run produced a
    # perfectly green tick — schedule fired, DISPATCHED, no errors — over a tenant whose subjects
    # were invisible to it. Zero verdicts, and every operational surface said fine. That is the
    # LQ-1 inert-control shape exactly: a control that is running, believed, and checking nothing.
    #
    # So it fails CLOSED. The run is FAILED and the ledger row carries the reason, which is honest
    # in both directions: a tenant with genuinely nothing to reproduce SHOULD be visible as such
    # rather than quietly counted among the reproducible ones.
    if not checks:
        reason = (
            "the reproduction sweep checked NOTHING: no registered family had a COMPLETED run to "
            f"reproduce (families with a reproducer: {', '.join(sorted(REPRODUCIBLE_FAMILIES))}). "
            "A sweep with zero verdicts proves nothing and is not recorded as a pass."
        )
        update_run_status(
            session,
            run,
            RunStatus.FAILED,
            actor_id=actor_id,
            outcome="failure",
            failure_reason=reason,
        )
        return ReproductionOutcome(
            run_id=run.run_id,
            status=RunStatus.FAILED.value,
            failure_reason=reason,
            checks=[],
            skipped=skipped,
            unresolved=unresolved,
        )

    update_run_status(session, run, RunStatus.COMPLETED, actor_id=actor_id)
    return ReproductionOutcome(
        run_id=run.run_id,
        status=RunStatus.COMPLETED.value,
        checks=checks,
        skipped=skipped,
        unresolved=unresolved,
    )


# ------------------------------------------------------------------------------ the alarm phase ---
def unalarmed_verdicts(session: Session, *, acting_tenant: str) -> list[ReproductionCheck]:
    """Alarming verdicts with no ``NOTIFY.DISPATCH`` audit event yet.

    Deliberately a per-verdict EVENT question, not a high-water cursor over a sequence. NOTIF-1
    learned that difference the hard way: a derived ``MAX`` cursor cannot represent a gap, so one
    row that jumps ahead permanently hides every earlier unalarmed one.

    A verdict leaves the queue when its alarm CONCLUDED (SENT, or SUPPRESSED — nobody to tell is a
    durable fact, not a transient one) or when its bounded FAILED retries are exhausted. Both of
    the simpler rules were wrong and both were executed: any-event-retires drops real alarms,
    SENT-only never terminates.
    """
    tenant = canonical_tenant_id(acting_tenant)
    # **Retry the wire, not the audience** (ratified 2026-08-07), and the history behind that
    # sentence is worth keeping because both naive answers are wrong:
    #
    #   * retiring on ANY recorded attempt drops real alarms — a webhook down for one night, or a
    #     tenant not yet provisioned with a `breach.review` holder, loses a genuine divergence
    #     forever. That was the pre-merge audit's finding;
    #   * retiring only on SENT never terminates. The re-audit executed it: an un-deliverable
    #     verdict re-fires on EVERY 300s tick, ~288 hash-chained audit rows per verdict per day,
    #     growing nightly, with an HTTP POST each time if a webhook is configured. That was a
    #     defect the previous fold INTRODUCED while fixing the first one.
    #
    # The distinction that resolves it is between a transient failure and a durable fact. A
    # SUPPRESSED attempt concluded CORRECTLY — it established, and recorded, that nobody in this
    # tenant holds the alarm permission. Re-POSTing that every five minutes tells nobody anything
    # new; the verdict row and the operational surface remain, and provisioning is a config act
    # with its own visibility. A FAILED attempt is the wire breaking, which is worth retrying — but
    # a bounded number of times, after which the durable FAILED attempts ARE the evidence.
    concluded = set(
        session.execute(
            select(AuditEvent.entity_id).where(
                AuditEvent.chain_id == tenant,
                AuditEvent.event_type == NOTIFY_DISPATCH_EVENT,
                AuditEvent.entity_type == ENTITY_REPRODUCTION_CHECK,
                AuditEvent.outcome == "success",  # SENT or SUPPRESSED — the attempt concluded
            )
        )
        .scalars()
        .all()
    )
    exhausted = {
        entity_id
        for entity_id, attempts in session.execute(
            select(AuditEvent.entity_id, func.count())
            .where(
                AuditEvent.chain_id == tenant,
                AuditEvent.event_type == NOTIFY_DISPATCH_EVENT,
                AuditEvent.entity_type == ENTITY_REPRODUCTION_CHECK,
                AuditEvent.outcome == "failure",
            )
            .group_by(AuditEvent.entity_id)
        ).all()
        if attempts >= MAX_ALARM_ATTEMPTS
    }
    alarmed = concluded | exhausted
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
    return (
        NOTIFY_OUTCOME_SENT
        if any(o == NOTIFY_OUTCOME_SENT for _, o, _ in attempts)
        else (NOTIFY_OUTCOME_FAILED)
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
        # "success" means THE ATTEMPT CONCLUDED CORRECTLY, not "a human read it". A SUPPRESSED
        # dispatch concluded correctly: it determined, durably, that nobody in the tenant holds the
        # alarm permission. Only a FAILED delivery — the wire broke — is a failure, and only that
        # is worth retrying. Ratified 2026-08-07: retry the wire, not the audience.
        outcome="failure" if outcome == NOTIFY_OUTCOME_FAILED else "success",
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
