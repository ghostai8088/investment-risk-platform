"""SQLite-local unit/behavior tests for DATA-1 benchmark_rate (ENT-070, captured PUBLISHED rates).

RLS + cross-tenant negatives live in the PG suite; here we prove: the TB3MS dataset census
(exact 30-key set + anchors + units band + negative pins — the hand-encoded literals are the
dataset, so the census IS the acceptance, CTRL-034 item 8); the FR single-row protocol on the
rate table; the vocab/coherence guards INCLUDING the reserved-basis branch (monkeypatched so the
coherence refusal is executed, not presumed — the vacuous-guard lesson); and the
``refresh_benchmark_rates`` semantics ratified at OQ-DATA-1-6: add-only, first-spec-wins,
differing-value refusal, forward-only horizon, horizon-may-not-outrun-the-data, ONE series per
head, effective-only completeness firing, idempotent-silent no-op, and the SAVEPOINT negative
control (a completeness FAIL persists its FAIL evidence while the batch — rows, horizon, head
event — is fully unwound).

Fixture realism (TD-1): rates are 2024–2026 T-bill fractions (0.03..0.055); out-of-band values
live ONLY in guard tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from irp_shared.audit.models import AuditEvent
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.dq.service import DataQualityError
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.marketdata import (
    COMPLETENESS_RULE_CODE,
    MARKET_BENCHMARK_RATE_CORRECTION_EVENT,
    MARKET_BENCHMARK_RATE_CREATE_EVENT,
    MARKET_BENCHMARK_RATE_UPDATE_EVENT,
    BenchmarkActor,
    BenchmarkRate,
    BenchmarkSeriesValueError,
    capture_benchmark,
    capture_benchmark_rate,
    correct_benchmark_rate,
    list_benchmark_rates,
    reconstruct_benchmark_rate_as_of,
    refresh_benchmark_rates,
    resolve_benchmark,
    supersede_benchmark_rate,
)
from irp_shared.marketdata import benchmark_rates as br_mod
from irp_shared.marketdata.models import (
    OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
    QUOTE_BASIS_DISCOUNT_360,
    RATE_TYPE_BILL_DISCOUNT_YIELD,
)
from irp_shared.marketdata.tb3ms_rates import (
    TB3MS_COMPLETE_THROUGH,
    TB3MS_RATES,
    TB3MS_SERIES_START,
)
from irp_shared.models import Base
from irp_shared.reference.events import REFERENCE_UPDATE_EVENT
from irp_shared.reference.models import Currency

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VA = datetime(2026, 6, 1, tzinfo=UTC)
KNOWN = datetime(2030, 1, 1, tzinfo=UTC)
ACTOR = BenchmarkActor(actor_id="steward")
RD = date(2026, 6, 1)  # the last published TB3MS observation date

_SERIES_KW = dict(
    rate_type=RATE_TYPE_BILL_DISCOUNT_YIELD,
    quote_basis=QUOTE_BASIS_DISCOUNT_360,
    observation_convention=OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
)


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


def _ccy(db: Session) -> None:
    db.add(Currency(tenant_id=SYSTEM_TENANT_ID, code="USD", name="USD", valid_from=T0))
    db.flush()


def _benchmark(db: Session, tenant: str, code: str = "US-TBILL-3M"):  # noqa: ANN202
    bm = capture_benchmark(
        db,
        benchmark_code=code,
        benchmark_source="US-FRB-H15",
        benchmark_currency="USD",
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
    )
    db.flush()
    return resolve_benchmark(db, bm.id, acting_tenant=tenant)


def _events(db: Session, event_type: str) -> int:
    return db.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _refresh(db: Session, bm, tenant: str, **overrides):  # noqa: ANN202, ANN003
    kwargs = dict(
        rates=dict(TB3MS_RATES),
        series_start=TB3MS_SERIES_START,
        acting_tenant=tenant,
        actor=ACTOR,
        complete_through=TB3MS_COMPLETE_THROUGH,
        **_SERIES_KW,
    )
    kwargs.update(overrides)
    return refresh_benchmark_rates(db, bm, **kwargs)


# ---------- the TB3MS dataset census (CTRL-034 Execution 2 item 8) ----------


def test_the_tb3ms_dataset_census() -> None:
    """Exact set-equality + anchors + units band + negative pins over the hand-encoded literals."""
    dates = [d for d, _ in TB3MS_RATES]
    values = [v for _, v in TB3MS_RATES]
    # exactly 30 observations, unique, ascending, each dated the FIRST of its month
    assert len(TB3MS_RATES) == 30 and len(set(dates)) == 30
    assert dates == sorted(dates)
    assert all(d.day == 1 for d in dates)
    # the exact month set: every month 2024-01..2026-06, none besides
    expected = set()
    year, month = 2024, 1
    while (year, month) <= (2026, 6):
        expected.add(date(year, month, 1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    assert set(dates) == expected
    # POSITIVE anchors: the published endpoints (5.22% and 3.66% as fractions)
    assert TB3MS_RATES[0] == (date(2024, 1, 1), Decimal("0.0522"))
    assert TB3MS_RATES[-1] == (date(2026, 6, 1), Decimal("0.0366"))
    # units: FRACTIONS, never percent (a 5.22 literal would be a percent-scale transcription slip)
    assert all(Decimal("0.03") < v < Decimal("0.055") for v in values)
    # the easing path: the 2024 average sits above the 2026 average
    assert values[0] > values[-1]
    # NEGATIVE pins: 2026-07 UNPUBLISHED at encoding; the horizon ends at the last published month
    assert date(2026, 7, 1) not in set(dates)
    assert TB3MS_COMPLETE_THROUGH == date(2026, 6, 30)
    assert TB3MS_SERIES_START == date(2024, 1, 1)


# ---------- vocab / coherence guards ----------


def test_vocab_refusals(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    bad = dict(_SERIES_KW)
    for field, value in (
        ("rate_type", "SOFR"),
        ("quote_basis", "ACT_365"),
        ("observation_convention", "MONTH_END_SAMPLED"),
    ):
        kwargs = dict(bad, **{field: value})
        with pytest.raises(BenchmarkSeriesValueError):
            capture_benchmark_rate(
                session,
                bm,
                rate_date=RD,
                rate_value=Decimal("0.0366"),
                acting_tenant=tenant,
                actor=ACTOR,
                **kwargs,
            )


def test_coherence_map_fires_when_the_reserved_basis_activates(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rate_type→basis coherence refusal EXECUTED (not presumed): with INVESTMENT_365 minted
    into the vocab, a BILL_DISCOUNT_YIELD × INVESTMENT_365 capture still refuses (the map, not the
    vocab, is the guard)."""
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    monkeypatch.setattr(
        br_mod, "BENCHMARK_RATE_QUOTE_BASES", (QUOTE_BASIS_DISCOUNT_360, "INVESTMENT_365")
    )
    with pytest.raises(BenchmarkSeriesValueError, match="incoherent"):
        capture_benchmark_rate(
            session,
            bm,
            rate_date=RD,
            rate_type=RATE_TYPE_BILL_DISCOUNT_YIELD,
            quote_basis="INVESTMENT_365",
            observation_convention=OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
            rate_value=Decimal("0.0381"),
            acting_tenant=tenant,
            actor=ACTOR,
        )


def test_finiteness_guard(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    for bad in (Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(BenchmarkSeriesValueError):
            capture_benchmark_rate(
                session,
                bm,
                rate_date=RD,
                rate_value=bad,
                acting_tenant=tenant,
                actor=ACTOR,
                **_SERIES_KW,
            )


# ---------- the FR single-row protocol ----------


def test_capture_supersede_correct_reconstruct_round_trip(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    row = capture_benchmark_rate(
        session,
        bm,
        rate_date=RD,
        rate_value=Decimal("0.0366"),
        acting_tenant=tenant,
        actor=ACTOR,
        valid_from=T0,
        **_SERIES_KW,
    )
    assert row.record_version == 1 and _events(session, MARKET_BENCHMARK_RATE_CREATE_EVENT) == 1

    superseded = supersede_benchmark_rate(
        session,
        bm,
        rate_date=RD,
        rate_value=Decimal("0.0367"),
        acting_tenant=tenant,
        actor=ACTOR,
        effective_at=VA,
        **_SERIES_KW,
    )
    assert superseded.record_version == 2 and superseded.supersedes_id == row.id
    assert _events(session, MARKET_BENCHMARK_RATE_UPDATE_EVENT) == 1

    corrected = correct_benchmark_rate(
        session,
        bm,
        rate_date=RD,
        rate_value=Decimal("0.0368"),
        restatement_reason="H.15 historical correction",
        acting_tenant=tenant,
        actor=ACTOR,
        **_SERIES_KW,
    )
    assert corrected.record_version == 3
    assert _events(session, MARKET_BENCHMARK_RATE_CORRECTION_EVENT) == 1
    # prior content NEVER mutated — the superseded head kept its value; only system_to closed
    assert superseded.rate_value == Decimal("0.0367") and superseded.system_to is not None

    # bitemporal as-of: the ORIGINAL value as known before the correction
    as_known_before = reconstruct_benchmark_rate_as_of(
        session,
        acting_tenant=tenant,
        benchmark_id=bm.id,
        rate_date=RD,
        valid_at=VA,
        known_at=superseded.system_from,
        **_SERIES_KW,
    )
    assert as_known_before is not None and as_known_before.rate_value == Decimal("0.0367")
    current = reconstruct_benchmark_rate_as_of(
        session,
        acting_tenant=tenant,
        benchmark_id=bm.id,
        rate_date=RD,
        valid_at=VA,
        known_at=KNOWN,
        **_SERIES_KW,
    )
    assert current is not None and current.rate_value == Decimal("0.0368")


# ---------- refresh_benchmark_rates (OQ-DATA-1-6) ----------


def test_first_refresh_captures_the_full_series_and_passes_completeness(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    out = _refresh(session, bm, tenant)
    assert out == {
        "added": 30,
        "rates_complete_through": TB3MS_COMPLETE_THROUGH,
        "completeness_ran": True,
    }
    rows = list_benchmark_rates(session, acting_tenant=tenant, benchmark_id=bm.id)
    assert len(rows) == 30
    assert bm.rates_complete_through == TB3MS_COMPLETE_THROUGH
    # ONE head REFERENCE.UPDATE per effective refresh; 30 per-row CREATEs
    assert _events(session, REFERENCE_UPDATE_EVENT) == 1
    assert _events(session, MARKET_BENCHMARK_RATE_CREATE_EVENT) == 30
    # the persisted rule literally says what was expected (the REF-1 trigger)
    rule = session.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == tenant, DataQualityRule.code == COMPLETENESS_RULE_CODE
        )
    ).scalar_one()
    assert rule.params["expected"][0] == "2024-01" and rule.params["expected"][-1] == "2026-06"
    assert len(rule.params["expected"]) == 30
    result = session.execute(
        select(DataQualityResult).where(DataQualityResult.rule_id == rule.id)
    ).scalar_one()
    assert result.outcome == "PASS"


def test_idempotent_rerun_is_a_true_silent_noop(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    _refresh(session, bm, tenant)
    before = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    out = _refresh(session, bm, tenant)  # identical re-supply
    assert out == {
        "added": 0,
        "rates_complete_through": TB3MS_COMPLETE_THROUGH,
        "completeness_ran": False,
    }
    after = session.execute(select(func.count()).select_from(AuditEvent)).scalar_one()
    assert after == before  # nothing written, nothing emitted, no DQ leg


def test_add_only_extension_advances_horizon_and_reruns_completeness(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    _refresh(session, bm, tenant)
    july = dict(TB3MS_RATES) | {date(2026, 7, 1): Decimal("0.0371")}
    out = _refresh(session, bm, tenant, rates=july, complete_through=date(2026, 7, 31))
    assert out["added"] == 1 and out["completeness_ran"] is True
    rule = session.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == tenant, DataQualityRule.code == COMPLETENESS_RULE_CODE
        )
    ).scalar_one()
    assert len(rule.params["expected"]) == 31 and rule.params["expected"][-1] == "2026-07"
    assert rule.record_version == 2  # the params advance went through update_dq_rule


def test_intra_call_duplicates_dedupe_first_spec_wins(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    pairs = [(date(2024, 1, 1), Decimal("0.0522")), (date(2024, 1, 1), Decimal("0.0599"))]
    out = _refresh(
        session,
        bm,
        tenant,
        rates=pairs,
        series_start=date(2024, 1, 1),
        complete_through=date(2024, 1, 31),
    )
    assert out["added"] == 1
    rows = list_benchmark_rates(session, acting_tenant=tenant, benchmark_id=bm.id)
    assert rows[0].rate_value == Decimal("0.0522")  # the FIRST spec won


def test_differing_value_for_a_captured_date_refuses_naming_the_correct_verb(
    session: Session,
) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    _refresh(session, bm, tenant)
    revised = dict(TB3MS_RATES) | {date(2026, 6, 1): Decimal("0.0367")}
    with pytest.raises(BenchmarkSeriesValueError, match="correct_benchmark_rate"):
        _refresh(session, bm, tenant, rates=revised)


def test_horizon_is_forward_only(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    _refresh(session, bm, tenant)
    with pytest.raises(BenchmarkSeriesValueError, match="forward-only"):
        _refresh(session, bm, tenant, complete_through=date(2026, 5, 31))


def test_horizon_may_not_outrun_the_data(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    with pytest.raises(BenchmarkSeriesValueError, match="outrun"):
        _refresh(session, bm, tenant, complete_through=date(2026, 7, 31))


def test_horizon_before_series_start_refuses(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    with pytest.raises(BenchmarkSeriesValueError, match="precedes series_start"):
        _refresh(
            session,
            bm,
            tenant,
            rates={date(2024, 1, 1): Decimal("0.0522")},
            series_start=date(2024, 2, 1),
            complete_through=date(2024, 1, 31),
        )


def test_completeness_FAIL_unwinds_the_batch_but_keeps_the_FAIL_evidence(
    session: Session,
) -> None:
    """THE savepoint negative control (OQ-DATA-1-6): a gap ⇒ DataQualityError, ZERO rate rows,
    horizon unmoved, NO head event — and the FAIL data_quality_result PERSISTS."""
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    gappy = {d: v for d, v in TB3MS_RATES if d != date(2025, 3, 1)}  # one interior month missing
    with pytest.raises(DataQualityError):
        _refresh(session, bm, tenant, rates=gappy)
    assert list_benchmark_rates(session, acting_tenant=tenant, benchmark_id=bm.id) == []
    assert bm.rates_complete_through is None
    assert _events(session, REFERENCE_UPDATE_EVENT) == 0
    assert _events(session, MARKET_BENCHMARK_RATE_CREATE_EVENT) == 0
    rule = session.execute(
        select(DataQualityRule).where(
            DataQualityRule.tenant_id == tenant, DataQualityRule.code == COMPLETENESS_RULE_CODE
        )
    ).scalar_one()
    result = session.execute(
        select(DataQualityResult).where(DataQualityResult.rule_id == rule.id)
    ).scalar_one()
    assert result.outcome == "FAIL" and "2025-03" in (result.detail or "")


def test_one_series_per_head(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """The v1 coverage-grain refusal: a head carrying one (rate_type, quote_basis) series refuses
    a refresh under another pair (executed via the reserved basis, monkeypatch-minted)."""
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    monkeypatch.setattr(
        br_mod, "BENCHMARK_RATE_QUOTE_BASES", (QUOTE_BASIS_DISCOUNT_360, "INVESTMENT_365")
    )
    monkeypatch.setitem(
        br_mod.RATE_TYPE_ALLOWED_QUOTE_BASES,
        RATE_TYPE_BILL_DISCOUNT_YIELD,
        (QUOTE_BASIS_DISCOUNT_360, "INVESTMENT_365"),
    )
    capture_benchmark_rate(
        session,
        bm,
        rate_date=date(2024, 1, 1),
        rate_type=RATE_TYPE_BILL_DISCOUNT_YIELD,
        quote_basis="INVESTMENT_365",
        observation_convention=OBSERVATION_CONVENTION_MONTHLY_AVG_BUSINESS_DAYS,
        rate_value=Decimal("0.0538"),
        acting_tenant=tenant,
        actor=ACTOR,
    )
    with pytest.raises(BenchmarkSeriesValueError, match="one \\(rate_type, quote_basis\\)"):
        _refresh(session, bm, tenant)


def test_no_horizon_refresh_commits_data_without_completeness(session: Session) -> None:
    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    out = _refresh(
        session,
        bm,
        tenant,
        rates={date(2024, 1, 1): Decimal("0.0522")},
        complete_through=None,
    )
    assert out == {"added": 1, "rates_complete_through": None, "completeness_ran": False}
    assert len(list_benchmark_rates(session, acting_tenant=tenant, benchmark_id=bm.id)) == 1


# ---------- scope ----------


def test_captured_input_scope_no_run_no_model_no_pin(session: Session) -> None:
    """The rate series is a captured INPUT: a full refresh mints NO calculation_run, NO
    model_version, NO snapshot (the CLAUDE.md pattern invariant)."""
    from irp_shared.calc.models import CalculationRun
    from irp_shared.model.models import ModelVersion
    from irp_shared.snapshot.models import DatasetSnapshot

    tenant = str(uuid.uuid4())
    _ccy(session)
    bm = _benchmark(session, tenant)
    _refresh(session, bm, tenant)
    for table in (CalculationRun, ModelVersion, DatasetSnapshot):
        assert session.execute(select(func.count()).select_from(table)).scalar_one() == 0
    # and every captured row is the verbatim fraction from the literals module
    rows = list_benchmark_rates(session, acting_tenant=tenant, benchmark_id=bm.id)
    assert {(r.rate_date, r.rate_value) for r in rows} == set(TB3MS_RATES)
    assert all(isinstance(r, BenchmarkRate) for r in rows)
