"""W19-S3a: REQ-INT-001 clause (4) — the interpreter is the ONLY write path FROM STAGED ROWS.

    "(4) The interpreter is the ONLY write path from staged rows to canonical positions, asserted by
    a census that DISCOVERS write paths mechanically, never a hand list."

**The clause is scoped to "from staged rows", and that scoping is load-bearing rather than a
convenience.** ``POST /positions`` calls ``create_position`` directly under the ``position.edit``
permission with no staged file anywhere near it. It is live, it stays live, and it is an
INTENTIONALLY UNMAPPED manual-entry path outside this requirement's guarantee — recorded here so a
reader is not left to infer it, because a census that pretended to close it would be asserting
something false. What the clause forbids is a SECOND route from a client's uploaded file into
canonical holdings, bypassing the ratified mapping.

**Why the census reads SOURCE and not the runtime.** A census measured through the mechanism it
audits is blind to whatever bypasses that mechanism (the recorded lesson at
``test_db_foreign_keys.py``). So this walks the AST of all three source trees and asks two
independent questions per module — does it READ staged rows, and does it WRITE positions — and
asserts the intersection by EXACT SET EQUALITY.

**Two guards, not one, because they catch different failures** (the shape both shipped precedents
carry and the first draft of this slice's plan had only half of):

- a POSITIVE CONTROL against KNOWN PRE-EXISTING PRODUCTION SITES — the matcher must still detect the
  three real binder sites and the real HTTP write path. A matcher that never matches reports an
  empty offender list, which is indistinguishable from total compliance;
- a P6 COVERAGE FLOOR on each discovered population, so a refactor that collapses the census's
  subject fails loudly rather than passing silently. A matcher covers only the shapes someone
  thought of; a floor notices coverage falling whatever the next shape is.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]

SOURCE_TREES = (
    REPO / "packages/shared-python/src/irp_shared",
    REPO / "apps/backend/src/irp_backend",
    REPO / "apps/worker/src/irp_worker",
)

#: The position-writing verbs. Constructing ``Position(...)`` is the raw shape; the three binder
#: verbs are the governed shape. Both count as "writes positions" — the census is about REACHING
#: canonical holdings, not about which spelling was used.
_POSITION_CALLS = frozenset(
    {"Position", "create_position", "supersede_position", "correct_position"}
)

#: The staged-row reading shapes. ``IngestionStagedRecord`` is the ORM class; the raw table name
#: covers a ``text()`` literal.
_STAGED_NAMES = frozenset({"IngestionStagedRecord"})
_STAGED_STRINGS = ("ingestion_staged_record", "FROM ingestion_staged_record")

#: Over-capturing on the string arm DELIBERATELY, the aggregation census's own trade: a prose match
#: costs one allowlist line, a missed raw INSERT would cost the census its subject.
_POSITION_STRINGS = ("INSERT INTO position", 'INSERT INTO "position"')

#: THE ANSWER. Exactly one module may do both — and it is the interpreter's service.
EXPECTED_STAGED_TO_POSITION = frozenset({"irp_shared.ingest_mapping.service"})

#: Known pre-existing PRODUCTION position writers, for the positive control. These are real sites
#: that existed before this slice; if the matcher stops seeing them it has broken, whatever it says
#: about the offender set.
KNOWN_POSITION_WRITERS = frozenset(
    {
        "irp_shared.position.position",  # the three governed binder verbs
        "irp_backend.api.positions",  # POST /positions — the manual path, outside clause (4)
    }
)

#: P6 floors, MEASURED at this slice rather than guessed. A collapse below these means the census's
#: population vanished — which is the failure a floor exists to make loud.
_MIN_POSITION_WRITERS = 4
_MIN_STAGED_READERS = 2


def _module_name(path: pathlib.Path) -> str:
    for tree in SOURCE_TREES:
        if tree in path.parents or tree == path.parent:
            rel = path.relative_to(tree.parent)
            return str(rel.with_suffix("")).replace("/", ".")
    raise AssertionError(path)  # pragma: no cover - every walked file is under a tree


def _iter_modules():  # noqa: ANN202
    for tree in SOURCE_TREES:
        for path in sorted(tree.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _writes_positions(tree: ast.AST, text: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in _POSITION_CALLS:
                return True
    return any(marker in text for marker in _POSITION_STRINGS)


def _reads_staged_rows(tree: ast.AST, text: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _STAGED_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in _STAGED_NAMES:
            return True
    return any(marker in text for marker in _STAGED_STRINGS)


def _census() -> tuple[set[str], set[str]]:
    writers: set[str] = set()
    readers: set[str] = set()
    for path in _iter_modules():
        text = path.read_text()
        tree = ast.parse(text)
        module = _module_name(path)
        if _writes_positions(tree, text):
            writers.add(module)
        if _reads_staged_rows(tree, text):
            readers.add(module)
    return writers, readers


def test_only_the_interpreter_writes_positions_from_staged_rows() -> None:
    """EXACT SET EQUALITY, never a subset — a subset check passes on an empty set, which is the
    shape that let a shipped contract census go green over nothing (the RPT-3 defect)."""
    writers, readers = _census()
    both = writers & readers
    assert both == EXPECTED_STAGED_TO_POSITION, (
        f"modules that both READ staged rows and WRITE canonical positions: {sorted(both)}. "
        f"REQ-INT-001 clause (4) admits exactly {sorted(EXPECTED_STAGED_TO_POSITION)} — a second "
        f"route from an uploaded file into canonical holdings bypasses the ratified mapping."
    )


def test_the_census_actually_detects_known_production_writers() -> None:
    """The POSITIVE CONTROL, against REAL pre-existing sites rather than a freshly authored plant.

    A plant tests the matcher against a shape the matcher was written for. These four sites were
    here before this slice and are what a refactor would silently move out of view.
    """
    writers, _ = _census()
    missing = KNOWN_POSITION_WRITERS - writers
    assert not missing, (
        f"the position-write matcher no longer sees known production writers: {sorted(missing)} — "
        f"the matcher is broken, and an empty offender list from a broken matcher is "
        f"indistinguishable from total compliance"
    )


def test_the_census_actually_detects_known_staged_readers() -> None:
    """The other half of the positive control: the staged-row side must also genuinely match."""
    _, readers = _census()
    assert "irp_shared.ingestion.service" in readers  # the stager itself
    assert "irp_shared.ingest_mapping.service" in readers  # the interpreter


def test_both_populations_have_a_coverage_floor() -> None:
    """P6. A matcher covers only the shapes someone thought of; a floor notices coverage FALLING,
    whatever the next shape turns out to be. The numbers are measured at this slice, not guessed."""
    writers, readers = _census()
    assert len(writers) >= _MIN_POSITION_WRITERS, (
        f"the position-writer population collapsed to {len(writers)} (floor "
        f"{_MIN_POSITION_WRITERS}) — the census has lost its subject"
    )
    assert (
        len(readers) >= _MIN_STAGED_READERS
    ), f"the staged-reader population collapsed to {len(readers)} (floor {_MIN_STAGED_READERS})"


def test_the_matcher_detects_a_raw_sql_insert_shape() -> None:
    """The string arm is over-capturing on purpose: a prose match costs one allowlist line, a missed
    raw ``INSERT INTO position`` would cost the census its subject. Proven on a synthetic module
    rather than assumed, because the AST arm alone would never see it."""
    text = 'session.execute(text("INSERT INTO position (id) VALUES (:i)"))'
    assert _writes_positions(ast.parse(text), text)
    quoted = "session.execute(text('INSERT INTO \"position\" (id) VALUES (:i)'))"
    assert _writes_positions(ast.parse(quoted), quoted)


def test_the_matcher_detects_a_bare_orm_construction() -> None:
    """The shape a bypass would most plausibly take: build the ORM object directly and add it,
    skipping the governed binder entirely."""
    text = "session.add(Position(tenant_id=t, portfolio_id=p, instrument_id=i, quantity=q))"
    assert _writes_positions(ast.parse(text), text)


def test_the_matcher_does_not_fire_on_an_unrelated_module() -> None:
    """The negative half: a module that mentions neither must not be counted, or the exact-set
    assertion above would be trivially satisfied by a matcher that matches everything."""
    text = "def add(a, b):\n    return a + b\n"
    assert not _writes_positions(ast.parse(text), text)
    assert not _reads_staged_rows(ast.parse(text), text)
