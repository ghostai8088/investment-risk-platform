"""Demo stage 28 (W19-S3a, REQ-INT-001) — a client file becomes a governed book.

    "Here is a position file. Watch the platform propose what its columns mean, watch me approve
    that, and watch the book load — governed, reproducible, and attributable to the mapping version
    that loaded it."

That sentence is the INGEST-1 record's own argument for why this slice exists, and this stage is it,
executed. Nothing here is a fixture short-cut: the file goes through the REAL anti-corruption layer
and the REAL data-quality gate, the mapping is a REAL model-drafted proposal ratified by a second
actor, and the positions are written by the interpreter through the governed binder.

**Its own book** (`DEMO-INGEST-UK`), per the stage-25 rule: a new holding in a SHARED demo book
moves every downstream golden; a new book moves none. That is also why D1 does not fire for this
slice — the loaded book is new, not one of the shared flat books the rename residual rests on.

What the stage executes, in order:

1. **A `staging.row` data-quality rule is registered.** Not decoration: ``stage_upload``'s gate is
   FAIL-CLOSED, so with no active rule every positions file is driven to REJECTED. Until this slice
   no such rule existed anywhere outside three test files, which means the demo would have rejected
   its own file and the failure would have read as a data problem.
2. **The file is staged** through ``stage_upload`` — anti-corruption, DQ, lineage, audit.
3. **The mapping is PROPOSED** with its model attribution: the registered drafting ``model_version``
   and the sha256 of the committed prompt. The operations are the ones the drafting act actually
   returned (``08_testing_qa/ingest_mapping_proposal/response.json``).
4. **A DIFFERENT actor RATIFIES it.** Self-ratification is refused (DS3a-3).
5. **The batch loads.** Four holdings, including a SHORT — which is the row that proves the
   anti-corruption quote is handled, because ``neutralize_cell`` prefixes every cell starting with
   ``-``.
6. **The book is read back** and every value checked against a hand-derived literal, then the
   EXPOSURE family runs **at a NON-ROOT node** — the D2 touch-trigger discharge for the touched
   chain.
7. **The load is reproduced**: re-interpreting the same staged rows under the same mapping version
   and the same ``lookup_as_of`` produces identical canonical values (clause 9).

Every golden below is hand-derived from the committed CSV, not a replay of the interpreter.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.demo.campaign import _CODE_VERSION, _ENVIRONMENT_ID, _T0, DEMO_TENANT_ID
from irp_shared.dq.service import register_dq_rule
from irp_shared.ingest_mapping.drafting import prompt_identity, register_drafting_model
from irp_shared.ingest_mapping.interpreter import ResolutionContext, interpret_row
from irp_shared.ingest_mapping.models import AUTHORSHIP_MODEL_PROPOSED, SOURCE_TYPE_POSITIONS
from irp_shared.ingest_mapping.service import (
    load_batch,
    propose_mapping_version,
    ratify_mapping_version,
)
from irp_shared.ingestion.models import IngestionStagedRecord
from irp_shared.ingestion.service import STAGING_ROW_TARGET, stage_upload
from irp_shared.lineage.service import register_data_source
from irp_shared.portfolio import PortfolioActor, create_portfolio
from irp_shared.portfolio.models import Portfolio
from irp_shared.position.models import Position
from irp_shared.position.service import PositionActor
from irp_shared.reference.identifier import create_identifier_xref
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.service import ReferenceActor

#: The committed artifacts of the drafting act. Repo-relative from this module:
#: .../packages/shared-python/src/irp_shared/demo/this.py -> up 5 lands on the repo root.
_REPO = pathlib.Path(__file__).resolve().parents[5]
_ARTIFACTS = _REPO / "08_testing_qa" / "ingest_mapping_proposal"
PROMPT_PATH = _ARTIFACTS / "prompt.md"
RESPONSE_PATH = _ARTIFACTS / "response.json"
CSV_FILENAME = "custodian_positions_2026-07-31.csv"
CSV_PATH = _ARTIFACTS / CSV_FILENAME

#: Relative refs stored on the mapping version — a reader follows them to the repo, not to a path
#: on the machine that happened to run the seed.
PROMPT_REF = "08_testing_qa/ingest_mapping_proposal/prompt.md"
RESPONSE_REF = "08_testing_qa/ingest_mapping_proposal/response.json"

_BOOK_CODE = "DEMO-INGEST-UK"
_SLEEVE_CODE = "DEMO-INGEST-UK-EQ"
_SOURCE_CODE = "DEMO-CUSTODIAN-A"
_AS_OF = datetime(2026, 7, 31, tzinfo=UTC)
_MARK_DATE = date(2026, 7, 31)

_PROPOSER = "onboarding.analyst@demo"
_RATIFIER = "data.steward@demo"

#: The instruments the file's SEDOLs must resolve to, seeded before the load so the code-lookup has
#: something to find. (name, internal code, SEDOL, asset class).
_SECURITIES: tuple[tuple[str, str, str, str], ...] = (
    ("Vodafone Group plc", "VOD-LN", "B1YW440", "EQUITY"),
    ("BP p.l.c.", "BP-LN", "0798059", "EQUITY"),
    ("UK Treasury 4.25% 2032", "UKT-4Q-32", "BLH38Y1", "GOVERNMENT_BOND"),
    ("Diageo plc", "DGE-LN", "0237400", "EQUITY"),
)

#: HAND-DERIVED from the committed CSV — nominal (thousands) x 1000, the book cost verbatim, and
#: the ACCOUNT the file's own `Account Ref` column names. Worked from the file, never from the
#: interpreter's output. The file names TWO accounts on purpose: the equities land in the SLEEVE and
#: the gilt at the root, which is both realistic and what gives the D2 non-root run something to
#: compute over — an exposure run against an EMPTY scope is refused by design.
#: SEDOL -> (quantity, cost_basis, unit, account ref, mark per unit)
_EXPECTED: dict[str, tuple[Decimal, Decimal, str, str, Decimal]] = {
    "B1YW440": (Decimal("12500.000"), Decimal("48150.00"), "SHARES", _SLEEVE_CODE, Decimal("4.10")),
    "0798059": (Decimal("8250.000"), Decimal("38940.50"), "SHARES", _SLEEVE_CODE, Decimal("4.85")),
    "BLH38Y1": (Decimal("150000.000"), Decimal("147375.00"), "PAR", _BOOK_CODE, Decimal("0.9925")),
    # THE SHORT. -3.2 thousands = -3,200, and it only parses because the numeric path strips the
    # anti-corruption quote `neutralize_cell` puts on any cell starting with `-`.
    "0237400": (
        Decimal("-3200.000"),
        Decimal("-8120.00"),
        "SHARES",
        _SLEEVE_CODE,
        Decimal("25.40"),
    ),
}


class DemoIngest1AlreadySeededError(RuntimeError):
    """The DEMO-INGEST-UK book already exists — refuse-not-skip, the campaign rule."""


class DemoIngest1Error(RuntimeError):
    """A stage-28 invariant did not hold."""


@dataclass(frozen=True)
class Ingest1StageSummary:
    tenant_id: str
    book_id: str
    sleeve_id: str
    data_source_id: str
    batch_id: str
    mapping_version_id: str
    model_version_id: str
    loaded_rows: int
    lookups: dict[str, int]
    short_quantity: Decimal


def committed_operations() -> list[dict[str, object]]:
    """The operations the drafting act actually returned, read from the committed envelope.

    Read rather than re-typed on purpose: if this list were transcribed into the module, the
    recorded provenance would drift from the artifact it claims to come from and nothing would
    notice. ``test_ingest1_stage28.py`` also pins the prompt hash against the committed prompt.
    """
    envelope = json.loads(RESPONSE_PATH.read_text())
    return list(envelope["operations"])


def run_demo_ingest1_stage28(session: Session, *, actor_id: str) -> Ingest1StageSummary:
    """Propose -> ratify -> load -> read back -> run the exposure family at a NON-ROOT node."""
    existing = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _BOOK_CODE)
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoIngest1AlreadySeededError(
            f"portfolio {_BOOK_CODE} already exists — re-seed from a clean database"
        )

    pf_actor = PortfolioActor(actor_id=actor_id)
    ref_actor = ReferenceActor(actor_id=actor_id)

    # --- the book: a root the file's Account Ref names, and a sleeve for the NON-ROOT read ------
    book = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_BOOK_CODE,
        name="Demo UK pension book (loaded from a custodian file)",
        node_type="FUND",
        base_currency_code="GBP",
        actor=pf_actor,
    )
    sleeve = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_SLEEVE_CODE,
        name="Demo UK equity sleeve",
        node_type="STRATEGY",
        parent_portfolio_id=book.id,
        actor=pf_actor,
    )

    # --- the security master the code-lookup resolves against ---------------------------------
    for name, code, sedol, asset_class in _SECURITIES:
        instrument = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class=asset_class,
            currency_code="GBP",
            actor=ref_actor,
        )
        create_identifier_xref(
            session,
            tenant_id=DEMO_TENANT_ID,
            instrument_id=instrument.id,
            scheme="SEDOL",
            value=sedol,
            actor=ref_actor,
            valid_from=_T0,
        )
    session.flush()

    # --- 1. the DQ rule the fail-closed gate requires ------------------------------------------
    register_dq_rule(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="POSITIONS-SEDOL-PRESENT",
        name="every staged positions row carries a SEDOL",
        rule_type="NOT_NULL",
        target_entity_type=STAGING_ROW_TARGET,
        severity="ERROR",
        params={"column": "SEDOL"},
        actor_id=actor_id,
    )
    session.flush()

    # --- 2. the file, through the REAL anti-corruption + DQ path -------------------------------
    source = register_data_source(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_SOURCE_CODE,
        name="Demo custodian A — daily positions",
        source_type="upload",
        actor_id=actor_id,
    )
    batch = stage_upload(
        session,
        tenant_id=DEMO_TENANT_ID,
        data_source_id=source.id,
        filename=CSV_FILENAME,
        content_type="text/csv",
        raw_bytes=CSV_PATH.read_bytes(),
        actor_id=actor_id,
    )
    if batch.staged_count != len(_EXPECTED):
        raise DemoIngest1Error(
            f"staged {batch.staged_count} rows, expected {len(_EXPECTED)} — the file or the "
            "anti-corruption layer changed under this stage"
        )

    # --- 3. the PROPOSAL, attributed to the registered drafting model --------------------------
    _model, model_version = register_drafting_model(
        session, tenant_id=DEMO_TENANT_ID, actor_id=actor_id
    )
    proposed = propose_mapping_version(
        session,
        tenant_id=DEMO_TENANT_ID,
        data_source_id=source.id,
        source_type=SOURCE_TYPE_POSITIONS,
        version_label="custodian-a-positions-v1",
        operations=committed_operations(),
        actor_id=_PROPOSER,
        authorship=AUTHORSHIP_MODEL_PROPOSED,
        proposer_model_version_id=model_version.id,
        proposal_prompt_hash=prompt_identity(PROMPT_PATH.read_bytes()),
        proposal_prompt_ref=PROMPT_REF,
        proposal_response_ref=RESPONSE_REF,
    )

    # --- 4. a DIFFERENT actor ratifies ---------------------------------------------------------
    mapping = ratify_mapping_version(
        session,
        mapping_version_id=proposed.id,
        acting_tenant=DEMO_TENANT_ID,
        actor_id=_RATIFIER,
    )
    if mapping.ratified_by_actor_id == mapping.proposed_by_actor_id:
        raise DemoIngest1Error("the ratifier is the proposer — four-eyes did not hold")

    # --- 5. the load ---------------------------------------------------------------------------
    result = load_batch(
        session,
        batch=batch,
        acting_tenant=DEMO_TENANT_ID,
        actor=PositionActor(actor_id=actor_id),
        source_type=SOURCE_TYPE_POSITIONS,
    )
    session.flush()
    if result.row_count != len(_EXPECTED):
        raise DemoIngest1Error(f"loaded {result.row_count} rows, expected {len(_EXPECTED)}")
    if result.lookups.get("SEDOL") != len(_EXPECTED):
        raise DemoIngest1Error(
            f"code-lookup ran {result.lookups} times — the P18 positive control for clause 9: a "
            "load that resolved nothing is indistinguishable from one that resolved by luck"
        )

    # --- 6. read back, against HAND-DERIVED literals -------------------------------------------
    short_quantity = _verify_book(session)

    # marks, so the D2 non-root run has something to compute over
    _mark_the_book(session, actor_id=actor_id)

    # the D2 discharge: the exposure family, at a NON-ROOT node, over the loaded book
    _run_exposure_at_non_root(session, actor_id=actor_id, sleeve_id=sleeve.id)

    # --- 7. reproduce: same mapping + same staged rows + same as-of -> identical values ---------
    _verify_reproducible(session, batch_id=batch.id, mapping=mapping, as_of=result.lookup_as_of)

    return Ingest1StageSummary(
        tenant_id=DEMO_TENANT_ID,
        book_id=book.id,
        sleeve_id=sleeve.id,
        data_source_id=source.id,
        batch_id=batch.id,
        mapping_version_id=mapping.id,
        model_version_id=str(model_version.id),
        loaded_rows=result.row_count,
        lookups=dict(result.lookups),
        short_quantity=short_quantity,
    )


def _verify_book(session: Session) -> Decimal:
    """Every loaded holding against its hand-derived literal, and the SHORT against its sign."""
    from irp_shared.reference.models import IdentifierXref

    node_ids = {
        code: str(pid)
        for code, pid in session.execute(
            select(Portfolio.code, Portfolio.id).where(
                Portfolio.tenant_id == DEMO_TENANT_ID,
                Portfolio.code.in_((_BOOK_CODE, _SLEEVE_CODE)),
            )
        ).all()
    }
    rows = (
        session.execute(
            select(Position).where(
                Position.portfolio_id.in_(list(node_ids.values())),
                Position.valid_to.is_(None),
                Position.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )
    if len(rows) != len(_EXPECTED):
        raise DemoIngest1Error(f"{len(rows)} open holdings, expected {len(_EXPECTED)}")

    by_instrument = {row.instrument_id: row for row in rows}
    short_quantity: Decimal | None = None
    for sedol, (quantity, cost, unit, _account, _mark) in _EXPECTED.items():  # noqa: B007
        xref = session.execute(
            select(IdentifierXref).where(
                IdentifierXref.tenant_id == DEMO_TENANT_ID,
                IdentifierXref.scheme == "SEDOL",
                IdentifierXref.value == sedol,
                IdentifierXref.valid_to.is_(None),
            )
        ).scalar_one()
        row = by_instrument.get(str(xref.entity_id))
        if row is None:
            raise DemoIngest1Error(f"SEDOL {sedol} did not load")
        if Decimal(row.quantity) != quantity:
            raise DemoIngest1Error(f"{sedol}: quantity {row.quantity} != {quantity}")
        if row.cost_basis is None or Decimal(row.cost_basis) != cost:
            raise DemoIngest1Error(f"{sedol}: cost_basis {row.cost_basis} != {cost}")
        if row.quantity_unit != unit:
            raise DemoIngest1Error(f"{sedol}: unit {row.quantity_unit!r} != {unit!r}")
        # The `Account Ref` column routed the row: the file decides which node a holding lands in,
        # which is what makes `rename -> portfolio_code` a real mapping rather than a constant.
        if row.portfolio_id != node_ids.get(_account):
            raise DemoIngest1Error(
                f"{sedol}: landed in node {row.portfolio_id}, expected the {_account} account"
            )
        # the amended requirement BANS free-text attribution
        if row.position_source is not None:
            raise DemoIngest1Error(
                f"{sedol}: position_source is populated — the amended REQ-INT-001 bans free-text "
                "attribution, and the mapping version is the binding"
            )
        if quantity < 0:
            short_quantity = Decimal(row.quantity)

    if short_quantity is None or short_quantity >= 0:
        raise DemoIngest1Error(
            "the SHORT position did not land negative — the anti-corruption layer prefixes any "
            "cell starting with '-', so this is the row that proves the numeric path handles it"
        )
    return short_quantity


def _mark_the_book(session: Session, *, actor_id: str) -> None:
    """One governed mark per loaded holding, at the file's own valuation date.

    Marks are CAPTURED here rather than loaded: this slice's mapping vocabulary targets positions
    (OQ-ING-4 = one source type, end to end, first), so prices are the next source type, not a
    silent extra target snuck into this one.
    """
    from irp_shared.reference.models import IdentifierXref
    from irp_shared.valuation import create_valuation
    from irp_shared.valuation.service import ValuationActor

    node_ids = {
        code: str(pid)
        for code, pid in session.execute(
            select(Portfolio.code, Portfolio.id).where(
                Portfolio.tenant_id == DEMO_TENANT_ID,
                Portfolio.code.in_((_BOOK_CODE, _SLEEVE_CODE)),
            )
        ).all()
    }
    actor = ValuationActor(actor_id=actor_id)
    for sedol, (_q, _c, _u, account, mark) in _EXPECTED.items():
        instrument_id = session.execute(
            select(IdentifierXref.entity_id).where(
                IdentifierXref.tenant_id == DEMO_TENANT_ID,
                IdentifierXref.scheme == "SEDOL",
                IdentifierXref.value == sedol,
                IdentifierXref.valid_to.is_(None),
            )
        ).scalar_one()
        create_valuation(
            session,
            portfolio_id=node_ids[account],
            instrument_id=str(instrument_id),
            valuation_date=_MARK_DATE,
            acting_tenant=DEMO_TENANT_ID,
            actor=actor,
            mark_value=mark,
            currency_code="GBP",
            # valid_from = the campaign epoch, NOT "now". The exposure run reads as-of the file's
            # valuation date (2026-07-31); a mark whose validity starts at wall-clock now would be
            # invisible to it, the component set would carry positions with no marks, and the
            # snapshot completeness rule would fail. Caught by the full-PG battery, which is the
            # only tier that runs the governed chain over this book.
            valid_from=_T0,
        )
    session.flush()


def _run_exposure_at_non_root(session: Session, *, actor_id: str, sleeve_id: str) -> None:
    """D2's touch-trigger discharge: the exposure family, over the loaded book, at a NON-ROOT node.

    The sleeve holds THREE of the four loaded holdings, because the file's own ``Account Ref``
    column routed them there. That matters: an exposure run over an EMPTY scope is REFUSED by
    design (``EmptySnapshotError``, fail-closed), so a non-root run against a node with no holdings
    would prove nothing at all — it would raise for a reason that has nothing to do with D2. The
    first draft of this stage made exactly that mistake and the full-PG battery caught it.

    Any exception propagates: a D2 discharge that swallowed a failure would be worse than none.
    """
    from irp_shared.exposure import ExposureActor, run_exposure

    run_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        portfolio_id=sleeve_id,
        as_of_valid_at=_AS_OF,
        base_currency="GBP",
    )


def _verify_reproducible(
    session: Session, *, batch_id: str, mapping: object, as_of: datetime
) -> None:
    """Clause (9): mapping version + staged file + code-lookup reference data AS OF the load.

    Re-interprets the SAME staged rows under the SAME ratified operations at the SAME recorded
    instant and requires identical canonical values. This is the honest form of the claim: it
    re-executes the interpreter rather than re-reading the rows it wrote, because comparing a
    stored row to itself proves nothing (the smoke-that-compared-a-report-to-itself class).
    """
    staged = (
        session.execute(
            select(IngestionStagedRecord)
            .where(IngestionStagedRecord.batch_id == batch_id)
            .order_by(IngestionStagedRecord.row_number)
        )
        .scalars()
        .all()
    )
    operations = list(mapping.operations)  # type: ignore[attr-defined]
    first = [
        interpret_row(
            operations,
            dict(record.payload),
            record.row_number,
            ResolutionContext(session=session, acting_tenant=DEMO_TENANT_ID, lookup_as_of=as_of),
        )
        for record in staged
    ]
    second = [
        interpret_row(
            operations,
            dict(record.payload),
            record.row_number,
            ResolutionContext(session=session, acting_tenant=DEMO_TENANT_ID, lookup_as_of=as_of),
        )
        for record in staged
    ]
    if first != second:
        raise DemoIngest1Error("the load is NOT reproducible from its own three recorded inputs")
    digest = hashlib.sha256(
        json.dumps([{k: str(v) for k, v in row.items()} for row in first], sort_keys=True).encode()
    ).hexdigest()
    if not digest:  # pragma: no cover - a sha256 is never empty
        raise DemoIngest1Error("reproduction digest is empty")
