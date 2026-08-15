"""REPRO-1 — the scheduled reproduction job (CTRL-018).

The load-bearing tests here are the ones that would fail if the control were decorative:

* the sweep persists NOTHING of what it recomputes, proven with a POSITIVE CONTROL that shows the
  same manoeuvre committed does move every count (without it, "nothing changed" could just mean
  "nothing ran");
* a PLANTED divergence produces DIVERGED and names the field — a reproduction job that has never
  been made to say no is not a control (P9);
* a divergence is NOT a failed dispatch, so an operator can tell "the platform's promise broke"
  from "the database hiccuped";
* coverage is a census by exact set equality, so a family that is silently unchecked fails here.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from test_var import _run, _seed_upstream_runs, _var_model

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.notification.events import (
    NOTIFY_CONCLUDING_OUTCOMES,
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SKIPPED,
    NOTIFY_OUTCOME_SUPPRESSED,
    NOTIFY_OUTCOMES,
)
from irp_shared.notification.sink import DeliveryResult, NotificationMessage
from irp_shared.reproduction.events import (
    ALARM_RECIPIENT_PERMISSION,
    ENTITY_REPRODUCTION_CHECK,
    VERDICT_DIVERGED,
    VERDICT_MATCH,
    VERDICT_UNREPRODUCIBLE,
    VERDICTS,
)
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck
from irp_shared.reproduction.registry import (
    REPRODUCIBLE_FAMILIES,
    UNREPRODUCIBLE_FAMILIES,
    ComparableRow,
    ReproductionUnsupported,
)
from irp_shared.reproduction.service import (
    DISPOSITION_RECORDED,
    DISPOSITION_UNCHECKABLE,
    DISPOSITION_UNRECORDED,
    DISPOSITIONS,
    MAX_ALARM_ATTEMPTS,
    FamilyOutcome,
    alarm_for_verdict,
    compare_rows,
    latest_completed_run,
    run_reproduction_sweep,
    unalarmed_verdicts,
)
from irp_shared.risk.models import VarResult

_CODE_VERSION = "risk-v1"


@pytest.fixture
def session() -> Session:
    """This suite's own engine, rather than importing ``test_var``'s fixture.

    Importing it would shadow the name in every test signature (ruff F811) and, more to the point,
    couple two suites' lifecycles for no benefit. The HELPERS are worth reusing — building a real
    VaR chain by hand here would duplicate 400 lines and drift from the thing it is meant to
    reproduce — but the fixture is three lines.
    """
    engine = make_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = make_session_factory(engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_var_run(db: Session, tenant: str):  # noqa: ANN202
    fx_run, cov_run = _seed_upstream_runs(db, tenant)
    mv = _var_model(db, tenant)
    return _run(db, tenant, mv, fx_run, cov_run)


def _sweep(db: Session, tenant: str):  # noqa: ANN202
    return run_reproduction_sweep(
        db,
        acting_tenant=tenant,
        actor_id="test",
        code_version=_CODE_VERSION,
        environment_id="ci",
    )


def _plant_sigma(db: Session, run_id: str, value: str) -> None:
    """Overwrite a stored ``var_result.sigma`` and PROVE the overwrite landed.

    Two things here are not decoration.

    **The raw SQL** is required because ``var_result`` is IA append-only: the ORM listener refuses
    an UPDATE and, on PostgreSQL, so does the P0001 trigger. Needing to reach past both to fake a
    divergence is the append-only control working.

    **The ``expire_all`` + read-back** is the non-vacuity floor, and it was written because the
    first version of this helper did NOT have it and the test SILENTLY PASSED WITH A MATCH VERDICT.
    ``make_session_factory`` sets ``expire_on_commit=False``, so the session kept serving the
    pre-plant object out of its identity map and the comparison never saw the planted value. A
    planted-divergence test that cannot plant is precisely the "written, believed and inert"
    control this platform keeps re-finding — so the plant now asserts itself.
    """
    db.execute(
        text("UPDATE var_result SET sigma = :s WHERE calculation_run_id = :r").bindparams(
            s=value, r=run_id
        )
    )
    db.commit()
    db.expire_all()
    landed = db.execute(
        select(VarResult.sigma).where(VarResult.calculation_run_id == run_id)
    ).scalar_one()
    assert Decimal(landed) == Decimal(value), (
        f"the plant did not land: stored {landed!r}, expected {value!r} — this test would have "
        "passed vacuously"
    )


def _counts(db: Session, tenant: str) -> tuple[int, int, int]:
    runs = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.tenant_id == tenant, CalculationRun.run_type == "VAR")
    ).scalar_one()
    results = db.execute(
        select(func.count()).select_from(VarResult).where(VarResult.tenant_id == tenant)
    ).scalar_one()
    events = db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.chain_id == tenant)
    ).scalar_one()
    return runs, results, events


# ---------------------------------------------------------------- I1: the sweep persists nothing --
def test_the_sweep_leaves_no_trace_of_what_it_recomputed(session: Session) -> None:
    """I1. Every ``latest_*`` resolver picks by (tenant, run_type, COMPLETED, recency), so a nightly
    sweep that persisted its re-runs would silently become the run production reads pick up — the
    PPF-2 defect class reached by a different road. Nothing may survive: no run, no result rows, no
    audit events, and the hash chain must still verify GAPLESS."""
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    before = _counts(session, tenant)
    assert verify_chain(session, tenant).ok

    outcome = _sweep(session, tenant)
    assert outcome.status == RunStatus.COMPLETED.value
    # The VaR fixture seeds an EXPOSURE_AGGREGATE run upstream too, so BOTH of those families have
    # a subject here. Asserting every verdict is MATCH (rather than a fixed list) keeps this honest
    # if the fixture's upstream chain changes; the family coverage itself is pinned by the census.
    assert {c.family_key for c in outcome.checks} >= {"VAR"}
    assert [c.verdict for c in outcome.checks] == [VERDICT_MATCH] * len(outcome.checks)

    runs, results, events = _counts(session, tenant)
    assert runs == before[0], "a phantom VAR calculation_run survived the sweep"
    assert results == before[1], "phantom var_result rows survived the sweep"
    # The sweep's OWN run and its status events are legitimate additions; what must not appear is
    # anything belonging to the re-executed VaR. Assert the delta is exactly the sweep's own work by
    # checking no VAR run was added, which the first assertion already does, and that the chain is
    # intact — a rolled-back SAVEPOINT that had consumed sequence numbers would show as a gap.
    assert events > before[2], "the sweep itself must be audited"
    after = verify_chain(session, tenant)
    assert after.ok, f"audit chain broken after the sweep: {after}"


def test_positive_control_the_recompute_really_does_write_when_not_rolled_back(
    session: Session,
) -> None:
    """The negative control's control (P5). Without this, the test above could pass because the
    re-execution silently did nothing at all — "no phantom rows" and "no work" are the same
    observation. Committing the identical manoeuvre must move every count."""
    tenant = str(uuid.uuid4())
    first = _seed_var_run(session, tenant)
    session.commit()
    before = _counts(session, tenant)

    savepoint = session.begin_nested()
    _run(
        session,
        tenant,
        first.rows[0].model_version_id,
        None,
        None,
        snapshot_id=first.run.input_snapshot_id,
    )
    savepoint.commit()

    runs, results, events = _counts(session, tenant)
    assert runs > before[0] and results > before[1] and events > before[2]


# ------------------------------------------------ I2: a planted divergence is made to FIRE ------
def test_a_planted_divergence_is_DIVERGED_and_names_the_field(session: Session) -> None:
    """I2 + P9. The alarm is not implemented until a test has made it fire.

    The divergence is planted with RAW SQL on purpose: ``var_result`` is IA append-only, so the ORM
    listener refuses an UPDATE and (on PostgreSQL) so does the P0001 trigger. Having to reach past
    both of them to fake a divergence is the append-only control working, and it is worth saying
    out loud rather than quietly routing around.
    """
    tenant = str(uuid.uuid4())
    subject = _seed_var_run(session, tenant)
    session.commit()

    _plant_sigma(session, subject.run.run_id, str(Decimal(subject.rows[0].sigma) + Decimal("1")))

    outcome = _sweep(session, tenant)
    check = next(c for c in outcome.checks if c.family_key == "VAR")
    assert check.verdict == VERDICT_DIVERGED
    assert check.rows_diverged == 1
    assert check.rows_compared == 1
    assert check.first_divergence is not None
    assert check.first_divergence.endswith(":: sigma"), check.first_divergence


def test_the_divergence_detail_never_carries_the_VALUES(session: Session) -> None:
    """The detail names the key and the field, never the two numbers.

    The moment a read surface is added over ENT-073 it will be gated by some permission, and the
    obvious candidate — ``schedule.view`` — is held by ``auditor_3l``, which holds no
    ``valuation.view`` / ``position.view`` / ``marketdata.view``. Writing governed values into a
    control-plane table now would plant the same disclosure RPT-2's audit found through a different
    door. This test is what stops a well-meant "make the alarm more useful" edit from doing it.
    """
    tenant = str(uuid.uuid4())
    subject = _seed_var_run(session, tenant)
    original = str(subject.rows[0].sigma)
    session.commit()
    planted = str(Decimal(original) + Decimal("7"))
    _plant_sigma(session, subject.run.run_id, planted)

    outcome = _sweep(session, tenant)
    check = next(c for c in outcome.checks if c.family_key == "VAR")
    detail = check.first_divergence or ""
    assert planted not in detail
    assert str(subject.rows[0].sigma) not in detail


# ------------------------------------------------------------------ the comparator, on its own ----
class _Fam:
    compared_fields = ("a", "b")


def test_compare_reports_a_missing_row_distinctly_from_a_changed_field() -> None:
    stored = [ComparableRow(key=("k1",), values={"a": 1, "b": 2})]
    compared, diverged, first = compare_rows(stored, [], _Fam())  # type: ignore[arg-type]
    assert (compared, diverged) == (1, 1)
    assert "MISSING from the recompute" in (first or "")


def test_compare_counts_an_EXTRA_recomputed_row_as_divergence() -> None:
    """The union of keys, not the stored side. A recompute that invented a row has diverged just as
    surely as one that got a number wrong, and counting only stored keys would hide it."""
    recomputed = [ComparableRow(key=("k9",), values={"a": 1, "b": 2})]
    compared, diverged, first = compare_rows([], recomputed, _Fam())  # type: ignore[arg-type]
    assert (compared, diverged) == (1, 1)
    assert "absent from the stored run" in (first or "")


def test_compare_treats_decimal_scale_as_representation_not_divergence() -> None:
    """``Decimal('500.0') == Decimal('500.000000')`` is the intended contract: the platform
    quantizes to declared scales, and trailing zeros are not a change in the number."""
    stored = [ComparableRow(key=("k",), values={"a": Decimal("500.000000"), "b": "x"})]
    fresh = [ComparableRow(key=("k",), values={"a": Decimal("500.0"), "b": "x"})]
    compared, diverged, _ = compare_rows(stored, fresh, _Fam())  # type: ignore[arg-type]
    assert (compared, diverged) == (1, 0)


# ---------------------------------------------------- an unrunnable check is NOT a silent pass ----
def test_a_family_that_cannot_be_recomputed_is_UNREPRODUCIBLE_not_MATCH(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "We could not check" and "we checked and it is fine" must never be the same verdict."""
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _boom(*_a: object, **_k: object) -> list[ComparableRow]:
        raise ReproductionUnsupported("the binder is unavailable in this test")

    # `ReproducibleFamily` is frozen, so the substitution is a whole replacement entry rather than
    # an attribute poke — which is the registry's design working, not an obstacle.
    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES, "VAR", replace(REPRODUCIBLE_FAMILIES["VAR"], recompute=_boom)
    )
    outcome = _sweep(session, tenant)
    check = next(c for c in outcome.checks if c.family_key == "VAR")
    assert check.verdict == VERDICT_UNREPRODUCIBLE
    assert check.rows_compared == 0
    assert "binder is unavailable" in (check.first_divergence or "")

    # AND the sweep carried on. A failed recompute rolls back a SAVEPOINT while the outer
    # transaction stays open, and if that left the session unusable the FIRST family to fail would
    # silently truncate the night's whole sweep — every later family unchecked, with a verdict row
    # for the failure making it look deliberate. The fixture seeds an EXPOSURE_AGGREGATE run
    # upstream, so there is a real second family to prove it on.
    others = [c for c in outcome.checks if c.family_key != "VAR"]
    assert others, "no second family was checked — the sweep may have stopped at the failure"
    assert all(c.verdict == VERDICT_MATCH for c in others), (
        "a family AFTER the failed one did not reproduce — the failed SAVEPOINT poisoned the "
        f"session: {[(c.family_key, c.verdict, c.first_divergence) for c in others]}"
    )


def test_a_recompute_that_fails_DURING_A_FLUSH_does_not_destroy_the_sweep(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The BLOCKING defect the adversarial review found, promoted to a test.

    The test above raises in plain Python, and that is NOT the dangerous case: SQLAlchemy leaves
    the Session usable. When the exception comes from a ``session.flush()`` — a 40P01 deadlock, a
    lock timeout, an FK violation, a dropped connection, all reachable inside the real binders the
    recompute calls — SQLAlchemy DEACTIVATES the savepoint and POISONS the Session. The first
    draft's ``if savepoint.is_active:`` guard then skipped the rollback, the sweep's next statement
    raised ``PendingRollbackError``, and the per-schedule SAVEPOINT in ``poll_tenant_schedules``
    discarded **the entire night's sweep** — including verdicts for families computed earlier, a
    DIVERGED among them if the platform's promise really had broken.

    So the bomb here goes off inside a flush, and it goes off on the LAST family in sort order, so
    that an earlier family's verdict exists to be lost.

    **The DISPOSITION changed at the 2026-08-07 ratification and the survival property did not.** A
    flush failure is a ``SQLAlchemyError``, so it is now infrastructure: no verdict row, no alarm,
    the family named in ``unresolved`` and the run FAILED. What this test exists to prove is
    unchanged and is the second half below — the earlier family's verdict SURVIVES. Under the
    guarded-rollback defect neither disposition was reachable, because the sweep raised.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _bomb_during_flush(db: Session, *_a: object, **_k: object) -> list[ComparableRow]:
        # A real flush that really fails: a ReproductionCheck with a NULL non-nullable column.
        db.add(
            ReproductionCheck(
                tenant_id=tenant,
                calculation_run_id=None,
                subject_run_id=None,
                family_key="VAR",
                verdict=VERDICT_MATCH,
                rows_compared=1,
                rows_diverged=0,
            )
        )
        db.flush()
        raise AssertionError("the flush should have raised")

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES,
        "VAR",  # sorts last of the three, so EXPOSURE_AGGREGATE is checked before the bomb
        replace(REPRODUCIBLE_FAMILIES["VAR"], recompute=_bomb_during_flush),
    )
    outcome = _sweep(session, tenant)
    session.commit()

    # The sweep SURVIVED. Under the guarded rollback this line was never reached — the sweep raised.
    by_family = {c.family_key: c.verdict for c in outcome.checks}
    assert (
        by_family.get("EXPOSURE_AGGREGATE") == VERDICT_MATCH
    ), "the family checked BEFORE the failing one lost its verdict — the whole sweep went with it"
    assert "VAR" not in by_family, "a database failure minted a verdict about a run"
    assert outcome.unresolved and outcome.unresolved[0].startswith("VAR: ")
    assert outcome.status == RunStatus.FAILED.value

    persisted = (
        session.execute(select(ReproductionCheck).where(ReproductionCheck.tenant_id == tenant))
        .scalars()
        .all()
    )
    assert (
        len(persisted) == len(outcome.checks) >= 1
    ), "verdicts computed before the failing family were discarded — the whole sweep was lost"


def test_a_read_stored_failure_that_is_NOT_the_database_is_a_verdict(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A family's own code failing is that family's verdict, and does not end the night.

    Note what this test canNOT prove, because believing it could was a BLOCKING defect for one
    commit: `RuntimeError` is pure Python and leaves the transaction healthy, so a bare `try/except`
    passes this test just as well as the savepoint-wrapped form. The DATABASE half is
    `test_a_read_stored_DATABASE_failure_does_not_poison_the_sweep` below, and it is the one that
    discriminates — on PostgreSQL only.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _boom(*_a: object, **_k: object) -> list[ComparableRow]:
        raise RuntimeError("the per-family read blew up")

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES, "VAR", replace(REPRODUCIBLE_FAMILIES["VAR"], read_stored=_boom)
    )
    outcome = _sweep(session, tenant)  # must NOT raise
    by_family = {c.family_key: c.verdict for c in outcome.checks}
    assert by_family.get("VAR") == VERDICT_UNREPRODUCIBLE
    assert (
        by_family.get("EXPOSURE_AGGREGATE") == VERDICT_MATCH
    ), "a read_stored failure took the night's other verdicts with it"


def test_a_DATABASE_failure_is_not_a_verdict_and_does_not_alarm(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ratified disposition (2026-08-07): infrastructure failure is loud, but not an alarm.

    Before this, any exception inside a per-family read minted an UNREPRODUCIBLE verdict — and
    UNREPRODUCIBLE is in `ALARMING_VERDICTS`, so a lock storm wrote permanent, undeletable rows
    claiming named runs had not reproduced AND paged every `breach.review` holder about a divergence
    that never happened. A claim about the DATABASE is not a claim about the RUN.

    So: no verdict row, the sweep FAILS, the reason names the family, and phase 5 has nothing to
    deliver. All four are asserted, because three of them would each individually make the
    disposition decorative.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _db_boom(*_a: object, **_k: object) -> list[ComparableRow]:
        raise OperationalError("SELECT 1", {}, Exception("canceling statement due to lock timeout"))

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES, "VAR", replace(REPRODUCIBLE_FAMILIES["VAR"], read_stored=_db_boom)
    )
    outcome = _sweep(session, tenant)  # must NOT raise

    # The PROPERTY is "the broken family minted no verdict", asserted directly. It used to be
    # spelled as list equality against the only other family that had a subject — which was the
    # same thing while three families existed, and became a fixture-shape assertion the moment
    # REPRO-2 registered sixteen more (this fixture's upstream seeding gives COVARIANCE and
    # FACTOR_EXPOSURE subjects too). Asserting the property keeps the test about the disposition.
    assert "VAR" not in [
        c.family_key for c in outcome.checks
    ], "a database failure minted a verdict — it is not a judgement about the run"
    assert outcome.status == RunStatus.FAILED.value, (
        "a sweep that could not check a governed family reported a clean night — the ratified "
        "disposition is non-alarming, not invisible"
    )
    assert outcome.unresolved and outcome.unresolved[0].startswith("VAR: ")
    assert outcome.failure_reason is not None
    assert "VAR" in outcome.failure_reason and "could not CHECK" in outcome.failure_reason
    assert (
        "no registered family had a COMPLETED run" not in outcome.failure_reason
    ), "the fail-closed reason asserted a cause the code had no basis for"
    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "an infrastructure failure reached the alarm queue and would have paged the risk desk"


def test_a_broken_SUBJECT_LOOKUP_is_unresolved_and_does_not_end_the_sweep(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling guard, which shipped with no test at all — deleting it left everything green.

    A lookup failure cannot become a verdict even in principle: `subject_run_id` is a NOT NULL FK
    and there is no subject to bind one to, so a verdict here would be a claim about a run the sweep
    could not identify. It is unresolved, the sweep continues, and the run FAILS.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    real = latest_completed_run

    def _selective(db: Session, *, acting_tenant: str, run_type: str):  # noqa: ANN202
        if run_type == "VAR":
            raise OperationalError("SELECT 1", {}, Exception("canceling statement due to conflict"))
        return real(db, acting_tenant=acting_tenant, run_type=run_type)

    monkeypatch.setattr("irp_shared.reproduction.service.latest_completed_run", _selective)
    outcome = _sweep(session, tenant)  # must NOT raise

    # Both halves of the property, stated as properties (see the sibling test above for why this
    # is no longer list equality): the broken family minted nothing, and the OTHERS still did.
    checked = [c.family_key for c in outcome.checks]
    assert "VAR" not in checked, "a verdict was minted about a run the sweep could not identify"
    assert (
        "EXPOSURE_AGGREGATE" in checked
    ), "a failing subject lookup took the night's other verdicts with it"
    assert outcome.unresolved and outcome.unresolved[0].startswith("VAR: ")
    assert outcome.status == RunStatus.FAILED.value
    assert unalarmed_verdicts(session, acting_tenant=tenant) == []


def test_a_verdict_ROW_that_cannot_be_written_does_not_take_the_others_with_it(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last shared statement in the sweep, and the one the executor's probe actually died on.

    Every read is now per-family guarded, but for one commit all the verdicts were still written by
    a SINGLE `session.flush()` after the loop — one point where they all die together. Forced here
    rather than argued: two families are made to resolve the SAME subject run, which collides on
    `uq_reproduction_check_sweep_subject`, so the second family's INSERT really fails. The first
    family's verdict must survive, and the collision must be reported rather than swallowed.

    That mis-registration is not far-fetched — it is what registering a family against the wrong
    `run_type` looks like, and eighteen unregistered families are waiting to be registered.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    var_subject = latest_completed_run(session, acting_tenant=tenant, run_type="VAR")
    assert var_subject is not None

    def _always_the_var_run(db: Session, *, acting_tenant: str, run_type: str):  # noqa: ANN202, ARG001
        return var_subject

    monkeypatch.setattr("irp_shared.reproduction.service.latest_completed_run", _always_the_var_run)
    outcome = _sweep(session, tenant)  # must NOT raise

    assert len(outcome.checks) == 1, (
        "a colliding verdict row took the other families' verdicts with it — the shared flush is "
        "back, and it is the single statement where the whole night dies"
    )
    assert any("could NOT be recorded" in u for u in outcome.unrecorded), (
        "the verdict that could not be written vanished silently — it must be reported, not "
        "swallowed"
    )
    assert not outcome.unresolved, (
        "an unwritable verdict was reported as UNRESOLVED — those two are opposites: unresolved "
        "means no claim was made, and here a claim was made and lost"
    )
    persisted = (
        session.execute(select(ReproductionCheck).where(ReproductionCheck.tenant_id == tenant))
        .scalars()
        .all()
    )
    assert len(persisted) == 1


def test_every_family_gets_EXACTLY_ONE_disposition(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural property the four parallel lists could not express.

    Both recent BLOCKING defects were a family counted in two categories at once, or in the wrong
    one: a family that HAD been judged appended to the list meaning "never judged". Neither was
    visible to a test that drove ONE disposition — which is every test that existed, because a test
    naturally exercises one path.

    This drives THREE dispositions in a single sweep and asserts the partition directly: each
    registered family appears exactly once, and the projections are disjoint by construction rather
    than by the code happening to append correctly.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _db_boom(*_a: object, **_k: object) -> list[ComparableRow]:
        raise OperationalError("SELECT 1", {}, Exception("lock timeout"))

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES,
        "EXPOSURE_AGGREGATE",
        replace(REPRODUCIBLE_FAMILIES["EXPOSURE_AGGREGATE"], read_stored=_db_boom),
    )
    outcome = _sweep(session, tenant)

    keys = [f.family_key for f in outcome.families]
    assert sorted(keys) == sorted(REPRODUCIBLE_FAMILIES), (
        "a registered family is missing from the outcome, or appears twice — the partition is not "
        "a partition"
    )
    assert len(keys) == len(set(keys))
    assert {f.disposition for f in outcome.families} <= DISPOSITIONS

    # The projections partition the same set: every family lands in exactly one of them.
    projected = (
        [str(c.family_key) for c in outcome.checks]
        + outcome.skipped
        + [u.split(":")[0] for u in outcome.unresolved]
        + [u.split(":")[0] for u in outcome.unrecorded]
    )
    assert sorted(projected) == sorted(
        keys
    ), "the derived views do not partition the families — one is double-counted or dropped"


def test_a_judgement_and_its_disposition_can_never_disagree() -> None:
    """`verdict is not None` iff the family was judged — checked on every construction.

    The states below are precisely the two BLOCKING defects, expressed directly: a family reported
    as unjudged while carrying a verdict, and a family reported as judged while carrying none. Both
    were reachable before; both are now unconstructable.
    """
    with pytest.raises(ValueError, match="disagree about whether a judgement was reached"):
        FamilyOutcome(
            family_key="VAR", disposition=DISPOSITION_UNCHECKABLE, verdict=VERDICT_DIVERGED
        )
    with pytest.raises(ValueError, match="disagree about whether a judgement was reached"):
        FamilyOutcome(family_key="VAR", disposition=DISPOSITION_RECORDED, verdict=None)
    with pytest.raises(ValueError, match="unknown disposition"):
        FamilyOutcome(family_key="VAR", disposition="PROBABLY_FINE")
    # And the positive control, so the guard is not merely a thing that raises.
    ok = FamilyOutcome(
        family_key="VAR", disposition=DISPOSITION_UNRECORDED, verdict=VERDICT_DIVERGED
    )
    assert ok.verdict == VERDICT_DIVERGED and ok.row is None


def test_a_DIVERGED_verdict_that_cannot_be_WRITTEN_is_reported_as_a_LOST_ALARM(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The BLOCKING defect of the fourth fold, pinned.

    A verdict is COMPUTED as DIVERGED and its row then fails to INSERT. The previous shape swept it
    into `unresolved` — the non-alarming bucket — so the risk desk was never paged AND the durable
    `failure_reason` read "This is NOT a divergence: no claim is made about whether those families
    reproduce, which is why no alarm was raised." Both halves were false: the sweep DID check it,
    and a claim WAS made.

    Two assertions matter and they are different. The verdict must be reported as a LOST ALARM, and
    the governed reason must not deny the divergence — because the reason is what an operator has
    in front of them when deciding whether the night was fine.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    var_subject = latest_completed_run(session, acting_tenant=tenant, run_type="VAR")
    assert var_subject is not None
    _plant_sigma(session, str(var_subject.run_id), "0.99999")

    def _always_the_var_run(db: Session, *, acting_tenant: str, run_type: str):  # noqa: ANN202, ARG001
        return var_subject

    monkeypatch.setattr("irp_shared.reproduction.service.latest_completed_run", _always_the_var_run)
    outcome = _sweep(session, tenant)

    assert outcome.lost_alarms and any(
        "VAR" in x and VERDICT_DIVERGED in x for x in outcome.lost_alarms
    ), (
        "a DIVERGED verdict was computed, could not be recorded, and was not reported as a lost "
        "alarm — nothing downstream will ever raise it"
    )
    assert outcome.failure_reason is not None
    assert "ALARM LOST" in outcome.failure_reason
    assert (
        "is NOT a divergence" not in outcome.failure_reason
    ), "the governed reason DENIES a divergence the sweep actually measured"


def test_a_divergence_alongside_an_infrastructure_failure_is_not_denied(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The night both controls exist for: one family times out, another genuinely diverges.

    The reason text must not assert "no alarm was raised" while phase 5 is queueing one. An operator
    paged at 02:00 opens the run, and a governed record contradicting the page is documentary
    grounds to dismiss the platform's most important alarm as spurious.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    var_run = latest_completed_run(session, acting_tenant=tenant, run_type="VAR")
    assert var_run is not None
    _plant_sigma(session, str(var_run.run_id), "0.4242")

    def _db_boom(*_a: object, **_k: object) -> list[ComparableRow]:
        raise OperationalError("SELECT 1", {}, Exception("canceling statement due to lock timeout"))

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES,
        "EXPOSURE_AGGREGATE",
        replace(REPRODUCIBLE_FAMILIES["EXPOSURE_AGGREGATE"], read_stored=_db_boom),
    )
    outcome = _sweep(session, tenant)
    session.flush()

    queued = unalarmed_verdicts(session, acting_tenant=tenant)
    assert [c.verdict for c in queued] == [VERDICT_DIVERGED], "the divergence was not queued"
    assert outcome.failure_reason is not None
    assert (
        "no alarm was raised" not in outcome.failure_reason
    ), "the ledger row denies an alarm that phase 5 is about to deliver"
    assert outcome.failure_reason.startswith(
        "1 ALARMING verdict"
    ), "the alarming verdict is not the FIRST thing an operator reads on this run"


def test_a_clean_sweep_with_a_DIVERGENCE_still_COMPLETES(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant I3: a divergence is a DISPATCHED fire, not a FAILED one.

    The fourth fold broke this by failing the run on any `unresolved` — but the plain case matters
    just as much and had no guard of its own here: a sweep that judged everything and recorded
    everything COMPLETES, even when what it recorded is the worst possible news. Otherwise the
    platform's most important alarm is indistinguishable from an infrastructure failure in the
    operator feed, which is the harm `test_a_divergence_is_a_DISPATCHED_fire_not_a_FAILED_one`
    names one level up.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    var_run = latest_completed_run(session, acting_tenant=tenant, run_type="VAR")
    assert var_run is not None
    _plant_sigma(session, str(var_run.run_id), "0.31337")

    outcome = _sweep(session, tenant)
    assert VERDICT_DIVERGED in [c.verdict for c in outcome.checks]
    assert (
        outcome.status == RunStatus.COMPLETED.value
    ), "a sweep that did its job and found a divergence was recorded as FAILED — I3"
    assert outcome.failure_reason is None


def test_the_fail_closed_reason_reaches_the_scheduled_run_ledger(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`unresolved` must have a CONSUMER, or it is the `produces_run_on_failure` anti-pattern again.

    It was written and read by nothing for one commit — five grep hits, all in one file — while the
    sweep returned a clean COMPLETED with a governed family silently unchecked. Its consumer is the
    run status and the reason, which `_dispatch_reproduction` carries onto the ledger row an
    operator actually looks at. This asserts the DURABLE end of that chain, not the dataclass.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _db_boom(*_a: object, **_k: object) -> list[ComparableRow]:
        raise OperationalError("SELECT 1", {}, Exception("server closed the connection"))

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES, "VAR", replace(REPRODUCIBLE_FAMILIES["VAR"], read_stored=_db_boom)
    )
    outcome = _sweep(session, tenant)
    session.flush()
    stored = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == outcome.run_id)
    ).scalar_one()
    assert stored.status == RunStatus.FAILED.value
    assert stored.failure_reason is not None and "VAR" in stored.failure_reason, (
        "the family the sweep could not check is absent from the durable ledger row — an operator "
        "reading the run learns nothing about it"
    )


def test_an_empty_comparison_is_never_reported_as_a_pass(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A check that compared nothing has proven nothing. Reporting zero-vs-zero as MATCH is exactly
    how a control becomes decorative — the empty-set-passes-vacuously shape MG-2 had to fix."""
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES,
        "VAR",
        replace(
            REPRODUCIBLE_FAMILIES["VAR"],
            read_stored=lambda *_a, **_k: [],
            recompute=lambda *_a, **_k: [],
        ),
    )
    outcome = _sweep(session, tenant)
    check = next(c for c in outcome.checks if c.family_key == "VAR")
    assert check.verdict == VERDICT_UNREPRODUCIBLE
    assert "compared nothing is not a pass" in (check.first_divergence or "")


def test_a_family_with_no_completed_run_is_reported_as_skipped_not_checked(
    session: Session,
) -> None:
    """No report is generated by this fixture, so the REPORT family has nothing to reproduce. It is
    NAMED in ``skipped`` rather than silently absent: "nothing to check" and "checked and fine" look
    identical from a verdict count alone."""
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    outcome = _sweep(session, tenant)
    checked = {c.family_key for c in outcome.checks}
    assert "REPORT" in outcome.skipped
    assert checked | set(outcome.skipped) == set(REPRODUCIBLE_FAMILIES)
    assert not (checked & set(outcome.skipped))


def test_a_sweep_that_checked_NOTHING_fails_closed(session: Session) -> None:
    """The deployed proof's best finding, promoted to a unit test.

    Its first run produced a perfectly green tick — schedule fired, DISPATCHED, no errors — over a
    tenant whose subjects were invisible to the sweep. Zero verdicts, and every operational surface
    said fine. A control that is running, believed and checking nothing is the LQ-1 shape, so a
    sweep with no verdicts is now a FAILED run carrying the reason.
    """
    tenant = str(uuid.uuid4())  # no runs at all for this tenant
    outcome = _sweep(session, tenant)
    assert outcome.status == RunStatus.FAILED.value
    assert outcome.checks == []
    assert "checked NOTHING" in (outcome.failure_reason or "")
    stored = session.execute(
        select(CalculationRun).where(
            CalculationRun.tenant_id == tenant, CalculationRun.run_type == "REPRODUCTION"
        )
    ).scalar_one()
    assert stored.status == RunStatus.FAILED.value
    assert "checked NOTHING" in (stored.failure_reason or "")


def test_latest_completed_run_ignores_a_FAILED_run(session: Session) -> None:
    """The subject must be a COMPLETED run. A FAILED run has no rows to reproduce, and picking one
    would make every sweep report an empty comparison."""
    tenant = str(uuid.uuid4())
    good = _seed_var_run(session, tenant)
    session.add(
        CalculationRun(
            tenant_id=tenant,
            run_type="VAR",
            status=RunStatus.FAILED.value,
            initiated_by="t",
            code_version=_CODE_VERSION,
        )
    )
    session.commit()
    assert latest_completed_run(session, acting_tenant=tenant, run_type="VAR").run_id == (
        good.run.run_id
    )


# ------------------------------------------------------------------------ I4: the alarm FIRES -----
class _RecordingSink:
    channel = "TEST"

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    def deliver(self, message: NotificationMessage) -> DeliveryResult:
        self.messages.append(message)
        return DeliveryResult(ok=True)


class _ExplodingSink:
    channel = "TEST"

    def deliver(self, message: NotificationMessage) -> DeliveryResult:
        raise RuntimeError("the wire is on fire")


def _diverged_check(db: Session, tenant: str) -> ReproductionCheck:
    subject = _seed_var_run(db, tenant)
    sigma = str(subject.rows[0].sigma)
    db.commit()
    _plant_sigma(db, subject.run.run_id, str(Decimal(sigma) + Decimal("1")))
    outcome = _sweep(db, tenant)
    db.commit()
    return next(c for c in outcome.checks if c.verdict == VERDICT_DIVERGED)


def test_a_divergence_reaches_the_sink_with_a_payload_that_names_itself_honestly(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I4/P9: the alarm is delivered, and it does not claim to be a breach."""
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1"],
    )
    sink = _RecordingSink()
    assert (
        alarm_for_verdict(session, check=check, sink=sink, acting_tenant=tenant)
        == NOTIFY_OUTCOME_SENT
    )
    assert len(sink.messages) == 1
    message = sink.messages[0]
    assert message.alert_type == "reproduction-divergence"
    assert message.subject_id == str(check.id)
    assert message.source_event_type == "REPRODUCTION.DIVERGED"


def test_a_sink_that_RAISES_still_leaves_durable_evidence(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sink must never rowless-drop a recipient. An exploding transport is a FAILED attempt with
    an audit event, not a lost alarm."""
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1"],
    )
    assert (
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_FAILED
    )
    events = _dispatch_events(session, tenant)
    assert len(events) == 1, "an exploding sink lost the alarm entirely"


def test_a_tenant_with_no_recipient_records_SUPPRESSED_rather_than_nothing(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Nobody was configured to hear this" is a fact an operator needs. Silence here would be
    indistinguishable from a healthy night — the LQ-1 inert-control shape."""
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: []
    )
    sink = _RecordingSink()
    assert (
        alarm_for_verdict(session, check=check, sink=sink, acting_tenant=tenant)
        == NOTIFY_OUTCOME_SUPPRESSED
    )
    assert sink.messages == []
    assert len(_dispatch_events(session, tenant)) == 1


def _dispatch_events(db: Session, tenant: str) -> list[AuditEvent]:
    return list(
        db.execute(
            select(AuditEvent).where(
                AuditEvent.chain_id == tenant,
                AuditEvent.event_type == NOTIFY_DISPATCH_EVENT,
                AuditEvent.entity_type == ENTITY_REPRODUCTION_CHECK,
            )
        )
        .scalars()
        .all()
    )


def test_an_alarmed_verdict_is_not_alarmed_twice(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queue is a per-verdict EVENT question, not a high-water cursor — NOTIF-1's lesson that a
    derived MAX cannot represent a gap. A CONCLUDED attempt (SENT or SUPPRESSED) retires the
    verdict; see the two tests below for the bounded-retry and terminal-suppression halves."""
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1"],
    )
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id]
    alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
    session.flush()
    assert unalarmed_verdicts(session, acting_tenant=tenant) == []


def test_an_alarm_that_was_NOT_delivered_stays_queued(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-merge audit finding. A FAILED delivery recorded an attempt, and the old
    existence-of-any-event queue then retired the verdict FOREVER — the platform's most important
    alarm dropped for the cost of one transient network failure, while the phase's own docstring
    promised a retry."""
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1"],
    )
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id]
    assert (
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_FAILED
    )
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [
        check.id
    ], "an undelivered alarm left the queue — it will never be retried"
    # And a successful delivery DOES retire it, so the queue is not merely never-draining.
    alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
    session.flush()
    assert unalarmed_verdicts(session, acting_tenant=tenant) == []


def test_a_suppressed_alarm_is_TERMINAL_not_retried_forever(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ratified 2026-08-07: retry the wire, not the audience.

    A SUPPRESSED attempt CONCLUDED CORRECTLY — it established, and durably recorded, that nobody in
    this tenant holds the alarm permission. Re-POSTing that every 300-second tick tells nobody
    anything new, and the re-audit executed what it costs: ~288 hash-chained audit rows per verdict
    per day, forever, plus an HTTP POST each time if a webhook is configured. So it is terminal.

    **The accepted trade-off, stated rather than buried:** a divergence detected before anyone is
    provisioned is not re-alarmed when a reviewer appears later. It remains in the verdict row and
    the operational surface; provisioning is a config act with its own visibility. That is carry
    (o).
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: []
    )
    assert (
        alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_SUPPRESSED
    )
    session.flush()
    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "a suppressed alarm stayed queued — it will re-fire on every tick, forever"


@pytest.mark.parametrize("n_recipients", [1, 2, 5])
def test_a_failed_delivery_is_retried_a_bounded_number_of_TICKS_whatever_the_audience(
    session: Session, monkeypatch: pytest.MonkeyPatch, n_recipients: int
) -> None:
    """The bound is per TICK, not per audit ROW — and the parametrize IS the test.

    A broken wire is transient and worth retrying; retrying forever is not. But the first bound
    counted ``NOTIFY.DISPATCH`` rows, and one attempt emits one row PER RECIPIENT — so the budget
    was consumed N times faster than documented, and at N >= MAX_ALARM_ATTEMPTS a SINGLE failed tick
    retired the platform's most important alarm with zero retries.

    That defect was invisible because the test pinned exactly one recipient, the only value at which
    rows and ticks coincide. ``breach.review`` is a 2L ROLE permission, so N > 1 is the ordinary
    production shape and N == 1 is the special case. Hence 1, 2 and 5: at 2 the old code dropped the
    alarm at tick 3, at 5 it dropped it at tick 1, and both are quoted numbers from the run that
    found this.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: [f"reviewer-{i}" for i in range(n_recipients)],
    )
    for tick in range(1, MAX_ALARM_ATTEMPTS + 1):
        assert (
            alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
            == NOTIFY_OUTCOME_FAILED
        )
        session.flush()
        queued = unalarmed_verdicts(session, acting_tenant=tenant)
        if tick < MAX_ALARM_ATTEMPTS:
            assert [c.id for c in queued] == [check.id], (
                f"tick {tick} of {MAX_ALARM_ATTEMPTS} dropped the alarm early with {n_recipients} "
                "recipient(s) — the bound is counting rows, not attempts"
            )
        else:
            assert queued == [], (
                f"the alarm is still queued after {MAX_ALARM_ATTEMPTS} failed ticks — this is the "
                "unbounded retry loop"
            )
    # The row count is asserted separately so the two quantities can never be conflated again: five
    # ticks to five recipients is twenty-five durable attempts, and the bound is FIVE.
    failures = [e for e in _dispatch_events(session, tenant) if e.outcome == "failure"]
    assert len(failures) == MAX_ALARM_ATTEMPTS * n_recipients


def _seed_reviewer_with_two_roles(db: Session, tenant: str) -> str:
    """ONE active user granted `breach.review` through TWO distinct roles.

    The multiplicity case no fixture in the repository produced: `_mk_reviewer` in
    `test_notification.py` gives every user exactly one role, so the join could fan out
    across the whole suite and no test would notice.
    """
    from irp_shared.entitlement.models import (
        AppUser,
        Permission,
        Role,
        RolePermission,
        UserRole,
    )

    user = AppUser(tenant_id=tenant, display_name="two-hatted reviewer", is_active=True)
    db.add(user)
    db.flush()
    perm = db.query(Permission).filter_by(
        code=ALARM_RECIPIENT_PERMISSION
    ).one_or_none() or Permission(code=ALARM_RECIPIENT_PERMISSION, description="d")
    db.add(perm)
    db.flush()
    for label in ("risk-manager", "duty-officer"):
        role = Role(tenant_id=tenant, code=f"{label}-{uuid.uuid4().hex[:6]}", name=label)
        db.add(role)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        db.add(
            UserRole(
                tenant_id=tenant,
                user_id=user.id,
                role_id=role.id,
                valid_from=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
    db.flush()
    return str(user.id)


def test_a_holder_reached_by_TWO_roles_is_ONE_recipient(session: Session) -> None:
    """The invariant the retry bound silently depends on, one call site upstream.

    The bound's safety rests on "a recipient accrues at most one row per tick", which is true only
    because `holders_of_permission` applies `.distinct()`. Nothing in the repository pinned that:
    every reproduction alarm test monkeypatches the function away with a hand-written list, and the
    two tests of the real query build each reviewer with exactly ONE role — so no test anywhere
    seeded the multiplicity case, and deleting `.distinct()` left both batteries green.

    A user holding `breach.review` through two roles is ordinary (it is a 2L ROLE permission). If
    the duplicate reaches `alarm_for_verdict`, one human produces N rows per tick and the BLOCKING
    zero-retry defect is restored — with everything passing. So the dependency is pinned HERE,
    where the bound lives, rather than left hostage to another module's query shape.
    """
    from irp_shared.entitlement.service import holders_of_permission

    tenant = str(uuid.uuid4())
    user_id = _seed_reviewer_with_two_roles(session, tenant)
    session.flush()
    holders = holders_of_permission(
        session, permission_code=ALARM_RECIPIENT_PERMISSION, acting_tenant=tenant
    )
    assert holders == [user_id], (
        "one human holding the alarm permission through two roles was returned twice — "
        "alarm_for_verdict would emit two rows per tick for one person and the per-recipient "
        "retry bound would trip in half the ticks it documents"
    )


class _PartialSink:
    """Succeeds for exactly one recipient and fails for the rest — one good address, four dead
    webhook endpoints. The ordinary shape of a partial outage, and the shape no sink in this suite
    could produce until it was the subject of a defect."""

    channel = "recording"

    def __init__(self, succeeds_for: str) -> None:
        self.succeeds_for = succeeds_for

    def deliver(self, message: NotificationMessage) -> DeliveryResult:
        if message.recipient_id == self.succeeds_for:
            return DeliveryResult(ok=True, detail=None)
        return DeliveryResult(ok=False, detail="endpoint gone")


def test_one_recipients_SUCCESS_does_not_retire_the_verdict_for_the_others(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONCLUSION is per recipient, exactly as EXHAUSTION is. They were asymmetric for one commit.

    The fold that made exhaustion per-recipient left conclusion as "any success row retires the
    verdict", so a partial-delivery tick retired it on the strength of ONE delivery and the other
    four holders of `breach.review` were never told about a live divergence and never retried —
    zero retries, not five. Executed before the fix: `QUEUED AFTER ONE PARTIAL TICK: []`.

    The whole per-recipient apparatus was therefore dead on every tick where anyone succeeded; it
    only ever operated in the all-fail corner. This is the test that distinguishes the two rules.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    recipients = [f"reviewer-{i}" for i in range(5)]
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: recipients
    )

    assert (
        alarm_for_verdict(
            session, check=check, sink=_PartialSink("reviewer-0"), acting_tenant=tenant
        )
        == NOTIFY_OUTCOME_SENT
    )
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id], (
        "one recipient's success retired the verdict for everyone — four holders of the alarm "
        "permission are never told about a live divergence and never retried"
    )

    # And it still TERMINATES: keep failing the four, and the backstop must eventually retire it.
    for _ in range(MAX_ALARM_ATTEMPTS):
        alarm_for_verdict(
            session, check=check, sink=_PartialSink("reviewer-0"), acting_tenant=tenant
        )
    session.flush()
    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "the partial-delivery case never terminates — the backstop did not fire"


def test_every_recipient_succeeding_retires_the_verdict_at_once(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control for the test above: when everyone IS told, nobody is re-told.

    Without this, 'per-recipient conclusion' could be satisfied by a rule that simply never retires
    on success at all — which would re-create the unbounded loop from the other direction.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-0", "reviewer-1", "reviewer-2"],
    )
    assert (
        alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_SENT
    )
    session.flush()
    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "every recipient was told and the verdict stayed queued — it will re-page them forever"


def test_tick_phase_5_alarms_the_queue_and_isolates_a_poison_verdict(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`poll_tenant_reproduction_alarms` — the PRODUCTION path — had no test at all.

    Every alarm test until now drove the library functions directly. The worker phase that actually
    delivers in a deployed tick was exercised by nothing on any tier, which the fifth pass flagged
    and this fold owed. Two properties, and the second is the one the module's docstring argues for
    at length: a failing verdict must NOT stop the batch, because one poison verdict silencing the
    night's other divergences is exactly what phase 4's cursor semantics force and this queue was
    designed to avoid.
    """
    from irp_worker.reproduction_alarms import poll_tenant_reproduction_alarms

    tenant = str(uuid.uuid4())
    first = _diverged_check(session, tenant)
    second = _diverged_check(session, tenant)
    session.commit()
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["reviewer-1"]
    )

    exploding = {str(first.id)}
    real = alarm_for_verdict

    # `attempt_id` is passed by the worker since ALERT-1 (it mints the id so a rolled-back
    # transaction can still name the attempt it was making) — the double must accept it, or
    # EVERY verdict fails with a TypeError, which looks exactly like the batch-stopping
    # defect this test exists to catch.
    def _selective(  # noqa: ANN202
        db: Session,
        *,
        check,  # noqa: ANN001
        sink,  # noqa: ANN001
        acting_tenant,  # noqa: ANN001
        now=None,  # noqa: ANN001
        attempt_id=None,  # noqa: ANN001
    ):
        if str(check.id) in exploding:
            raise RuntimeError("this verdict's alarm transaction blew up")
        return real(
            db,
            check=check,
            sink=sink,
            acting_tenant=acting_tenant,
            now=now,
            attempt_id=attempt_id,
        )

    monkeypatch.setattr("irp_worker.reproduction_alarms.alarm_for_verdict", _selective)
    delivered = poll_tenant_reproduction_alarms(
        session, datetime(2026, 8, 8, tzinfo=UTC), acting_tenant=tenant, sink=_RecordingSink()
    )
    assert [d[0] for d in delivered] == [
        str(second.id)
    ], "one poison verdict stopped the batch — the night's other divergences went undelivered"
    assert str(first.id) in {
        str(c.id) for c in unalarmed_verdicts(session, acting_tenant=tenant)
    }, "the failed verdict left the queue despite recording no attempt"


def _poison_row(db: Session, tenant: str, entity_id: str) -> None:
    """A NOTIFY.DISPATCH row whose after_value is a bare string, not a dict.

    No monkeypatch: the FROZEN record_event persists this happily, so the fault is real rather than
    simulated. Any buggy caller can produce it.
    """
    from irp_shared.audit.actions import ACTION_RECORD
    from irp_shared.audit.service import record_event

    record_event(
        db,
        tenant_id=tenant,
        event_type=NOTIFY_DISPATCH_EVENT,
        action=ACTION_RECORD,
        entity_type=ENTITY_REPRODUCTION_CHECK,
        entity_id=entity_id,
        actor_id="some-buggy-caller",
        actor_type="SYSTEM",
        source_module="notification",
        severity="warning",
        outcome="failure",
        after_value="i am not a dict",  # type: ignore[arg-type]
    )
    db.flush()


def test_a_poison_row_cannot_silence_a_LIVE_divergence_found_afterwards(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Wave-16 close review's finding, and the test that would have caught it.

    ONE malformed payload — about an entity with nothing to do with this divergence — used to make
    the whole phase raise, which the worker caught and turned into an empty list, which every
    consumer reads as "nothing to alarm". The tenant's alarm channel then went silent on every
    subsequent tick, permanently, with a log line as the only trace. The review reproduced exactly
    this and watched a genuine divergence created afterwards go unalarmed for five ticks.

    **The test that shipped asserted the empty list as EXPECTED BEHAVIOUR** — it wrote the poison
    row for the diverged verdict itself and checked that nothing was delivered. It encoded the
    fail-open as the contract instead of catching it, which is the defect wearing a passing test.
    """
    from irp_worker.reproduction_alarms import poll_tenant_reproduction_alarms

    tenant = str(uuid.uuid4())
    _poison_row(session, tenant, str(uuid.uuid4()))  # an UNRELATED entity

    live = _diverged_check(session, tenant)  # the divergence arrives AFTER the poison
    session.commit()
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["reviewer-1"]
    )
    sink = _RecordingSink()
    delivered = poll_tenant_reproduction_alarms(
        session, datetime(2026, 8, 8, tzinfo=UTC), acting_tenant=tenant, sink=sink
    )
    assert [d[0] for d in delivered] == [str(live.id)], (
        "a malformed row about an unrelated entity silenced a live divergence — the alarm channel "
        "is permanently inert for this tenant and only a log line says so"
    )
    assert len(sink.messages) == 1


def test_a_verdict_with_an_unreadable_row_stays_QUEUED_rather_than_retiring(
    session: Session,
) -> None:
    """Fail CLOSED toward alarming, which is the only safe direction for a detective control.

    If a verdict's own delivery history contains a row we cannot parse, we do not know whether it
    was ever delivered. The choice is to re-alarm (noise) or to assume delivered (silence). For a
    control whose entire value is telling someone a governed number stopped reproducing, noise is
    the correct failure.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    _poison_row(session, tenant, str(check.id))
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id], (
        "a verdict whose delivery history is unreadable was treated as delivered — the fail-open "
        "direction, on the one control where silence is the failure that matters"
    )


def test_a_MIXED_history_stays_queued_even_when_the_readable_half_says_delivered(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case the ``poisoned`` skip exists for — and the one the battery caught nothing testing.

    ``test_a_verdict_with_an_unreadable_row_stays_QUEUED_rather_than_retiring`` looked like this
    control's proof and is not. There the poison row is the verdict's ONLY row, so the entity never
    enters ``attempts_by_entity`` at all and stays queued whether or not the guard exists — a test
    passing for a reason that has nothing to do with what it claims to check. The mutation battery
    is what found that: deleting the guard left it green (M-A2, a SURVIVOR).

    The guard only bites on a MIXED history: a completed, all-success attempt AND an unreadable row
    for the same verdict. The readable half says "delivered, retire it"; the unreadable half means
    the history is incomplete, so that conclusion is not trustworthy. Fail closed — stay queued.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    session.commit()
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["reviewer-1"]
    )
    alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
    session.flush()
    # The DISCRIMINATING control, inline: a clean success history DOES retire the verdict. Without
    # this the assertion below is equally consistent with a delivery that never succeeded.
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == []

    _poison_row(session, tenant, str(check.id))

    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id], (
        "a verdict with an unreadable row in its delivery history was retired on the strength of "
        "the rows that happened to parse — the fail-open direction on a detective control"
    )


def test_a_poisoned_verdict_still_TERMINATES_at_the_attempts_ceiling(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The v6 OR-clause is UNCONDITIONAL — found broken at the close-fold review, by execution.

    The fold's first shape put the poisoned skip BEFORE the ``MAX_ALARM_ATTEMPTS`` check, which
    disabled the termination backstop for exactly the poisoned class: one permanently-malformed
    row and the verdict re-alarmed every tick forever (executed: ten ticks, ten pages, never
    retired). That is v5's non-termination defect — the one the sixth REPRO-1 fold existed to
    kill — resurrected on a new trigger by the fix for the opposite direction.

    Both properties, in one test, because each alone was already believed and wrong once:
    below the ceiling the poisoned verdict stays QUEUED even though every readable attempt says
    delivered (fail-closed toward alarming); AT the ceiling it retires (bounded noise). The only
    way out of the queue for a poisoned verdict is the ceiling, never an inferred success.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    _poison_row(session, tenant, str(check.id))
    session.commit()
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["reviewer-1"]
    )

    for attempt_no in range(1, MAX_ALARM_ATTEMPTS + 1):
        queue = unalarmed_verdicts(session, acting_tenant=tenant)
        assert [c.id for c in queue] == [check.id], (
            f"a poisoned verdict left the queue after {attempt_no - 1} attempts on the strength "
            "of readable rows alone — an inferred success over an incomplete history"
        )
        alarm_for_verdict(session, check=queue[0], sink=_RecordingSink(), acting_tenant=tenant)
        session.flush()

    assert unalarmed_verdicts(session, acting_tenant=tenant) == [], (
        f"a poisoned verdict did NOT retire after MAX_ALARM_ATTEMPTS={MAX_ALARM_ATTEMPTS} "
        "recorded attempts — the termination backstop is dead for the poisoned class and the "
        "risk desk is paged every tick forever"
    )


def test_alarm_channel_health_is_RECOMPUTED_from_source_not_inferred_from_silence(
    session: Session,
) -> None:
    """An operator must be able to tell 'nothing to alarm' from 'the alarm channel is broken'.

    Both look identical from phase 5's return value — an empty list — which is exactly how the
    permanent-silence defect stayed invisible. LIM-1's standing lesson applies verbatim: a
    fail-open control's health surface must RECOMPUTE from source, never infer from the presence or
    absence of an evidence row.
    """
    from irp_shared.reproduction.service import alarm_channel_health

    tenant = str(uuid.uuid4())
    healthy = alarm_channel_health(session, acting_tenant=tenant)
    assert healthy.unreadable_rows == 0 and healthy.healthy is True

    check = _diverged_check(session, tenant)
    _poison_row(session, tenant, str(check.id))
    sick = alarm_channel_health(session, acting_tenant=tenant)
    assert sick.unreadable_rows == 1, "a malformed delivery row is invisible to the health surface"
    assert sick.healthy is False
    assert sick.queued >= 1, "the health surface must count what is still owed an alarm"


def _legacy_dispatch_row(db: Session, tenant: str, check_id: str, outcome: str) -> None:
    """A `NOTIFY.DISPATCH` row in the PRE-`attempt_id` format — exactly what v5 wrote.

    Written through the real `record_event` so the chain, sequence and payload shape are genuine;
    the payload simply lacks the key that did not exist yet.
    """
    from irp_shared.audit.actions import ACTION_RECORD
    from irp_shared.audit.service import record_event

    record_event(
        db,
        tenant_id=tenant,
        event_type=NOTIFY_DISPATCH_EVENT,
        action=ACTION_RECORD,
        entity_type=ENTITY_REPRODUCTION_CHECK,
        entity_id=check_id,
        actor_id="reproduction-alarm",
        actor_type="SYSTEM",
        source_module="notification",
        severity="warning",
        outcome=outcome,
        after_value={"verdict": VERDICT_DIVERGED, "recipient_id": "legacy-reviewer"},
    )


def test_pre_attempt_id_rows_cannot_spend_the_retry_budget_at_the_UPGRADE_BOUNDARY(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The upgrade boundary resurrected the BLOCKING defect the rule exists to kill.

    One pre-upgrade FAILED tick to five recipients is five rows. Giving each unkeyed row its own
    attempt made that five spent attempts, so the verdict retired the moment this code deployed —
    with zero retries ever taken. That is v3's zero-retry shape reached through a migration rather
    than through the rule, and the comment that justified it called counting up "the safe
    direction": true for audit volume, exactly backwards for an alarm queue, which drops deliveries.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    for _ in range(5):
        _legacy_dispatch_row(session, tenant, str(check.id), "failure")
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id], (
        "legacy rows from ONE failed tick spent the whole retry budget — the verdict retired on "
        "upgrade having never been retried"
    )
    # And the budget is genuinely intact: the collapsed history costs ONE unit, so four more
    # attempts remain before the backstop fires.
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["reviewer-1"]
    )
    for _ in range(MAX_ALARM_ATTEMPTS - 2):
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id]
    # The BOUNDARY, which the assertion above alone cannot see: it holds whether the collapsed
    # bucket costs one budget unit or zero, and those are different rules. One more keyed attempt
    # must retire it — bucket(1) + 4 keyed == MAX_ALARM_ATTEMPTS.
    alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
    session.flush()
    assert unalarmed_verdicts(session, acting_tenant=tenant) == [], (
        "the collapsed legacy bucket cost NOTHING — it must cost exactly one attempt, or the "
        "budget silently grows by one for every verdict that predates the key"
    )


def test_a_pre_attempt_id_PARTIAL_tick_is_not_retired_by_row_ORDER(session: Session) -> None:
    """The same fallback made retirement depend on which row happened to be written last.

    A pre-upgrade partial tick — one delivered, one failed — retired the verdict when the success
    row carried the higher sequence_no, because that lone row looked like a singleton all-success
    "latest attempt". The unreached recipient was silenced by an ordering accident. Collapsing the
    legacy rows into one attempt makes a mixed history mixed, whatever order it was written in.
    """
    for order in (("failure", "success"), ("success", "failure")):
        tenant = str(uuid.uuid4())
        check = _diverged_check(session, tenant)
        for outcome in order:
            _legacy_dispatch_row(session, tenant, str(check.id), outcome)
        session.flush()
        assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id], (
            f"a partial legacy tick written in order {order} retired the verdict — the recipient "
            "that was never reached is silenced by which row happened to land last"
        )


def test_a_departed_recipient_cannot_freeze_the_queue_while_the_survivor_SUCCEEDS(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sixth BLOCKING, found by an independent model on a different engine.

    The previous rule retired a verdict when every recipient was done OR the most-tried recipient
    hit the budget. A recipient who leaves the holder set at `failed=2` satisfies neither and can
    never advance: nothing attempts it again, so `every_recipient_done` stays false, and the
    most-tried backstop only moves while someone CURRENTLY attempted keeps failing.

    The test that existed kept the survivor FAILING — the one sub-case the backstop covers. Here the
    survivor SUCCEEDS, which is the production-normal recovery, and the old rule then re-paged that
    live human every 300-second tick indefinitely: 25 ticks, 25 duplicate pages, unbounded.

    Counting ATTEMPTS rather than recipients is what makes this terminate, because an attempt is a
    thing the system did rather than a fact about a population that moves.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["survivor", "departing"],
    )
    for _ in range(2):
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id]

    # `departing` loses the permission at failed=2 and is never attempted again. The survivor's
    # wire recovers, which under the old rule meant nothing could ever advance.
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["survivor"]
    )
    sink = _RecordingSink()
    assert (
        alarm_for_verdict(session, check=check, sink=sink, acting_tenant=tenant)
        == NOTIFY_OUTCOME_SENT
    )
    session.flush()
    assert unalarmed_verdicts(session, acting_tenant=tenant) == [], (
        "a departed recipient's frozen state held the verdict in the queue — the surviving "
        "reviewer is re-paged on every tick, forever, for an alarm already delivered"
    )
    assert len(sink.messages) == 1, "the survivor was paged more than once after delivery succeeded"


def test_a_FAILED_tick_then_an_EMPTY_TENANT_still_terminates(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second manifestation, and it falsified a USER-RATIFIED rule.

    "A SUPPRESSED attempt is terminal" (retry the wire, not the audience) was ratified — but on the
    ordering "one FAILED tick, then the tenant has no holders at all", the previous rule appended a
    fresh SUPPRESSED sentinel row on every tick forever, because the failed recipient's state was
    frozen below budget and the sentinel could not retire the verdict alone. The ratified semantics
    were not implemented for that ordering; they only held when SUPPRESSED came first.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: ["reviewer-1"]
    )
    assert (
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_FAILED
    )
    session.flush()

    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: []
    )
    assert (
        alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_SUPPRESSED
    )
    session.flush()
    assert unalarmed_verdicts(session, acting_tenant=tenant) == [], (
        "a SUPPRESSED attempt after a FAILED one did not conclude the verdict — a sentinel row is "
        "appended every tick, forever, and the ratified terminal-SUPPRESSED rule is not implemented"
    )
    before = len(_dispatch_events(session, tenant))
    for _ in range(3):
        if unalarmed_verdicts(session, acting_tenant=tenant):
            alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
    session.flush()
    assert (
        len(_dispatch_events(session, tenant)) == before
    ), "rows kept accumulating after the queue emptied"


def test_a_recipient_who_DISAPPEARS_cannot_pin_the_retry_loop_open_forever(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the rule that reads generously and does not terminate.

    Exhaustion is the MAX across recipients. The obvious alternative — MIN, "every recipient has
    had their five" — was written first and executed: a reviewer who loses `breach.review` after two
    failed ticks leaves a stale count of two that no later tick can ever raise, so the minimum stays
    below the bound forever and the retry loop is unbounded again. That is the exact defect
    MAX_ALARM_ATTEMPTS exists to close, so the generous-sounding rule is not the safe one.

    Two recipients for two ticks, then one of them is de-provisioned. Under MIN this verdict never
    leaves the queue.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1", "departing-reviewer"],
    )
    for _ in range(2):
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id]

    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1"],
    )
    for _ in range(MAX_ALARM_ATTEMPTS - 2):
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
    session.flush()
    assert unalarmed_verdicts(session, acting_tenant=tenant) == [], (
        "the departed recipient's stale attempt count held the verdict in the queue — it will "
        "re-fire on every tick forever, which is the unbounded loop the bound exists to close"
    )


def test_a_FAILED_run_of_attempts_ending_in_SENT_retires_the_verdict(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A MIXED sequence — the state machine was only ever proven on uniform ones.

    Four failures then a success is the ordinary shape of a transient outage that recovers, and it
    must retire the verdict without waiting out the remaining budget.
    """
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission",
        lambda *_a, **_k: ["reviewer-1"],
    )
    for _ in range(MAX_ALARM_ATTEMPTS - 1):
        alarm_for_verdict(session, check=check, sink=_ExplodingSink(), acting_tenant=tenant)
    session.flush()
    assert [c.id for c in unalarmed_verdicts(session, acting_tenant=tenant)] == [check.id]

    assert (
        alarm_for_verdict(session, check=check, sink=_RecordingSink(), acting_tenant=tenant)
        == NOTIFY_OUTCOME_SENT
    )
    session.flush()
    assert (
        unalarmed_verdicts(session, acting_tenant=tenant) == []
    ), "a delivery that finally SUCCEEDED did not retire the verdict"


def test_the_audit_outcome_mapping_is_TOTAL_over_the_notify_vocabulary() -> None:
    """The mapping must fail CLOSED on a value it does not recognise.

    `success` is the TERMINAL branch — one such row retires a verdict permanently — so a mapping
    written as "not FAILED" defaults an unknown outcome to terminal. This family has already grown
    a SUPPRESSED sentinel once; the next addition must not silently retire divergences. Pinned
    against the declared vocabulary rather than against a hand-written list, so minting a fourth
    outcome fails HERE until someone decides which way it maps.

    **It worked.** ALERT-1 minted the fourth outcome (``SKIPPED``, the courtesy skip's concluding
    row) and this test is what stopped it being minted silently — the mint had to come here and
    say which way it maps. The trap is re-armed for a FIFTH: the vocabulary is pinned as an exact
    set, and the concluding subset is pinned separately, because "a new outcome exists" and "a new
    outcome CONCLUDES an alarm" are the two different decisions and only the second one can retire
    a divergence.
    """
    assert NOTIFY_OUTCOMES == {
        NOTIFY_OUTCOME_SENT,
        NOTIFY_OUTCOME_FAILED,
        NOTIFY_OUTCOME_SUPPRESSED,
        NOTIFY_OUTCOME_SKIPPED,
    }, (
        "a NOTIFY outcome was minted without deciding whether it CONCLUDES an alarm — see "
        "_emit_dispatch, where an unrecognised value now maps to 'failure' and keeps retrying"
    )
    assert NOTIFY_CONCLUDING_OUTCOMES == {
        NOTIFY_OUTCOME_SENT,
        NOTIFY_OUTCOME_SUPPRESSED,
        NOTIFY_OUTCOME_SKIPPED,
    }, "the concluding set changed — every member of it RETIRES a divergence permanently"
    assert (
        NOTIFY_OUTCOME_FAILED not in NOTIFY_CONCLUDING_OUTCOMES
    ), "a FAILED delivery must never conclude an attempt — retrying the wire is the point"


def test_a_MATCH_verdict_is_never_queued_for_an_alarm(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    outcome = _sweep(session, tenant)
    session.commit()
    assert outcome.checks and all(c.verdict == VERDICT_MATCH for c in outcome.checks)
    assert unalarmed_verdicts(session, acting_tenant=tenant) == []


# ------------------------------------------------------------------------- I5: coverage census ----
def test_coverage_is_a_census_over_every_governed_family() -> None:
    """I5. Registered ∪ unregistered == every run type except REPRODUCTION itself, and the two sets
    are disjoint. A new governed family landing in neither fails HERE, which is the whole point:
    partial coverage is honest, unenumerated partial coverage is a control lying about its reach."""
    import importlib
    import pkgutil

    import irp_shared

    run_types: set[str] = set()
    for info in pkgutil.walk_packages(irp_shared.__path__, prefix="irp_shared."):
        if not info.name.endswith((".events", ".models")):
            continue
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if name.startswith("RUN_TYPE_") and isinstance(value, str):
                run_types.add(value)

    registered = set(REPRODUCIBLE_FAMILIES)
    unregistered = set(UNREPRODUCIBLE_FAMILIES)
    assert not (registered & unregistered), sorted(registered & unregistered)
    assert registered | unregistered == run_types - {RUN_TYPE_REPRODUCTION}, {
        "unclassified": sorted(run_types - {RUN_TYPE_REPRODUCTION} - registered - unregistered),
        "stale": sorted((registered | unregistered) - run_types),
    }


def test_a_divergence_is_a_DISPATCHED_fire_not_a_FAILED_one(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I3, which the review correctly found had NO test — the invariant was asserted in the remit
    and nowhere in code.

    A divergence means the check RAN and the platform's promise broke. Infrastructure failure means
    the check could not run. `dispatch_one` maps `status != COMPLETED` to `OUTCOME_FAILED`, so a
    natural "make a divergence louder" edit — returning FAILED from the sweep when any verdict
    diverges — would put the platform's most important alarm into the same operator feed as a
    database hiccup, and burn the tick bucket so it is not re-checked until the next grid point.
    """
    tenant = str(uuid.uuid4())
    subject = _seed_var_run(session, tenant)
    sigma = str(subject.rows[0].sigma)
    session.commit()
    _plant_sigma(session, subject.run.run_id, str(Decimal(sigma) + Decimal("1")))

    outcome = _sweep(session, tenant)
    assert any(c.verdict == VERDICT_DIVERGED for c in outcome.checks), "the plant did not diverge"
    # The SWEEP completed. This is what `dispatch_one` reads to choose the ledger outcome, so
    # asserting it here is asserting the operator-visible disposition.
    assert outcome.status == RunStatus.COMPLETED.value, (
        "a DIVERGED verdict turned the sweep into a FAILED run — the divergence alarm is now "
        "indistinguishable from an infrastructure failure in the operator feed"
    )
    assert outcome.failure_reason is None


def test_every_column_of_every_reproduced_model_is_classified() -> None:
    """The FIELD-level census — the adversarial review's HIGH, mechanized.

    The first draft declared `compared_fields` by hand and claimed that made a newly-added column
    "a visible decision rather than a silent omission". Nothing backed that: `_VAR_COMPARED` omitted
    five governed columns and `_EXPOSURE_COMPARED` omitted one, and a planted change to `n_factors`
    produced a MATCH verdict — the durable evidence row asserting a pass for a stored governed row
    that demonstrably had not reproduced. This census covers ADDITIONS; `_MUST_COMPARE` below
    covers REMOVALS, which the re-audit proved this test alone did not.

    So the partition is now checked against the MODEL, not against the reader's intent: every
    column is in exactly one of key / compared / explicitly-uncompared, and a new column fails here
    until someone chooses a side.
    """
    for key, family in REPRODUCIBLE_FAMILIES.items():
        assert family.model is not None, f"{key} declares no model — the census cannot check it"
        columns = {c.name for c in family.model.__table__.columns}
        classified = set(family.key_fields) | set(family.compared_fields) | set(family.uncompared)
        assert classified == columns, {
            "family": key,
            "unclassified (add to compared_fields or uncompared, with a reason)": sorted(
                columns - classified
            ),
            "declared but not on the model": sorted(classified - columns),
        }
        overlap = set(family.compared_fields) & set(family.uncompared)
        assert not overlap, f"{key} both compares and excludes {sorted(overlap)}"
        for column, reason in family.uncompared.items():
            assert len(reason) >= 40, (
                f"{key}.{column} is excluded from the comparison with a placeholder reason: "
                f"{reason!r}"
            )


#: The columns that MUST be compared, per family — a PIN, not a floor.
#:
#: The re-audit executed why a reason-length check is not enough: the four `_WHY_*` constants are
#: module-level and reusable, so a maintainer can move the five governed VaR columns out of the
#: comparison, map each to an existing constant, and every test stays green — reaching the exact
#: false-MATCH defect the review's HIGH was about. A length check measures prose, not intent.
#:
#: So the governed value columns are pinned by NAME. Removing one fails HERE, loudly, and the pin
#: moves only with a slice that means to move it — the run-type-census discipline this project
#: already uses ("a census that tolerates shrinkage is a floor wearing a census's name").
_MUST_COMPARE = {
    "VAR": {
        "sigma",
        "var_value",
        "confidence_level",
        "horizon_days",
        "base_currency",
        "n_observations",
        "window_start",
        "window_end",
        "z_score",
        "n_factors",
        "residual_variance",
        "private_variance",
        "estimate_age_days",
    },
    # STRUCT-1 (REQ-PPM-006): ``exposure_type`` left this set because it moved INTO the row key —
    # a STRONGER position (a divergence in it now fails row pairing, not just a field compare).
    # Its key membership is pinned by ``test_exposure_type_is_a_key_field`` below so it cannot
    # silently leave both.
    "EXPOSURE_AGGREGATE": {
        "signed_quantity",
        "mark_value",
        "fx_rate",
        "exposure_amount",
        "mark_currency",
        "fx_legs",
    },
    "REPORT": {"content_hash"},
    # REPRO-2's sixteen. These are HAND-CHOSEN governed value columns, deliberately not derived
    # from each family's `compared_fields` — a pin generated from the thing it pins is a tautology
    # that would pass no matter what left the comparison, which is the failure `_MUST_COMPARE`
    # itself was written to close ("a census that tolerates shrinkage is a floor wearing a
    # census's name"). The rule applied: every column carrying a NUMBER the family exists to
    # produce, plus the counts and conventions that make that number mean what it says.
    "COVARIANCE": {"covariance_value", "n_observations", "window_start", "window_end"},
    "COVARIANCE_PRIVATE": {"covariance_value", "n_observations", "window_start", "window_end"},
    "FACTOR_EXPOSURE": {"loading", "exposure_amount", "base_currency"},
    "SENSITIVITY": {"sensitivity_value", "bump_bps"},
    "SCENARIO": {
        "pnl",
        "shock_value",
        "exposure_amount",
        "n_factors_exposed",
        "n_factors_shocked",
        "n_shocks_unmatched",
    },
    "ACTIVE_RISK": {"te_value", "portfolio_value", "n_factors", "n_constituents"},
    "VAR_BACKTEST": {
        "metric_value",
        "n_exceptions",
        "n_pairs",
        "test_decision",
        "basel_zone",
        "var_value",
        "realized_pnl",
    },
    "ES_BACKTEST": {
        "metric_value",
        "n_exceptions",
        "n_pairs",
        "test_decision",
        "es_value",
        "var_value",
    },
    "PORTFOLIO_RETURN": {
        "return_value",
        "begin_mv",
        "end_mv",
        "net_external_flow",
        "n_flows",
        "n_periods",
    },
    "BENCHMARK_RELATIVE": {
        "metric_value",
        "portfolio_return_value",
        "benchmark_return_value",
        "n_benchmark_obs",
        "n_periods",
        "return_basis",
    },
    "DESMOOTHED_RETURN": {
        "metric_value",
        "observed_return",
        "alpha",
        "alpha_stderr",
        "observed_stdev",
    },
    "ROLLING_RISK": {"metric_value", "suppressed", "n_observations", "annualization_basis"},
    "SHARPE": {"metric_value", "suppressed", "n_observations", "rf_return_basis"},
    "PROXY_WEIGHT_ESTIMATE": {
        "metric_value",
        "std_error",
        "residual_stdev",
        "n_observations",
        "n_regressors",
    },
    "PURE_PRIVATE_FACTOR": {"metric_value", "member_count", "period_count"},
    "PACING_PROJECTION": {
        "projected_call",
        "projected_distribution",
        "projected_nav",
        "unfunded_end",
    },
}


def test_exposure_type_is_a_key_field() -> None:
    """STRUCT-1 (REQ-PPM-006): the measure discriminator is part of the row-pairing KEY. Without
    it, two measures for one holding produce duplicate comparison keys and the adapter pairs a
    stored NOTIONAL row against a recomputed MARKET_VALUE row."""
    assert "exposure_type" in REPRODUCIBLE_FAMILIES["EXPOSURE_AGGREGATE"].key_fields


def test_no_governed_column_can_be_dropped_from_the_comparison() -> None:
    """The re-audit's HIGH: the reason floor was satisfiable by copying an existing constant, so
    the five columns that WERE the original defect could be removed with all tests green. This pins
    them by name — shrinkage now fails, and the pin can only move deliberately."""
    assert set(_MUST_COMPARE) == set(
        REPRODUCIBLE_FAMILIES
    ), "a registered family has no must-compare pin — it could shrink silently"
    for key, required in _MUST_COMPARE.items():
        missing = required - set(REPRODUCIBLE_FAMILIES[key].compared_fields)
        assert not missing, (
            f"{key} no longer compares {sorted(missing)} — a governed column left the comparison, "
            "so a divergence confined to it would be reported as MATCH"
        )


#: The REPORT columns that `regenerate_report` does NOT read — measured against its source, not
#: asserted from memory. Pinned because the reason attached to them was WRONG for one commit and
#: every existing guard passed over it: the column census passed (they were classified), the
#: 40-character reason floor passed (the constant was 168 characters), and `_MUST_COMPARE["REPORT"]`
#: holds only `content_hash`, the one column that structurally cannot diverge. A floor measures
#: prose, not truth.
_REPORT_NOT_REDERIVED = ("report_code", "report_version_label", "render_format")


def test_the_report_columns_regeneration_never_reads_say_so_honestly() -> None:
    """`_WHY_RENDER_INPUT` claimed these three were compared-against-themselves. They are not.

    `regenerate_report` takes a report id and reads exactly `input_snapshot_id`, `portfolio_code`
    and `as_of_date`. It never reads `report_code`, `report_version_label` or `render_format` — so
    the vacuity claim was false, and the cost was measured rather than argued: tampering the stored
    `render_format` produced a durable MATCH verdict with `rows_diverged=0`.

    They still cannot be compared (the recompute genuinely does not produce them — the review fold
    tried, and every report diverged), so this is a NAMED coverage gap. This pins the distinction
    so a later edit cannot quietly fold them back under the vacuity reason and re-acquire a claim
    that is well-written and false.
    """
    report = REPRODUCIBLE_FAMILIES["REPORT"]
    for column in _REPORT_NOT_REDERIVED:
        reason = report.uncompared[column]
        assert "does not re-derive and does not read" in reason, (
            f"{column} is excluded with a reason that claims a vacuous comparison; regeneration "
            "never reads it, so the exclusion is a coverage GAP and must say so"
        )
        assert column not in report.compared_fields
    # And the two that genuinely ARE read back keep the vacuity reason — the distinction is the
    # point, so a blanket rename of all five would fail here too.
    for column in ("as_of_date", "portfolio_code"):
        assert "reads FROM THE ROW" in report.uncompared[column]


def test_the_comparison_actually_reads_every_declared_field() -> None:
    """A declaration with no consumer is worse than no declaration (the deleted
    `produces_run_on_failure`). This proves `compared_fields` is what `compare_rows` iterates: a
    field declared but never read would let the census above pass while the comparison stayed
    narrow."""
    fam = REPRODUCIBLE_FAMILIES["VAR"]
    for field in fam.compared_fields:
        stored = [ComparableRow(key=("K",), values=dict.fromkeys(fam.compared_fields, "same"))]
        fresh = [ComparableRow(key=("K",), values=dict.fromkeys(fam.compared_fields, "same"))]
        fresh[0].values[field] = "DIFFERENT"
        _compared, diverged, first = compare_rows(stored, fresh, fam)
        assert diverged == 1, f"a change to {field!r} was invisible to compare_rows"
        assert (first or "").endswith(f":: {field}")


def test_duplicate_natural_keys_are_refused_rather_than_silently_collapsed() -> None:
    """The review's MEDIUM: `compare_rows` builds dicts keyed by the natural key, so a family whose
    key does not uniquely identify a row within a run would silently collapse N rows to one and
    report a confident MATCH over a single survivor. Eight of the eighteen unregistered families
    have multi-row grains, so this is the next slice's foot-gun, not a hypothetical."""
    fam = REPRODUCIBLE_FAMILIES["VAR"]
    dupes = [
        ComparableRow(key=("K",), values=dict.fromkeys(fam.compared_fields, "a")),
        ComparableRow(key=("K",), values=dict.fromkeys(fam.compared_fields, "b")),
    ]
    with pytest.raises(ValueError, match="natural key"):
        compare_rows(dupes, dupes, fam)


def test_a_duplicate_key_refusal_is_a_VERDICT_not_an_outage(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix for the audit's blast-radius finding, exercised through the SWEEP.

    The direct-call test above proves `compare_rows` refuses. It does NOT prove the refusal is
    CONTAINED — and the mutation battery caught exactly that: removing the guard in
    `check_one_family` left that test green. A ValueError escaping the sweep rolls back the
    per-schedule SAVEPOINT and discards the night's other verdicts, which is the precise blast
    radius the BLOCKING savepoint fix removed and the fold accidentally re-created one line over.
    """
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()

    def _dupes(*_a: object, **_k: object) -> list[ComparableRow]:
        fam = REPRODUCIBLE_FAMILIES["VAR"]
        row = ComparableRow(key=("SAME",), values=dict.fromkeys(fam.compared_fields, "x"))
        return [row, row]

    monkeypatch.setitem(
        REPRODUCIBLE_FAMILIES,
        "VAR",
        replace(REPRODUCIBLE_FAMILIES["VAR"], read_stored=_dupes, recompute=_dupes),
    )
    outcome = _sweep(session, tenant)  # must NOT raise
    by_family = {c.family_key: c.verdict for c in outcome.checks}
    assert by_family.get("VAR") == VERDICT_UNREPRODUCIBLE
    assert "natural key" in (
        next(c.first_divergence or "" for c in outcome.checks if c.family_key == "VAR")
    )
    assert (
        by_family.get("EXPOSURE_AGGREGATE") == VERDICT_MATCH
    ), "the duplicate-key refusal took the night's other verdicts with it"


def test_every_exclusion_carries_a_real_reason() -> None:
    """A blank or placeholder reason would make the census pass while telling a reader nothing —
    the enumerating-guard non-vacuity floor (P6)."""
    for family, reason in UNREPRODUCIBLE_FAMILIES.items():
        assert len(reason) >= 30, f"{family} has a placeholder reason: {reason!r}"


#: The coverage census, pinned by NAME at 19+2 (REPRO-2, OQ-REP2-4 — was 3+18 at REPRO-1).
#:
#: A COUNT would have been cheaper and would have measured nothing: a family moved from one
#: declaration to the other keeps the total, and moving one INTO `UNREPRODUCIBLE_FAMILIES` (with a
#: plausible reason) is exactly how reproduction coverage would quietly shrink. So both sets are
#: named, and shrinking either fails here.
_EXPECTED_REPRODUCIBLE = {
    "VAR",
    "EXPOSURE_AGGREGATE",
    "REPORT",
    # REPRO-2's sixteen.
    "COVARIANCE",
    "COVARIANCE_PRIVATE",
    "FACTOR_EXPOSURE",
    "SENSITIVITY",
    "SCENARIO",
    "ACTIVE_RISK",
    "VAR_BACKTEST",
    "ES_BACKTEST",
    "PORTFOLIO_RETURN",
    "BENCHMARK_RELATIVE",
    "DESMOOTHED_RETURN",
    "ROLLING_RISK",
    "SHARPE",
    "PROXY_WEIGHT_ESTIMATE",
    "PURE_PRIVATE_FACTOR",
    "PACING_PROJECTION",
}
#: The two that are structurally blocked, NOT "not yet adapted" — each keeps its own trigger.
_EXPECTED_UNREPRODUCIBLE = {"CONCENTRATION", "LIQUIDITY"}


def test_the_verdict_vocabulary_and_the_registry_agree_with_the_model() -> None:
    assert VERDICTS == {VERDICT_MATCH, VERDICT_DIVERGED, VERDICT_UNREPRODUCIBLE}
    assert set(REPRODUCIBLE_FAMILIES) == _EXPECTED_REPRODUCIBLE
    assert set(UNREPRODUCIBLE_FAMILIES) == _EXPECTED_UNREPRODUCIBLE
    assert all(key == fam.family_key for key, fam in REPRODUCIBLE_FAMILIES.items())
    assert ALARM_RECIPIENT_PERMISSION == "breach.review"


def test_the_sixteen_new_families_are_actually_INSTALLED() -> None:
    """The eager-install's own control.

    `registry.py` installs REPRO-2's families by calling `_install_repro2_families()` at import.
    If that call were ever removed — or moved behind a lazy accessor nobody invokes — the sixteen
    would silently vanish from the sweep while every other test that names a family individually
    kept passing. An unregistered family is an UNCHECKED family, which is the one thing the
    two-declaration census exists to make impossible.
    """
    for family_key in _EXPECTED_REPRODUCIBLE - {"VAR", "EXPOSURE_AGGREGATE", "REPORT"}:
        family = REPRODUCIBLE_FAMILIES[family_key]
        assert callable(family.read_stored) and callable(family.recompute)
        assert family.model is not None, f"{family_key} installed without its census model"


# -------------------------------------------------------------------------- I8: append-only -------
def test_a_verdict_cannot_be_edited_or_deleted(session: Session) -> None:
    """A verdict that could be rewritten after the fact is not evidence. The DB trigger is the real
    fence; this proves the ORM guard on the tier where no trigger exists."""
    tenant = str(uuid.uuid4())
    _seed_var_run(session, tenant)
    session.commit()
    check = _sweep(session, tenant).checks[0]
    session.commit()

    check.verdict = VERDICT_DIVERGED
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()

    fresh = session.execute(
        select(ReproductionCheck).where(ReproductionCheck.tenant_id == tenant).limit(1)
    ).scalar_one()
    session.delete(fresh)
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()
