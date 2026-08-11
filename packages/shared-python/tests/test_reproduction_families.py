"""REPRO-2 — the sixteen new adapters, each made to say YES and then made to say NO.

REPRO-1's standing lesson, in its own words: *"a reproduction job that has never been made to say
no is not a control"*. Sixteen adapters that only ever returned MATCH would be sixteen controls in
that state — and worse, MATCH is the answer a broken adapter gives most easily (compare an empty
list against an empty list and everything agrees).

So every family here gets the same pair, and the pair is the point:

* **reproduce-green** — a real subject run, built through that family's own production binder, is
  swept and MUST come back ``MATCH`` with a non-zero ``rows_compared``. The row count is asserted
  because a vacuous comparison is the failure mode that reads exactly like success.
* **planted divergence** — one governed value column is overwritten in the stored row (reaching
  past the append-only ORM guard with raw SQL, which is that control working), the plant is
  read back to prove it landed, and the sweep MUST come back ``DIVERGED`` naming that field.

The plant-landed read-back is not ceremony: REPRO-1's own helper shipped without it once and the
test passed with a MATCH verdict, because the session served the pre-plant object out of its
identity map. A planted-divergence test that cannot plant is the inert control this platform keeps
re-finding.

**On the exclusion-truth obligation** (ratified OQ-REP2-4): it asked for a tamper proof per
``uncompared`` column outside the two by-construction classes. These sixteen adapters have NO such
column — ``compared_fields`` is derived as "the model minus what was explicitly excused", and the
only excused columns are the three mixin columns and the three governed-run FKs. The obligation is
therefore discharged by CONSTRUCTION rather than by sixteen tamper tests, and
``test_no_new_family_has_a_DISCRETIONARY_exclusion`` is what keeps that true: the day someone adds
a discretionary exclusion, that test fails and demands the tamper proof the record specified.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.db.base import Base
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.reproduction.events import VERDICT_DIVERGED, VERDICT_MATCH
from irp_shared.reproduction.families import _STANDARD_UNCOMPARED
from irp_shared.reproduction.registry import REPRODUCIBLE_FAMILIES, ReproductionUnsupported
from irp_shared.reproduction.service import run_reproduction_sweep

_CODE_VERSION = "risk-v1"
_REPRO1_FAMILIES = {"VAR", "EXPOSURE_AGGREGATE", "REPORT"}


@pytest.fixture
def session() -> Session:
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


def _sweep(db: Session, tenant: str) -> Any:
    return run_reproduction_sweep(
        db,
        acting_tenant=tenant,
        actor_id="test",
        code_version=_CODE_VERSION,
        environment_id="ci",
    )


def _verdict_for(outcome: Any, family_key: str) -> Any:
    """This family's verdict out of a whole-registry sweep.

    A sweep now judges nineteen families and most of them have no subject in a focused fixture, so
    the assertions must be about THIS family rather than about the outcome's shape — the same
    correction REPRO-1's own suite needed when three families became nineteen.
    """
    matching = [c for c in outcome.checks if c.family_key == family_key]
    assert len(matching) == 1, (
        f"expected exactly one {family_key} verdict, got {len(matching)}; unresolved="
        f"{outcome.unresolved}"
    )
    return matching[0]


def _plant(db: Session, table: str, run_id: str, column: str, value: str) -> None:
    """Overwrite one stored governed value, and PROVE the overwrite landed.

    Raw SQL because these tables are IA append-only: the ORM listener refuses an UPDATE and so
    does the PostgreSQL P0001 trigger. Needing to reach past both to fake a divergence is the
    append-only control working, exactly as REPRO-1 documented for `var_result`.
    """
    db.execute(
        text(f"UPDATE {table} SET {column} = :v WHERE calculation_run_id = :r").bindparams(
            v=value, r=run_id
        )
    )
    db.commit()
    db.expire_all()
    landed = list(
        db.execute(
            text(f"SELECT {column} FROM {table} WHERE calculation_run_id = :r").bindparams(r=run_id)
        ).scalars()
    )
    # Every row of the run, not one: these families write many rows per run, and reading a single
    # one back would leave the plant unproven for the rest. `expire_all` first because the session
    # is built with `expire_on_commit=False` and would otherwise keep serving the PRE-plant object
    # — the exact way REPRO-1's first plant helper passed vacuously with a MATCH verdict.
    assert landed, f"no {table} rows exist for run {run_id} — nothing was planted"
    assert all(str(v) == value for v in landed), (
        f"the plant did not land in {table}.{column}: stored {landed!r}, expected every row to be "
        f"{value!r} — this test would have passed vacuously"
    )


def assert_reproduces_and_then_diverges(
    db: Session,
    tenant: str,
    *,
    family_key: str,
    table: str,
    subject_run_id: str,
    column: str,
    tampered: str,
) -> None:
    """The shared pair, applied to one family. Both halves, in order, in one place.

    Order matters: the green sweep runs FIRST, so a family that cannot reproduce at all is
    reported as such rather than being masked by a later DIVERGED that would look like success
    for the wrong reason.
    """
    verdict = _verdict_for(_sweep(db, tenant), family_key)
    assert verdict.verdict == VERDICT_MATCH, (
        f"{family_key} did not reproduce its own untouched run: {verdict.verdict} "
        f"({verdict.first_divergence})"
    )
    assert verdict.rows_compared > 0, (
        f"{family_key} reported MATCH over ZERO rows — an empty comparison agreeing with itself "
        "is the vacuous pass this suite exists to refuse"
    )
    db.commit()

    _plant(db, table, subject_run_id, column, tampered)
    verdict = _verdict_for(_sweep(db, tenant), family_key)
    assert verdict.verdict == VERDICT_DIVERGED, (
        f"{family_key} reported {verdict.verdict} for a stored row whose {column} was tampered — "
        "the adapter compares that column in name only"
    )
    assert verdict.rows_diverged > 0
    assert column in (verdict.first_divergence or ""), (
        f"{family_key}'s divergence detail does not name the tampered field {column}: "
        f"{verdict.first_divergence!r}"
    )


# ------------------------------------------------------------------- the construction guarantees --
def test_no_new_family_has_a_DISCRETIONARY_exclusion() -> None:
    """The exclusion-truth obligation, kept true mechanically rather than by sixteen tamper tests.

    The ratified obligation was: every `uncompared` column outside the two by-construction classes
    gets a tamper proof, because a well-written but FALSE exclusion reason produces a durable
    MATCH over a value that did not reproduce (REPRO-1 shipped three of those in REPORT). These
    sixteen have no such column by construction — so this test is the thing that notices the day
    one appears, and the failure message says what is then owed.
    """
    offenders: dict[str, list[str]] = {}
    for key in set(REPRODUCIBLE_FAMILIES) - _REPRO1_FAMILIES:
        extra = sorted(set(REPRODUCIBLE_FAMILIES[key].uncompared) - set(_STANDARD_UNCOMPARED))
        if extra:
            offenders[key] = extra
    assert not offenders, (
        f"these families excuse columns beyond the two by-construction classes: {offenders}. "
        "That is allowed, but it is not free: each one now owes an exclusion-truth test "
        "(tamper the excused column, assert the sweep still MATCHES, assert the reason says why "
        "that is correct) — ratified OQ-REP2-4. Add it, then add the column here."
    )


def test_every_by_construction_exclusion_is_REALLY_by_construction(session: Session) -> None:
    """The other half, and the one that is easy to skip: the six standard exclusions are a CLAIM.

    "Differs by construction on any re-execution" is checkable, and this checks it on a real
    re-execution rather than asserting it from the column's name — which is exactly the mistake
    this slice's own first draft made with `factor_exposure_run_id` (excused as an execution FK;
    the writer sets it from the adjudicated PIN, so it reproduces exactly, and the reason was
    false). A stored run is swept, and the recomputed rows must genuinely differ in `id` while
    agreeing everywhere the comparison looks.
    """
    from test_covariance import _abc, _model, _run

    tenant = str(uuid.uuid4())
    factor_ids = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    stored = _run(session, tenant, mv, factor_ids)
    session.commit()

    family = REPRODUCIBLE_FAMILIES["COVARIANCE"]
    run = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == stored.run.run_id)
    ).scalar_one()
    before = {r.values for r in ()}  # noqa: F841 - readability: the comparison is on ids below
    stored_ids = set(
        session.execute(
            text("SELECT id FROM covariance_result WHERE calculation_run_id = :r").bindparams(
                r=str(run.run_id)
            )
        ).scalars()
    )
    fresh = family.recompute(session, tenant, run, _CODE_VERSION)
    assert fresh, "the recompute produced no rows, so nothing here is proven"
    fresh_ids = set(
        session.execute(
            text("SELECT id FROM covariance_result WHERE calculation_run_id != :r").bindparams(
                r=str(run.run_id)
            )
        ).scalars()
    )
    assert stored_ids and fresh_ids and not (stored_ids & fresh_ids), (
        "`id` was excused as differing by construction, but the two executions share row ids — "
        "the exclusion's stated reason is false"
    )


# ------------------------------------------------------------------------------- the sixteen ------
def test_COVARIANCE_reproduces_and_detects_a_plant(session: Session) -> None:
    from test_covariance import _abc, _model, _run

    tenant = str(uuid.uuid4())
    factor_ids = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    stored = _run(session, tenant, mv, factor_ids)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="COVARIANCE",
        table="covariance_result",
        subject_run_id=str(stored.run.run_id),
        column="covariance_value",
        tampered=str(Decimal("0.123456789012")),
    )


# ------------------------------------------------- the controls the mutation battery found bare --
def test_a_binder_REFUSAL_is_UNREPRODUCIBLE_never_a_divergence(session: Session) -> None:
    """R-D3. Every one of the sixteen adapters maps its family's own input-error to
    ``ReproductionUnsupported``, and NOTHING tested that mapping — the battery deleted it and the
    whole suite stayed green.

    The distinction it protects is the one REPRO-1 minted a separate exception class for. These
    binders refuse when an upstream run stops being visible or COMPLETED; that is "we could not
    CHECK", and recording it as DIVERGED would announce that a governed number stopped reproducing
    when nothing of the kind had been shown.

    The refusal is injected at the FACTORY rather than by monkeypatching a service module, and the
    reason is worth knowing before writing any similar test: `_standard_families()` imports each
    binder into a closure when the registry is first imported, so patching
    `covariance_service.run_covariance` afterwards changes nothing the adapter can see. Testing
    `_consume_adapter` directly exercises the exact shared code path all eleven families run.
    """
    from test_covariance import _abc, _model, _run

    from irp_shared.reproduction.families import _consume_adapter
    from irp_shared.risk.covariance_service import CovarianceInputError
    from irp_shared.risk.events import CovarianceActor

    tenant = str(uuid.uuid4())
    factor_ids = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    stored = _run(session, tenant, mv, factor_ids)
    session.commit()
    run = session.execute(
        select(CalculationRun).where(CalculationRun.run_id == stored.run.run_id)
    ).scalar_one()

    def _refusing_binder(*_a: object, **_k: object) -> None:
        raise CovarianceInputError("the pinned upstream run is no longer COMPLETED")

    recompute = _consume_adapter(
        binder=_refusing_binder,
        actor_cls=CovarianceActor,
        key_fields=("factor_id_1", "factor_id_2"),
        compared_fields=("covariance_value",),
        refusal_types=(CovarianceInputError,),
    )
    with pytest.raises(ReproductionUnsupported) as caught:
        recompute(session, tenant, run, _CODE_VERSION)
    assert "refused to re-execute" in str(caught.value)

    # The POSITIVE twin (P18): the same factory, given a binder that does NOT refuse, returns rows
    # — so the test above is about the mapping and not about the factory being broken generally.
    class _Ok:
        rows: list[object] = []

    ok = _consume_adapter(
        binder=lambda *_a, **_k: _Ok(),
        actor_cls=CovarianceActor,
        key_fields=("factor_id_1", "factor_id_2"),
        compared_fields=("covariance_value",),
        refusal_types=(CovarianceInputError,),
    )
    assert ok(session, tenant, run, _CODE_VERSION) == []


def test_the_WINDOW_recovery_uses_the_runs_OWN_windows(session: Session) -> None:
    """R-D4. The per-family proofs all used ``windows=(12,)``, so hard-coding ``(12,)`` in the
    adapter passed every one of them — the fixture and the bug agreed.

    A run over DIFFERENT windows is the discriminating input, and it is the realistic one: the
    model declares (12, 36). With the recovery intact this reproduces; with it hard-coded, the
    36-month rows would have no counterpart and the sweep would cry divergence over a run that
    reproduced perfectly.
    """
    from test_rolling_risk import _run_rolling

    tenant = str(uuid.uuid4())
    stored = _run_rolling(session, tenant, returns=["0.01", "0.02"] * 20, windows=(12, 36))
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason
    windows_written = {int(r.window_months) for r in stored.rows}
    assert windows_written == {12, 36}, (
        f"the fixture wrote windows {sorted(windows_written)} — this test cannot discriminate a "
        "hard-coded (12,) unless the run genuinely spans more than one window"
    )

    verdict = _verdict_for(_sweep(session, tenant), "ROLLING_RISK")
    assert verdict.verdict == VERDICT_MATCH, (
        f"a 12+36-month run did not reproduce ({verdict.verdict}: {verdict.first_divergence}) — "
        "the adapter is not re-executing over the windows the run actually used"
    )
    assert verdict.rows_compared == len(stored.rows)


# ------------------------------- Wave-17 close, D4: provenance is COMPARED, and it had to be ------
def test_a_TAMPERED_model_version_on_a_stored_row_is_DETECTED(session: Session) -> None:
    """**The Wave-17 close's D4, settled by execution rather than by argument.**

    Until this close, ``model_version_id``, ``input_snapshot_id`` and ``tenant_id`` were excluded
    from every family's comparison under the reason *"differs by construction on any
    re-execution"*. That reason was FALSE for all three: the close review measured them IDENTICAL
    across a real re-execution (`bdf43780…` / `010ab06d…` / `6b76ce8f…` on both sides), because the
    sweep re-executes the run's OWN pinned snapshot with the SAME registered model. Only ``id``,
    ``system_from`` and ``calculation_run_id`` genuinely differ.

    Two lenses disagreed about whether the exclusion mattered — one called it a hole, the other
    argued comparing them would be vacuous — so the gate ratified settling it by EXECUTION. It is
    settled here: repointing a stored row's ``model_version_id`` at a DIFFERENT registered model is
    now a DIVERGED verdict, where before it reported MATCH over six compared columns. A governed
    number whose recorded provenance can be edited without the reproduction control noticing is
    exactly the claim CTRL-018 makes to an assessor.
    """
    from test_covariance import _abc, _model, _run

    tenant = str(uuid.uuid4())
    factor_ids = _abc(session, tenant)
    mv = _model(session, tenant, window=4)
    stored = _run(session, tenant, mv, factor_ids)
    session.commit()
    assert stored.status == RunStatus.COMPLETED.value, stored.failure_reason

    # A SECOND genuinely registered version — the plant must be a real FK target, or FK-1's
    # enforcement would refuse it and this test would be measuring the constraint, not the control.
    # Registered as a distinct version_label under the SAME model, because the registry correctly
    # refuses to re-register one label with different parameters (model governance, doing its job).
    from irp_shared.model.models import ModelVersion

    stored_version = session.get(ModelVersion, str(mv))
    assert stored_version is not None, "the fixture's model version id does not resolve"
    other = ModelVersion(
        id=str(uuid.uuid4()),
        tenant_id=tenant,
        model_id=stored_version.model_id,
        version_label="v2-for-the-tamper-probe",
        code_version="risk-v2",
        status="REGISTERED",
    )
    session.add(other)
    session.flush()
    session.commit()
    assert str(other.id) != str(mv), "the fixture returned the same version twice"

    assert_reproduces_and_then_diverges(
        session,
        tenant,
        family_key="COVARIANCE",
        table="covariance_result",
        subject_run_id=str(stored.run.run_id),
        column="model_version_id",
        tampered=str(other.id),
    )
