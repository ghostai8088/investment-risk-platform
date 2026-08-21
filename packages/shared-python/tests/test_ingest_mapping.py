"""W19-S3a: the INGEST-1 mapping spine (REQ-INT-001) — SQLite-local unit/behavior tests.

RLS, the FORCE flags, the partial-unique index's PostgreSQL behaviour and the ``irp_ops`` privilege
floor live in ``test_ingest_mapping_pg.py``. Here we prove the vocabulary is genuinely closed, every
refusal FIRES, the lifecycle holds, and the acceptance clauses that are behavioural rather than
structural — (3) an edited mapping moves exactly the rows the edit touches, (8) the demonstrating
file exercises at least three operation kinds, (9) the load is reproducible from three named
inputs, and (10) an overlapping re-load refuses unless flagged a restatement.

**Every negative control here carries a positive control** (P18 clause 1): before "the refusal
fired" is evidence, something must prove the input that should trigger it actually arrived —
otherwise a refusal is indistinguishable from a harness that delivers nothing.
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from irp_shared.audit.models import AuditEvent
from irp_shared.audit.service import verify_chain
from irp_shared.ingest_mapping import operations as ops
from irp_shared.ingest_mapping.errors import (
    CastRefusedError,
    CodeLookupRefusedError,
    ConcatenateRefusedError,
    ConstantTypeRefusedError,
    DateParseRefusedError,
    IncoherentTargetOperationError,
    MappingContentImmutableError,
    MappingLifecycleError,
    MappingNotVisible,
    MissingSourceColumnError,
    OverlappingLoadError,
    PortfolioCodeNotVisible,
    QuantityUnitTooLongError,
    ScaleRefusedError,
    SelfRatificationError,
    UnknownTargetFieldError,
    UnratifiedMappingError,
    UnsupportedOperationError,
)
from irp_shared.ingest_mapping.events import ENTITY_MAPPING_VERSION, MAPPING_EVENT
from irp_shared.ingest_mapping.interpreter import (
    TARGET_FIELDS,
    ResolutionContext,
    declared_operation_kinds,
    interpret_row,
)
from irp_shared.ingest_mapping.models import (
    AUTHORSHIP_HAND_AUTHORED,
    AUTHORSHIP_MODEL_PROPOSED,
    SOURCE_TYPE_POSITIONS,
    STATUS_PROPOSED,
    STATUS_RATIFIED,
    STATUS_SUPERSEDED,
    IngestionMappingVersion,
)
from irp_shared.ingest_mapping.ratification_models import IngestionMappingRatification
from irp_shared.ingest_mapping.service import (
    assert_only_lifecycle_fields_change,
    canonical_operations_hash,
    load_batch,
    propose_mapping_version,
    ratified_mapping_for,
    ratify_mapping_version,
    resolve_mapping_version,
)
from irp_shared.ingestion.models import IngestionBatch, IngestionStagedRecord
from irp_shared.lineage.models import LineageEdge
from irp_shared.lineage.service import register_data_source
from irp_shared.model.service import register_model, register_model_version
from irp_shared.portfolio.portfolio import create_portfolio
from irp_shared.portfolio.service import PortfolioActor
from irp_shared.position import PositionActor
from irp_shared.position.models import Position
from irp_shared.reference.identifier import create_identifier_xref
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.models import IdentifierXref
from irp_shared.reference.service import ReferenceActor
from irp_shared.temporal import TemporalClass

PROPOSER = "proposer@irp"
RATIFIER = "ratifier@irp"

# The demonstrating mapping: a broker-statement shape exercising SIX of the seven operations.
# Clause (8)'s floor is three, so a rename-only demo must not be able to pass.
DEMO_OPS: list[dict[str, object]] = [
    {"op": "constant", "target": "portfolio_code", "value": "DEMO-INGEST"},
    {"op": "code-lookup", "target": "instrument", "source": "SEDOL_CODE", "scheme": "SEDOL"},
    {"op": "scale", "target": "quantity", "source": "QTY_THOUSANDS", "factor": "1000"},
    {"op": "cast", "target": "cost_basis", "source": "BOOK_COST", "to": "decimal"},
    {"op": "rename", "target": "quantity_unit", "source": "UNIT"},
    {"op": "parse-date", "target": "valid_from", "source": "AS_AT", "format": "%d/%m/%Y"},
]


def _row(
    sedol: str = "B1YW440",
    qty: str = "12.5",
    cost: str = "48,150.00",
    as_at: str = "31/07/2026",
) -> dict[str, object]:
    return {
        "SEDOL_CODE": sedol,
        "QTY_THOUSANDS": qty,
        "BOOK_COST": cost,
        "UNIT": "SHARES",
        "AS_AT": as_at,
    }


# --- fixtures ---------------------------------------------------------------------------------


def _tenant() -> str:
    return str(uuid.uuid4())


def _source(session: Session, tenant: str, code: str = "CUSTODIAN-A") -> str:
    return register_data_source(
        session,
        tenant_id=tenant,
        code=code,
        name="Custodian A positions feed",
        source_type="upload",
        actor_id="ops",
    ).id


def _book(session: Session, tenant: str, sedol: str = "B1YW440") -> tuple[str, str]:
    """A portfolio by code plus an instrument reachable by SEDOL.

    Returns ``(portfolio_id, instrument_id)``.
    """
    pf = create_portfolio(
        session,
        tenant_id=tenant,
        code="DEMO-INGEST",
        name="Ingest demo book",
        node_type="PORTFOLIO",
        actor=PortfolioActor(actor_id="ops"),
        base_currency_code="GBP",
    )
    instr = create_instrument(
        session,
        tenant_id=tenant,
        code="VOD-LN",
        name="Vodafone Group plc",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="ops"),
        currency_code="GBP",
    )
    create_identifier_xref(
        session,
        tenant_id=tenant,
        instrument_id=instr.id,
        scheme="SEDOL",
        value=sedol,
        actor=ReferenceActor(actor_id="ops"),
    )
    session.flush()
    return pf.id, instr.id


def _batch(
    session: Session, tenant: str, source_id: str, rows: list[dict[str, object]]
) -> IngestionBatch:
    """A staged batch, built directly.

    ``stage_upload``'s own path (anti-corruption, DQ gate, audit) is covered by test_ingestion.py;
    this fixture exists so the interpreter's tests are about the interpreter. Staged rows are
    0-based on ``row_number`` — the ``enumerate`` index, matching the shipped stager exactly.
    """
    batch = IngestionBatch(
        tenant_id=tenant,
        data_source_id=source_id,
        filename="positions.csv",
        content_type="text/csv",
        byte_size=1024,
        status="COMPLETED",
        scan_status="SKIPPED",
        row_count=len(rows),
        staged_count=len(rows),
    )
    session.add(batch)
    session.flush()
    for index, payload in enumerate(rows):
        session.add(
            IngestionStagedRecord(
                tenant_id=tenant, batch_id=batch.id, row_number=index, payload=dict(payload)
            )
        )
    session.flush()
    return batch


def _ratified(
    session: Session,
    tenant: str,
    source_id: str,
    operations: list[dict[str, object]] | None = None,
) -> IngestionMappingVersion:
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(operations if operations is not None else DEMO_OPS),
        actor_id=PROPOSER,
    )
    return ratify_mapping_version(
        session, mapping_version_id=version.id, acting_tenant=tenant, actor_id=RATIFIER
    )


def _ctx(session: Session, tenant: str, as_of: datetime | None = None) -> ResolutionContext:
    return ResolutionContext(
        session=session, acting_tenant=tenant, lookup_as_of=as_of or datetime.now(tz=UTC)
    )


def _open_head(session: Session) -> Position:
    return (
        session.execute(
            select(Position).where(Position.system_to.is_(None), Position.valid_to.is_(None))
        )
        .scalars()
        .one()
    )


# --- the vocabulary is genuinely closed (the LQ-1 T4 trap) ------------------------------------


def test_vocabulary_and_dispatch_are_exactly_equal_both_ways() -> None:
    """A name in the tuple with no dispatch arm compiles, imports, passes a vocabulary census, and
    then refuses every capture at runtime (``DIMENSION_KIND_LIQUIDITY_TIER`` did exactly that).
    Two mandatory sites, censused against each other by EXACT SET EQUALITY in BOTH directions."""
    assert set(ops.OPERATIONS) == set(ops.dispatch_names())
    # ...and the population has not collapsed to nothing (P6): the ratified set is SEVEN, by name.
    assert set(ops.OPERATIONS) == {
        "rename",
        "cast",
        "scale",
        "parse-date",
        "code-lookup",
        "constant",
        "concatenate",
    }
    assert len(ops.OPERATIONS) == len(set(ops.OPERATIONS)) == 7


@pytest.mark.parametrize("op_name", ops.OPERATIONS)
def test_every_operation_actually_executes(session: Session, op_name: str) -> None:
    """A vocabulary census cannot see whether an arm RUNS — an operation reachable only through a
    dispatch table is invisible to it. So every one of the seven is executed here, for real."""
    tenant = _tenant()
    _book(session, tenant)
    payload = dict(_row())
    payload["EXCHANGE"] = "LN"
    specs: dict[str, dict[str, object]] = {
        "rename": {"op": "rename", "source": "UNIT"},
        "cast": {"op": "cast", "source": "BOOK_COST", "to": "decimal"},
        "scale": {"op": "scale", "source": "QTY_THOUSANDS", "factor": "1000"},
        "parse-date": {"op": "parse-date", "source": "AS_AT", "format": "%d/%m/%Y"},
        "code-lookup": {"op": "code-lookup", "source": "SEDOL_CODE", "scheme": "SEDOL"},
        "constant": {"op": "constant", "value": "DEMO-INGEST"},
        "concatenate": {
            "op": "concatenate",
            "sources": ["EXCHANGE", "SEDOL_CODE"],
            "separator": ":",
        },
    }
    result = ops.apply_operation(specs[op_name], payload, 0, _ctx(session, tenant))
    assert result is not None
    expected: dict[str, object] = {
        "rename": "SHARES",
        "cast": Decimal("48150.00"),
        "scale": Decimal("12500.0"),
        "parse-date": datetime(2026, 7, 31),  # noqa: DTZ001 - tz applied downstream by _coerce
        "constant": "DEMO-INGEST",
        "concatenate": "LN:B1YW440",
    }
    if op_name in expected:
        assert result == expected[op_name]
    else:  # code-lookup returns the resolved instrument id
        assert uuid.UUID(str(result))


# --- every refusal FIRES (P9), each with its positive control ---------------------------------


def test_unsupported_operation_is_refused_by_name() -> None:
    """The ratified decision requires the refusal to NAME the unsupported operation rather than
    fail vaguely, so a file that cannot be expressed forces a new operation to be added
    deliberately. Asserted on the MESSAGE, not the exception type — the type would pass either
    way."""
    # positive control: the same dispatch call SUCCEEDS for a supported op, so the harness is live
    assert ops.apply_operation({"op": "rename", "source": "UNIT"}, _row(), 0, None) == "SHARES"
    with pytest.raises(UnsupportedOperationError) as exc:
        ops.apply_operation({"op": "regex_replace", "source": "UNIT"}, _row(), 0, None)
    assert "regex_replace" in str(exc.value)


def test_missing_source_column_refuses() -> None:
    payload = _row()
    assert "UNIT" in payload  # positive control: the column the happy path reads IS present
    assert ops.apply_operation({"op": "rename", "source": "UNIT"}, payload, 3, None) == "SHARES"
    with pytest.raises(MissingSourceColumnError) as exc:
        ops.apply_operation({"op": "rename", "source": "NOT_THERE"}, payload, 3, None)
    assert exc.value.row_number == 3


@pytest.mark.parametrize("bad", ["n/a", "", "  ", "1.2.3"])
def test_cast_refuses_uncastable_values(bad: str) -> None:
    spec = {"op": "cast", "source": "C", "to": "decimal"}
    assert ops.apply_operation(spec, {"C": "1,000.5"}, 0, None) == Decimal("1000.5")
    with pytest.raises(CastRefusedError):
        ops.apply_operation(spec, {"C": bad}, 0, None)


def test_cast_to_integer_refuses_a_fraction() -> None:
    spec = {"op": "cast", "source": "C", "to": "integer"}
    assert ops.apply_operation(spec, {"C": "12"}, 0, None) == 12
    with pytest.raises(CastRefusedError):
        ops.apply_operation(spec, {"C": "12.5"}, 0, None)


@pytest.mark.parametrize("value", ["31/02/2026", "2026-07-31", "not a date"])
def test_parse_date_refuses_a_shape_miss_and_a_calendar_miss(value: str) -> None:
    """``31/02/2026`` matches the FORMAT and is not a date — the case a shape-only check misses."""
    spec = {"op": "parse-date", "source": "D", "format": "%d/%m/%Y"}
    ok = ops.apply_operation(spec, {"D": "31/07/2026"}, 0, None)
    assert ok == datetime(2026, 7, 31)  # noqa: DTZ001 - naive by design; _coerce stamps UTC
    with pytest.raises(DateParseRefusedError):
        ops.apply_operation(spec, {"D": value}, 0, None)


@pytest.mark.parametrize("factor", ["0", "-1", "nan", "abc"])
def test_scale_refuses_a_degenerate_declared_factor(factor: str) -> None:
    """The factor arm is the one that matters: a ZERO factor turns a whole book into zero holdings,
    and every downstream reproduction of that load would agree with itself perfectly."""
    good = {"op": "scale", "source": "Q", "factor": "1000"}
    assert ops.apply_operation(good, {"Q": "1.5"}, 0, None) == Decimal("1500.0")
    with pytest.raises(ScaleRefusedError):
        ops.apply_operation({"op": "scale", "source": "Q", "factor": factor}, {"Q": "1.5"}, 0, None)


def test_scale_refuses_a_non_numeric_cell() -> None:
    with pytest.raises(ScaleRefusedError):
        ops.apply_operation({"op": "scale", "source": "Q", "factor": "10"}, {"Q": "many"}, 0, None)


def test_concatenate_refuses_a_partial_input() -> None:
    """Half an identifier looks like a valid identifier — so a missing input refuses rather than
    joining what it has."""
    spec = {"op": "concatenate", "sources": ["A", "B"], "separator": ":"}
    assert ops.apply_operation(spec, {"A": "LN", "B": "X"}, 0, None) == "LN:X"
    with pytest.raises(ConcatenateRefusedError) as exc:
        ops.apply_operation(spec, {"A": "LN"}, 7, None)
    assert exc.value.missing == ("B",)


def test_constant_of_the_wrong_type_is_refused_at_proposal(session: Session) -> None:
    """Refused when the mapping is PROPOSED, not only at load: a mapping that could never load
    anything must not be able to reach a human for ratification."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    base = [
        {"op": "constant", "target": "portfolio_code", "value": "P"},
        {"op": "code-lookup", "target": "instrument", "source": "S", "scheme": "SEDOL"},
        {"op": "parse-date", "target": "valid_from", "source": "D", "format": "%Y-%m-%d"},
    ]
    with pytest.raises(ConstantTypeRefusedError):
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="bad",
            operations=[*base, {"op": "constant", "target": "quantity", "value": "SHARES"}],
            actor_id=PROPOSER,
        )
    # positive control: the same proposal with a COERCIBLE constant succeeds
    ok = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="good",
        operations=[*base, {"op": "constant", "target": "quantity", "value": "100"}],
        actor_id=PROPOSER,
    )
    assert ok.status == STATUS_PROPOSED


def test_unknown_target_field_is_refused(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    assert "market_value" not in TARGET_FIELDS  # the column `position` deliberately does not have
    with pytest.raises(UnknownTargetFieldError):
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="bad",
            operations=[*DEMO_OPS, {"op": "rename", "target": "market_value", "source": "MV"}],
            actor_id=PROPOSER,
        )


def test_a_mapping_missing_a_required_target_is_refused(session: Session) -> None:
    """A mapping producing no quantity would write a null holding, which reads as a real position
    of zero — refused at proposal."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    with pytest.raises(UnknownTargetFieldError) as exc:
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="bad",
            operations=[op for op in DEMO_OPS if op["target"] != "quantity"],
            actor_id=PROPOSER,
        )
    assert "quantity" in str(exc.value)


def test_code_lookup_refuses_unresolved_and_ambiguous(session: Session) -> None:
    tenant = _tenant()
    _book(session, tenant)
    ctx = _ctx(session, tenant)
    spec = {"op": "code-lookup", "source": "SEDOL_CODE", "scheme": "SEDOL"}
    assert ops.apply_operation(spec, _row(), 0, ctx)  # positive control: it DOES resolve

    with pytest.raises(CodeLookupRefusedError) as exc:
        ops.apply_operation(spec, _row(sedol="NOPE999"), 4, ctx)
    assert "resolves to nothing" in str(exc.value)

    # Ambiguity needs care to plant, and the care is the point. `uq_identifier_xref_active` is
    # unique on (tenant, scheme, value) WHERE valid_to IS NULL, so two OPEN-ENDED rows cannot
    # coexist — but `resolve_identifier` matches `valid_from <= as_of AND (valid_to IS NULL OR
    # valid_to > as_of)`, so a row with a FUTURE valid_to is live at as_of while escaping that
    # index. A reachable real state (a cross-reference with a known end date), not a contrived one,
    # and it is what makes the ambiguity arm firable at all.
    other = create_instrument(
        session,
        tenant_id=tenant,
        code="VOD-DUP",
        name="Vodafone duplicate listing",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="ops"),
    )
    session.add(
        IdentifierXref(
            tenant_id=tenant,
            entity_type="instrument",
            entity_id=other.id,
            scheme="SEDOL",
            value="B1YW440",
            valid_from=datetime.now(tz=UTC) - timedelta(days=1),
            valid_to=datetime.now(tz=UTC) + timedelta(days=365),
            is_active=True,
            record_version=1,
        )
    )
    session.flush()
    with pytest.raises(CodeLookupRefusedError) as exc2:
        ops.apply_operation(spec, _row(), 5, ctx)
    assert "ambiguously" in str(exc2.value)


def test_load_with_no_ratified_mapping_refuses(session: Session) -> None:
    """Clause (1). The PROPOSED version exists and is NOT enough — that is the whole point."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    proposed = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
    )
    assert proposed.status == STATUS_PROPOSED  # positive control: a version DOES exist
    batch = _batch(session, tenant, source_id, [_row()])
    with pytest.raises(UnratifiedMappingError):
        load_batch(
            session,
            batch=batch,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="ops"),
            source_type=SOURCE_TYPE_POSITIONS,
        )
    assert session.execute(select(func.count()).select_from(Position)).scalar_one() == 0


def test_self_ratification_refuses(session: Session) -> None:
    """Clause (6)'s refusal half (DS3a-3). The permission separation lands at S3b."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
    )
    with pytest.raises(SelfRatificationError):
        ratify_mapping_version(
            session, mapping_version_id=version.id, acting_tenant=tenant, actor_id=PROPOSER
        )
    assert version.status == STATUS_PROPOSED
    # positive control: a DIFFERENT actor ratifies the very same version
    ratified = ratify_mapping_version(
        session, mapping_version_id=version.id, acting_tenant=tenant, actor_id=RATIFIER
    )
    assert ratified.status == STATUS_RATIFIED


def test_ratifying_a_non_proposed_version_refuses(session: Session) -> None:
    """The alternate-path half: a gate that fires only in the obvious state is not a control."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = _ratified(session, tenant, source_id)
    with pytest.raises(MappingLifecycleError):
        ratify_mapping_version(
            session, mapping_version_id=version.id, acting_tenant=tenant, actor_id=RATIFIER
        )


def test_a_cross_tenant_mapping_id_is_not_visible(session: Session) -> None:
    tenant_a, tenant_b = _tenant(), _tenant()
    source_a = _source(session, tenant_a)
    version = _ratified(session, tenant_a, source_a)
    assert resolve_mapping_version(session, version.id, acting_tenant=tenant_a).id == version.id
    with pytest.raises(MappingNotVisible):
        resolve_mapping_version(session, version.id, acting_tenant=tenant_b)


def test_the_eager_content_guard_still_refuses_when_called_directly(session: Session) -> None:
    """The service keeps an EAGER pre-flush assertion beside the listener, because it fails at the
    point of the mistake rather than at the next flush. It is no longer THE control — see
    ``test_a_content_edit_is_refused_on_an_ORDINARY_flush``, which does not call it at all."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = _ratified(session, tenant, source_id)
    session.flush()
    version.operations = [{"op": "rename", "target": "quantity", "source": "ELSEWHERE"}]
    with pytest.raises(MappingContentImmutableError) as exc:
        assert_only_lifecycle_fields_change(version)
    assert "operations" in str(exc.value)
    session.rollback()


def test_a_lifecycle_only_change_is_permitted(session: Session) -> None:
    """The positive control for the guard above: it must not refuse the transition it sits
    beside."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = _ratified(session, tenant, source_id)
    session.flush()
    version.status = STATUS_SUPERSEDED
    assert_only_lifecycle_fields_change(version)  # does not raise


# --- the lifecycle ----------------------------------------------------------------------------


def test_ratifying_a_replacement_supersedes_the_incumbent(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    v1 = _ratified(session, tenant, source_id)
    v2 = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v2",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
        supersedes_id=v1.id,
    )
    ratify_mapping_version(
        session, mapping_version_id=v2.id, acting_tenant=tenant, actor_id=RATIFIER
    )
    session.flush()
    assert v1.status == STATUS_SUPERSEDED
    assert v1.superseded_at is not None
    current = ratified_mapping_for(
        session,
        acting_tenant=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
    )
    assert current.id == v2.id


def test_the_operations_hash_moves_with_one_edited_factor() -> None:
    """The reproducibility key must be sensitive to meaning and insensitive to formatting."""
    a = canonical_operations_hash(DEMO_OPS)
    reordered = [dict(reversed(list(op.items()))) for op in DEMO_OPS]
    assert canonical_operations_hash(reordered) == a  # key order is not meaning
    edited = [dict(op) for op in DEMO_OPS]
    edited[2]["factor"] = "1"
    assert canonical_operations_hash(edited) != a  # one declared factor IS meaning


def test_authorship_model_proposed_requires_its_evidence(session: Session) -> None:
    """Clause (7): a MODEL_PROPOSED version without a model version and prompt identity is refused,
    and the model version is re-resolved TENANT-FILTERED before it is stamped — PostgreSQL FK
    checks bypass RLS, so the FK alone would durably admit a cross-tenant reference."""
    tenant, other = _tenant(), _tenant()
    source_id = _source(session, tenant)
    with pytest.raises(MappingLifecycleError):
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="m1",
            operations=list(DEMO_OPS),
            actor_id=PROPOSER,
            authorship=AUTHORSHIP_MODEL_PROPOSED,
        )
    model = register_model(
        session,
        tenant_id=other,
        code="MAPPING-DRAFTER",
        name="Mapping drafter",
        model_type="AI_ML",
        actor_id="ops",
    )
    version = register_model_version(
        session,
        model=model,
        version_label="1.0.0",
        actor_id="ops",
        methodology_ref="05_analytics_methodologies/ingest_mapping_drafting_v1.md",
        code_version="1",
        status="REGISTERED",
    )
    session.flush()
    with pytest.raises(MappingNotVisible):
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="m2",
            operations=list(DEMO_OPS),
            actor_id=PROPOSER,
            authorship=AUTHORSHIP_MODEL_PROPOSED,
            proposer_model_version_id=version.id,
            proposal_prompt_hash="0" * 64,
        )


# --- the load path: clauses 3, 8, 9, 10 -------------------------------------------------------


def test_the_demonstrating_mapping_exercises_at_least_three_operation_kinds() -> None:
    """Clause (8), so a rename-only demo cannot pass."""
    kinds = declared_operation_kinds(DEMO_OPS)
    assert len(kinds) >= 3
    assert kinds == {"constant", "code-lookup", "scale", "cast", "rename", "parse-date"}


def test_a_ratified_mapping_loads_a_book_and_binds_its_version(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    portfolio_id, instrument_id = _book(session, tenant)
    mapping = _ratified(session, tenant, source_id)
    batch = _batch(session, tenant, source_id, [_row()])

    result = load_batch(
        session,
        batch=batch,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()

    assert result.row_count == 1
    assert result.lookups == {"SEDOL": 1}  # P18: the lookup provably HAPPENED
    # clause (2), the batch half: a HARD FK, and the as-of instant is recorded
    assert batch.mapping_version_id == mapping.id
    assert batch.lookup_as_of == result.lookup_as_of

    row = session.execute(select(Position)).scalars().one()
    assert row.portfolio_id == portfolio_id
    assert row.instrument_id == instrument_id
    assert row.quantity == Decimal("12500.0")  # 12.5 thousands, scaled
    assert row.cost_basis == Decimal("48150.00")  # the comma stripped, not mis-parsed
    assert row.quantity_unit == "SHARES"
    # SQLite drops the tz on read (the DateTime(timezone=True) column is naive there); compare the
    # instant rather than the tzinfo object, so this asserts the DATE the file declared rather than
    # the dialect's storage convention.
    assert row.valid_from.replace(tzinfo=None) == datetime(2026, 7, 31)  # noqa: DTZ001
    # the amended requirement BANS free-text attribution, so the loader must not have used it
    assert row.position_source is None


def test_the_loaded_row_is_attributed_to_the_ingestion_source_not_manual(session: Session) -> None:
    """DS3a-4. Recording a file-loaded holding as manual entry would be a FALSE provenance record —
    worse than none, because a reader cannot tell it from a genuine hand capture."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    _ratified(session, tenant, source_id)
    batch = _batch(session, tenant, source_id, [_row()])
    result = load_batch(
        session,
        batch=batch,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()
    edges = (
        session.execute(
            select(LineageEdge).where(
                LineageEdge.target_entity_type == "position",
                LineageEdge.target_entity_id == result.created[0],
            )
        )
        .scalars()
        .all()
    )
    assert len(edges) == 1
    assert edges[0].source_id == source_id  # the CUSTODIAN feed, not the tenant's MANUAL root


def test_an_overlapping_reload_refuses_unless_flagged_a_restatement(session: Session) -> None:
    """Clause (10) / DP-19-7, fail-closed. Silently overwriting a client's holdings is the failure
    this platform exists to make impossible."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    _ratified(session, tenant, source_id)

    first = _batch(session, tenant, source_id, [_row()])
    load_batch(
        session,
        batch=first,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()

    second = _batch(session, tenant, source_id, [_row(qty="13.0")])
    with pytest.raises(OverlappingLoadError):
        load_batch(
            session,
            batch=second,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="ops"),
            source_type=SOURCE_TYPE_POSITIONS,
        )


def test_a_later_dated_file_supersedes_and_needs_no_restatement_flag(session: Session) -> None:
    """The ordinary next periodic file is NOT an overlap. Asserted so the fail-closed refusal above
    cannot be satisfied by a loader that simply refuses every second load."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    _ratified(session, tenant, source_id)

    first = _batch(session, tenant, source_id, [_row()])
    load_batch(
        session,
        batch=first,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()

    later = _batch(session, tenant, source_id, [_row(qty="14.0", as_at="31/08/2026")])
    result = load_batch(
        session,
        batch=later,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()
    assert len(result.superseded) == 1
    assert not result.restated
    assert _open_head(session).quantity == Decimal("14000.0")


def test_a_backdated_file_refuses_even_when_flagged(session: Session) -> None:
    """An as-known correction cannot express "the truth for an earlier valid date than the one
    already open", so letting it through would silently reorder a client's history."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    _ratified(session, tenant, source_id)

    first = _batch(session, tenant, source_id, [_row(as_at="31/08/2026")])
    load_batch(
        session,
        batch=first,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()

    backdated = _batch(session, tenant, source_id, [_row(as_at="31/07/2026")])
    with pytest.raises(OverlappingLoadError):
        load_batch(
            session,
            batch=backdated,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="ops"),
            source_type=SOURCE_TYPE_POSITIONS,
            restatement_reason="attempted backdate",
        )


def test_an_edited_mapping_moves_exactly_the_rows_the_edit_touches(session: Session) -> None:
    """Clause (3), COMPOSED with clause (10) rather than in conflict with it.

    "Re-load the same file" IS the overlap clause (10) refuses, so the re-load is FLAGGED a
    restatement — which is simultaneously clause (10)'s positive control. The assertion is a
    DIFFERENTIAL: the corrected version differs in the field the edited operation touches, and in
    NOTHING else.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    _ratified(session, tenant, source_id)

    first = _batch(session, tenant, source_id, [_row()])
    load_batch(
        session,
        batch=first,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()
    before = _open_head(session)
    before_snapshot = {
        "portfolio_id": before.portfolio_id,
        "instrument_id": before.instrument_id,
        "quantity": before.quantity,
        "cost_basis": before.cost_basis,
        "quantity_unit": before.quantity_unit,
        "valid_from": before.valid_from,
    }

    # ONE operation edited: the scale factor. V2 is HAND_AUTHORED, because it is an operator's edit
    # of a ratified artifact and labelling it MODEL_PROPOSED would be the false record clause (7)
    # exists to prevent.
    edited = [dict(op) for op in DEMO_OPS]
    edited[2]["factor"] = "1000000"
    v2 = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v2",
        operations=edited,
        actor_id=PROPOSER,
        authorship=AUTHORSHIP_HAND_AUTHORED,
    )
    ratify_mapping_version(
        session, mapping_version_id=v2.id, acting_tenant=tenant, actor_id=RATIFIER
    )

    second = _batch(session, tenant, source_id, [_row()])
    load_batch(
        session,
        batch=second,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
        restatement_reason="re-load under mapping v2 (scale factor corrected)",
    )
    session.flush()

    after = _open_head(session)
    # exactly where the edit says: quantity x1000
    assert after.quantity == before_snapshot["quantity"] * 1000
    # ...and NOWHERE else
    for field_name in (
        "portfolio_id",
        "instrument_id",
        "cost_basis",
        "quantity_unit",
        "valid_from",
    ):
        assert getattr(after, field_name) == before_snapshot[field_name], field_name
    assert after.restatement_reason is not None
    assert second.mapping_version_id == v2.id


def test_the_load_is_reproducible_and_the_as_of_is_load_bearing(session: Session) -> None:
    """Clause (9): mapping version + staged file + code-lookup reference data AS OF the load.

    The third input is proven real by a DIFFERENTIAL rather than asserted: moving ``lookup_as_of``
    across an ``identifier_xref`` supersession resolves a DIFFERENT instrument from the same file
    and the same mapping. Without that, "as of the load" is a sentence no test could fail.
    """
    tenant = _tenant()
    _book(session, tenant)
    later = create_instrument(
        session,
        tenant_id=tenant,
        code="VOD-LN-NEW",
        name="Vodafone (post-reorganisation line)",
        asset_class="EQUITY",
        actor=ReferenceActor(actor_id="ops"),
    )
    cutover = datetime.now(tz=UTC) + timedelta(days=1)
    create_identifier_xref(
        session,
        tenant_id=tenant,
        instrument_id=later.id,
        scheme="SEDOL",
        value="B1YW441",
        actor=ReferenceActor(actor_id="ops"),
        valid_from=cutover,
    )
    session.flush()

    spec = {"op": "code-lookup", "source": "SEDOL_CODE", "scheme": "SEDOL"}
    payload = _row(sedol="B1YW441")
    # BEFORE the cutover the identifier resolves to nothing — a refusal fired by the as-of alone
    with pytest.raises(CodeLookupRefusedError):
        ops.apply_operation(spec, payload, 0, _ctx(session, tenant, datetime.now(tz=UTC)))
    # AFTER it, the same file and the same mapping resolve to the new line
    resolved = ops.apply_operation(
        spec, payload, 0, _ctx(session, tenant, cutover + timedelta(hours=1))
    )
    assert resolved == later.id


def test_interpret_row_is_deterministic(session: Session) -> None:
    tenant = _tenant()
    _book(session, tenant)
    as_of = datetime.now(tz=UTC)
    a = interpret_row(DEMO_OPS, _row(), 0, _ctx(session, tenant, as_of))
    b = interpret_row(DEMO_OPS, _row(), 0, _ctx(session, tenant, as_of))
    assert a == b


# --- governance surface -----------------------------------------------------------------------


def test_the_lifecycle_emits_data_mapping_and_the_chain_verifies(session: Session) -> None:
    tenant = _tenant()
    source_id = _source(session, tenant)
    _ratified(session, tenant, source_id)
    session.flush()
    events = (
        session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == MAPPING_EVENT, AuditEvent.tenant_id == tenant
            )
        )
        .scalars()
        .all()
    )
    # one create (propose) + one status_change (ratify)
    assert [e.action for e in events] == ["create", "status_change"]
    assert {e.entity_type for e in events} == {ENTITY_MAPPING_VERSION}
    assert verify_chain(session, tenant_id=tenant)


def test_the_audit_payload_carries_no_operations_and_no_staged_cell(session: Session) -> None:
    """A mapping's column names are CLIENT SCHEMA. The ingest path's redaction rule (metadata and
    reason codes only) applies here too, and this asserts it rather than trusting a docstring."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _ratified(session, tenant, source_id)
    session.flush()
    events = (
        session.execute(select(AuditEvent).where(AuditEvent.event_type == MAPPING_EVENT))
        .scalars()
        .all()
    )
    assert events
    for event in events:
        blob = str(event.after_value)
        assert "QTY_THOUSANDS" not in blob
        assert "SEDOL_CODE" not in blob
        assert "operations_hash" in blob


def test_the_table_declares_its_temporal_class_and_is_not_append_only() -> None:
    """The choice is unusual on this project (the commoner one is true IA + trigger), so it is
    asserted rather than left to a reader to infer from an empty table."""
    assert IngestionMappingVersion.__temporal_class__ is TemporalClass.IMMUTABLE_APPEND_ONLY

    # (a) The listener set is ASYMMETRIC, and the asymmetry is the design:
    #   - `before_update` HAS a guard — the content-immutability refusal. It was a helper called by
    #     hand until the slice review proved that could never fire in production.
    #   - `before_delete` has NONE, and must not: a delete guard would make this a truly
    #     append-only table, and the status projection has to transition.
    dispatch = IngestionMappingVersion.__mapper__.dispatch
    assert list(dispatch.before_update), "the content-immutability listener is not registered"
    assert list(dispatch.before_delete) == []

    # (a-control) the read is not vacuous in EITHER direction: a truly append-only peer has BOTH,
    # and the status-mutable peer this table otherwise follows has NEITHER.
    guarded = IngestionStagedRecord.__mapper__.dispatch
    assert list(guarded.before_update) and list(guarded.before_delete)
    status_mutable_peer = IngestionBatch.__mapper__.dispatch
    assert list(status_mutable_peer.before_update) == []

    # (b) NO irp_prevent_mutation TRIGGER in the migration that creates it — matched on the DDL
    # statement, not the function name, which the module docstring legitimately mentions.
    migration = (
        pathlib.Path(__file__).resolve().parents[3]
        / "migrations/versions/0074_ingestion_mapping_version.py"
    ).read_text()
    assert "CREATE TRIGGER" not in migration
    assert "FORCE ROW LEVEL SECURITY" in migration


def test_the_partial_unique_index_is_spelled_on_both_dialects() -> None:
    """A ``postgresql_where``-only index renders on SQLite as a PLAIN unique index with the
    predicate SILENTLY DROPPED — so the omission would make the unit tier reject a legal second
    PROPOSED row while proving nothing about Postgres. Both precedents carry the twin predicate."""
    index = next(
        ix
        for ix in IngestionMappingVersion.__table__.indexes
        if ix.name == "uq_ingestion_mapping_version_active"
    )
    assert index.unique
    pg_where = index.dialect_options["postgresql"]["where"]
    sqlite_where = index.dialect_options["sqlite"]["where"]
    assert pg_where is not None, "the PostgreSQL predicate is missing — the index is not partial"
    assert sqlite_where is not None, (
        "the SQLite predicate is missing — SQLAlchemy would render a PLAIN unique index here and "
        "the unit tier would reject a legal second PROPOSED row"
    )
    assert str(pg_where) == str(sqlite_where) == "status = 'RATIFIED'"


def test_two_proposed_versions_may_coexist(session: Session) -> None:
    """The behavioural consequence of the partial predicate, asserted through the service rather
    than by reading the index — a test of the DDL would pass on an index that is never enforced."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    for label in ("a", "b"):
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label=label,
            operations=list(DEMO_OPS),
            actor_id=PROPOSER,
        )
    session.flush()
    count = session.execute(
        select(func.count())
        .select_from(IngestionMappingVersion)
        .where(IngestionMappingVersion.status == STATUS_PROPOSED)
    ).scalar_one()
    assert count == 2


def test_import_direction() -> None:
    """``ingest_mapping`` may import the domain packages it composes, and nothing may import back.

    ``rglob``, not ``glob``: the ingestion package's own fence globs top-level ``*.py`` only, so a
    subpackage would be invisible to it. That hole is not inherited here.
    """
    pkg = pathlib.Path(__file__).resolve().parents[1] / "src/irp_shared/ingest_mapping"
    allowed = {
        "ingest_mapping",
        "ingestion",
        "position",
        "portfolio",
        "reference",
        "model",
        "lineage",
        "audit",
        "db",
        "temporal",
    }
    for path in pkg.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            assert "irp_backend" not in stripped, f"{path.name}: {stripped}"
            assert "irp_shared.models" not in stripped, f"{path.name}: {stripped}"
            if "irp_shared." in stripped:
                seg = stripped.split("irp_shared.", 1)[1].split(".")[0].split()[0].split(",")[0]
                assert seg in allowed, f"{path.name} imports irp_shared.{seg}: {stripped}"


def test_nothing_imports_ingest_mapping_backwards() -> None:
    """The dependency runs ONE way. ``position`` in particular must never import this package — its
    own fence forbids it, which is why S3b's FK is spelled as a literal table name.

    Matched on IMPORT LINES rather than raw text: ``ingestion/models.py`` legitimately NAMES this
    package in the comment explaining why its FK is spelled as a string, and a raw-text fence would
    make that explanation impossible to write.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "src/irp_shared"
    for package in ("position", "portfolio", "reference", "model", "lineage", "dq", "ingestion"):
        for path in (root / package).rglob("*.py"):
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    assert "ingest_mapping" not in stripped, f"{path}: {stripped}"


# --- the anti-corruption interaction: SHORT POSITIONS -----------------------------------------


@pytest.mark.parametrize(
    ("staged", "expected"),
    [
        ("'-3.2", Decimal("-3200.0")),  # a SHORT, as the anti-corruption layer stages it
        ("'+4.0", Decimal("4000.0")),  # an explicitly-signed long, same treatment
        ("12.5", Decimal("12500.0")),  # the ordinary case, unchanged
    ],
)
def test_scale_reads_a_short_position_through_the_anticorruption_quote(
    staged: str, expected: Decimal
) -> None:
    """``neutralize_cell`` prefixes ``'`` to any cell starting with ``= + - @`` (THR-06), and a
    SHORT POSITION starts with ``-``. Without the numeric-path repair the platform would refuse to
    load any book containing a short, while ``position.quantity`` is documented as SIGNED.

    Found by execution during this slice, not by reading.
    """
    spec = {"op": "scale", "source": "Q", "factor": "1000"}
    assert ops.apply_operation(spec, {"Q": staged}, 0, None) == expected


def test_the_anticorruption_quote_survives_on_TEXT_fields() -> None:
    """The repair is confined to the NUMERIC path on purpose. A text field keeps the neutralized
    form, because the CSV-injection defence exists for values that flow onward into a spreadsheet
    — and a quantity does not, since it is coerced to Decimal and stored as a number."""
    assert ops.apply_operation({"op": "rename", "source": "T"}, {"T": "'=SUM(A1)"}, 0, None) == (
        "'=SUM(A1)"
    )


def test_a_formula_cell_is_still_refused_as_a_number() -> None:
    """The repair must not turn a genuine injection attempt into a parseable number: the quote is
    only dropped when what follows is a sign or a digit."""
    with pytest.raises(ScaleRefusedError):
        ops.apply_operation(
            {"op": "scale", "source": "Q", "factor": "10"}, {"Q": "'=SUM(A1)"}, 0, None
        )
    with pytest.raises(CastRefusedError):
        ops.apply_operation({"op": "cast", "source": "C", "to": "decimal"}, {"C": "'@x"}, 0, None)


def test_a_loaded_short_position_lands_signed(session: Session) -> None:
    """End to end: a short in the file becomes a NEGATIVE canonical quantity."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    _ratified(session, tenant, source_id)
    row = dict(_row())
    row["QTY_THOUSANDS"] = "'-3.2"  # exactly what the anti-corruption layer stages
    batch = _batch(session, tenant, source_id, [row])
    load_batch(
        session,
        batch=batch,
        acting_tenant=tenant,
        actor=PositionActor(actor_id="ops"),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()
    assert _open_head(session).quantity == Decimal("-3200.0")


# --- the refusal census: P9's MECHANICAL limb, which this repo did not have ---------------------


def _refusal_classes() -> set[str]:
    """Every concrete refusal in the mapping spine, discovered from the class tree."""
    from irp_shared.ingest_mapping import errors as errs

    found: set[str] = set()

    def walk(cls: type) -> None:
        for sub in cls.__subclasses__():
            found.add(sub.__name__)
            walk(sub)

    walk(errs.MappingError)
    return found


def test_every_declared_refusal_is_fired_by_a_test() -> None:
    """P9's mechanical limb.

    *A refusal that cannot fire and a refusal that never fires are indistinguishable from the diff.*
    This repo has shipped structurally unfireable refusals twice, and P9's own text says the
    mechanical half should be a census — but no such census existed anywhere in the repo, in any
    slice. ``errors.py``'s docstring nonetheless CLAIMED one, which a slice reviewer caught: a false
    governance record inside the module whose purpose is to prevent them. This is the census the
    claim needed.

    It DISCOVERS its population from ``MappingError.__subclasses__()`` rather than a hand list, so a
    refusal minted tomorrow joins it by construction.
    """
    here = pathlib.Path(__file__).resolve().parent
    corpus = "\n".join(
        path.read_text()
        for path in (
            here / "test_ingest_mapping.py",
            here / "test_ingest_mapping_pg.py",
            here / "test_ingestion.py",
        )
    )
    declared = _refusal_classes()
    assert declared, "the refusal collector found NOTHING — the census walked an empty population"

    unfired = sorted(
        name
        for name in declared
        if f"pytest.raises({name}" not in corpus and f"{name})" not in corpus
    )
    assert not unfired, (
        f"refusals with no test that makes them FIRE: {unfired}. A refusal that cannot fire and a "
        f"refusal that never fires are indistinguishable from the diff."
    )


def test_the_refusal_census_population_has_not_collapsed() -> None:
    """P6's floor on the census above. A collector that silently stopped finding subclasses would
    report zero unfired refusals — which reads exactly like full coverage."""
    declared = _refusal_classes()
    assert len(declared) >= 14, (
        f"the refusal census discovered only {len(declared)} classes — the collector has stopped "
        "matching, not the module stopped declaring refusals"
    )
    # named instances, so a collector that found a DIFFERENT 14 classes still fails
    assert {"UnratifiedMappingError", "SelfRatificationError", "OverlappingLoadError"} <= declared


# --- the folds from the slice review -----------------------------------------------------------


def test_a_mapping_whose_operations_are_all_unsupported_cannot_be_PROPOSED(
    session: Session,
) -> None:
    """The coherence check never validated the OPERATION, only the target.

    A reviewer reproduced the consequence: a mapping whose every op was `regex_replace` passed
    cleanly and could be RATIFIED — a governance record saying a human approved something
    guaranteed to refuse every row, which is precisely the outcome the check's docstring says it
    exists to prevent.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    bad = [dict(op, op="regex_replace") for op in DEMO_OPS]
    with pytest.raises(UnsupportedOperationError) as exc:
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="bad",
            operations=bad,
            actor_id=PROPOSER,
        )
    assert "regex_replace" in str(exc.value)
    # positive control: the SAME shape with supported ops proposes fine
    assert (
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="good",
            operations=list(DEMO_OPS),
            actor_id=PROPOSER,
        ).status
        == STATUS_PROPOSED
    )


@pytest.mark.parametrize("op_name", ["rename", "concatenate", "code-lookup"])
def test_an_operation_that_cannot_produce_a_decimal_is_refused_at_PROPOSAL(
    session: Session, op_name: str
) -> None:
    """The BLOCKING finding two lanes reproduced end to end.

    A `rename` into `quantity` used to pass coherence, get RATIFIED through the real service verbs,
    and then raise a bare ``decimal.InvalidOperation`` at load — an ArithmeticError, not a
    ``MappingError``, so a caller failing closed on the family caught nothing. The trigger value was
    ``1,234.50``: an ordinary comma-formatted number, structurally identical to the demonstrating
    file's own book-cost column.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    spec: dict[str, object] = {"op": op_name, "target": "quantity", "source": "QTY"}
    if op_name == "concatenate":
        spec = {"op": op_name, "target": "quantity", "sources": ["A", "B"]}
    if op_name == "code-lookup":
        spec = {"op": op_name, "target": "quantity", "source": "S", "scheme": "SEDOL"}
    ops_list = [op for op in DEMO_OPS if op["target"] != "quantity"] + [spec]
    with pytest.raises(IncoherentTargetOperationError) as exc:
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label=f"bad-{op_name}",
            operations=ops_list,
            actor_id=PROPOSER,
        )
    assert "quantity" in str(exc.value)


def test_a_constant_valid_from_is_refused_at_PROPOSAL(session: Session) -> None:
    """The datetime half of the same rule: only `parse-date` may fill `valid_from`. A constant
    would pin every row of every load to one instant."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    ops_list = [op for op in DEMO_OPS if op["target"] != "valid_from"] + [
        {"op": "constant", "target": "valid_from", "value": "2026-07-31"}
    ]
    with pytest.raises((IncoherentTargetOperationError, ConstantTypeRefusedError)):
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="bad-const-date",
            operations=ops_list,
            actor_id=PROPOSER,
        )


def test_a_non_numeric_reaching_a_decimal_target_refuses_GOVERNED(session: Session) -> None:
    """Defense in depth for the same class: even if a shape slipped past ratification, the write
    path must refuse with a ``MappingError``, never a bare ``decimal.InvalidOperation``."""
    from irp_shared.ingest_mapping.interpreter import _as_decimal

    with pytest.raises(CastRefusedError):
        _as_decimal("not a number", "quantity", 3)
    # ...and the anti-corruption quote is handled HERE too, not only inside cast/scale
    assert _as_decimal("'-3.2", "quantity", 0) == Decimal("-3.2")
    assert _as_decimal("1,234.50", "cost_basis", 0) == Decimal("1234.50")


def test_a_content_edit_is_refused_on_an_ORDINARY_flush(session: Session) -> None:
    """THE fold that mattered most: the guard is an ORM listener now, not a helper called by hand.

    It could never fire before. Both production call sites assign nothing but lifecycle fields, and
    the two tests exercising it called it DIRECTLY. A reviewer proved the consequence by execution:
    ``version.operations = [...]`` followed by any query let autoflush push the UPDATE with no
    refusal, no audit event, and the ratified mapping's meaning silently changed.

    This test does NOT call the guard. It edits and flushes, the way real code would.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = _ratified(session, tenant, source_id)
    session.flush()
    version.operations = [{"op": "rename", "target": "quantity", "source": "SOMEWHERE_ELSE"}]
    with pytest.raises(MappingContentImmutableError) as exc:
        session.flush()
    assert "operations" in str(exc.value)
    session.rollback()


def test_the_listener_permits_the_lifecycle_it_sits_beside(session: Session) -> None:
    """The positive control: a listener that refused everything would pass the test above and break
    ratification entirely — and ratification is a flush of exactly this shape."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = _ratified(session, tenant, source_id)  # this ITSELF flushes two status transitions
    session.flush()
    assert version.status == STATUS_RATIFIED
    version.status = STATUS_SUPERSEDED
    version.superseded_at = datetime.now(tz=UTC)
    session.flush()  # must NOT raise
    assert version.status == STATUS_SUPERSEDED


def test_self_ratification_is_not_defeated_by_an_UPPERCASE_uuid(session: Session) -> None:
    """The four-eyes refusal compared RAW STRINGS, and a reviewer showed the vector.

    ``require_uuid_principal_id`` accepts any spelling ``uuid.UUID()`` parses, so the same person
    authenticating with the uppercase form is the SAME PRINCIPAL to authentication and a DIFFERENT
    STRING to ``==``. The proposer re-authenticates uppercase and ratifies their own mapping. The
    ENT-075 four-eyes rail already carries this exact vector as a named test; this slice did not
    reuse that rail and so did not inherit the lesson.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    proposer = str(uuid.uuid4())
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=proposer,
    )
    assert proposer != proposer.upper()  # the two spellings really are different strings
    with pytest.raises(SelfRatificationError):
        ratify_mapping_version(
            session,
            mapping_version_id=version.id,
            acting_tenant=tenant,
            actor_id=proposer.upper(),
        )
    # positive control: a genuinely different principal still ratifies
    ratified = ratify_mapping_version(
        session,
        mapping_version_id=version.id,
        acting_tenant=tenant,
        actor_id=str(uuid.uuid4()),
    )
    assert ratified.status == STATUS_RATIFIED


def test_an_over_long_quantity_unit_is_REFUSED_not_truncated(session: Session) -> None:
    """Truncating would write a governed record saying something the client's file did not say,
    with nothing downstream able to tell it was altered. The first draft truncated silently."""
    tenant = _tenant()
    _book(session, tenant)
    payload = dict(_row())
    payload["UNIT"] = "SHARES (POST-SPLIT ADJUSTED)"  # 28 characters; the column holds 20
    with pytest.raises(QuantityUnitTooLongError) as exc:
        interpret_row(DEMO_OPS, payload, 2, _ctx(session, tenant))
    assert "28 characters" in str(exc.value)
    # positive control: a unit that FITS passes through unchanged, not silently shortened
    payload["UNIT"] = "SHARES"
    assert interpret_row(DEMO_OPS, payload, 2, _ctx(session, tenant))["quantity_unit"] == "SHARES"


def test_an_unresolvable_portfolio_code_raises_its_OWN_error(session: Session) -> None:
    """``MappingNotVisible`` stores its argument as ``mapping_version_id``; handing it a portfolio
    code made a handler reading that attribute report something untrue about what failed."""
    from irp_shared.ingest_mapping.service import _resolve_portfolio_by_code

    tenant = _tenant()
    with pytest.raises(PortfolioCodeNotVisible) as exc:
        _resolve_portfolio_by_code(session, "NO-SUCH-BOOK", acting_tenant=tenant)
    assert exc.value.code == "NO-SUCH-BOOK"


def test_the_DEMONSTRATING_mapping_itself_clears_the_clause_8_floor() -> None:
    """Clause (8) is about THE DEMONSTRATING FILE, and the original test asserted it of a local
    fixture instead. A reviewer proved the gap by mutating the real ``committed_operations()`` down
    to one operation kind and watching the test stay green."""
    from irp_shared.demo.ingest1_stage28 import committed_operations

    kinds = declared_operation_kinds(committed_operations())
    assert len(kinds) >= 3, f"the shipped demonstrating mapping declares only {sorted(kinds)}"


# --- W19-S3b: four-eyes as an APPEND-ONLY resolution row (ENT-078) ----------------------------


def _resolutions(session: Session, tenant: str) -> list[IngestionMappingRatification]:
    return list(
        session.execute(
            select(IngestionMappingRatification)
            .where(IngestionMappingRatification.tenant_id == tenant)
            .order_by(IngestionMappingRatification.seq)
        )
        .scalars()
        .all()
    )


def test_ratifying_appends_a_resolution_row_rather_than_only_a_status(session: Session) -> None:
    """The decision is a ROW. ENT-077's status is a projection of it, never the authority."""
    tenant = _tenant()
    source_id = _source(session, tenant)
    version = _ratified(session, tenant, source_id)
    session.flush()

    rows = _resolutions(session, tenant)
    assert [r.outcome for r in rows] == ["RATIFIED"]
    assert rows[0].mapping_version_id == version.id
    assert rows[0].resolved_by == RATIFIER
    assert rows[0].seq == 1
    # the denormalized source, without which the invariant has nothing to key on
    assert rows[0].data_source_id == source_id
    assert rows[0].source_type == SOURCE_TYPE_POSITIONS


def test_a_resolution_row_cannot_be_edited(session: Session) -> None:
    """The one property that matters here. A decision that can be edited after the fact is not
    evidence of a decision — the ENT-075 lesson, applied rather than re-learned."""
    from irp_shared.audit.models import AppendOnlyViolation

    tenant = _tenant()
    source_id = _source(session, tenant)
    _ratified(session, tenant, source_id)
    session.flush()
    row = _resolutions(session, tenant)[0]
    row.outcome = "WITHDRAWN"
    with pytest.raises(AppendOnlyViolation):
        session.flush()
    session.rollback()


def test_the_load_gate_reads_the_RESOLUTION_not_the_status(session: Session) -> None:
    """The re-pointing, proven the only way that means anything: force ENT-077's status to RATIFIED
    with NO resolution row behind it, and the load must still refuse.

    Without this the append-only table would be evidence nobody consults — a governance record
    placed beside the real gate instead of in front of it.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
    )
    session.flush()
    # the shape a non-ORM UPDATE produces: the projection says RATIFIED, nobody decided anything
    session.execute(
        text("UPDATE ingestion_mapping_version SET status = 'RATIFIED' WHERE id = :i"),
        {"i": version.id},
    )
    session.flush()
    assert not _resolutions(session, tenant)

    batch = _batch(session, tenant, source_id, [_row()])
    with pytest.raises(UnratifiedMappingError):
        load_batch(
            session,
            batch=batch,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="ops"),
            source_type=SOURCE_TYPE_POSITIONS,
        )


def test_supersession_is_its_own_appended_fact_and_the_latest_row_governs(
    session: Session,
) -> None:
    """The invariant, enforced structurally rather than by an index.

    On an append-only log the incumbent's ratification is still there after it is superseded, so
    "is there a RATIFIED row" is true forever once it has been true once. The current decision is
    the LAST one made, and the seq uniqueness makes that unique by construction.
    """
    tenant = _tenant()
    source_id = _source(session, tenant)
    v1 = _ratified(session, tenant, source_id)
    v2 = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v2",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
        supersedes_id=v1.id,
    )
    ratify_mapping_version(
        session, mapping_version_id=v2.id, acting_tenant=tenant, actor_id=RATIFIER
    )
    session.flush()

    rows = _resolutions(session, tenant)
    assert [r.outcome for r in rows] == ["RATIFIED", "SUPERSEDED", "RATIFIED"]
    assert [r.seq for r in rows] == [1, 2, 3]
    # v1's ORIGINAL ratification is still on the log — it happened, and it is not erased
    assert rows[0].mapping_version_id == v1.id
    assert rows[1].mapping_version_id == v1.id  # the supersession, as its own fact
    assert rows[2].mapping_version_id == v2.id
    # ...and the gate follows the LATEST row
    current = ratified_mapping_for(
        session,
        acting_tenant=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
    )
    assert current.id == v2.id


def test_the_seq_is_monotonic_per_tenant_and_does_not_leak_across_tenants(
    session: Session,
) -> None:
    """A DB-monotonic ordering key, because a wall clock ties and two ratifiers acting in the same
    millisecond is exactly what this table adjudicates."""
    tenant_a, tenant_b = _tenant(), _tenant()
    _ratified(session, tenant_a, _source(session, tenant_a))
    _ratified(session, tenant_b, _source(session, tenant_b, code="OTHER"))
    session.flush()
    assert [r.seq for r in _resolutions(session, tenant_a)] == [1]
    assert [r.seq for r in _resolutions(session, tenant_b)] == [1]


# --- the withdraw verb (DS3b-6) ----------------------------------------------------------------


def test_the_proposer_can_withdraw_their_own_proposal(session: Session) -> None:
    """`STATUS_WITHDRAWN` was declared at S3a with no path producing it — the inert-state class the
    ENT-075 review struck when it deleted REJECTED. This is the verb that makes it real."""
    from irp_shared.ingest_mapping.models import STATUS_WITHDRAWN
    from irp_shared.ingest_mapping.service import withdraw_mapping_version

    tenant = _tenant()
    source_id = _source(session, tenant)
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
    )
    withdrawn = withdraw_mapping_version(
        session,
        mapping_version_id=version.id,
        acting_tenant=tenant,
        actor_id=PROPOSER,
        reason="the custodian re-issued the file with different headers",
    )
    session.flush()
    assert withdrawn.status == STATUS_WITHDRAWN
    rows = _resolutions(session, tenant)
    assert [r.outcome for r in rows] == ["WITHDRAWN"]
    assert rows[0].reason.startswith("the custodian")


def test_a_third_party_cannot_withdraw_someone_elses_proposal(session: Session) -> None:
    """Withdrawal is the PROPOSER's own act. Letting a third party do it would be a rejection verb
    wearing a withdrawal's name — and this platform deliberately has no rejection verb, because a
    checker's refusal to ratify is inaction."""
    from irp_shared.ingest_mapping.errors import NotTheProposerError
    from irp_shared.ingest_mapping.service import withdraw_mapping_version

    tenant = _tenant()
    source_id = _source(session, tenant)
    proposer = str(uuid.uuid4())
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=proposer,
    )
    with pytest.raises(NotTheProposerError):
        withdraw_mapping_version(
            session,
            mapping_version_id=version.id,
            acting_tenant=tenant,
            actor_id=str(uuid.uuid4()),
            reason="not mine to withdraw",
        )
    # ...and the UPPERCASE spelling of the proposer's OWN id is still the proposer (the S3a vector)
    ok = withdraw_mapping_version(
        session,
        mapping_version_id=version.id,
        acting_tenant=tenant,
        actor_id=proposer.upper(),
        reason="mine, spelled differently",
    )
    assert ok.status == "WITHDRAWN"


def test_a_withdrawn_version_cannot_load_and_cannot_be_ratified(session: Session) -> None:
    """The alternate-path half: a gate that fires only in the obvious state is not a control."""
    from irp_shared.ingest_mapping.service import withdraw_mapping_version

    tenant = _tenant()
    source_id = _source(session, tenant)
    _book(session, tenant)
    version = propose_mapping_version(
        session,
        tenant_id=tenant,
        data_source_id=source_id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="v1",
        operations=list(DEMO_OPS),
        actor_id=PROPOSER,
    )
    withdraw_mapping_version(
        session,
        mapping_version_id=version.id,
        acting_tenant=tenant,
        actor_id=PROPOSER,
        reason="withdrawn",
    )
    session.flush()
    with pytest.raises(MappingLifecycleError):
        ratify_mapping_version(
            session, mapping_version_id=version.id, acting_tenant=tenant, actor_id=RATIFIER
        )
    batch = _batch(session, tenant, source_id, [_row()])
    with pytest.raises(UnratifiedMappingError):
        load_batch(
            session,
            batch=batch,
            acting_tenant=tenant,
            actor=PositionActor(actor_id="ops"),
            source_type=SOURCE_TYPE_POSITIONS,
        )
