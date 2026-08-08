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
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
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
    MAX_ALARM_ATTEMPTS,
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

    assert [c.family_key for c in outcome.checks] == [
        "EXPOSURE_AGGREGATE"
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

    assert [c.family_key for c in outcome.checks] == ["EXPOSURE_AGGREGATE"], (
        "a failing subject lookup took the night's other verdicts with it, or minted a verdict "
        "about a run it could not identify"
    )
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
    assert any("recording the" in u for u in outcome.unresolved), (
        "the verdict that could not be written vanished silently — it must be reported, not "
        "swallowed"
    )
    persisted = (
        session.execute(select(ReproductionCheck).where(ReproductionCheck.tenant_id == tenant))
        .scalars()
        .all()
    )
    assert len(persisted) == 1


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
    """
    assert NOTIFY_OUTCOMES == {
        NOTIFY_OUTCOME_SENT,
        NOTIFY_OUTCOME_FAILED,
        NOTIFY_OUTCOME_SUPPRESSED,
    }, (
        "a NOTIFY outcome was minted without deciding whether it CONCLUDES an alarm — see "
        "_emit_dispatch, where an unrecognised value now maps to 'failure' and keeps retrying"
    )


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
    "EXPOSURE_AGGREGATE": {
        "signed_quantity",
        "mark_value",
        "fx_rate",
        "exposure_amount",
        "mark_currency",
        "exposure_type",
        "fx_legs",
    },
    "REPORT": {"content_hash"},
}


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


def test_the_verdict_vocabulary_and_the_registry_agree_with_the_model() -> None:
    assert VERDICTS == {VERDICT_MATCH, VERDICT_DIVERGED, VERDICT_UNREPRODUCIBLE}
    assert set(REPRODUCIBLE_FAMILIES) == {"VAR", "EXPOSURE_AGGREGATE", "REPORT"}
    assert all(key == fam.family_key for key, fam in REPRODUCIBLE_FAMILIES.items())
    assert ALARM_RECIPIENT_PERMISSION == "breach.review"


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
