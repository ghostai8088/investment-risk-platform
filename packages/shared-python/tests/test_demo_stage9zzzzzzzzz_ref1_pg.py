"""PostgreSQL end-state test for the REF-1 demo stage 18 — the first classified book.

Gated on ``IRP_TEST_DATABASE_URL``. Runs the stage ONCE (module-scoped) over the living demo tenant
and asserts the governed end state.

**The filename is load-bearing** (the standing stage-ordering discipline): batteries collect
alphabetically and earlier suites pin governed sets with set-equality, so each stage appends one
more ``z``. SR-1's stage-17 suite is ``stage9zzzzzzzz`` (eight), so this is ``stage9zzzzzzzzz``
(NINE) — verified by ``ls`` on the tests directory, not read off a decision record, which is
exactly how RM-1 discovered its own ratified name had gone stale.

**The FINAL-POSITION count pin RELAYED ONWARD at CON-1 (stage 19, the 10-z suite): this file's
25/40/133 is now a POSITIONAL assertion** — true at THIS point of the battery (after stage 18,
before stage 19), while the final-position pin lives in
``test_demo_stage9zzzzzzzzzz_con1_pg.py`` at 26/41/136. The relay discipline is unchanged: the
previous holder collates BEFORE the newest stage and therefore cannot see anything it does (the
SCH-2 109-vs-110 defect). A pin's value is its POSITION, not its number.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.pool import NullPool

from irp_shared.calc.models import CalculationRun
from irp_shared.classification.models import (
    BASIS_IMMEDIATE_ISSUER_RESIDENCE,
    BASIS_NOT_APPLICABLE,
    DIMENSION_KIND_COUNTRY_OF_RISK,
    DIMENSION_KIND_SECTOR_INDUSTRY,
    ClassificationAssignment,
    ClassificationNode,
    ClassificationScheme,
)
from irp_shared.classification.service import resolve_ancestors, resolve_node
from irp_shared.db.session import make_engine, make_session_factory
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo import DEMO_TENANT_ID, DemoRef1AlreadySeededError, run_demo_ref1_stage18
from irp_shared.entitlement.bootstrap import SYSTEM_TENANT_ID
from irp_shared.model.models import Model, ModelValidation
from irp_shared.reference.models import Instrument, Issuer

URL = os.environ.get("IRP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires PostgreSQL (IRP_TEST_DATABASE_URL)")


@pytest.fixture(scope="module")
def summary():  # noqa: ANN201
    engine = make_engine(URL, poolclass=NullPool)
    factory = make_session_factory(engine)
    session = factory()
    result = None
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        try:
            result = run_demo_ref1_stage18(session)
            session.commit()
        except DemoRef1AlreadySeededError:
            session.rollback()  # dirty double-run: assert the existing end state
    finally:
        session.close()
    yield factory, result
    engine.dispose()


@pytest.fixture()
def db(summary):  # noqa: ANN001, ANN201
    factory, _ = summary
    session = factory()
    try:
        persistent_tenant_context(session, DEMO_TENANT_ID)
        yield session
    finally:
        session.close()


def test_the_stage_seeded_the_global_taxonomy_and_classified_the_book(summary) -> None:  # noqa: ANN001
    _factory, result = summary
    if result is None:
        pytest.skip("stage already seeded in this database")
    assert result.nodes_created == 7  # 2 ISIC sections + 3 divisions + 2 countries
    assert result.issuers_created == 3
    assert result.instruments_backfilled == 3
    assert result.assignments_created == 6  # one sector + one country per instrument


def _demo_schemes(db):  # noqa: ANN001, ANN202
    """The two schemes THIS stage seeds.

    Scoped by family rather than "everything in the table": these suites connect as the superuser,
    which bypasses RLS, so a whole-table assertion would silently take a dependency on which other
    modules happened to run first in the same database. Scoping to the stage's own rows makes the
    assertion about this stage.
    """
    return list(
        db.execute(
            select(ClassificationScheme).where(
                ClassificationScheme.scheme_family.in_(("ISIC", "ISO_3166_1")),
                ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
                ClassificationScheme.version_label.in_(("Rev. 5", "2026")),
            )
        ).scalars()
    )


def _demo_assignments(db):  # noqa: ANN001, ANN202
    """Assignments belonging to the DEMO tenant only (see ``_demo_schemes`` on why scoping)."""
    return list(
        db.execute(
            select(ClassificationAssignment).where(
                ClassificationAssignment.tenant_id == DEMO_TENANT_ID
            )
        ).scalars()
    )


def test_the_taxonomy_is_SYSTEM_owned_and_the_assignments_are_the_tenants(db) -> None:  # noqa: ANN001
    """The two tenancy classes, visible in the demo's own data rather than only in a policy test."""
    schemes = _demo_schemes(db)
    assert len(schemes) == 2, "the stage seeds exactly the ISIC and ISO 3166-1 schemes"
    assert {str(s.tenant_id) for s in schemes} == {SYSTEM_TENANT_ID}, (
        "taxonomy schemes are SYSTEM-owned global reference — a demo-tenant scheme row would mean "
        "the seed ran under the wrong context"
    )
    scheme_ids = [str(s.id) for s in schemes]
    nodes = list(
        db.execute(
            select(ClassificationNode).where(ClassificationNode.scheme_id.in_(scheme_ids))
        ).scalars()
    )
    assert len(nodes) == 7
    assert {str(n.tenant_id) for n in nodes} == {SYSTEM_TENANT_ID}

    assignments = _demo_assignments(db)
    assert len(assignments) == 6
    assert {str(a.tenant_id) for a in assignments} == {
        DEMO_TENANT_ID
    }, "assignments are PROPRIETARY — they must carry the demo tenant, never SYSTEM"


def test_every_classified_instrument_carries_a_real_issuer(db) -> None:  # noqa: ANN001
    """The backfill CON-1 depends on: an unclassified book would make its demo vacuous."""
    for code in ("EQ-ACME-US", "EQ-EURX-DE", "PE-HARBOR-IV"):
        inst = db.execute(
            select(Instrument).where(
                Instrument.tenant_id == DEMO_TENANT_ID, Instrument.code == code
            )
        ).scalar_one()
        assert inst.issuer_id is not None, f"{code} still has a NULL issuer after the backfill"
        issuer = db.get(Issuer, str(inst.issuer_id))
        assert issuer is not None and str(issuer.tenant_id) == DEMO_TENANT_ID


def test_both_dimensions_are_assigned_with_the_correct_basis(db) -> None:  # noqa: ANN001
    """The kind-invariant, proven on real captured rows rather than only at the binder."""
    rows = _demo_assignments(db)
    sector = [r for r in rows if r.dimension_kind == DIMENSION_KIND_SECTOR_INDUSTRY]
    country = [r for r in rows if r.dimension_kind == DIMENSION_KIND_COUNTRY_OF_RISK]
    assert len(sector) == 3 and len(country) == 3
    # A sector row carries ONLY the sentinel; a country row NEVER does.
    assert {r.basis for r in sector} == {BASIS_NOT_APPLICABLE}
    assert {r.basis for r in country} == {BASIS_IMMEDIATE_ISSUER_RESIDENCE}
    # Every assignment is open on both axes.
    assert all(r.valid_to is None and r.system_to is None for r in rows)


def test_the_sector_of_a_leaf_resolves_through_the_ancestor_walk(db) -> None:  # noqa: ANN001
    """CON-1's per-sector bucket, demonstrated end to end.

    The book is classified at DIVISION level (C26/C28/K64). "Sector" is the level-1 ancestor, so
    this is the read the next slice performs — proven here on the demo's own data, because a
    hierarchy nobody can walk is not a hierarchy.
    """
    isic = db.execute(
        select(ClassificationScheme).where(
            ClassificationScheme.scheme_family == "ISIC",
            ClassificationScheme.tenant_id == SYSTEM_TENANT_ID,
            # Version-scoped: other suites seed SYSTEM ISIC fixtures under distinct labels, and
            # these demo suites connect as the superuser (which bypasses RLS), so family alone is
            # not a unique key across a shared database.
            ClassificationScheme.version_label == "Rev. 5",
        )
    ).scalar_one()
    node = resolve_node(db, scheme_id=str(isic.id), code="C26", acting_tenant=DEMO_TENANT_ID)
    chain = resolve_ancestors(db, node=node, acting_tenant=DEMO_TENANT_ID)
    assert [n.code for n in chain] == ["C"]
    assert chain[-1].level == 1
    assert chain[-1].name == "Manufacturing"

    # Two of the three holdings roll up to the SAME sector — which is what makes a concentration
    # number non-trivial on this book. A book where every holding sat in its own sector could not
    # demonstrate concentration at all (the OPS-1 reachability lesson).
    sectors = []
    for code in ("C26", "C28", "K64"):
        n = resolve_node(db, scheme_id=str(isic.id), code=code, acting_tenant=DEMO_TENANT_ID)
        sectors.append(resolve_ancestors(db, node=n, acting_tenant=DEMO_TENANT_ID)[-1].code)
    assert sectors == ["C", "C", "K"]


def test_demo_counts_are_UNCHANGED_at_the_final_position(db) -> None:  # noqa: ANN001
    """THE FINAL-POSITION PIN, relayed to this suite — and asserting the numbers did NOT move.

    A capture-only stage registers no model code, files no validation and creates no run (the CC-1
    stage-8 precedent). The pin still had to MOVE here: the previous holder collates before this
    stage and is structurally unable to see it, which is the SCH-2 109-vs-110 defect exactly.
    """
    model_codes = db.execute(
        select(func.count(func.distinct(Model.code))).where(Model.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    validations = db.execute(
        select(func.count())
        .select_from(ModelValidation)
        .where(ModelValidation.tenant_id == DEMO_TENANT_ID)
    ).scalar_one()
    completed = db.execute(
        select(func.count())
        .select_from(CalculationRun)
        .where(
            CalculationRun.tenant_id == DEMO_TENANT_ID,
            CalculationRun.status == "COMPLETED",
        )
    ).scalar_one()

    assert (model_codes, validations, completed) == (
        25,
        40,
        133,
    ), f"demo counts drifted: {model_codes}/{validations}/{completed} (expected 25/40/133)"


def test_ref1_contributed_no_model_no_validation_no_run(db) -> None:  # noqa: ANN001
    """The slice's OWN contribution, isolated — a capture family adds governed DATA, not a number.

    Asserted BY EVIDENCE rather than by absence: the classification rows exist (so the stage really
    ran) AND no `classification.*` model code was registered.
    """
    assert len(_demo_assignments(db)) == 6
    codes = set(
        db.execute(select(Model.code).where(Model.tenant_id == DEMO_TENANT_ID)).scalars().all()
    )
    assert not any(
        c.startswith("classification") for c in codes
    ), f"a captured-input family must register NO model code; found {sorted(codes)}"
