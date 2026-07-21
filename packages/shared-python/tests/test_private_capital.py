"""SQLite-local unit/behavior tests for CC-1 private capital (ENT-015/016).

RLS is a no-op on SQLite, so symmetric isolation + the P0001 DB triggers live in the PG
file; here we prove the model contracts (temporal classes; the FR manual trio on
``commitment``; NO TimestampMixin on the IA event tables — the transaction precedent;
the ORM append-only guards; the current-row and reversal partial-unique indexes; the
capture-only scope fence: no snapshot/run/model column anywhere), and the service-layer
behavior added at steps 4-5.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.private_capital.models import (
    CALL_TYPES,
    DISTRIBUTION_TYPES,
    CapitalCall,
    Commitment,
    Distribution,
)
from irp_shared.temporal import TemporalClass

# --- temporal classes + column contracts ---


def test_commitment_is_fr_with_manual_trio() -> None:
    assert Commitment.__temporal_class__ == TemporalClass.FULL_REPRODUCIBLE
    for attr in ("valid_from", "valid_to", "system_from", "system_to"):
        assert hasattr(Commitment, attr)
    # The FR manual trio is declared on the model (the mixin supplies only the axes).
    for attr in ("record_version", "supersedes_id", "restatement_reason"):
        assert hasattr(Commitment, attr)


def test_event_tables_are_ia_without_timestamps() -> None:
    for model in (CapitalCall, Distribution):
        assert model.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
        assert hasattr(model, "system_from")
        # No FR/EV axis, no lifecycle, and NO TimestampMixin (updated_* on a
        # P0001-guarded table is dead from birth — the transaction precedent).
        for attr in (
            "valid_from",
            "valid_to",
            "system_to",
            "record_version",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ):
            assert not hasattr(model, attr), f"{model.__name__} must not have {attr}"


def test_capture_only_scope_fence() -> None:
    # Captured inputs bind NO snapshot/run/model (the house contract, OD-CC-1-D/E) and
    # store NO derived economics (funded/unfunded are CC-2's).
    forbidden = {
        "input_snapshot_id",
        "calculation_run_id",
        "model_version_id",
        "funded_amount",
        "unfunded_amount",
        "vintage_year",
    }
    for model in (Commitment, CapitalCall, Distribution):
        cols = set(model.__table__.columns.keys())
        assert not (forbidden & cols), f"{model.__name__} leaks: {forbidden & cols}"


def test_event_tables_key_on_stable_identity_not_version_fk() -> None:
    # The verifier's structural HIGH: events key on (portfolio_id, instrument_id); the
    # commitment_version_id echo is provenance-only and deliberately NOT an FK (an FR
    # version row is not a stable link target).
    for model in (CapitalCall, Distribution):
        cols = model.__table__.columns
        assert not cols["commitment_version_id"].foreign_keys
        assert cols["portfolio_id"].foreign_keys and cols["instrument_id"].foreign_keys


def test_vocab_constants() -> None:
    assert CALL_TYPES == ("DRAWDOWN", "EQUALIZATION", "FEE")
    assert DISTRIBUTION_TYPES == ("RETURN_OF_CAPITAL", "CAPITAL_GAIN", "INCOME")
    assert hasattr(Distribution, "is_recallable")
    assert not hasattr(CapitalCall, "is_recallable")  # distribution-only (OD-CC-1-C)


def test_partial_unique_indexes_declared() -> None:
    def _index(model, name):  # noqa: ANN001, ANN202
        by_name = {ix.name: ix for ix in model.__table__.indexes}
        assert name in by_name, f"{model.__name__} missing index {name}"
        return by_name[name]

    current = _index(Commitment, "uq_commitment_current")
    assert current.unique
    assert [c.name for c in current.columns] == ["tenant_id", "portfolio_id", "instrument_id"]
    for model, name in (
        (CapitalCall, "uq_capital_call_reverses"),
        (Distribution, "uq_distribution_reverses"),
    ):
        ix = _index(model, name)
        assert ix.unique
        assert [c.name for c in ix.columns] == ["reverses_id"]


def test_migration_head_and_chain() -> None:
    root = pathlib.Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_current_head() == "0046_run_scope_portfolio"  # API-1b
    assert script.get_revision("0044_private_capital").down_revision == "0043_es_backtest"


# --- the ORM append-only guards (the DB trigger halves live in the PG suite) ---


def _minimal_call(session: Session) -> CapitalCall:
    row = CapitalCall(
        tenant_id=str(uuid.uuid4()),
        portfolio_id=None,  # replaced below; FKs unenforced default-off on SQLite
        instrument_id=None,
        commitment_version_id=str(uuid.uuid4()),
        event_date=date(2026, 3, 2),
        amount=Decimal("1000000.000000"),
        currency_code="USD",
        call_type="DRAWDOWN",
    )
    # SQLite in these unit tests doesn't enforce FKs; the service layer (steps 4-5)
    # resolves them fail-closed — here we only exercise the ORM guard mechanics.
    row.portfolio_id = str(uuid.uuid4())
    row.instrument_id = str(uuid.uuid4())
    session.add(row)
    session.flush()
    return row


def test_orm_guard_blocks_update(session: Session) -> None:
    row = _minimal_call(session)
    row.amount = Decimal("2.000000")
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_orm_guard_blocks_delete(session: Session) -> None:
    row = _minimal_call(session)
    session.delete(row)
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_distribution_orm_guard_blocks_update(session: Session) -> None:
    row = Distribution(
        tenant_id=str(uuid.uuid4()),
        portfolio_id=str(uuid.uuid4()),
        instrument_id=str(uuid.uuid4()),
        commitment_version_id=str(uuid.uuid4()),
        event_date=date(2026, 3, 2),
        amount=Decimal("500000.000000"),
        currency_code="USD",
        distribution_type="INCOME",
    )
    session.add(row)
    session.flush()
    row.is_recallable = True
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


# --- step 4: the commitment service (five-op FR set; chain rules; rails) ---

from sqlalchemy import func, select  # noqa: E402

from irp_shared.audit.models import AuditEvent  # noqa: E402
from irp_shared.audit.service import verify_chain  # noqa: E402
from irp_shared.db.mixins import utcnow  # noqa: E402
from irp_shared.lineage.service import assert_has_lineage  # noqa: E402
from irp_shared.portfolio import PortfolioActor, create_portfolio  # noqa: E402
from irp_shared.private_capital.commitment_service import (  # noqa: E402
    CommitmentActor,
    CommitmentValueError,
    NoCurrentCommitment,
    capture_commitment,
    correct_commitment,
    current_commitment,
    list_commitments,
    reconstruct_commitment_as_of,
    supersede_commitment,
)
from irp_shared.reference.instrument import create_instrument  # noqa: E402
from irp_shared.reference.service import ReferenceActor  # noqa: E402

_ACT = CommitmentActor(actor_id="steward")


def _tenant() -> str:
    return str(uuid.uuid4())


def _seed_pf_fund(session: Session, tenant: str, suffix: str = "") -> tuple[str, str]:
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"PF{suffix}",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    fund = create_instrument(
        session,
        tenant_id=tenant,
        code=f"FUND{suffix}",
        name="Fund",
        asset_class="PRIVATE_EQUITY",
        actor=ReferenceActor(actor_id="steward"),
    )
    return pf.id, fund.id


def _capture(session: Session, tenant: str, pf: str, fund: str, **kw):  # noqa: ANN003, ANN202
    base = dict(
        committed_amount=Decimal("25000000.000000"),
        currency_code="USD",
        commitment_date=date(2026, 1, 15),
    )
    base.update(kw)
    return capture_commitment(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        acting_tenant=tenant,
        actor=_ACT,
        **base,
    )


def _event_count(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def test_capture_rails(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    row = _capture(session, tenant, pf, fund)
    assert row.record_version == 1 and row.valid_to is None and row.system_to is None
    assert_has_lineage(session, "commitment", row.id, tenant_id=tenant)
    assert _event_count(session, "PRIVATE.COMMITMENT_CREATE") == 1
    assert verify_chain(session, tenant).ok is True


def test_capture_validators(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    for bad_amount in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(CommitmentValueError):
            _capture(session, tenant, pf, fund, committed_amount=bad_amount)
    for bad_ccy in ("usd", "US", "USDX", "U1D"):
        with pytest.raises(CommitmentValueError):
            _capture(session, tenant, pf, fund, currency_code=bad_ccy)
    # The post-quantize envelope (the numeric-finder fold): a sub-quantum amount would
    # quantize to a PERMANENT zero row past a raw >0 check; an oversized finite one would
    # detonate at bind as an unmapped 500. Both refuse fail-closed now.
    for bad_amount in (Decimal("0.0000004"), Decimal("1E+25"), Decimal("1E+15")):
        with pytest.raises(CommitmentValueError):
            _capture(session, tenant, pf, fund, committed_amount=bad_amount)
    # One micro-unit and the (20,6) ceiling both remain capturable.
    _capture(session, tenant, pf, fund, committed_amount=Decimal("0.000001"))


def test_capture_cross_tenant_targets_fail_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    a_pf, a_fund = _seed_pf_fund(session, a, "A")
    b_pf, b_fund = _seed_pf_fund(session, b, "B")
    with pytest.raises(CommitmentValueError):
        _capture(session, a, b_pf, a_fund)
    with pytest.raises(CommitmentValueError):
        _capture(session, a, a_pf, b_fund)


def test_supersede_close_first_and_chain(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    v1 = _capture(session, tenant, pf, fund)
    eff = v1.valid_from + timedelta(days=30)
    v2 = supersede_commitment(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        committed_amount=Decimal("35000000.000000"),
        currency_code="USD",
        commitment_date=date(2026, 1, 15),
        acting_tenant=tenant,
        actor=_ACT,
        effective_at=eff,
    )
    assert v1.valid_to == eff and v2.supersedes_id == v1.id and v2.record_version == 2
    # The per-op event grain pinned (the taxonomy row's claim): supersede = UPDATE close-out
    # + CREATE, so counts are now CREATE=2 (capture + the new version) and UPDATE=1.
    assert _event_count(session, "PRIVATE.COMMITMENT_CREATE") == 2
    assert _event_count(session, "PRIVATE.COMMITMENT_UPDATE") == 1
    assert (
        current_commitment(session, acting_tenant=tenant, portfolio_id=pf, instrument_id=fund).id
        == v2.id
    )
    # Supersede below Σ-calls is permitted by design (no economics here) — and the
    # window-coherence guard refuses an inverting effective_at.
    with pytest.raises(CommitmentValueError):
        supersede_commitment(
            session,
            portfolio_id=pf,
            instrument_id=fund,
            committed_amount=Decimal("1.000000"),
            currency_code="USD",
            commitment_date=date(2026, 1, 15),
            acting_tenant=tenant,
            actor=_ACT,
            effective_at=v1.valid_from,  # <= the new head's valid_from -> refused
        )


def test_currency_chain_immutable_on_supersede(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    v1 = _capture(session, tenant, pf, fund)
    with pytest.raises(CommitmentValueError, match="chain-immutable"):
        supersede_commitment(
            session,
            portfolio_id=pf,
            instrument_id=fund,
            committed_amount=Decimal("30000000.000000"),
            currency_code="EUR",
            commitment_date=date(2026, 1, 15),
            acting_tenant=tenant,
            actor=_ACT,
            effective_at=v1.valid_from + timedelta(days=1),
        )


def test_correct_symmetric_payload_and_action(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    v1 = _capture(session, tenant, pf, fund)
    corrected = correct_commitment(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        committed_amount=Decimal("26000000.000000"),
        restatement_reason="typo in the signed amount",
        acting_tenant=tenant,
        actor=_ACT,
    )
    assert corrected.valid_from == v1.valid_from  # same valid window
    assert corrected.currency_code == v1.currency_code  # no re-denomination path exists
    # The per-op grain pinned: correct = UPDATE close-out + CORRECTION.
    assert _event_count(session, "PRIVATE.COMMITMENT_UPDATE") == 1
    assert _event_count(session, "PRIVATE.COMMITMENT_CORRECTION") == 1
    ev = session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "PRIVATE.COMMITMENT_CORRECTION")
    ).scalar_one()
    # The two PA-0 review-fold lessons, pinned: action="correct" + symmetric old->new.
    assert ev.action == "correct"
    assert ev.before_value["committed_amount"] == "25000000.000000"
    assert ev.after_value["committed_amount"] == "26000000.000000"
    with pytest.raises(CommitmentValueError):
        correct_commitment(
            session,
            portfolio_id=pf,
            instrument_id=fund,
            committed_amount=Decimal("1.000000"),
            restatement_reason="",
            acting_tenant=tenant,
            actor=_ACT,
        )


def test_no_current_head_refused(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    with pytest.raises(NoCurrentCommitment):
        supersede_commitment(
            session,
            portfolio_id=pf,
            instrument_id=fund,
            committed_amount=Decimal("1.000000"),
            currency_code="USD",
            commitment_date=date(2026, 1, 15),
            acting_tenant=tenant,
            actor=_ACT,
            effective_at=utcnow(),
        )


def test_reconstruct_both_axes(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    v1 = _capture(session, tenant, pf, fund)
    correct_commitment(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        committed_amount=Decimal("26000000.000000"),
        restatement_reason="restated",
        acting_tenant=tenant,
        actor=_ACT,
    )
    # As known BEFORE the correction: the original value; after: the corrected one.
    old = reconstruct_commitment_as_of(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        valid_at=v1.valid_from + timedelta(seconds=1),
        known_at=v1.system_from + timedelta(microseconds=1),
        acting_tenant=tenant,
    )
    assert old is not None and old.committed_amount == Decimal("25000000.000000")
    new = reconstruct_commitment_as_of(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        valid_at=v1.valid_from + timedelta(seconds=1),
        known_at=utcnow(),
        acting_tenant=tenant,
    )
    assert new is not None and new.committed_amount == Decimal("26000000.000000")


def test_list_filters_rule7(session: Session) -> None:
    tenant = _tenant()
    pf1, fund1 = _seed_pf_fund(session, tenant, "1")
    pf2, fund2 = _seed_pf_fund(session, tenant, "2")
    _capture(session, tenant, pf1, fund1)
    _capture(session, tenant, pf1, fund2)
    _capture(session, tenant, pf2, fund2)
    assert len(list_commitments(session, acting_tenant=tenant)) == 3
    assert len(list_commitments(session, acting_tenant=tenant, portfolio_id=pf1)) == 2
    assert len(list_commitments(session, acting_tenant=tenant, instrument_id=fund2)) == 2
    assert (
        len(list_commitments(session, acting_tenant=tenant, portfolio_id=pf2, instrument_id=fund2))
        == 1
    )
    assert list_commitments(session, acting_tenant=_tenant()) == []


# --- step 5: the capital-flow services (capture; negation reversal; fences; lists) ---

from irp_shared.private_capital.capital_flow_service import (  # noqa: E402
    CapitalFlowActor,
    CapitalFlowNotVisible,
    CapitalFlowValueError,
    capture_capital_call,
    capture_distribution,
    list_capital_calls,
    list_distributions,
    reverse_capital_call,
    reverse_distribution,
)

_FLOW_ACT = CapitalFlowActor(actor_id="steward")


def _call(session: Session, tenant: str, pf: str, fund: str, **kw):  # noqa: ANN003, ANN202
    base = dict(
        event_date=date(2026, 2, 10),
        amount=Decimal("5000000.000000"),
        currency_code="USD",
        call_type="DRAWDOWN",
    )
    base.update(kw)
    return capture_capital_call(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        acting_tenant=tenant,
        actor=_FLOW_ACT,
        **base,
    )


def _dist(session: Session, tenant: str, pf: str, fund: str, **kw):  # noqa: ANN003, ANN202
    base = dict(
        event_date=date(2026, 5, 20),
        amount=Decimal("1500000.000000"),
        currency_code="USD",
        distribution_type="RETURN_OF_CAPITAL",
    )
    base.update(kw)
    return capture_distribution(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        acting_tenant=tenant,
        actor=_FLOW_ACT,
        **base,
    )


def test_call_requires_current_commitment(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    with pytest.raises(NoCurrentCommitment):
        _call(session, tenant, pf, fund)


def test_call_capture_rails_and_provenance(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    v1 = _capture(session, tenant, pf, fund)
    row = _call(session, tenant, pf, fund)
    assert row.commitment_version_id == v1.id  # provenance echo = the version current NOW
    assert row.reverses_id is None
    assert_has_lineage(session, "capital_call", row.id, tenant_id=tenant)
    assert _event_count(session, "PRIVATE.CAPITAL_CALL_CREATE") == 1
    assert verify_chain(session, tenant).ok is True
    # After a supersede, a new event echoes the NEW version id — the pair identity is the key.
    v2 = supersede_commitment(
        session,
        portfolio_id=pf,
        instrument_id=fund,
        committed_amount=Decimal("30000000.000000"),
        currency_code="USD",
        commitment_date=date(2026, 1, 15),
        acting_tenant=tenant,
        actor=_ACT,
        effective_at=v1.valid_from + timedelta(days=5),
    )
    row2 = _call(session, tenant, pf, fund, event_date=date(2026, 3, 10))
    assert row2.commitment_version_id == v2.id
    assert row2.portfolio_id == row.portfolio_id and row2.instrument_id == row.instrument_id


def test_event_validators(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    _capture(session, tenant, pf, fund)
    with pytest.raises(CapitalFlowValueError):
        _call(session, tenant, pf, fund, amount=Decimal("-5"))
    with pytest.raises(CapitalFlowValueError):
        _call(session, tenant, pf, fund, amount=Decimal("NaN"))
    for bad in (Decimal("0.0000004"), Decimal("1E+25")):  # the post-quantize envelope fold
        with pytest.raises(CapitalFlowValueError):
            _call(session, tenant, pf, fund, amount=bad)
    with pytest.raises(CapitalFlowValueError):
        _call(session, tenant, pf, fund, currency_code="EUR")  # commitment is USD
    with pytest.raises(CapitalFlowValueError):
        _call(session, tenant, pf, fund, call_type="BOGUS")
    with pytest.raises(CapitalFlowValueError):
        _dist(session, tenant, pf, fund, distribution_type="BOGUS")


def test_reversal_negation_sum_self_corrects(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    _capture(session, tenant, pf, fund)
    wrong = _call(session, tenant, pf, fund, amount=Decimal("9000000.000000"))
    rev = reverse_capital_call(
        session,
        capital_call_id=wrong.id,
        acting_tenant=tenant,
        actor=_FLOW_ACT,
        reason="mis-captured amount",
    )
    right = _call(session, tenant, pf, fund, amount=Decimal("5000000.000000"))
    # The negation convention: byte-equal echo except the sign; Σ self-corrects.
    assert rev.amount == Decimal("-9000000.000000")
    assert rev.call_type == wrong.call_type and rev.event_date == wrong.event_date
    assert rev.currency_code == wrong.currency_code and rev.reverses_id == wrong.id
    rows = list_capital_calls(session, acting_tenant=tenant, portfolio_id=pf, instrument_id=fund)
    assert sum(r.amount for r in rows) == Decimal("5000000.000000")
    assert _event_count(session, "PRIVATE.CAPITAL_CALL_REVERSE") == 1
    assert right.reverses_id is None


def test_reversal_fences(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    _capture(session, tenant, pf, fund)
    call = _call(session, tenant, pf, fund)
    rev = reverse_capital_call(
        session, capital_call_id=call.id, acting_tenant=tenant, actor=_FLOW_ACT, reason="e"
    )
    with pytest.raises(CapitalFlowValueError, match="already reversed"):
        reverse_capital_call(
            session, capital_call_id=call.id, acting_tenant=tenant, actor=_FLOW_ACT, reason="e"
        )
    with pytest.raises(CapitalFlowValueError, match="cannot be reversed"):
        reverse_capital_call(
            session, capital_call_id=rev.id, acting_tenant=tenant, actor=_FLOW_ACT, reason="e"
        )
    with pytest.raises(CapitalFlowValueError):
        reverse_capital_call(
            session, capital_call_id=call.id, acting_tenant=tenant, actor=_FLOW_ACT, reason=""
        )
    with pytest.raises(CapitalFlowNotVisible):
        reverse_capital_call(
            session,
            capital_call_id=call.id,
            acting_tenant=_tenant(),  # foreign tenant
            actor=_FLOW_ACT,
            reason="e",
        )


def test_distribution_recallable_and_reversal_echo(session: Session) -> None:
    tenant = _tenant()
    pf, fund = _seed_pf_fund(session, tenant)
    _capture(session, tenant, pf, fund)
    d = _dist(session, tenant, pf, fund, is_recallable=True)
    assert d.is_recallable is True
    rev = reverse_distribution(
        session, distribution_id=d.id, acting_tenant=tenant, actor=_FLOW_ACT, reason="err"
    )
    assert rev.amount == -d.amount and rev.is_recallable is True
    assert rev.distribution_type == d.distribution_type
    assert _event_count(session, "PRIVATE.DISTRIBUTION_REVERSE") == 1
    assert verify_chain(session, tenant).ok is True


def test_event_list_filters_rule7(session: Session) -> None:
    tenant = _tenant()
    pf1, fund1 = _seed_pf_fund(session, tenant, "1")
    pf2, fund2 = _seed_pf_fund(session, tenant, "2")
    _capture(session, tenant, pf1, fund1)
    _capture(session, tenant, pf2, fund2)
    _call(session, tenant, pf1, fund1)
    _call(session, tenant, pf1, fund1, event_date=date(2026, 3, 10))
    _call(session, tenant, pf2, fund2)
    _dist(session, tenant, pf1, fund1)
    assert len(list_capital_calls(session, acting_tenant=tenant)) == 3
    assert len(list_capital_calls(session, acting_tenant=tenant, portfolio_id=pf1)) == 2
    assert len(list_capital_calls(session, acting_tenant=tenant, instrument_id=fund2)) == 1
    assert len(list_distributions(session, acting_tenant=tenant, portfolio_id=pf1)) == 1
    assert list_capital_calls(session, acting_tenant=_tenant()) == []
