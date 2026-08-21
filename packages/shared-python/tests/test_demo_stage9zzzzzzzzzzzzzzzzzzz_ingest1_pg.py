"""The W19-S3a demo-stage suite (stage 28) — a client file becomes a governed book, live on PG.

The stage itself asserts the load against hand-derived literals, the code-lookup positive control,
the four-eyes ratification and the reproduction. This suite proves the END STATE under RLS, from the
STORED rows: the batch's mapping binding, the provenance a reviewer would actually follow, the
lineage rooted at the custodian feed rather than at MANUAL, and the short position's sign.

Filename z-count = 19: alpha-sort runs this AFTER stage 27. Its own book, so it moves no golden.
"""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, run_demo_ingest1_stage28
from irp_shared.demo.ingest1_stage28 import (
    _BOOK_CODE,
    _EXPECTED,
    _SLEEVE_CODE,
    _SOURCE_CODE,
    CSV_FILENAME,
    PROMPT_PATH,
    PROMPT_REF,
    RESPONSE_PATH,
    DemoIngest1AlreadySeededError,
    committed_operations,
)
from irp_shared.ingest_mapping.models import (
    AUTHORSHIP_MODEL_PROPOSED,
    STATUS_RATIFIED,
    IngestionMappingVersion,
)
from irp_shared.ingestion.models import IngestionBatch
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.portfolio.models import Portfolio
from irp_shared.position.models import Position

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def staged():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        from irp_shared.entitlement.models import AppUser

        actor = session.execute(
            select(AppUser.id).where(AppUser.tenant_id == DEMO_TENANT_ID).limit(1)
        ).scalar_one()
        try:
            run_demo_ingest1_stage28(session, actor_id=str(actor))
            session.commit()
        except DemoIngest1AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory


def _session(factory):  # noqa: ANN001, ANN202
    session = factory()
    persistent_tenant_context(session, DEMO_TENANT_ID)
    return session


def _mapping(session) -> IngestionMappingVersion:  # noqa: ANN001
    return session.execute(
        select(IngestionMappingVersion).where(
            IngestionMappingVersion.tenant_id == DEMO_TENANT_ID,
            IngestionMappingVersion.status == STATUS_RATIFIED,
        )
    ).scalar_one()


def test_the_batch_binds_the_ratified_mapping_and_records_its_as_of(staged) -> None:  # noqa: ANN001
    """Clause (2), the batch half, and clause (9)'s third input — read from the STORED row."""
    session = _session(staged)
    try:
        mapping = _mapping(session)
        batch = session.execute(
            select(IngestionBatch).where(
                IngestionBatch.tenant_id == DEMO_TENANT_ID,
                IngestionBatch.mapping_version_id.is_not(None),
            )
        ).scalar_one()
        assert batch.mapping_version_id == mapping.id
        assert batch.lookup_as_of is not None, (
            "the batch recorded no lookup_as_of — clause (9)'s third input would be an assumption "
            "a re-run could not read back"
        )
        assert batch.staged_count == len(_EXPECTED)
    finally:
        session.close()


def test_the_mapping_carries_checkable_model_provenance(staged) -> None:  # noqa: ANN001
    """Clause (7). The point of a hash is that a reviewer can RECOMPUTE it, so this recomputes it
    from the committed prompt rather than asserting the field is non-empty."""
    session = _session(staged)
    try:
        mapping = _mapping(session)
        assert mapping.authorship == AUTHORSHIP_MODEL_PROPOSED
        assert mapping.proposer_model_version_id is not None
        assert mapping.proposal_prompt_ref == PROMPT_REF
        expected = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()
        assert mapping.proposal_prompt_hash == expected, (
            "the recorded prompt hash does not match the committed prompt — the provenance points "
            "at an artifact that is not the one it names"
        )
    finally:
        session.close()


def test_the_stored_operations_are_the_ones_the_drafting_act_returned(staged) -> None:  # noqa: ANN001
    """A transcription check with teeth: the stored operations must equal the committed envelope's,
    so the mapping in the database and the artifact its provenance names cannot drift apart."""
    session = _session(staged)
    try:
        mapping = _mapping(session)
        assert list(mapping.operations) == committed_operations()
        envelope = json.loads(RESPONSE_PATH.read_text())
        assert envelope["prompt_sha256"] == mapping.proposal_prompt_hash
    finally:
        session.close()


def test_four_eyes_held_on_the_demonstrating_ratification(staged) -> None:  # noqa: ANN001
    session = _session(staged)
    try:
        mapping = _mapping(session)
        assert mapping.ratified_by_actor_id
        assert mapping.ratified_by_actor_id != mapping.proposed_by_actor_id
        assert mapping.ratified_at is not None
    finally:
        session.close()


def test_the_loaded_book_matches_its_hand_derived_literals(staged) -> None:  # noqa: ANN001
    """Read back from the persisted rows, not from the loader's return value."""
    session = _session(staged)
    try:
        node_ids = [
            str(pid)
            for pid in session.execute(
                select(Portfolio.id).where(
                    Portfolio.tenant_id == DEMO_TENANT_ID,
                    Portfolio.code.in_((_BOOK_CODE, _SLEEVE_CODE)),
                )
            )
            .scalars()
            .all()
        ]
        assert len(node_ids) == 2
        rows = (
            session.execute(
                select(Position).where(
                    Position.portfolio_id.in_(node_ids),
                    Position.valid_to.is_(None),
                    Position.system_to.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == len(_EXPECTED)
        quantities = sorted(Decimal(r.quantity) for r in rows)
        assert quantities == sorted(q for q, _c, _u, _a, _m in _EXPECTED.values())
        # THREE of the four landed in the sleeve, because the file's Account Ref said so — the
        # mapping ROUTES rows, it does not stamp one constant node onto the whole file.
        sleeve_id = str(
            session.execute(
                select(Portfolio.id).where(
                    Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _SLEEVE_CODE
                )
            ).scalar_one()
        )
        assert sum(1 for r in rows if r.portfolio_id == sleeve_id) == 3
        # the amended requirement BANS free-text attribution
        assert all(r.position_source is None for r in rows)
    finally:
        session.close()


def test_the_short_position_landed_negative(staged) -> None:  # noqa: ANN001
    """The row that proves the anti-corruption interaction is handled.

    ``neutralize_cell`` prefixes ``'`` to any cell starting with ``-``, so a short arrives at the
    interpreter as ``'-3.2``. Without the numeric-path repair the platform could not load ANY book
    containing a short, while ``position.quantity`` is documented as signed.
    """
    session = _session(staged)
    try:
        shorts = (
            session.execute(
                select(Position).where(
                    Position.tenant_id == DEMO_TENANT_ID,
                    Position.quantity < 0,
                    Position.valid_to.is_(None),
                    Position.system_to.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert any(Decimal(r.quantity) == Decimal("-3200.000") for r in shorts)
    finally:
        session.close()


def test_every_loaded_row_is_attributed_to_the_custodian_feed_not_manual(staged) -> None:  # noqa: ANN001
    """DS3a-4, on the stored lineage. A file-loaded holding recorded as MANUAL entry would be a
    false provenance record — worse than none, because nothing distinguishes it from a hand
    capture."""
    session = _session(staged)
    try:
        custodian_id = session.execute(
            select(DataSource.id).where(
                DataSource.tenant_id == DEMO_TENANT_ID, DataSource.code == _SOURCE_CODE
            )
        ).scalar_one()
        manual_id = session.execute(
            select(DataSource.id).where(
                DataSource.tenant_id == DEMO_TENANT_ID, DataSource.code == "MANUAL"
            )
        ).scalar_one_or_none()

        node_ids = [
            str(pid)
            for pid in session.execute(
                select(Portfolio.id).where(
                    Portfolio.tenant_id == DEMO_TENANT_ID,
                    Portfolio.code.in_((_BOOK_CODE, _SLEEVE_CODE)),
                )
            )
            .scalars()
            .all()
        ]
        loaded = (
            session.execute(
                select(Position.id).where(
                    Position.portfolio_id.in_(node_ids),
                    Position.system_to.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert loaded
        # Scoped to DATA_SOURCE-rooted edges deliberately. A loaded position also carries a
        # SNAPSHOT-rooted ORIGIN edge once a governed run pins it (three of these four are in the
        # sleeve the D2 exposure run covers), and that edge is a different claim entirely — where
        # the RUN read the row from, not where the ROW came from. Counting both together would
        # make this assertion pass or fail on whether a run happened to have executed.
        edges = (
            session.execute(
                select(LineageEdge).where(
                    LineageEdge.target_entity_type == "position",
                    LineageEdge.source_type == "data_source",
                    LineageEdge.target_entity_id.in_([str(p) for p in loaded]),
                )
            )
            .scalars()
            .all()
        )
        assert len(edges) == len(loaded), (
            "every loaded holding must carry EXACTLY ONE data-source ORIGIN edge — one missing is "
            "an unattributed holding, and two is an ambiguous one"
        )
        assert {str(e.source_id) for e in edges} == {str(custodian_id)}
        assert {e.edge_kind for e in edges} == {"ORIGIN"}
        if manual_id is not None:
            assert str(manual_id) not in {str(e.source_id) for e in edges}
    finally:
        session.close()


def test_the_committed_csv_is_what_the_stage_loaded(staged) -> None:  # noqa: ANN001
    """A conformance pin between the committed artifact and the persisted batch. Without it the
    file could be edited and the stage would keep asserting stale literals."""
    session = _session(staged)
    try:
        batch = session.execute(
            select(IngestionBatch).where(
                IngestionBatch.tenant_id == DEMO_TENANT_ID,
                IngestionBatch.mapping_version_id.is_not(None),
            )
        ).scalar_one()
        from irp_shared.demo.ingest1_stage28 import CSV_PATH

        assert batch.filename == CSV_FILENAME
        assert batch.byte_size == len(CSV_PATH.read_bytes())
    finally:
        session.close()
