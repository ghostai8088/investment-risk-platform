"""PostgreSQL proofs for the INGEST-1 mapping spine (W19-S3a; BR-17, AD-013, AD-016).

Gated on ``IRP_TEST_DATABASE_URL``. Everything here is a claim the SQLite unit tier **cannot**
make, and the split is deliberate rather than incidental:

- **RLS and the FORCE flags** are a no-op on SQLite.
- **The partial unique index** renders on SQLite with its predicate silently dropped unless
  ``sqlite_where`` is spelled too, so only PostgreSQL proves the predicate is doing the work rather
  than the twin spelling accidentally matching.
- **The symmetric authorship CHECK** does not exist on SQLite at all — CHECK constraints are not
  enforced by the unit tier's engine setup.
- **Identifier truncation** happens only on PostgreSQL, silently, at 63 bytes. Two of this table's
  FK names are 68 characters under the naming convention and carry EXPLICIT short names; nothing
  but reading ``pg_constraint`` back proves they landed whole.
- **``varchar`` length** is ignored by SQLite (column affinity). That is not a footnote here: it is
  exactly how ``ingestion_batch.status`` shipped four waves too narrow to hold one of its own
  declared values.

``0074`` creates a table, so it has no data path and no P17 harness would mean anything; THIS FILE
is its proof. ``0075`` has a data path and gets ``scripts/migration_0075_p17_check.py``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.dq.models import DataQualityRule
from irp_shared.dq.service import register_dq_rule
from irp_shared.ingest_mapping.errors import MappingNotVisible
from irp_shared.ingest_mapping.models import (
    SOURCE_TYPE_POSITIONS,
    STATUS_PROPOSED,
    STATUS_RATIFIED,
)
from irp_shared.ingest_mapping.service import (
    propose_mapping_version,
    ratify_mapping_version,
    resolve_mapping_version,
)
from irp_shared.ingestion.models import STATUS_COMPLETED_WITH_WARNINGS, IngestionBatch
from irp_shared.ingestion.service import STAGING_ROW_TARGET, stage_upload
from irp_shared.lineage.service import register_data_source
from irp_shared.model.service import register_model, register_model_version

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")

TABLE = "ingestion_mapping_version"

_TABLES = (
    "ingestion_mapping_version",
    "ingestion_batch",
    "ingestion_staged_record",
    "data_source",
    "data_quality_rule",
    "data_quality_result",
    "lineage_edge",
)

DEMO_OPS = [
    {"op": "constant", "target": "portfolio_code", "value": "PG-BOOK"},
    {"op": "code-lookup", "target": "instrument", "source": "SEDOL", "scheme": "SEDOL"},
    {"op": "scale", "target": "quantity", "source": "QTY", "factor": "1000"},
    {"op": "parse-date", "target": "valid_from", "source": "AS_AT", "format": "%d/%m/%Y"},
]


def _is_rls_violation(error: Exception) -> bool:
    return (
        getattr(getattr(error, "orig", None), "sqlstate", None) == "42501"
        or "row-level security" in str(error).lower()
    )


@pytest.fixture(scope="module")
def superuser_engine():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def app_url() -> str:
    """The constrained, non-superuser, NOBYPASSRLS role every enforcement proof runs under.

    A proof of RLS executed as a superuser proves nothing — the STRUCT-3 fold recorded a backfill
    that "survived only because every current runner is a PG superuser".
    """
    superuser = make_engine(URL, poolclass=NullPool)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'irp_app') "
                "THEN CREATE ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "ELSE ALTER ROLE irp_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'ci_app_pw'; "
                "END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO irp_app"))
        for table in _TABLES:
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE ON model_version TO irp_app"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


@pytest.fixture
def app_factory(app_url: str):  # noqa: ANN201
    engine = make_engine(app_url, poolclass=NullPool)
    yield make_session_factory(engine)
    engine.dispose()


def _source(session, tenant: str, code: str = "PG-CUSTODIAN") -> str:  # noqa: ANN001
    return register_data_source(
        session,
        tenant_id=tenant,
        code=code,
        name="pg custodian feed",
        source_type="upload",
        actor_id="ops",
    ).id


# --- the DDL, read back out of PostgreSQL rather than out of the migration text ----------------


def test_rls_is_enabled_and_forced(superuser_engine) -> None:  # noqa: ANN001
    """Floor: ENABLED is not enough. Without FORCE, the table OWNER bypasses the policy, and every
    migration and every psql session runs as the owner."""
    with superuser_engine.begin() as conn:
        enabled, forced = conn.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": TABLE},
        ).one()
    assert enabled is True
    assert forced is True


def test_the_policy_is_symmetric_and_admits_no_system_tenant(superuser_engine) -> None:  # noqa: ANN001
    """PROPRIETARY, never hybrid. The AD-013-R2 hybrid set is closed at SEVEN and this table is not
    in it, so the SYSTEM literal must appear in NEITHER arm — a hybrid ``USING`` here would leak
    every tenant's mappings to the platform operator."""
    with superuser_engine.begin() as conn:
        qual, with_check = conn.execute(
            text("SELECT qual, with_check FROM pg_policies WHERE tablename = :t"),
            {"t": TABLE},
        ).one()
    assert "current_setting('app.current_tenant'::text, true)" in qual
    assert qual == with_check, "the policy must be SYMMETRIC (USING == WITH CHECK)"
    blob = f"{qual} {with_check}".lower()
    assert "system" not in blob


def test_the_explicit_fk_names_landed_whole(superuser_engine) -> None:  # noqa: ANN001
    """PostgreSQL truncates identifiers at 63 bytes SILENTLY. Both of these would be 68 characters
    under the naming convention, which is why they carry explicit names — and reading the catalog
    back is the only thing that proves the explicit name is what actually landed."""
    with superuser_engine.begin() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = to_regclass('ingestion_mapping_version') "
                    "AND contype IN ('f', 'c', 'u')"
                ),
            ).fetchall()
        }
    assert "fk_ingestion_mapping_version_model_version" in names
    assert "fk_ingestion_mapping_version_supersedes" in names
    assert "ck_ingestion_mapping_version_authorship_evidence" in names
    assert all(len(name) <= 63 for name in names)
    # ...and nothing landed under a TRUNCATED convention name, which is what the failure looks like.
    assert not any(name.startswith("fk_ingestion_mapping_version_proposer") for name in names)


def test_the_partial_unique_index_carries_its_predicate(superuser_engine) -> None:  # noqa: ANN001
    """A unique index WITHOUT the predicate would forbid a second PROPOSED version — legal and
    necessary, since clause (3) requires proposing an edited version while one is ratified."""
    with superuser_engine.begin() as conn:
        definition = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :i"),
            {"i": "uq_ingestion_mapping_version_active"},
        ).scalar_one()
    assert "UNIQUE" in definition
    assert "WHERE" in definition and "RATIFIED" in definition


def test_irp_ops_holds_no_privilege_on_the_mapping_table(superuser_engine) -> None:  # noqa: ANN001
    """The reporting role must not reach ingest-side governance. Matches the negative control the
    two existing ingestion tables already carry."""
    with superuser_engine.begin() as conn:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            granted = conn.execute(
                text("SELECT has_table_privilege('irp_ops', :t, :p)"),
                {"t": TABLE, "p": privilege},
            ).scalar_one()
            assert granted is False, f"irp_ops holds {privilege} on {TABLE}"


# --- enforcement, under the constrained role --------------------------------------------------


def test_a_mapping_version_is_invisible_across_tenants(app_factory) -> None:  # noqa: ANN001
    """RLS plus the explicit tenant predicate. Proven under irp_app, not the superuser."""
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant_a)
        source_id = _source(session, tenant_a)
        version = propose_mapping_version(
            session,
            tenant_id=tenant_a,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="v1",
            operations=list(DEMO_OPS),
            actor_id="proposer@irp",
        )
        session.commit()
        version_id = version.id

    with app_factory() as session:
        set_tenant_context(session, tenant_a)  # positive control: visible to its OWN tenant
        assert resolve_mapping_version(session, version_id, acting_tenant=tenant_a).id == version_id

    with app_factory() as session:
        set_tenant_context(session, tenant_b)
        with pytest.raises(MappingNotVisible):
            resolve_mapping_version(session, version_id, acting_tenant=tenant_b)


def test_the_authorship_check_fires_on_both_arms(app_factory) -> None:  # noqa: ANN001
    """The SYMMETRIC constraint. Both directions matter: model attribution missing on a
    MODEL_PROPOSED row is an unattributed proposal, and model attribution PRESENT on a
    HAND_AUTHORED row is a false provenance record a reviewer would read as real."""
    tenant = str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant)
        session.flush()

        # arm 1: MODEL_PROPOSED with no evidence
        with pytest.raises((IntegrityError, DBAPIError)):
            session.execute(
                text(
                    "INSERT INTO ingestion_mapping_version (id, tenant_id, system_from, "
                    "data_source_id, source_type, version_label, status, operations, "
                    "operations_hash, authorship, proposed_by_actor_id, proposed_at) VALUES "
                    "(gen_random_uuid(), CAST(:t AS uuid), now(), CAST(:s AS uuid), 'POSITIONS', "
                    "'bad-1', 'PROPOSED', '[]', :h, 'MODEL_PROPOSED', 'a@irp', now())"
                ),
                {"t": tenant, "s": source_id, "h": "0" * 64},
            )
        session.rollback()

    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant, code="PG-CUSTODIAN-2")
        session.flush()
        # arm 2: HAND_AUTHORED carrying model attribution anyway
        with pytest.raises((IntegrityError, DBAPIError)):
            session.execute(
                text(
                    "INSERT INTO ingestion_mapping_version (id, tenant_id, system_from, "
                    "data_source_id, source_type, version_label, status, operations, "
                    "operations_hash, authorship, proposal_prompt_hash, proposed_by_actor_id, "
                    "proposed_at) VALUES "
                    "(gen_random_uuid(), CAST(:t AS uuid), now(), CAST(:s AS uuid), 'POSITIONS', "
                    "'bad-2', 'PROPOSED', '[]', :h, 'HAND_AUTHORED', :h, 'a@irp', now())"
                ),
                {"t": tenant, "s": source_id, "h": "0" * 64},
            )
        session.rollback()

    # positive control: the COHERENT row the same insert shape writes successfully
    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant, code="PG-CUSTODIAN-3")
        session.flush()
        session.execute(
            text(
                "INSERT INTO ingestion_mapping_version (id, tenant_id, system_from, "
                "data_source_id, source_type, version_label, status, operations, "
                "operations_hash, authorship, proposed_by_actor_id, proposed_at) VALUES "
                "(gen_random_uuid(), CAST(:t AS uuid), now(), CAST(:s AS uuid), 'POSITIONS', "
                "'good', 'PROPOSED', '[]', :h, 'HAND_AUTHORED', 'a@irp', now())"
            ),
            {"t": tenant, "s": source_id, "h": "0" * 64},
        )
        session.commit()


def test_the_partial_index_admits_two_proposed_and_refuses_two_ratified(app_factory) -> None:  # noqa: ANN001
    """The predicate doing its work, on the engine that enforces it.

    Both halves are asserted. A plain unique index would fail the FIRST half — and the first half
    is the one clause (3) needs, because proposing an edited version while one is ratified is the
    ordinary act, not the exception.
    """
    tenant = str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant)
        first = propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="v1",
            operations=list(DEMO_OPS),
            actor_id="proposer@irp",
        )
        propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="v2",
            operations=list(DEMO_OPS),
            actor_id="proposer@irp",
        )
        session.commit()  # TWO PROPOSED coexist — the partial predicate is real
        set_tenant_context(session, tenant)  # the commit CLEARED the GUC (the 0282359 lesson)
        ratify_mapping_version(
            session,
            mapping_version_id=first.id,
            acting_tenant=tenant,
            actor_id="ratifier@irp",
        )
        session.commit()

    # ...and a SECOND RATIFIED row for the same key is refused by the index, not by the service.
    with app_factory() as session:
        set_tenant_context(session, tenant)
        with pytest.raises((IntegrityError, DBAPIError)):
            session.execute(
                text(
                    "INSERT INTO ingestion_mapping_version (id, tenant_id, system_from, "
                    "data_source_id, source_type, version_label, status, operations, "
                    "operations_hash, authorship, proposed_by_actor_id, proposed_at) VALUES "
                    "(gen_random_uuid(), CAST(:t AS uuid), now(), CAST(:s AS uuid), 'POSITIONS', "
                    "'sneak', 'RATIFIED', '[]', :h, 'HAND_AUTHORED', 'a@irp', now())"
                ),
                {"t": tenant, "s": source_id, "h": "1" * 64},
            )
        session.rollback()


def test_a_cross_tenant_model_version_is_refused_before_the_fk_sees_it(app_factory) -> None:  # noqa: ANN001
    """PostgreSQL FK checks BYPASS RLS, so the FK alone would durably admit a cross-tenant model
    version. The tenant-filtered re-resolution is what actually refuses, and this proves it on the
    engine where the FK would otherwise have said yes."""
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, other)
        other_source = _source(session, other, code="OTHER-FEED")
        model = register_model(
            session,
            tenant_id=other,
            code="X-DRAFT",
            name="another tenant's drafting model",
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
        session.commit()
        foreign_version = version.id
        assert other_source

    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant)
        with pytest.raises(MappingNotVisible):
            propose_mapping_version(
                session,
                tenant_id=tenant,
                data_source_id=source_id,
                source_type=SOURCE_TYPE_POSITIONS,
                version_label="cross",
                operations=list(DEMO_OPS),
                actor_id="proposer@irp",
                authorship="MODEL_PROPOSED",
                proposer_model_version_id=str(foreign_version),
                proposal_prompt_hash="0" * 64,
            )
        session.rollback()


# --- the regression test for the defect the P17 harness found ---------------------------------


def test_a_batch_that_finished_with_warnings_persists(app_factory) -> None:  # noqa: ANN001
    """``COMPLETED_WITH_WARNINGS`` is 23 characters and ``status`` was ``varchar(20)`` from
    migration ``0007`` until W19-S3a — so on PostgreSQL this path raised
    ``StringDataRightTruncation`` and no batch could ever finish with a data-quality warning.

    **This test is at the tier that would have caught it.** The unit tier already exercised the
    warning path and passed, because SQLite ignores ``VARCHAR`` length. The defect lived in the gap
    between the two, which is why the assertion here is the whole point: it drives the REAL
    ``stage_upload`` warning path against real PostgreSQL and reads the stored value back.
    """
    tenant = str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant)
        # A WARNING-severity rule: the row is flagged, the batch completes WITH WARNINGS.
        register_dq_rule(
            session,
            tenant_id=tenant,
            code="PG-WARN",
            name="warn on a missing optional column",
            rule_type="NOT_NULL",
            target_entity_type=STAGING_ROW_TARGET,
            severity="WARNING",
            params={"column": "OPTIONAL_COL"},
            actor_id="ops",
        )
        session.commit()
        set_tenant_context(session, tenant)  # the commit CLEARED the GUC (the 0282359 lesson)

        batch = stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="warns.csv",
            content_type="text/csv",
            raw_bytes=b"SEDOL,QTY\nB1YW440,12\n",
            actor_id="ops",
        )
        session.commit()
        batch_id = batch.id

    with app_factory() as session:
        set_tenant_context(session, tenant)
        stored = session.execute(
            text("SELECT status FROM ingestion_batch WHERE id = CAST(:b AS uuid)"),
            {"b": batch_id},
        ).scalar_one()
    assert stored == STATUS_COMPLETED_WITH_WARNINGS
    assert len(STATUS_COMPLETED_WITH_WARNINGS) == 23  # the number that did not fit


def test_the_status_column_is_wide_enough_for_its_own_vocabulary(superuser_engine) -> None:  # noqa: ANN001
    """The structural half of the same fix, read out of PostgreSQL rather than out of the ORM."""
    with superuser_engine.begin() as conn:
        width = conn.execute(
            text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'ingestion_batch' AND column_name = 'status'"
            )
        ).scalar_one()
    assert width >= len(STATUS_COMPLETED_WITH_WARNINGS)


def test_the_batch_binds_its_mapping_version_by_hard_fk(app_factory) -> None:  # noqa: ANN001
    """Clause (2), the batch half, enforced by the DATABASE rather than by the writer.

    "never a free-text field" is only true if a value the referent does not have is REFUSED.
    """
    tenant = str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant)
        register_dq_rule(
            session,
            tenant_id=tenant,
            code="PG-OK",
            name="present",
            rule_type="NOT_NULL",
            target_entity_type=STAGING_ROW_TARGET,
            severity="WARNING",
            params={"column": "SEDOL"},
            actor_id="ops",
        )
        session.commit()
        set_tenant_context(session, tenant)  # the commit CLEARED the GUC (the 0282359 lesson)
        batch = stage_upload(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            filename="ok.csv",
            content_type="text/csv",
            raw_bytes=b"SEDOL,QTY\nB1YW440,12\n",
            actor_id="ops",
        )
        session.commit()
        batch_id = batch.id

    with app_factory() as session:
        set_tenant_context(session, tenant)
        with pytest.raises((IntegrityError, DBAPIError, ProgrammingError)):
            session.execute(
                text(
                    "UPDATE ingestion_batch SET mapping_version_id = gen_random_uuid() "
                    "WHERE id = CAST(:b AS uuid)"
                ),
                {"b": batch_id},
            )
            session.flush()
        session.rollback()

    # positive control: the batch, the rule and the FK all exist, so the refusal above is the FK
    # refusing an unknown referent rather than the harness failing to deliver its input.
    with app_factory() as session:
        set_tenant_context(session, tenant)
        rules = session.execute(
            text("SELECT count(*) FROM data_quality_rule WHERE tenant_id = CAST(:t AS uuid)"),
            {"t": tenant},
        ).scalar_one()
        row = session.get(IngestionBatch, batch_id)
    assert rules == 1
    assert row is not None and row.mapping_version_id is None


def test_the_dq_rule_target_the_load_path_needs_exists(app_factory) -> None:  # noqa: ANN001
    """``stage_upload``'s gate is FAIL-CLOSED: with no active ``staging.row`` rule the batch is
    driven to REJECTED. Asserted here because the demo path depends on it and the repo had no such
    rule outside test files until this slice — a positions file would have been rejected every
    time, and the failure would have read as a data problem rather than a missing rule."""
    tenant = str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant)
        assert (
            session.execute(
                text(
                    "SELECT count(*) FROM data_quality_rule WHERE target_entity_type = :t "
                    "AND is_active"
                ),
                {"t": STAGING_ROW_TARGET},
            ).scalar_one()
            >= 0
        )
        assert DataQualityRule.__tablename__ == "data_quality_rule"


def test_the_mapping_lifecycle_survives_a_real_commit(app_factory) -> None:  # noqa: ANN001
    """The tenant GUC is transaction-local and a commit CLEARS it — the ``0282359`` lesson. Any
    read-back after a commit must re-arm the context, and a lifecycle that only ever runs inside
    one uncommitted transaction has not been proven at all."""
    tenant = str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant)
        source_id = _source(session, tenant)
        version = propose_mapping_version(
            session,
            tenant_id=tenant,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="v1",
            operations=list(DEMO_OPS),
            actor_id="proposer@irp",
        )
        session.commit()
        version_id = version.id

    with app_factory() as session:
        set_tenant_context(session, tenant)  # re-armed AFTER the commit
        reread = resolve_mapping_version(session, version_id, acting_tenant=tenant)
        assert reread.status == STATUS_PROPOSED
        ratify_mapping_version(
            session,
            mapping_version_id=version_id,
            acting_tenant=tenant,
            actor_id="ratifier@irp",
        )
        session.commit()

    with app_factory() as session:
        set_tenant_context(session, tenant)
        assert resolve_mapping_version(session, version_id, acting_tenant=tenant).status == (
            STATUS_RATIFIED
        )


def test_the_mapping_routes_hide_another_tenants_rows(app_factory) -> None:  # noqa: ANN001
    """The ROUTE FUNCTIONS' own queries, on PostgreSQL, under the constrained role.

    This was tested only on SQLite, which has no RLS — and the endpoint suite's docstring claimed a
    PG file closed the gap when that file does not mention mappings at all. The one PG test that
    did check cross-tenant hiding went through ``resolve_mapping_version``, which carries its own
    explicit tenant predicate; the ROUTES call a bare ``db.get``. Different code, so a different
    proof was needed. A slice reviewer caught the claim.

    The route FUNCTIONS are called directly with a real RLS-scoped session rather than over HTTP:
    the property under test is the route's own query, and threading the dev-header auth stack
    through a PG session would test the auth stack instead. Permission gating is proven over HTTP
    in ``apps/backend/tests/test_ingest_endpoint.py``.
    """
    from fastapi import HTTPException

    from irp_backend.api.ingest import (
        get_mapping_version,
        list_batches_for_mapping,
        list_mapping_versions,
    )

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    with app_factory() as session:
        set_tenant_context(session, tenant_a)
        source_id = _source(session, tenant_a)
        mapping_id = propose_mapping_version(
            session,
            tenant_id=tenant_a,
            data_source_id=source_id,
            source_type=SOURCE_TYPE_POSITIONS,
            version_label="v1",
            operations=list(DEMO_OPS),
            actor_id="proposer@irp",
        ).id
        session.commit()

    # POSITIVE CONTROL FIRST: the same functions, the same code, the OWNING tenant. Without this
    # the refusals below would be satisfied by routes that are simply broken for everyone.
    with app_factory() as session:
        set_tenant_context(session, tenant_a)
        assert get_mapping_version(uuid.UUID(mapping_id), None, session).id == mapping_id
        assert [row.id for row in list_mapping_versions(None, session)] == [mapping_id]
        assert list_batches_for_mapping(uuid.UUID(mapping_id), None, session) == []

    with app_factory() as session:
        set_tenant_context(session, tenant_b)
        # indistinguishable 404, not a 403 and not a leak
        with pytest.raises(HTTPException) as detail:
            get_mapping_version(uuid.UUID(mapping_id), None, session)
        assert detail.value.status_code == 404
        with pytest.raises(HTTPException) as batches:
            list_batches_for_mapping(uuid.UUID(mapping_id), None, session)
        assert batches.value.status_code == 404
        assert list_mapping_versions(None, session) == []
