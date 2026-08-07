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
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent, AppendOnlyViolation
from irp_shared.audit.service import verify_chain
from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.notification.events import (
    NOTIFY_DISPATCH_EVENT,
    NOTIFY_OUTCOME_FAILED,
    NOTIFY_OUTCOME_SENT,
    NOTIFY_OUTCOME_SUPPRESSED,
)
from irp_shared.notification.sink import DeliveryResult, NotificationMessage
from irp_shared.reproduction.events import (
    ALARM_RECIPIENT_PERMISSION,
    ENTITY_REPRODUCTION_CHECK,
    VERDICTS,
    VERDICT_DIVERGED,
    VERDICT_MATCH,
    VERDICT_UNREPRODUCIBLE,
)
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck
from irp_shared.reproduction.registry import (
    REPRODUCIBLE_FAMILIES,
    UNREPRODUCIBLE_FAMILIES,
    ComparableRow,
    ReproductionUnsupported,
)
from irp_shared.reproduction.service import (
    alarm_for_verdict,
    compare_rows,
    latest_completed_run,
    run_reproduction_sweep,
    unalarmed_verdicts,
)
from irp_shared.risk.models import VarResult
from test_var import (  # noqa: F401 - `session` is the shared in-memory-SQLite fixture
    _run,
    _seed_upstream_runs,
    _var_model,
    session,
)

_CODE_VERSION = "risk-v1"


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
    _run(session, tenant, first.rows[0].model_version_id, None, None,
         snapshot_id=first.run.input_snapshot_id)
    savepoint.commit()

    runs, results, events = _counts(session, tenant)
    assert runs > before[0] and results > before[1] and events > before[2]


# ------------------------------------------------------- I2: a planted divergence is made to FIRE --
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
    """"We could not check" and "we checked and it is fine" must never be the same verdict."""
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
    assert alarm_for_verdict(
        session, check=check, sink=sink, acting_tenant=tenant
    ) == NOTIFY_OUTCOME_SENT
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
    assert alarm_for_verdict(
        session, check=check, sink=_ExplodingSink(), acting_tenant=tenant
    ) == NOTIFY_OUTCOME_FAILED
    events = _dispatch_events(session, tenant)
    assert len(events) == 1, "an exploding sink lost the alarm entirely"


def test_a_tenant_with_no_recipient_records_SUPPRESSED_rather_than_nothing(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Nobody was configured to hear this" is a fact an operator needs. Silence here would be
    indistinguishable from a healthy night — the LQ-1 inert-control shape."""
    tenant = str(uuid.uuid4())
    check = _diverged_check(session, tenant)
    monkeypatch.setattr(
        "irp_shared.entitlement.service.holders_of_permission", lambda *_a, **_k: []
    )
    sink = _RecordingSink()
    assert alarm_for_verdict(
        session, check=check, sink=sink, acting_tenant=tenant
    ) == NOTIFY_OUTCOME_SUPPRESSED
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
    """The queue is an EXISTENCE test per verdict, not a high-water cursor — NOTIF-1's lesson that
    a derived MAX cannot represent a gap."""
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
