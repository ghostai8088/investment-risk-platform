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

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
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

#: How many times a FAILED delivery is re-attempted, **per recipient**, before the verdict is left
#: alone.
#:
#: Bounded on purpose. Unbounded retry was a HIGH the re-audit executed: at the supervisor's 300s
#: cadence an un-deliverable verdict wrote ~288 hash-chained audit rows a day, forever. Five
#: attempts spans roughly 25 minutes of ticking, which covers a transient outage; past that the
#: five durable FAILED attempts ARE the evidence an operator needs, and continuing to POST adds
#: nothing but volume.
#:
#: **"Per recipient" is the whole correction, and it was a BLOCKING defect for one commit.** The
#: first draft of this bound counted ``NOTIFY.DISPATCH`` ROWS, and ``alarm_for_verdict`` emits one
#: row per RECIPIENT per attempt — so a tenant with five ``breach.review`` holders exhausted the
#: entire budget in a SINGLE tick and dropped the divergence forever, which is precisely the
#: "retiring on any recorded attempt drops real alarms" failure the bound was written to avoid,
#: reached from the other side. ``breach.review`` is a 2L ROLE permission, so N > 1 is the
#: production-normal shape and N == 1 — the only value the first test used — is the single value at
#: which rows and attempts coincide. Executed at N=5: retired after one tick.
MAX_ALARM_ATTEMPTS = 5

#: The single synthetic attempt that every `NOTIFY.DISPATCH` row predating `attempt_id`
#: collapses into, per verdict. One bucket, so an upgrade cannot turn a handful of legacy rows
#: into a handful of spent retries.
_PRE_ATTEMPT_ID_HISTORY = "pre-attempt-id-history"


class ReproductionInfrastructureFailure(Exception):
    """The DATABASE failed under a per-family read — the sweep could not CHECK, it did not JUDGE.

    **The ratified disposition (2026-08-07): a distinct, non-alarming one.** A lock timeout, a
    statement timeout or a half-applied migration says nothing whatever about whether a governed
    number reproduces, so it must not mint an ``UNREPRODUCIBLE`` verdict. Two reasons, and the
    second is the one that decided it:

    * ENT-073 is IA append-only with a DB trigger refusing DELETE. A verdict row is a permanent,
      unretractable claim that a NAMED ``subject_run_id`` did not reproduce. A lock storm would
      write one of those per family per night, about runs that are very likely fine.
    * ``ALARMING_VERDICTS`` contains ``UNREPRODUCIBLE``, so every such row pages every
      ``breach.review`` holder with ``alert_type='reproduction-divergence'`` — waking the risk desk
      about a divergence that did not occur, with ``rows_compared=0`` as the only clue.

    So it fails LOUDLY but on the OPERATIONAL surface, not the alarm channel: the sweep's
    ``calculation_run`` is FAILED, the reason names the families, and ``_dispatch_reproduction``
    carries both onto the ``scheduled_run`` ledger row. Nothing is silent; nobody is paged.

    The discriminator is ``SQLAlchemyError``. A binder's own refusal, a ``ReproductionUnsupported``,
    or ``compare_rows``'s duplicate-key refusal are all statements ABOUT THE RUN and keep their
    ``UNREPRODUCIBLE`` verdict — they alarm, and should. An ``IntegrityError`` from inside a
    recompute is the genuinely ambiguous case and is deliberately classed as infrastructure: the
    fail-closed direction for an ambiguous signal is the visible-but-not-paging one.
    """


class _Discard(Exception):
    """Raised to unwind ``begin_nested()`` so the recompute is ALWAYS rolled back.

    A ``with session.begin_nested():`` block that returns normally COMMITS its savepoint, which
    would persist exactly the phantom run and result rows invariant I1 exists to prevent. Raising
    is how the context manager is told to discard — and it makes the discard structural: there is
    no code path out of that block that commits.
    """


#: The four mutually exclusive things that can happen to one family in one sweep.
#:
#: Exhaustive and disjoint ON PURPOSE. The invariant that matters is pinned by a test rather than
#: left to reading: ``verdict is not None`` **iff** the family was judged, which is true for exactly
#: RECORDED and UNRECORDED. Everything the sweep reports — the run status, the operator-facing
#: reason, the alarm queue's inputs — is a fold over these, so a family cannot be counted as both
#: judged and unjudged, which is the shape both recent BLOCKING defects took.
DISPOSITION_RECORDED = "RECORDED"  # judged, and the verdict row was written
DISPOSITION_SKIPPED = "SKIPPED"  # nothing to reproduce yet — a quiet tenant
DISPOSITION_UNCHECKABLE = "UNCHECKABLE"  # the database failed under it; NO judgement was reached
DISPOSITION_UNRECORDED = "UNRECORDED"  # judged, but the verdict row could not be written
DISPOSITIONS = frozenset(
    {
        DISPOSITION_RECORDED,
        DISPOSITION_SKIPPED,
        DISPOSITION_UNCHECKABLE,
        DISPOSITION_UNRECORDED,
    }
)
#: The dispositions that mean "this sweep did not do its whole job" — the ones that FAIL the run.
#: A DIVERGED verdict is deliberately NOT among them: the sweep did its job and the finding is the
#: point (invariant I3 — a divergence is a DISPATCHED fire, not a FAILED one).
FAILING_DISPOSITIONS = frozenset({DISPOSITION_UNCHECKABLE, DISPOSITION_UNRECORDED})


@dataclass(frozen=True)
class FamilyOutcome:
    """What happened to ONE family in ONE sweep — the single record everything else is derived from.

    ``verdict`` is non-None **iff a judgement was reached**. That single fact replaces an inference
    from which of four parallel lists a family had been appended to, and it is the fact both recent
    BLOCKING defects got wrong in opposite directions.
    """

    family_key: str
    disposition: str
    verdict: str | None = None
    detail: str | None = None
    row: ReproductionCheck | None = None

    def __post_init__(self) -> None:
        # A cheap structural check, run on every construction rather than asserted in one test.
        # The two invariants are the ones the parallel lists could not express.
        if self.disposition not in DISPOSITIONS:
            raise ValueError(f"unknown disposition {self.disposition!r}")
        judged = self.disposition in (DISPOSITION_RECORDED, DISPOSITION_UNRECORDED)
        if judged != (self.verdict is not None):
            raise ValueError(
                f"{self.family_key}: disposition {self.disposition!r} and verdict "
                f"{self.verdict!r} disagree about whether a judgement was reached"
            )
        if (self.row is not None) != (self.disposition == DISPOSITION_RECORDED):
            raise ValueError(
                f"{self.family_key}: a verdict row exists iff the disposition is RECORDED"
            )


@dataclass(frozen=True)
class ReproductionOutcome:
    """What one sweep did — ONE record per family, and every other view is derived from it.

    **Why this shape, and what it replaced.** For two folds the sweep tracked four PARALLEL LISTS —
    ``checks``, ``skipped``, ``unresolved``, ``unrecorded`` — plus a fifth (``lost_alarms``) that
    was
    a subset of one of them, with the run status and the operator-facing reason computed from all
    five. Nothing structural said a family belonged to exactly one, or that "was this family
    judged?" had a single answer; those were properties of the code that happened to append. Both of
    the last two BLOCKING defects lived in exactly that gap:

    * a family that HAD been judged was appended to the list meaning "never judged", so a DIVERGED
      verdict became a governed record denying a divergence had been found;
    * a reason assembled from a branch that could not see the other lists asserted "no alarm was
      raised" on a night when phase 5 was raising one.

    Neither was carelessness and neither was visible to a test that drove ONE disposition — which is
    every test that existed, because a test naturally exercises one path. They were COMBINATIONS.
    Five successive adversarial passes each found a defect of this class in the previous pass's fix,
    so the fix here is not another correction: it is removing the ability to express the wrong
    state.

    Now each family produces exactly one :class:`FamilyOutcome` whose ``disposition`` is one of four
    mutually exclusive values, and whose ``verdict`` is non-None **iff a judgement was reached**.
    The
    parallel lists survive as read-only projections so every existing caller and test is unchanged,
    but they can no longer disagree with each other, because there is only one place to disagree
    with. ``status`` and ``failure_reason`` are folds over the same list.

    **What this does NOT make unrepresentable**, named rather than left for a reader to assume from
    the paragraph above — an independent review pointed out that "removes the ability to express the
    wrong state" is true of the two defect shapes it was written about and not of everything:
    a duplicate ``family_key`` in ``families`` is prevented by the loop and a test, not by the type;
    ``verdict`` is not validated against ``VERDICTS``; nothing checks that a RECORDED family's
    ``verdict``/``family_key`` agree with its ``row``'s (the reason fold reads the dataclass, the
    alarm phase reads the DB row, and a future edit could desynchronise them); and ``status`` and
    ``failure_reason`` are ordinary fields, so "folds over the same list" is a property of the one
    call site that builds them rather than of this type. Each is a real residual, not a
    hypothetical.
    """

    run_id: str
    status: str
    failure_reason: str | None = None
    families: tuple[FamilyOutcome, ...] = ()

    @property
    def checks(self) -> list[ReproductionCheck]:
        """The verdict rows that were durably WRITTEN. Not "judged" — see ``lost_alarms``."""
        return [f.row for f in self.families if f.row is not None]

    @property
    def skipped(self) -> list[str]:
        """Families with a reproducer but no COMPLETED run to reproduce — a quiet tenant.

        Reported rather than silently absent, because "nothing to check" and "checked and fine"
        look identical from a verdict count alone.
        """
        return [f.family_key for f in self.families if f.disposition == DISPOSITION_SKIPPED]

    @property
    def unresolved(self) -> list[str]:
        """Families the sweep could not CHECK — the database failed under it.

        The ratified disposition for infrastructure failure (2026-08-07): it FAILS the sweep and the
        reason reaches the ``scheduled_run`` ledger, so the night is loudly not-green on an
        operational surface — but it does NOT page the risk desk, because an unreadable database is
        a claim about the DATABASE and a divergence alarm is a claim about a RUN.
        """
        return [
            f"{f.family_key}: {f.detail}"
            for f in self.families
            if f.disposition == DISPOSITION_UNCHECKABLE
        ]

    @property
    def unrecorded(self) -> list[str]:
        """Families the sweep DID judge but whose verdict row could not be WRITTEN.

        The opposite of ``unresolved`` however similar it looks: there no claim was made, here a
        claim was made and lost.
        """
        return [
            f"{f.family_key}: {f.detail}"
            for f in self.families
            if f.disposition == DISPOSITION_UNRECORDED
        ]

    @property
    def lost_alarms(self) -> list[str]:
        """The judged-but-unwritten families whose lost verdict was ALARMING.

        The one thing here an operator must act on immediately: a divergence was detected and its
        alarm can never fire, because nothing downstream will ever see the row. Derived rather than
        tracked, so it cannot drift from the verdict it describes.
        """
        return [
            f"{f.family_key} ({f.verdict})"
            for f in self.families
            if f.disposition == DISPOSITION_UNRECORDED and f.verdict in ALARMING_VERDICTS
        ]


def _redact(text: str) -> str:
    """Cut a driver's statement/parameter dump off an operator-facing reason, then cap it.

    Mirrors ``scheduling.service.redact_failure_reason``: a DBAPI error string carries the failing
    statement AND its bound parameters, and PostgreSQL appends a ``DETAIL:`` line quoting the
    failing row's values — governed data that has no business in a control-plane evidence column.

    ``\\nLINE `` is in the marker list because psycopg quotes the failing statement under a
    ``LINE n:`` caret, which the other four markers do not cover. That was found by EXECUTION, not
    by reading: a guarded failure on PostgreSQL persisted ``relation "..." does not exist / LINE 1:
    SELECT * FROM ...`` into the governed evidence column this function exists to keep statements
    out of. It became reachable in the same commit that first routed DBAPI errors through here, and
    the enumeration two files away already claimed statements were stripped.
    """
    cut = text
    for marker in ("\n[SQL:", "\n[parameters:", "\nDETAIL:", "\nCONTEXT:", "\nLINE "):
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


def resolve_subject(
    session: Session, *, acting_tenant: str, run_type: str
) -> tuple[CalculationRun | None, str | None]:
    """The subject lookup, savepointed. Returns ``(subject, unresolved_reason)`` — never both.

    A named function rather than four lines inline in the sweep, because the savepoint is a CONTROL
    and an inline control cannot be tested on the tier that can see it. The PostgreSQL tier has no
    grants to run a whole sweep, so with this guard inline the only available test monkeypatched
    ``latest_completed_run`` to raise a hand-constructed ``OperationalError`` — which never touches
    the database and therefore never aborts a transaction. Deleting the savepoint left that test
    green. It was the same defect it was written to prevent, one call site over: a proof that shares
    the code's assumption (P15).
    """
    try:
        with session.begin_nested():
            return latest_completed_run(
                session, acting_tenant=acting_tenant, run_type=run_type
            ), None
    except Exception as exc:  # noqa: BLE001 - one family's lookup must not end the sweep
        return None, _redact(f"{type(exc).__name__}: {exc}")


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

    **Raises ``ReproductionInfrastructureFailure``** when the DATABASE failed under the read or the
    recompute, rather than returning a verdict. That is the one path on which this function declines
    to judge: see that exception's docstring for why an unreadable database must not mint an
    append-only row claiming a named run did not reproduce, nor page the risk desk. The sole caller
    handles it by reporting the family as unresolved and FAILING the sweep.

    The recompute is discarded on EVERY path. That is enforced STRUCTURALLY by the
    ``with session.begin_nested():`` block plus the ``_Discard`` unwind below — there is no
    ``finally`` and deliberately no guard, because the guarded form was the BLOCKING defect the
    adversarial review found (see the comment on the block itself).
    """
    # GUARDED, and guarded INSIDE A SAVEPOINT — the two are not the same thing, and believing they
    # were was a BLOCKING defect that survived three scrutiny stages.
    #
    # The previous fold put a bare `try/except` here, on the correct reasoning that `read_stored`
    # runs arbitrary per-family SQL and can raise for the same reasons the recompute can. But
    # catching a DBAPI error does not UNDO it: on PostgreSQL the backend transaction is left
    # ABORTED, and every subsequent statement raises `InFailedSqlTransaction` — so the sweep built a
    # correct UNREPRODUCIBLE verdict and then died on the next flush, discarding the night exactly
    # as before. EXECUTED against a real PostgreSQL: `PERSISTED reproduction_check ROWS: 0`. The
    # `begin_nested()` wrapper is what makes the catch mean something, because ROLLBACK TO SAVEPOINT
    # clears the aborted state; with it, the same probe returned COMPLETED with both verdicts.
    #
    # And the reason nobody saw it for three stages is worth keeping: the test written to prove
    # this guard raised a plain `RuntimeError` from monkeypatched Python. SQLite does not poison a
    # session on a failed statement and PostgreSQL does, so the test was green with the bug AND
    # green with the fix. It never discriminated. That is P15 — a proof sharing its code's
    # assumption.
    try:
        with session.begin_nested():
            stored = family.read_stored(session, acting_tenant, subject)
    except SQLAlchemyError as exc:
        raise ReproductionInfrastructureFailure(
            _redact(f"reading the stored rows failed: {type(exc).__name__}: {exc}")
        ) from exc
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
    except SQLAlchemyError as exc:
        # The DATABASE failed under the recompute — not the binder refusing. See
        # `ReproductionInfrastructureFailure` for why that is a different disposition and not a
        # verdict. The savepoint has already rolled back by the time this arm runs, so the session
        # is usable and the sweep's next family proceeds normally.
        raise ReproductionInfrastructureFailure(
            _redact(f"the recompute failed: {type(exc).__name__}: {exc}")
        ) from exc
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

    # ONE record per family. The four parallel lists this replaced could disagree with each other
    # about whether a family had been judged, and both recent BLOCKING defects lived in that gap.
    families: list[FamilyOutcome] = []
    for family_key in sorted(REPRODUCIBLE_FAMILIES):
        family = REPRODUCIBLE_FAMILIES[family_key]
        # Savepointed inside `resolve_subject` for the same reason as `read_stored` — a failed
        # lookup on PostgreSQL aborts the transaction, and the previous fold's bare catch then died
        # on the fail-closed write ITSELF. Executed: `UPDATE calculation_run SET status='FAILED'`
        # raising `InFailedSqlTransaction`, so the sweep produced no FAILED ledger row and no reason
        # at all — the strongest control this slice built, unreachable on the authoritative engine.
        subject, lookup_failure = resolve_subject(
            session, acting_tenant=tenant, run_type=family_key
        )
        if lookup_failure is not None:
            # NO verdict row, and not merely because the disposition is nicer: `subject_run_id` is
            # a NOT NULL FK and there is no subject to bind one to. A verdict here would be a claim
            # about a run we could not identify.
            families.append(
                FamilyOutcome(
                    family_key=family_key,
                    disposition=DISPOSITION_UNCHECKABLE,
                    detail=lookup_failure,
                )
            )
            continue
        if subject is None:
            families.append(FamilyOutcome(family_key=family_key, disposition=DISPOSITION_SKIPPED))
            continue
        try:
            verdict, compared, diverged, detail = check_one_family(
                session,
                acting_tenant=tenant,
                family=family,
                subject=subject,
                code_version=code_version,
            )
        except ReproductionInfrastructureFailure as exc:
            families.append(
                FamilyOutcome(
                    family_key=family_key,
                    disposition=DISPOSITION_UNCHECKABLE,
                    detail=str(exc),
                )
            )
            continue
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
        # Flushed PER FAMILY, inside a savepoint, instead of once for all of them after the loop.
        # The single shared flush was the one statement where every family's verdict died together
        # — it is where the executor's probe actually raised — and a per-family write is the same
        # doctrine this function already applies to reads: one family's failure is one family's
        # problem. On failure the savepoint rollback takes the INSERT back out AND removes the
        # object from the session, so the enclosing transaction cannot re-attempt it at commit.
        #
        # An explicit `if row in session: session.expunge(row)` used to sit in the except arm, and
        # the comment credited it with that safety. It was DEAD CODE — after the rollback the object
        # is already gone, so the guard never fired and the branch it protected never ran. Removed
        # rather than left: a line nothing executes, described as load-bearing, is how the next
        # reader is taught to trust the wrong thing.
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except SQLAlchemyError as exc:
            # A separate list from `unresolved`, and the separation is a BLOCKING defect's fix.
            #
            # These two buckets look alike and are opposites. `unresolved` means the sweep could not
            # JUDGE — no verdict exists, so "no claim is made about this family" is true. Here the
            # verdict EXISTS; only the write failed. Folding it into `unresolved` made the sweep
            # report, in a governed evidence column, that no claim had been made about a family it
            # had just judged — and when that verdict was DIVERGED, the divergence went unalarmed
            # while the durable record denied there had been one. Executed: a planted `sigma`
            # divergence produced DIVERGED, collided on the unique key, and vanished into a reason
            # reading "This is NOT a divergence ... which is why no alarm was raised".
            #
            # The ratified disposition is scoped by its own justification — infrastructure failure
            # is "a claim about the DATABASE, not about the run" — and a failed verdict WRITE is the
            # one member of the SQLAlchemyError family where that justification does not hold,
            # because the judgement already exists.
            families.append(
                FamilyOutcome(
                    family_key=family_key,
                    disposition=DISPOSITION_UNRECORDED,
                    verdict=verdict,
                    detail=(
                        f"the {verdict} verdict was computed but could NOT be recorded: "
                        f"{_redact(f'{type(exc).__name__}: {exc}')}"
                    ),
                )
            )
            continue
        families.append(
            FamilyOutcome(
                family_key=family_key,
                disposition=DISPOSITION_RECORDED,
                verdict=verdict,
                detail=detail,
                row=row,
            )
        )

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
    # `unresolved` is checked FIRST, and that ordering is the fix for a reason that was durably
    # FALSE. The previous fold could reach the "checked NOTHING" text below with three broken
    # lookups behind it, writing into a governed `calculation_run.failure_reason` the specific
    # assertion "no registered family had a COMPLETED run to reproduce" — when the truth was that
    # the sweep could not find out. A fail-closed reason that states the wrong cause sends an
    # operator to the wrong place.
    #
    # This branch is also what gives `unresolved` a CONSUMER. The field was added in the previous
    # fold and read by nothing — five grep hits, all in this file — while the sweep returned a clean
    # COMPLETED with a governed family silently unchecked. A declaration with no consumer is worse
    # than no declaration (the deleted `produces_run_on_failure`), and here it was worse still: it
    # made the omission look handled.
    # The reason is DERIVED from what actually happened, never a fixed sentence about it.
    #
    # The previous shape hard-coded "This is NOT a divergence ... which is why no alarm was raised"
    # onto the whole infrastructure branch. That sentence was false in two separate executed
    # scenarios, and both are the night this control exists for: (1) one family times out while
    # another genuinely DIVERGES — the divergence IS queued and phase 5 DOES page, while the ledger
    # row the woken operator opens says no alarm was raised, giving them documentary grounds to
    # dismiss it; (2) a DIVERGED verdict fails to WRITE, so a claim was made and then denied.
    #
    # The lesson is more general than the sentence: a governed evidence column must not carry a
    # universal claim assembled at a branch that does not know the whole state. Every clause below
    # is conditioned on a value computed above it, and the alarming clauses come FIRST, because the
    # first line is what an operator reads at 02:00.
    # STATUS FIRST, then the text — so the two can never disagree. BOTH are folds over `families`,
    # so neither can be assembled from a branch that cannot see the whole state, which is exactly
    # how the previous shape produced a governed reason denying a divergence it had just measured.
    #
    # A sweep FAILS when something it was supposed to do did not happen: a family it could not
    # check, a verdict it could not record, or nothing checked at all. A DIVERGED verdict is NOT
    # one of those: the sweep did its job and the finding is the point. That is invariant I3 — a
    # divergence is a DISPATCHED fire, not a FAILED one — and it exists so the platform's most
    # important alarm stays distinguishable from an infrastructure failure in the operator feed.
    outcome = ReproductionOutcome(
        run_id=run.run_id,
        status=RunStatus.COMPLETED.value,
        families=tuple(families),
    )
    recorded = [f for f in families if f.disposition == DISPOSITION_RECORDED]
    failing = [f for f in families if f.disposition in FAILING_DISPOSITIONS]
    failed = bool(failing or not recorded)

    reason: str | None = None
    if failed:
        parts: list[str] = []
        alarming = [f for f in recorded if f.verdict in ALARMING_VERDICTS]
        # Alarming material LEADS, because the first clause is what a woken operator reads.
        if outcome.lost_alarms:
            parts.append(
                f"ALARM LOST — {len(outcome.lost_alarms)} alarming verdict(s) were computed but "
                f"could NOT be recorded, so they were never delivered: "
                f"{', '.join(outcome.lost_alarms)}. Investigate these FIRST: the sweep judged "
                "these "
                "families and the judgement did not survive the write."
            )
        if alarming:
            parts.append(
                f"{len(alarming)} ALARMING verdict(s) WERE recorded and ARE queued for "
                f"delivery: {', '.join(sorted(f'{f.family_key} ({f.verdict})' for f in alarming))}"
                " — this run FAILED for a separate reason, below; the alarm is real."
            )
        if outcome.unrecorded:
            parts.append(
                f"{len(outcome.unrecorded)} verdict(s) could not be written: "
                f"{'; '.join(outcome.unrecorded)}."
            )
        if outcome.unresolved:
            # Note what this does NOT say: "the database failed". `resolve_subject` catches bare
            # `Exception`, so a plain code bug in the lookup lands here too, and a governed evidence
            # column must not name a cause the code has not established. The exception type is in
            # the text; the operator can read it.
            parts.append(
                f"the sweep could not CHECK {len(outcome.unresolved)} of "
                f"{len(REPRODUCIBLE_FAMILIES)} registered families, so it makes NO claim about "
                f"whether those families reproduce: {'; '.join(outcome.unresolved)}."
            )
        if not failing:
            parts.append(
                "the reproduction sweep checked NOTHING: no registered family had a COMPLETED run "
                f"to reproduce (families with a reproducer: "
                f"{', '.join(sorted(REPRODUCIBLE_FAMILIES))}). A sweep with zero verdicts proves "
                "nothing and is not recorded as a pass."
            )
        elif recorded and not alarming and not outcome.lost_alarms:
            parts.append(f"{len(recorded)} verdict(s) were recorded and stand, none alarming.")
        reason = " ".join(parts)

    if reason is not None:
        update_run_status(
            session,
            run,
            RunStatus.FAILED,
            actor_id=actor_id,
            outcome="failure",
            failure_reason=reason,
        )
        return replace(outcome, status=RunStatus.FAILED.value, failure_reason=reason)

    update_run_status(session, run, RunStatus.COMPLETED, actor_id=actor_id)
    return outcome


@dataclass(frozen=True)
class AlarmChannelHealth:
    """Whether the reproduction alarm channel is WORKING, recomputed from source.

    **Why this exists at all.** Phase 5 returns an empty list both when there is nothing to alarm
    and when it could not read the queue, and every programmatic consumer reads the two identically.
    That is how a tenant-wide permanent silence stayed invisible: the control was *Implemented*, the
    tick was green, and nothing anywhere said the alarm channel had stopped working.

    LIM-1's standing lesson, verbatim and applying here: **a fail-open control's health surface must
    RECOMPUTE from source, never infer from an evidence row's presence.** So this counts what is
    actually owed and what is actually broken, rather than reporting "fine" because nothing was
    delivered.
    """

    queued: int
    unreadable_rows: int

    @property
    def healthy(self) -> bool:
        """False if ANY delivery row is unparseable — not "false if nothing was delivered".

        A quiet night and a broken channel are different facts and this is the field that tells
        them apart.
        """
        return self.unreadable_rows == 0


def alarm_channel_health(session: Session, *, acting_tenant: str) -> AlarmChannelHealth:
    """Recompute the alarm channel's health for one tenant, from the rows themselves."""
    tenant = canonical_tenant_id(acting_tenant)
    unreadable = 0
    for (payload,) in session.execute(
        select(AuditEvent.after_value).where(
            AuditEvent.chain_id == tenant,
            AuditEvent.event_type == NOTIFY_DISPATCH_EVENT,
            AuditEvent.entity_type == ENTITY_REPRODUCTION_CHECK,
        )
    ).all():
        if not isinstance(payload, dict):
            unreadable += 1
    return AlarmChannelHealth(
        queued=len(unalarmed_verdicts(session, acting_tenant=tenant)),
        unreadable_rows=unreadable,
    )


# ------------------------------------------------------------------------------ the alarm phase ---
def unalarmed_verdicts(session: Session, *, acting_tenant: str) -> list[ReproductionCheck]:
    """Alarming verdicts still owed a delivery attempt.

    **The rule, sixth and simplest version: a verdict is retired when its LATEST ATTEMPT concluded
    for everyone it tried, or when it has been ATTEMPTED ``MAX_ALARM_ATTEMPTS`` times.** Nothing
    else. Two conditions over one grouping, and the second guarantees termination unconditionally.

    Five earlier rules were each wrong, and the sequence is worth keeping because every one of them
    read as obviously right when written:

    * ANY recorded event retires it — dropped real alarms; one bad night lost a divergence forever.
    * Only ``SENT`` retires it — never terminated; ~288 audit rows per verdict per day, growing.
    * Exhaustion = COUNT of failure ROWS >= 5 — but one attempt emits one row PER RECIPIENT, so
      five ``breach.review`` holders spent the whole budget in a single tick. Zero retries.
    * Exhaustion per RECIPIENT (max) — but CONCLUSION stayed per verdict, so one good address
      retired the verdict and the other four holders were never told.
    * Conclusion AND exhaustion both per recipient — and it still did not terminate. A recipient
      who leaves the holder set at ``failed=2`` freezes a pair-state that no later tick can advance:
      ``every_recipient_done`` never becomes true, and the most-tried backstop only moves while
      someone currently attempted keeps FAILING. Executed by an independent model on a different
      engine: 25 ticks after the departure the verdict was still queued, re-paging the surviving
      reviewer every one of them; and in the ordering "one failure, then the tenant empties", a
      SUPPRESSED sentinel row was appended every tick forever, falsifying the ratified rule that a
      SUPPRESSED attempt is terminal.

    The lesson underneath all five: **per-recipient state is hostage to the holder set, which this
    function does not own.** Recipients appear and disappear (a role edit, a ``UserRole.valid_to``
    expiry — no admin action required), and any rule that must reach a per-recipient terminal state
    can be frozen by a recipient who simply stops being attempted. Counting ATTEMPTS instead is
    immune: an attempt is a thing this system did, not a thing about a population that moves.

    So the grouping key is ``attempt_id`` — one uuid per ``alarm_for_verdict`` call, stamped into
    every row that call emits. Note what is no longer read: ``recipient_id``. The fold does not
    depend on the payload's recipient shape at all, which also closes the brittleness the same
    review flagged (a future second writer omitting the key would have pooled every recipient into
    one bucket and silently restored the count-the-rows defect).
    """
    tenant = canonical_tenant_id(acting_tenant)
    attempts_by_entity: dict[str, dict[str, list[tuple[int, str]]]] = {}
    unreadable_rows: list[str] = []
    for entity_id, outcome_value, payload, seq in session.execute(
        select(
            AuditEvent.entity_id,
            AuditEvent.outcome,
            AuditEvent.after_value,
            AuditEvent.sequence_no,
        ).where(
            AuditEvent.chain_id == tenant,
            AuditEvent.event_type == NOTIFY_DISPATCH_EVENT,
            AuditEvent.entity_type == ENTITY_REPRODUCTION_CHECK,
        )
    ).all():
        # Rows written before `attempt_id` existed collapse into ONE synthetic attempt per verdict.
        #
        # The first draft gave each unkeyed row its own attempt, with a comment calling that
        # "conservative in the safe direction (it counts UP, toward termination)". **That comment
        # was backwards, and the independent review executed why.** Counting up is the safe
        # direction for
        # AUDIT VOLUME; for an ALARM QUEUE it DROPS DELIVERIES, and it resurrected both of the
        # defects this rule exists to kill, at the upgrade boundary:
        #
        #   * one pre-upgrade FAILED tick with five recipients is five rows — five "attempts" — so
        #     the verdict retired the instant v6 deployed, with zero retries ever taken. That is
        #     v3's
        #     BLOCKING zero-retry shape, reached through a migration rather than through the rule.
        #   * a pre-upgrade PARTIAL tick retired or not depending on which row happened to be
        #     written
        #     last: a lone success row with the higher sequence_no is a singleton "latest attempt",
        #     all-success, so the same real tick's unreached recipient was silenced. That is v4,
        #     order-dependent.
        #
        # Collapsing instead is a bounded UNDERCOUNT — the whole pre-v6 history costs one budget
        # unit — and a mixed history can never masquerade as an all-success latest attempt. Narrowly
        # reachable (only a deployment holding live un-retired rows at upgrade, and no production
        # deployment exists), fixed anyway: a load-bearing comment that is false is itself a defect.
        # A row whose payload cannot be read RETIRES NOTHING, and cannot raise.
        #
        # This fold reads a JSON column, and the FROZEN `record_event` will persist a bare string
        # there for any buggy caller. The first shape let that raise: the exception escaped the
        # fold, the worker caught it one level up, and phase 5 returned an empty list — which every
        # consumer reads as "nothing to alarm". ONE malformed row, about ANY entity, then silenced
        # the whole tenant's alarm channel on every subsequent tick, permanently, with a log line as
        # the only trace. The Wave-16 close review reproduced it with a poison row about an
        # UNRELATED entity and watched a genuine divergence created afterwards go unalarmed across
        # five consecutive ticks.
        #
        # Two properties, and the second is the one that matters for a DETECTIVE control:
        #   * the failure is scoped to the ROW — a payload we cannot parse tells us nothing about
        #     any other verdict, so it must not affect any other verdict;
        #   * the direction is FAIL-CLOSED TOWARD ALARMING. If we cannot tell whether a verdict was
        #     delivered, we assume it was NOT and leave it queued. A repeated alarm is noise; a
        #     divergence nobody hears is the thing this control exists to prevent.
        if not isinstance(payload, dict):
            unreadable_rows.append(str(entity_id))
            continue
        attempt = str(payload.get("attempt_id") or _PRE_ATTEMPT_ID_HISTORY)
        attempts_by_entity.setdefault(str(entity_id), {}).setdefault(attempt, []).append(
            (int(seq), str(outcome_value))
        )

    alarmed: set[str] = set()
    poisoned = set(unreadable_rows)
    for entity_id, attempts in attempts_by_entity.items():
        # ORDER MATTERS, and the first draft of this fold had it backwards: the poisoned skip sat
        # FIRST, which quietly disabled the attempts backstop for exactly the poisoned class — one
        # permanently-malformed row and the verdict re-alarmed every tick forever (executed at the
        # close-fold review: ten ticks, ten pages, never retired). That is v5's non-termination
        # defect on a new trigger. The ratified v6 rule is "retire when the latest attempt
        # concluded for everyone it tried, OR after MAX attempts" — and the OR-clause is
        # UNCONDITIONAL, which is what checking it first restores. The attempts counted here are
        # readable rows only (the poison row itself joins no attempt), so a poisoned verdict still
        # gets its MAX real deliveries before retiring: fail-closed toward alarming, but BOUNDED.
        if len(attempts) >= MAX_ALARM_ATTEMPTS:
            alarmed.add(entity_id)
            continue
        if entity_id in poisoned:
            # Some row for THIS verdict was unparseable, so its delivery history is incomplete and
            # no SUCCESS conclusion drawn from the rest of it is trustworthy. Stay queued — the
            # attempts ceiling above, not an inferred delivery, is the only way out.
            continue
        # The LATEST attempt, by the audit chain's own monotonic ordering rather than by wall clock.
        latest = max(attempts.values(), key=lambda rows: max(seq for seq, _ in rows))
        if all(outcome_value == "success" for _, outcome_value in latest):
            # Everyone that attempt tried concluded — SENT, or SUPPRESSED because there was nobody
            # to tell. A partial delivery does NOT retire it: the holders who were not reached are
            # exactly the point of retrying.
            alarmed.add(entity_id)

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
    # ONE id for this ATTEMPT, stamped onto every row this call emits — the grouping key
    # `unalarmed_verdicts` counts. It is minted here, at the call boundary, precisely because an
    # "attempt" is one invocation of this function: whatever the holder set happens to be, whatever
    # succeeds and whatever fails, it is one thing this system did. Deriving that grouping from the
    # rows afterwards is what five previous versions of the queue tried, and the recipient
    # population moves underneath any such derivation.
    attempt_id = str(uuid4())
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
            attempt_id=attempt_id,
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
            attempt_id=attempt_id,
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
    attempt_id: str,
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
        #
        # Written as a TOTAL mapping over the two concluding values rather than as "not FAILED",
        # because `success` is now the TERMINAL branch: `unalarmed_verdicts` retires a verdict the
        # instant one such row exists. The negated form defaulted an unrecognised outcome to
        # `success`, so the first time a fourth NOTIFY outcome is minted — this family has already
        # grown a SUPPRESSED sentinel once — it would have silently and permanently retired every
        # divergence it touched, with no test failing. This form fails CLOSED on an unknown value.
        outcome=(
            "success" if outcome in (NOTIFY_OUTCOME_SENT, NOTIFY_OUTCOME_SUPPRESSED) else "failure"
        ),
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
            # The grouping key for the retry bound: every row from one `alarm_for_verdict` call
            # shares it. DC-2 metadata like the rest — an opaque identifier for a control-plane
            # event, carrying no governed value. The NOTIFY.DISPATCH taxonomy row enumerates this
            # key set and is amended in the same commit, because an unamended mint record that no
            # longer describes the payload is a false record no test would catch.
            "attempt_id": attempt_id,
        },
        event_time=now,
    )


__all__ = [
    "AlarmChannelHealth",
    "DISPOSITIONS",
    "DISPOSITION_RECORDED",
    "DISPOSITION_SKIPPED",
    "DISPOSITION_UNCHECKABLE",
    "DISPOSITION_UNRECORDED",
    "FAILING_DISPOSITIONS",
    "FamilyOutcome",
    "MAX_ALARM_ATTEMPTS",
    "ReproductionInfrastructureFailure",
    "ReproductionOutcome",
    "alarm_channel_health",
    "alarm_for_verdict",
    "check_one_family",
    "compare_rows",
    "latest_completed_run",
    "resolve_subject",
    "run_reproduction_sweep",
    "unalarmed_verdicts",
]
