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

**The census follows IMPORTS, and the first version did not — that was a real hole.** The original
computed two per-module booleans (does this file read staged rows? does this file write positions?)
and asserted their pairwise intersection. A bypass split across two modules — one reads
``IngestionStagedRecord`` and calls a plainly-named helper, the other calls ``create_position`` and
never mentions staged rows — has NO single module that is both, so the intersection was unchanged
and the assertion passed. Two review lanes found this independently and one PLANTED the three-file
shape and watched all seven tests stay green. It is not a contrived attack: extract-a-helper and
put-the-reader-behind-a-repository-module are the two most ordinary refactors there are.

So the census now follows CALLS, at function granularity, to a fixed point: a function reaches a
position write if it calls one of the four write names, or calls a function that does. A module
reaches a write if any of its functions does. That catches the two-hop shape — the reader calls
``apply_row``, ``apply_row`` calls ``create_position``, so ``apply_row`` joins the write names and
the reader is caught.

**Import-following was tried first and was too coarse**, which is worth recording because the
failure is instructive: it flagged the demo stage, on the grounds that the stage imports
``demo.campaign`` and campaign seeds positions somewhere. The stage imports campaign for two
CONSTANTS. A census that cannot tell "imports a module that happens to contain a writer" from
"actually reaches a writer" produces exemption lists, and an exemption list is how a census stops
meaning anything.

**And the sanctioned route is cut out of the graph.** Functions defined in the interpreter's service
do NOT propagate write-reachability to their callers, because calling ``load_batch`` is the
permitted path — every legitimate caller uses it, and counting them would again mean exemptions. The
question the census actually asks is: *who reaches a position write WITHOUT going through the
ratified mapping?* The planted two-hop shape is a permanent negative control.

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

#: THE ANSWER. Exactly one module may read staged rows and REACH a position write, transitively.
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
_MIN_POSITION_WRITERS = 4  # direct + transitive reachers; the floor is on the DIRECT set
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


_ROOT_PACKAGES = frozenset({"irp_shared", "irp_backend", "irp_worker"})

#: The SANCTIONED route. A function defined here does NOT propagate write-reachability to whoever
#: calls it: calling ``load_batch`` IS the permitted path. Without this the census would flag every
#: legitimate caller of the loader and have to be silenced with exemptions.
INTERPRETER_MODULE = "irp_shared.ingest_mapping.service"


def _called_names(node: ast.AST) -> set[str]:
    """Every function name called anywhere inside ``node`` — bare and attribute forms alike.

    Attribute calls collapse to the attribute (``svc.create_position`` -> ``create_position``),
    deliberately over-capturing: a name collision costs a false positive that a reviewer resolves in
    one line, while a missed call costs the census its subject.
    """
    out: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        fn = child.func
        if isinstance(fn, ast.Name):
            out.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            out.add(fn.attr)
    return out


def _functions_of(tree: ast.AST) -> dict[str, set[str]]:
    """Top-level (and nested) function name -> the names its body calls."""
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out[node.name] = _called_names(node)
    return out


def _census(extra: dict[str, str] | None = None) -> tuple[set[str], set[str]]:
    """(modules that REACH a position write without the sanctioned route, modules that read staged
    rows).

    Reachability is a fixed point over CALL names at function granularity — see the module
    docstring for why import-following was rejected.

    ``extra`` injects synthetic module sources into the SAME analysis. It exists so the negative
    control can drive THIS function rather than its parts: a control that re-implements the
    algorithm proves the control works, not the census. A mutant that disabled the fixed point
    survived the first version of that control for exactly this reason.
    """
    readers: set[str] = set()
    module_calls: dict[str, set[str]] = {}
    functions: dict[str, dict[str, set[str]]] = {}
    text_writers: set[str] = set()

    sources: list[tuple[str, str]] = [
        (_module_name(path), path.read_text()) for path in _iter_modules()
    ]
    sources.extend((name, src) for name, src in (extra or {}).items())

    for module, text in sources:
        tree = ast.parse(text)
        module_calls[module] = _called_names(tree)
        functions[module] = _functions_of(tree)
        if _reads_staged_rows(tree, text):
            readers.add(module)
        if any(marker in text for marker in _POSITION_STRINGS):
            text_writers.add(module)  # a raw SQL INSERT is a write with no call name to follow

    write_names = set(_POSITION_CALLS)
    changed = True
    while changed:
        changed = False
        for module, defs in functions.items():
            for name, calls in defs.items():
                if name in write_names or module == INTERPRETER_MODULE:
                    continue  # the sanctioned route does not propagate
                if calls & write_names:
                    write_names.add(name)
                    changed = True

    reaches = set(text_writers)
    for module, calls in module_calls.items():
        if calls & write_names:
            reaches.add(module)
    return reaches, readers


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


def test_a_two_hop_bypass_is_caught() -> None:
    """The NEGATIVE CONTROL for the hole the first version had, kept permanently — and it drives
    ``_census()`` ITSELF.

    Module A reads staged rows and calls a plainly-named helper; module B calls ``create_position``
    and never mentions staged rows. Neither file is both a reader and a writer, so a per-file
    co-occurrence check reports nothing — which is what the first version did, verified by a
    reviewer who planted exactly this and watched every test stay green.

    The FIRST version of this control asserted against the algorithm's parts and a mutant that
    disabled the fixed point survived it. Driving the real function is the difference between
    testing the census and testing a re-implementation of it.
    """
    extra = {
        "irp_shared.zz_reader": (
            "from irp_shared.zz_writer import apply_row\n"
            "from irp_shared.ingestion.models import IngestionStagedRecord\n"
            "def load(session, batch_id):\n"
            "    for row in session.query(IngestionStagedRecord).all():\n"
            "        apply_row(session, row.payload)\n"
        ),
        "irp_shared.zz_writer": (
            "from irp_shared.position import create_position\n"
            "def apply_row(session, payload):\n"
            "    create_position(session, **payload)\n"
        ),
    }
    clean_writers, clean_readers = _census()
    assert (clean_writers & clean_readers) == EXPECTED_STAGED_TO_POSITION  # baseline

    writers, readers = _census(extra=extra)
    assert "irp_shared.zz_reader" in readers  # A alone looks like a mere reader...
    assert "irp_shared.zz_writer" in writers  # ...and B alone like a mere writer
    offenders = writers & readers
    assert "irp_shared.zz_reader" in offenders, (
        "the two-hop bypass was NOT caught — the census is back to per-file co-occurrence, which "
        "reports an empty offender list for a genuine second write path"
    )
    assert offenders != EXPECTED_STAGED_TO_POSITION


def test_a_legitimate_caller_of_the_loader_is_NOT_an_offender() -> None:
    """The other half, and it is what makes the census usable rather than merely strict.

    The demo stage reads staged rows AND reaches a position write — through ``load_batch``. If the
    census counted that it would flag the sanctioned route's own users, and the only way to keep it
    green would be an exemption list, which is how a census stops meaning anything. This asserts the
    real module is NOT in the offender set while genuinely being both a reader and a caller.
    """
    writers, readers = _census()
    stage = "irp_shared.demo.ingest1_stage28"
    assert stage in readers, "the demo stage really does read staged rows — the control is live"
    assert stage not in (writers & readers)


def test_the_call_walker_sees_both_call_shapes() -> None:
    """A bare call and an attribute call must both register, or which spelling a refactor happens to
    use decides whether the census can see it."""
    assert "create_position" in _called_names(ast.parse("create_position(s, x=1)\n"))
    assert "create_position" in _called_names(ast.parse("position.create_position(s, x=1)\n"))
    # ...and a mere REFERENCE without a call is not a call.
    assert "create_position" not in _called_names(ast.parse("fn = create_position\n"))


def test_the_census_actually_detects_known_production_writers() -> None:
    """The POSITIVE CONTROL, against REAL pre-existing sites rather than a freshly authored plant.

    A plant tests the matcher against a shape the matcher was written for. The sites in
    ``KNOWN_POSITION_WRITERS`` were here before this slice and are what a refactor would silently
    move out of view.

    *The sentence above said "these four sites" while the set held two — a stale prose count inside
    the slice's own positive control, corrected at W19-S3b. Naming the constant instead of counting
    it in prose is the fix that cannot go stale again.*
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
