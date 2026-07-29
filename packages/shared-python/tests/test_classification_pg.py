"""PostgreSQL tests for REF-1 classification — the two tenancy classes, proven on the real engine.

Gated on ``IRP_TEST_DATABASE_URL``; enforcement runs under the constrained non-superuser,
non-BYPASSRLS ``irp_app`` role, the same posture as ``test_reference_pg.py``.

**Why these live in the PG tier specifically.** The unit tier has no RLS at all, so every assertion
about who can read or write a SYSTEM row is unprovable there. And the Wave-13 close ended an
eight-wave runtime-clean streak on exactly this asymmetry: SQLite's column affinity silently
converts a mistyped bind, so a filter bound at the wrong type is green on the unit tier and 500s on
PostgreSQL. This slice's reads filter on GUID ``entity_id`` and on ``valid_from``/``valid_to``
(timestamps) — non-String column classes — so their binds are pinned HERE, where a unit pin could
never fail.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from irp_shared.classification.models import (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    ClassificationAssignment,
    ClassificationNode,
)
from irp_shared.classification.service import (
    ClassificationActor,
    capture_assignment,
    create_node,
    create_scheme,
    supersede_assignment,
)
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import set_tenant_context
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


def _is_rls_violation(exc: Exception) -> bool:
    return getattr(getattr(exc, "orig", None), "sqlstate", None) == "42501"


#: The three REF-1 tables plus the rails the binder writes (provenance, DQ, audit).
_CLASSIFICATION_TABLES = (
    "classification_scheme",
    "classification_node",
    "classification_assignment",
)
_RAILS = ("data_source", "lineage_edge", "data_quality_rule", "data_quality_result")


@pytest.fixture(scope="module")
def app_url() -> str:
    """Constrained non-superuser, non-BYPASSRLS app role with grants on the REF-1 tables + rails;
    clears this module's tables once as superuser so the module is order/re-run independent."""
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
        for table in (*_CLASSIFICATION_TABLES, *_RAILS):
            conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO irp_app"))
        conn.execute(text("GRANT SELECT, INSERT ON audit_event TO irp_app"))
        # Children before parents (FK order); superuser DELETE bypasses RLS.
        for table in (
            "classification_assignment",
            "classification_node",
            "classification_scheme",
        ):
            conn.execute(text(f"DELETE FROM {table}"))
    superuser.dispose()
    return (
        make_url(URL)
        .set(username="irp_app", password="ci_app_pw")
        .render_as_string(hide_password=False)
    )


def _session(url: str, tenant: str):  # noqa: ANN202
    engine = make_engine(url, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    set_tenant_context(session, tenant)
    return engine, session


def test_vocabulary_is_hybrid_and_assignment_is_not(app_url: str) -> None:
    """The two tenancy classes, in one test: a tenant READS the SYSTEM taxonomy but its own
    assignments are invisible cross-tenant."""
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())

    # Seed the global taxonomy under SYSTEM context.
    engine, sys_session = _session(app_url, SYSTEM_TENANT_ID)
    sys_actor = ClassificationActor(tenant_id=SYSTEM_TENANT_ID, actor_id="platform_admin")
    # SYSTEM_TENANT_ID is a FIXED tenant, so a SYSTEM row seeded here is visible to every other
    # module in the same database. This suite therefore uses a DISTINCT version label — the
    # test_reference_pg isolation convention ("each test uses a distinct SYSTEM currency code").
    # Without it this row collides with the demo stage's real ISIC Rev. 5 and makes the demo
    # suite's refuse-not-skip guard fire against a scheme the demo never seeded.
    scheme = create_scheme(
        sys_session,
        actor=sys_actor,
        scheme_family="ISIC",
        version_label=f"pgtest-{uuid.uuid4().hex[:8]}",
        name="ISIC (PG suite fixture)",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        authority="UNSD",
    )
    create_node(
        sys_session, actor=sys_actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1
    )
    sys_session.commit()
    scheme_id = str(scheme.id)
    sys_session.close()
    engine.dispose()

    # Tenant A reads the SYSTEM scheme (hybrid USING) and captures its own assignment.
    engine_a, sess_a = _session(app_url, tenant_a)
    actor_a = ClassificationActor(tenant_id=tenant_a, actor_id="steward_a")
    instrument = str(uuid.uuid4())
    capture_assignment(
        sess_a,
        actor=actor_a,
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=scheme_id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="C",
    )
    sess_a.commit()
    # Re-set context after commit before a read-back (the 0282359 lesson).
    set_tenant_context(sess_a, tenant_a)
    assert sess_a.execute(select(ClassificationAssignment)).scalars().all()
    sess_a.close()
    engine_a.dispose()

    # Tenant B reads the SAME SYSTEM scheme (hybrid) but NOT tenant A's assignment (symmetric).
    engine_b, sess_b = _session(app_url, tenant_b)
    visible_schemes = sess_b.execute(
        text("SELECT count(*) FROM classification_scheme WHERE id = :i"), {"i": scheme_id}
    ).scalar_one()
    assert visible_schemes == 1, "the SYSTEM taxonomy must be readable by every tenant"
    leaked = sess_b.execute(select(ClassificationAssignment)).scalars().all()
    assert leaked == [], "classification_assignment is PROPRIETARY — no cross-tenant read"
    sess_b.close()
    engine_b.dispose()


def test_a_tenant_cannot_write_a_system_taxonomy_row(app_url: str) -> None:
    """The asymmetry's second arm: WITH CHECK stays own-tenant, so a SYSTEM write is 42501."""
    tenant = str(uuid.uuid4())
    engine, session = _session(app_url, tenant)
    try:
        # Narrow by design: `pytest.raises(Exception)` would pass on a typo, a missing column, or a
        # FK error — i.e. it would "prove" RLS while RLS was switched off. The assertion below
        # requires SQLSTATE 42501 specifically, so only an actual policy denial satisfies it.
        with pytest.raises(ProgrammingError) as exc:
            session.execute(
                text(
                    "INSERT INTO classification_scheme "
                    "(id, tenant_id, valid_from, created_at, updated_at, scheme_family, "
                    " version_label, name, dimension_kind, is_active, record_version) "
                    "VALUES (gen_random_uuid(), CAST(:sys AS uuid), now(), now(), now(), "
                    " 'ROGUE', 'v1', 'rogue', 'SECTOR_INDUSTRY', true, 1)"
                ),
                {"sys": SYSTEM_TENANT_ID},
            )
            session.flush()
        assert _is_rls_violation(exc.value), (
            f"expected an RLS policy denial (SQLSTATE 42501), got "
            f"{getattr(getattr(exc.value, 'orig', None), 'sqlstate', None)}: {exc.value}"
        )

        # POSITIVE CONTROL: the SAME statement under the tenant's OWN id succeeds, so the refusal
        # above is attributable to the SYSTEM tenant_id and not to a malformed statement.
        session.rollback()
        set_tenant_context(session, tenant)
        session.execute(
            text(
                "INSERT INTO classification_scheme "
                "(id, tenant_id, valid_from, created_at, updated_at, scheme_family, "
                " version_label, name, dimension_kind, is_active, record_version) "
                "VALUES (gen_random_uuid(), CAST(:own AS uuid), now(), now(), now(), "
                " 'OWNSCHEME', :v, 'own', 'SECTOR_INDUSTRY', true, 1)"
            ),
            {"own": tenant, "v": uuid.uuid4().hex[:8]},
        )
        session.flush()
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_fr_supersede_leaves_the_prior_version_byte_stable_on_pg(app_url: str) -> None:
    """The slice's load-bearing property, proven on the real engine rather than in SQLite."""
    tenant = str(uuid.uuid4())
    engine, session = _session(app_url, tenant)
    actor = ClassificationActor(tenant_id=tenant, actor_id="steward")
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family="ISIC",
        version_label=f"Rev. {uuid.uuid4().hex[:6]}",
        name="ISIC",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
    )
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    create_node(session, actor=actor, scheme_id=scheme.id, code="J", name="Information", level=1)
    instrument = str(uuid.uuid4())
    first = capture_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="C",
    )
    first_id = str(first.id)
    session.commit()
    set_tenant_context(session, tenant)

    supersede_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=str(scheme.id),
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
        node_code="J",
    )
    session.commit()
    set_tenant_context(session, tenant)

    prior = session.get(ClassificationAssignment, first_id)
    assert prior is not None
    assert prior.node_code == "C", "the prior version's CONTENT must be untouched"
    assert prior.valid_to is not None and prior.system_to is None
    open_rows = (
        session.execute(
            select(ClassificationAssignment).where(
                ClassificationAssignment.entity_id == instrument,
                ClassificationAssignment.valid_to.is_(None),
                ClassificationAssignment.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert len(open_rows) == 1 and open_rows[0].node_code == "J"
    session.close()
    engine.dispose()


def test_read_filters_bind_at_the_column_type_on_pg(app_url: str) -> None:
    """PG-TIER PIN for the non-String filter columns (the streak-ending class).

    ``entity_id`` is a GUID/uuid column and the temporal axes are timestamps. PostgreSQL refuses
    ``uuid = character varying``; SQLite's affinity silently coerces, so a mistyped bind is
    invisible on the unit tier. This pin exercises the exact filter shapes the read surface uses,
    on the engine that can actually reject them.
    """
    tenant = str(uuid.uuid4())
    engine, session = _session(app_url, tenant)
    actor = ClassificationActor(tenant_id=tenant, actor_id="steward")
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family="ISO_3166_1",
        version_label=f"{uuid.uuid4().hex[:6]}",
        name="ISO 3166-1",
        dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
    )
    create_node(session, actor=actor, scheme_id=scheme.id, code="US", name="United States", level=1)
    instrument = str(uuid.uuid4())
    row = capture_assignment(
        session,
        actor=actor,
        entity_type="instrument",
        entity_id=instrument,
        scheme_id=scheme.id,
        dimension_kind=DIMENSION_KIND_COUNTRY_OF_RISK,
        node_code="US",
        basis=BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    )
    session.commit()
    set_tenant_context(session, tenant)

    # GUID equality filter — the shape that 500'd four endpoints at the Wave-13 close.
    by_entity = (
        session.execute(
            select(ClassificationAssignment).where(ClassificationAssignment.entity_id == instrument)
        )
        .scalars()
        .all()
    )
    assert len(by_entity) == 1

    # Timestamp (as-of) filter over the FR valid axis.
    as_of = row.valid_from
    as_of_rows = (
        session.execute(
            select(ClassificationAssignment).where(
                ClassificationAssignment.entity_id == instrument,
                ClassificationAssignment.valid_from <= as_of,
                ClassificationAssignment.system_to.is_(None),
            )
        )
        .scalars()
        .all()
    )
    assert len(as_of_rows) == 1
    assert as_of_rows[0].basis == BASIS_IMMEDIATE_ISSUER_RESIDENCE
    session.close()
    engine.dispose()


def test_integer_level_filter_binds_as_integer_on_pg(app_url: str) -> None:
    """PG-TIER PIN for the INTEGER filter — the exact column class that ended the streak.

    ``GET /classification/schemes/{id}/nodes?level=N`` filters ``classification_node.level``, an
    Integer column. At the Wave-13 close a blanket ``str()`` bind made ``window_months`` reach
    PostgreSQL as ``integer = character varying`` and 500 four endpoints while every gate was green
    — because SQLite's INTEGER affinity converts ``'1'`` to ``1`` and the unit tier is
    STRUCTURALLY incapable of seeing it. This pin exercises both the correct bind and, as a
    negative control, proves the stringified form is genuinely rejected here.
    """
    tenant = str(uuid.uuid4())
    engine, session = _session(app_url, tenant)
    actor = ClassificationActor(tenant_id=tenant, actor_id="steward")
    scheme = create_scheme(
        session,
        actor=actor,
        scheme_family="ISIC",
        version_label=f"Rev. {uuid.uuid4().hex[:6]}",
        name="ISIC",
        dimension_kind=DIMENSION_KIND_SECTOR_INDUSTRY,
    )
    create_node(session, actor=actor, scheme_id=scheme.id, code="C", name="Manufacturing", level=1)
    create_node(
        session, actor=actor, scheme_id=scheme.id, code="C10", name="Food", level=2, parent_code="C"
    )
    session.commit()
    set_tenant_context(session, tenant)

    level_1 = (
        session.execute(
            select(ClassificationNode).where(
                ClassificationNode.scheme_id == str(scheme.id),
                ClassificationNode.level == 1,
            )
        )
        .scalars()
        .all()
    )
    assert [n.code for n in level_1] == ["C"]

    # NEGATIVE CONTROL — and the cast here is deliberate, not decoration.
    #
    # A first attempt passed a Python ``str`` as a bind parameter and did NOT raise: psycopg sends
    # it as *unknown*, and PostgreSQL happily coerces unknown to integer. That control would have
    # been a lie — green while proving nothing. The Wave-13 defect was not an unknown-typed value;
    # it was a value bound at an explicit VARCHAR type (the blanket ``str()`` in the read seam),
    # which PostgreSQL refuses with "operator does not exist: integer = character varying". So the
    # control reproduces THAT shape.
    with pytest.raises(ProgrammingError) as exc:
        session.execute(
            text(
                "SELECT count(*) FROM classification_node "
                "WHERE scheme_id = CAST(:s AS uuid) AND level = CAST(:lvl AS varchar)"
            ),
            {"s": str(scheme.id), "lvl": "1"},
        )
    message = str(exc.value).lower()
    assert "operator does not exist" in message and "character varying" in message
    session.rollback()
    session.close()
    engine.dispose()
