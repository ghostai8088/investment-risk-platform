"""SQLite-local unit/behavior tests for P1C-2 transaction (REQ-PPM-003 transaction half, IA).

RLS is a no-op on SQLite, so symmetric-isolation + the P0001 DB trigger live in the PG file; here we
prove the IA contract (ImmutableAppendOnlyMixin; ORM append-only guard), the governed-write contract
(TRANSACTION.RECORD + MANUAL ORIGIN lineage), the reversal-as-new-record convention (original
unchanged; exactly two rows; reversal linked + emits TRANSACTION.REVERSE), the tenant-filtered
cross-tenant fail-closed (portfolio / instrument / reversal target — MUST hold on SQLite too),
external_ref idempotency, fail-closed audit rollback, the import direction, and the scope fence.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.audit.models import AppendOnlyViolation, AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.lineage.service import assert_has_lineage
from irp_shared.portfolio import PortfolioActor, PortfolioNotVisible, create_portfolio
from irp_shared.reference.instrument import InstrumentNotVisible, create_instrument
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass
from irp_shared.transaction import (
    Transaction,
    TransactionActor,
    TransactionNotVisible,
    record_transaction,
    resolve_transaction,
    reverse_transaction,
)


def _tenant() -> str:
    return str(uuid.uuid4())


def _actor() -> TransactionActor:
    return TransactionActor(actor_id="recorder")


def _events(session: Session, event_type: str) -> int:
    return session.execute(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == event_type)
    ).scalar_one()


def _seed_pf_inst(session: Session, tenant: str, suffix: str = "") -> tuple[str, str]:
    """Create a portfolio + instrument (the FK targets a transaction needs) in ``tenant``."""
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code=f"PF{suffix}",
        name="pf",
        node_type="ACCOUNT",
        actor=PortfolioActor(actor_id="steward"),
    )
    inst = create_instrument(
        session,
        tenant_id=tenant,
        code=f"INST{suffix}",
        name="i",
        asset_class="BOND",
        actor=ReferenceActor(actor_id="steward"),
    )
    return pf.id, inst.id


def _record(session: Session, tenant: str, pf_id: str, inst_id: str, **kw) -> Transaction:  # noqa: ANN003
    base = dict(txn_type="BUY", trade_date=date(2026, 3, 1), quantity=Decimal("100"))
    base.update(kw)
    return record_transaction(
        session,
        tenant_id=tenant,
        portfolio_id=pf_id,
        instrument_id=inst_id,
        actor=_actor(),
        **base,
    )


# --- temporal class: IA append-only; no EV/FR axis; no record_version/status ---


def test_transaction_is_ia_append_only() -> None:
    assert Transaction.__temporal_class__ == TemporalClass.IMMUTABLE_APPEND_ONLY
    assert hasattr(Transaction, "system_from")
    for attr in ("valid_from", "valid_to", "system_to", "record_version", "status", "is_active"):
        assert not hasattr(Transaction, attr), f"transaction must not have {attr}"


def test_transaction_holds_nothing_scope_fence() -> None:
    cols = set(Transaction.__table__.columns.keys())
    forbidden = {"position", "valuation", "holding", "market_value", "exposure", "nav", "net_qty"}
    assert not (forbidden & cols), f"transaction leaks domain columns: {forbidden & cols}"


# --- governed-write contract: lineage + audit ---


def test_record_lineage_and_audit(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    txn = _record(session, tenant, pf_id, inst_id)
    edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == txn.id)
    ).scalar_one()
    assert edge.target_entity_type == "transaction" and edge.edge_kind == "ORIGIN"
    source = session.get(DataSource, edge.source_id)
    assert source is not None and source.source_type == "MANUAL"
    assert_has_lineage(session, "transaction", txn.id, tenant_id=tenant)
    ev = session.execute(select(AuditEvent).where(AuditEvent.entity_id == txn.id)).scalar_one()
    assert ev.event_type == "TRANSACTION.RECORD" and ev.entity_type == "transaction"
    assert ev.action == "record"
    assert verify_chain(session, tenant).ok is True


# --- IA immutability via the ORM guard (the P0001 DB trigger is proven in the PG file) ---


def test_orm_guard_blocks_update(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    txn = _record(session, tenant, pf_id, inst_id)
    session.commit()
    txn.description = "tampered"
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_orm_guard_blocks_delete(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    txn = _record(session, tenant, pf_id, inst_id)
    session.commit()
    with pytest.raises(AppendOnlyViolation):
        session.delete(txn)
        session.flush()
    session.rollback()


# --- reversal: a NEW record; original NEVER mutated ---


def test_reversal_appends_new_record_original_unchanged(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    original = _record(
        session, tenant, pf_id, inst_id, quantity=Decimal("100"), gross_amount=Decimal("1000")
    )
    orig_id = original.id
    orig_system_from = original.system_from
    session.commit()

    reversal = reverse_transaction(session, original, actor=_actor(), reason="booked in error")
    session.commit()

    # reversal is a NEW row linking to the original, with negated economics + REVERSAL type.
    assert reversal.id != orig_id
    assert reversal.reverses_transaction_id == orig_id
    assert reversal.txn_type == "REVERSAL"
    assert reversal.quantity == Decimal("-100")
    assert reversal.gross_amount == Decimal("-1000")
    assert _events(session, "TRANSACTION.REVERSE") == 1
    # the reversal is a NEW record -> it roots its OWN MANUAL-source ORIGIN lineage edge.
    rev_edge = session.execute(
        select(LineageEdge).where(LineageEdge.target_entity_id == reversal.id)
    ).scalar_one()
    assert rev_edge.target_entity_type == "transaction" and rev_edge.edge_kind == "ORIGIN"
    assert session.get(DataSource, rev_edge.source_id).source_type == "MANUAL"
    assert_has_lineage(session, "transaction", reversal.id, tenant_id=tenant)

    # the ORIGINAL is byte-for-byte unchanged (refresh from the DB).
    session.expire_all()
    refreshed = session.get(Transaction, orig_id)
    assert refreshed is not None
    assert refreshed.quantity == Decimal("100") and refreshed.gross_amount == Decimal("1000")
    assert refreshed.txn_type == "BUY" and refreshed.reverses_transaction_id is None
    # system_from unchanged (compare naive — SQLite drops tzinfo on round-trip; the value is
    # identical).
    assert refreshed.system_from.replace(tzinfo=None) == orig_system_from.replace(tzinfo=None)
    # exactly two rows for the pair.
    assert session.execute(select(func.count()).select_from(Transaction)).scalar_one() == 2
    assert reversal.id != orig_id


# --- cross-tenant references fail closed at the service layer (MUST hold on SQLite too) ---


def test_cross_tenant_portfolio_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    b_pf, _b_inst = _seed_pf_inst(session, b, "_B")
    a_pf, a_inst = _seed_pf_inst(session, a, "_A")
    session.commit()
    with pytest.raises(PortfolioNotVisible):
        _record(session, a, b_pf, a_inst)  # tenant a referencing tenant b's portfolio
    session.rollback()


def test_cross_tenant_instrument_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    _b_pf, b_inst = _seed_pf_inst(session, b, "_B")
    a_pf, a_inst = _seed_pf_inst(session, a, "_A")
    session.commit()
    with pytest.raises(InstrumentNotVisible):
        _record(session, a, a_pf, b_inst)  # tenant a referencing tenant b's instrument
    session.rollback()


def test_cross_tenant_reversal_target_fails_closed(session: Session) -> None:
    a, b = _tenant(), _tenant()
    b_pf, b_inst = _seed_pf_inst(session, b, "_B")
    b_txn = _record(session, b, b_pf, b_inst)
    session.commit()
    with pytest.raises(TransactionNotVisible):
        resolve_transaction(session, b_txn.id, acting_tenant=a)  # a cannot see b's transaction


# --- idempotency: partial-unique external_ref per tenant ---


def test_external_ref_idempotency(session: Session) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _record(session, tenant, pf_id, inst_id, external_ref="EXT-1")
    session.commit()
    with pytest.raises(IntegrityError):
        _record(session, tenant, pf_id, inst_id, external_ref="EXT-1")  # dup external_ref rejected
    session.rollback()
    # two records with NO external_ref coexist (NULLs distinct).
    _record(session, tenant, pf_id, inst_id, external_ref=None)
    _record(session, tenant, pf_id, inst_id, external_ref=None)
    session.commit()


# --- fail-closed audit rollback (CTRL-032) ---


def _raise_audit(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
    raise RuntimeError("audit boom")


def test_record_rolls_back_no_orphan(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    session.commit()  # seed committed
    import irp_shared.transaction.service as svc

    monkeypatch.setattr(svc, "record_event", _raise_audit)
    with pytest.raises(RuntimeError):
        _record(session, tenant, pf_id, inst_id)
    session.rollback()
    # the whole transaction-record unit (row + its ORIGIN edge + audit) rolled back — no orphan txn.
    assert session.execute(select(func.count()).select_from(Transaction)).scalar_one() == 0
    assert _events(session, "TRANSACTION.RECORD") == 0


# --- scope fence: a transaction creates no position/valuation (no derivation) ---


def test_record_creates_no_position_or_valuation(session: Session) -> None:
    from irp_shared.models import metadata
    from irp_shared.position.models import Position

    # Still-future (P2-4+) tables must NOT exist (P2-1/2/3 build dataset_snapshot/fx_rate/
    # exposure_aggregate, but a transaction never derives position/valuation/exposure — captured-
    # not-derived, OD-P1C-E).
    for table in ("price_point", "yield_curve"):
        assert table not in metadata.tables
    tenant = _tenant()
    pf_id, inst_id = _seed_pf_inst(session, tenant)
    _record(session, tenant, pf_id, inst_id)
    # the only domain rows are the transaction + its FK targets; NO position is derived from it.
    assert session.execute(select(func.count()).select_from(Transaction)).scalar_one() == 1
    assert session.execute(select(func.count()).select_from(Position)).scalar_one() == 0


# --- import direction: transaction imports only portfolio/reference/rails (one-way) ---


def test_transaction_import_direction() -> None:
    import irp_shared.transaction as pkg

    forbidden = (
        "irp_backend",
        "irp_shared.models",  # the plural aggregator (cycle vector)
        "irp_shared.position",
        "irp_shared.valuation",
        "irp_shared.risk",
        "irp_shared.reporting",
        "irp_shared.market_data",
        "irp_shared.calc",
    )
    allowed_subpackages = {
        "lineage",
        "audit",
        "db",
        "temporal",
        "portfolio",
        "reference",
        "transaction",
    }
    pkg_dir = pathlib.Path(pkg.__file__).parent
    for py in sorted(pkg_dir.glob("*.py")):
        for line in py.read_text().splitlines():
            stripped = line.strip()
            mods: list[str] = []
            if stripped.startswith("from "):
                base = stripped.split()[1]
                mods.append(base)
                if " import " in stripped:
                    for name in stripped.split(" import ", 1)[1].replace("(", "").split(","):
                        token = name.strip().split(" as ")[0].strip()
                        if token and token != "*":
                            mods.append(f"{base}.{token}")
            elif stripped.startswith("import "):
                mods.append(stripped.split()[1].split(",")[0])
            else:
                continue
            for mod in mods:
                for root in forbidden:
                    assert mod != root and not mod.startswith(
                        root + "."
                    ), f"{py.name} imports forbidden {mod}"
                if mod.startswith("irp_shared."):
                    segments = mod.split(".")
                    assert (
                        segments[1] in allowed_subpackages
                    ), f"{py.name} imports non-allowlisted {mod} (irp_shared.{segments[1]})"
