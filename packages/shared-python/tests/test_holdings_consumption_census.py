"""W19-S3b: REQ-PPM-002 — every governed family resolves holdings through the position master.

The row, as re-amended at the Wave-19 planning gate:

    "every governed family that consumes holdings resolves them THROUGH the position master's
    as-of reconstruction at the run's pinned snapshot, asserted by a census of holdings-consuming
    code paths checked by EXACT SET EQUALITY, never subset... the holdings-consuming set is
    DISCOVERED MECHANICALLY, never hand-listed."

**Why the original wording was replaced, kept here because it is the whole point.** "Reconstructable
for any past as-of date" stays green while the next analytic ingests its own holdings CSV. The
purpose lives entirely in the word SINGLE and no clause tested it. And a hand list checked by exact
set equality against another hand list is circular — so the population is discovered from the
source, and the pin below is a RECORD of what discovery found, not the definition of it.

## What the census asks

Three questions, each answered mechanically from the AST of all three source trees:

1. **Which modules are governed families?** The ones that MINT a calculation run — a module whose
   own call set contains ``create_run`` or ``execute_governed_run``. Not the transitive closure:
   a demo stage that calls ``run_exposure`` is a CALLER of a family, not a family, and counting it
   would put the whole demo package in the subject and force an exemption list.
2. **Which of them consume holdings?** A family consumes holdings if it reaches the position
   master's as-of reconstruction (``reconstruct_holdings_as_of`` and siblings, or
   ``build_snapshot``, which is the direct caller of them) or reads pinned
   ``COMPONENT_KIND_POSITION`` components.
3. **Which of them reach the ``position`` TABLE directly?** That is the failure the row forbids —
   a family assembling run inputs from raw holdings rows instead of from the reconstruction.

The answer to (3), intersected with (1), must be EMPTY, and the answer to (2) is pinned by exact set
equality so a family silently dropping out of the reconstruction is loud rather than invisible.

**An empty expected set is the RPT-3 vacuity shape**, so it is never asserted alone: the offender
set is empty only alongside a positive control proving the raw-read matcher still fires on real
production sites, two negative controls proving a planted offender IS caught (one direct, one
two-hop), and a coverage floor on each population.

## DS3b-1, owner-ratified: consuming a PRE-BUILT snapshot counts

``run_exposure`` takes either a portfolio (build-in-request) or a pre-built ``snapshot_id`` produced
in an earlier, disconnected transaction, possibly by a different actor — reachable as
``POST /snapshots`` followed by a separate run. That COUNTS as resolving through the reconstruction.
The row's words are "at the run's pinned snapshot", and a snapshot's provenance is a property of the
snapshot: its components were produced by the as-of reader whoever asked for them. The alternative
would make a legitimate two-step workflow non-compliant, which nothing in the row asks for.

So the census asserts the HOLDINGS' provenance, not the caller's call graph — which is also why
``COMPONENT_KIND_POSITION`` counts as a sanctioned consumption shape.

## The rule that had to be repaired before it could be written

The first framing was binder-versus-consumer: "a family module may only read pinned components,
never call the binder". It contradicts itself. On ``run_exposure``'s DEFAULT path the consumer *is*
the binder-caller — it calls ``build_snapshot`` in its own transaction — so that rule would flag
exposure's own compliant path as the offender.

## The sanctioned route is CUT from the graph, not exempted

``irp_shared.holdings.service`` and ``irp_shared.position.position`` are where the as-of
reconstruction lives, and they necessarily query the ``position`` table. Functions defined there do
not propagate raw-read reachability to their callers, because calling them IS the permitted path.
Without the cut the census would flag every compliant family and the only way to keep it green would
be an exemption list — and an exemption list is how a census stops meaning anything (S3a's census
says so about itself, and this one inherits the rule rather than re-deciding it).

Two real raw readers survive the cut and are NOT families, so they need no exemption either: the
``GET /positions`` open-head listing, and S3a's demo stage reading the table as an ORACLE to verify
what the loader wrote. Both fall out of the intersection on their own.
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

#: Minting a governed calculation run. A module calling one of these IS a family; a module that
#: merely calls a family is not.
RUN_MINT_NAMES = frozenset({"create_run", "execute_governed_run"})

#: ...and the run-minting machinery itself is not a family. `create_run` is DEFINED in
#: `calc.service` and wrapped by `calc.scaffold`; both would otherwise nominate themselves.
CALC_MODULES = frozenset({"irp_shared.calc.service", "irp_shared.calc.scaffold"})

#: The SANCTIONED holdings routes. The first five are the position master's as-of readers;
#: ``build_snapshot`` is their direct caller and is what a family on the build-in-request path
#: actually invokes; ``COMPONENT_KIND_POSITION`` is the pinned-component shape DS3b-1 ratified as
#: equally compliant.
SANCTIONED_HOLDINGS_NAMES = frozenset(
    {
        "reconstruct_holdings_as_of",
        "reconstruct_subtree_holdings_as_of",
        "attach_marks_as_of",
        "reconstruct_position_as_of",
        "resolve_position",
        "build_snapshot",
        "COMPONENT_KIND_POSITION",
    }
)

#: The modules the sanctioned route is IMPLEMENTED in. Cut from the raw-read graph — see the module
#: docstring. This is a cut, not an exemption: it removes a ROUTE, and anything reaching the table
#: by any other path is still caught.
SANCTIONED_MODULES = frozenset({"irp_shared.holdings.service", "irp_shared.position.position"})

#: THE ANSWER to question (3). A family reaching the `position` table other than through the
#: reconstruction is what REQ-PPM-002 forbids.
EXPECTED_OFFENDERS: frozenset[str] = frozenset()

#: THE ANSWER to question (2), DISCOVERED and then recorded. Twenty-one of the twenty-five governed
#: families consume holdings, every one of them through the reconstruction.
EXPECTED_HOLDINGS_CONSUMERS = frozenset(
    {
        "irp_shared.concentration.service",
        "irp_shared.exposure.service",
        "irp_shared.pacing.service",
        "irp_shared.perf.benchmark_relative_service",
        "irp_shared.perf.desmoothing_service",
        "irp_shared.perf.return_service",
        "irp_shared.perf.rolling_service",
        "irp_shared.perf.sharpe_service",
        "irp_shared.risk.active_risk_service",
        "irp_shared.risk.covariance_service",
        "irp_shared.risk.es_backtest_service",
        "irp_shared.risk.factor_service",
        "irp_shared.risk.private_covariance_service",
        "irp_shared.risk.private_factor_service",
        "irp_shared.risk.proxy_weight_service",
        "irp_shared.risk.residual_shrinkage_service",
        "irp_shared.risk.scenario_service",
        "irp_shared.risk.service",
        "irp_shared.risk.var_backtest_service",
        "irp_shared.risk.var_hs_service",
        "irp_shared.risk.var_service",
    }
)

#: The four families that mint runs and do NOT consume holdings, pinned for the same reason: if one
#: of them starts reading holdings, that is a change to this requirement's subject and must be seen.
#: `report` and `reproduction` consume other families' governed OUTPUT; `liquidity` consumes
#: exposure results; `report_identity_proof` is a deploy-time proof.
EXPECTED_NON_CONSUMERS = frozenset(
    {
        "irp_shared.deploy.report_identity_proof",
        "irp_shared.liquidity.service",
        "irp_shared.report.service",
        "irp_shared.reproduction.service",
    }
)

#: Known RAW readers, for the positive control. Real pre-existing sites, neither of them a family.
KNOWN_RAW_READERS = frozenset(
    {
        "irp_backend.api.positions",  # GET /positions — the open-head listing
        "irp_shared.demo.ingest1_stage28",  # S3a's oracle, reading the table to VERIFY the load
    }
)

#: P6 floors, MEASURED at this slice. A collapse means the census lost its subject.
_MIN_FAMILIES = 20
_MIN_CONSUMERS = 18
_MIN_RAW_READERS = 2

#: A query construct naming the ORM class. Narrow on purpose: merely IMPORTING `Position` (the way
#: `snapshot.service` imports `PositionNotVisible` beside it) is not reading the table, and a
#: matcher that counted the import would flag half the repo and be silenced with exemptions.
_QUERY_CALLS = frozenset({"select", "query"})
_POSITION_CLASS = "Position"

#: The raw-SQL arm. Over-capturing deliberately, S3a's trade: a prose match costs one line of
#: review, a missed raw SELECT costs the census its subject.
_POSITION_SQL = ("FROM position", 'FROM "position"')


def _module_name(path: pathlib.Path) -> str:
    for tree in SOURCE_TREES:
        if tree in path.parents or tree == path.parent:
            return str(path.relative_to(tree.parent).with_suffix("")).replace("/", ".")
    raise AssertionError(path)  # pragma: no cover - every walked file is under a tree


def _iter_modules():  # noqa: ANN202
    for tree in SOURCE_TREES:
        for path in sorted(tree.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _called_names(node: ast.AST) -> set[str]:
    """Every function name called inside ``node`` — bare and attribute forms alike."""
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


def _referenced_names(node: ast.AST) -> set[str]:
    """Every name MENTIONED inside ``node``, called or not.

    Needed because ``COMPONENT_KIND_POSITION`` is a constant compared against, never called: a
    call-only walker would report every component-reading family as not consuming holdings.
    """
    out: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            out.add(child.id)
        elif isinstance(child, ast.Attribute):
            out.add(child.attr)
    return out


def queries_position_table(node: ast.AST) -> bool:
    """Does this node build a query over the ``position`` table itself?

    ``select(Position)`` / ``session.query(Position)`` / a raw ``FROM position``. Deliberately NOT
    "mentions the name Position": an import, a type annotation, or an exception class beside it are
    not reads, and treating them as reads is what turns a census into an exemption list.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            name = (
                fn.id
                if isinstance(fn, ast.Name)
                else fn.attr
                if isinstance(fn, ast.Attribute)
                else None
            )
            if name in _QUERY_CALLS and any(
                isinstance(arg, ast.Name) and arg.id == _POSITION_CLASS for arg in child.args
            ):
                return True
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if any(marker in child.value for marker in _POSITION_SQL):
                return True
    return False


class _Census:
    """What one run of the census found. Exposed as an object so every control drives the SAME
    computation rather than a re-implementation of it — the S3a lesson, where a mutant that disabled
    the fixed point survived a control asserting against the algorithm's parts."""

    def __init__(
        self,
        families: set[str],
        consumers: set[str],
        raw_readers: set[str],
        offenders: set[str],
    ) -> None:
        self.families = families
        self.consumers = consumers
        self.raw_readers = raw_readers
        self.offenders = offenders


def census(extra: dict[str, str] | None = None) -> _Census:
    """Walk the source trees and answer the census's three questions.

    ``extra`` injects synthetic module sources into the SAME analysis, so a negative control can
    plant an offender and watch this function catch it.
    """
    sources: list[tuple[str, str]] = [
        (_module_name(path), path.read_text()) for path in _iter_modules()
    ]
    sources.extend((name, src) for name, src in (extra or {}).items())

    module_names: dict[str, set[str]] = {}
    module_calls: dict[str, set[str]] = {}
    # module -> function name -> (names it mentions, does its own body query the table?)
    functions: dict[str, dict[str, tuple[set[str], bool]]] = {}

    for module, text in sources:
        tree = ast.parse(text)
        module_calls[module] = _called_names(tree)
        module_names[module] = _referenced_names(tree)
        functions[module] = {
            node.name: (
                _referenced_names(node) | _called_names(node),
                queries_position_table(node),
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }

    families = {
        module
        for module, calls in module_calls.items()
        if (calls & RUN_MINT_NAMES) and module not in CALC_MODULES
    }

    # (2) Sanctioned-route reachability, as a fixed point over names.
    sanctioned = set(SANCTIONED_HOLDINGS_NAMES)
    changed = True
    while changed:
        changed = False
        for defs in functions.values():
            for name, (mentions, _) in defs.items():
                if name not in sanctioned and mentions & sanctioned:
                    sanctioned.add(name)
                    changed = True
    consumers = {m for m in families if (module_calls[m] | module_names[m]) & sanctioned}

    # (3) Raw-read reachability, with the sanctioned route CUT out of the graph.
    raw_names: set[str] = set()
    seed_modules: set[str] = set()
    for module, defs in functions.items():
        if module in SANCTIONED_MODULES:
            continue
        for name, (_, reads) in defs.items():
            if reads:
                raw_names.add(name)
                seed_modules.add(module)
    changed = True
    while changed:
        changed = False
        for module, defs in functions.items():
            if module in SANCTIONED_MODULES:
                continue
            for name, (mentions, _) in defs.items():
                if name not in raw_names and mentions & raw_names:
                    raw_names.add(name)
                    changed = True
    raw_readers = set(seed_modules)
    for module, calls in module_calls.items():
        if module in SANCTIONED_MODULES:
            continue
        if calls & raw_names:
            raw_readers.add(module)

    return _Census(families, consumers, raw_readers, families & raw_readers)


def test_no_governed_family_reads_the_position_table_directly() -> None:
    """THE requirement. EXACT SET EQUALITY, never subset — a subset check passes on an empty set,
    the shape that let a shipped contract census go green over nothing (the RPT-3 defect).

    This assertion is empty-set-valued, which is exactly the vacuity risk, so it is meaningless on
    its own: the controls below prove the matcher fires, prove a planted offender is caught in both
    the direct and the two-hop shape, and floor each population.
    """
    result = census()
    assert result.offenders == EXPECTED_OFFENDERS, (
        f"governed families reading the `position` table outside the as-of reconstruction: "
        f"{sorted(result.offenders)}. REQ-PPM-002's word is SINGLE — a family assembling run "
        f"inputs from raw holdings rows is a second source of holdings, whatever it agrees with."
    )


def test_the_holdings_consuming_population_is_pinned_exactly() -> None:
    """The discovered population, RECORDED. Exact equality in both directions, so a family that
    stops resolving through the reconstruction — or a new family that never started — is loud."""
    result = census()
    assert result.consumers == EXPECTED_HOLDINGS_CONSUMERS, (
        f"added: {sorted(result.consumers - EXPECTED_HOLDINGS_CONSUMERS)}; "
        f"dropped: {sorted(EXPECTED_HOLDINGS_CONSUMERS - result.consumers)}"
    )
    assert result.families - result.consumers == EXPECTED_NON_CONSUMERS, (
        f"the set of run-minting families that do NOT consume holdings changed: "
        f"{sorted(result.families - result.consumers)}"
    )
    # ...and every consumer is a family, which is what makes the intersection above meaningful.
    assert result.consumers <= result.families


def test_a_family_reading_the_table_directly_is_CAUGHT() -> None:
    """NEGATIVE CONTROL, direct shape — and it drives ``census()`` itself.

    A new family mints a run and builds its holdings from ``select(Position)``. This is the exact
    thing the row's original wording stayed green over: both-axes as-of reconstruction still passes
    while this module ingests holdings its own way.
    """
    planted = {
        "irp_shared.zz_rogue_family": (
            "from sqlalchemy import select\n"
            "from irp_shared.position.models import Position\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_rogue(session, tenant_id, as_of):\n"
            "    rows = session.execute(select(Position)).scalars().all()\n"
            "    run = create_run(session, tenant_id=tenant_id, run_type='ROGUE')\n"
            "    return run, rows\n"
        )
    }
    baseline = census()
    assert baseline.offenders == EXPECTED_OFFENDERS

    result = census(extra=planted)
    assert "irp_shared.zz_rogue_family" in result.families
    assert "irp_shared.zz_rogue_family" in result.raw_readers
    assert "irp_shared.zz_rogue_family" in result.offenders, (
        "a family reading the `position` table directly was NOT caught — the census cannot see "
        "the one thing REQ-PPM-002 forbids"
    )
    assert result.offenders != EXPECTED_OFFENDERS


def test_a_TWO_HOP_family_bypass_is_CAUGHT() -> None:
    """NEGATIVE CONTROL, two-hop shape — the hole S3a's census shipped with and had to repair.

    The family never names ``Position``; it calls a plainly-named helper in another module that
    does. No single file is both, so a per-file co-occurrence check reports nothing.
    Extract-a-helper is the most ordinary refactor there is, which is why this control is
    permanent.
    """
    planted = {
        "irp_shared.zz_holdings_repo": (
            "from sqlalchemy import select\n"
            "from irp_shared.position.models import Position\n"
            "def fetch_book(session):\n"
            "    return session.execute(select(Position)).scalars().all()\n"
        ),
        "irp_shared.zz_sneaky_family": (
            "from irp_shared.zz_holdings_repo import fetch_book\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_sneaky(session, tenant_id):\n"
            "    rows = fetch_book(session)\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='SNEAKY'), rows\n"
        ),
    }
    result = census(extra=planted)
    assert "irp_shared.zz_sneaky_family" in result.families
    assert "irp_shared.zz_holdings_repo" not in result.families  # the helper mints nothing...
    assert "irp_shared.zz_sneaky_family" in result.offenders, (
        "the two-hop bypass was NOT caught — the census is back to per-file co-occurrence, which "
        "reports an empty offender list for a genuine second source of holdings"
    )


def test_a_family_using_the_SANCTIONED_route_is_not_an_offender() -> None:
    """The other half, and it is what makes the census usable rather than merely strict.

    A compliant family calls ``build_snapshot``, which calls the as-of readers, which query the
    table. If the census counted that, it would flag every compliant family and the only way back to
    green would be an exemption list. Planted rather than asserted about a real module, so the claim
    is about the RULE and not about one file's current contents.
    """
    planted = {
        "irp_shared.zz_good_family": (
            "from irp_shared.snapshot.service import build_snapshot\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_good(session, tenant_id, portfolio_id, as_of):\n"
            "    snap = build_snapshot(session, tenant_id=tenant_id, portfolio_id=portfolio_id)\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='GOOD'), snap\n"
        )
    }
    result = census(extra=planted)
    assert "irp_shared.zz_good_family" in result.families
    assert "irp_shared.zz_good_family" in result.consumers, (
        "a family reaching holdings through `build_snapshot` was not counted as a holdings "
        "consumer — the sanctioned-route arm has stopped matching, and then the offender set is "
        "empty for the wrong reason"
    )
    assert "irp_shared.zz_good_family" not in result.offenders


def test_the_pinned_component_shape_counts_as_consumption() -> None:
    """DS3b-1(a), as an executable statement rather than a note.

    A family handed a pre-built ``snapshot_id`` reads ``COMPONENT_KIND_POSITION`` components and
    never calls a binder. That IS resolving through the reconstruction: the components are its
    output, and a snapshot's provenance is a property of the snapshot.
    """
    planted = {
        "irp_shared.zz_pinned_family": (
            "from irp_shared.snapshot.models import COMPONENT_KIND_POSITION\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_pinned(session, tenant_id, comps):\n"
            "    rows = [c for c in comps if c.component_kind == COMPONENT_KIND_POSITION]\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='PINNED'), rows\n"
        )
    }
    result = census(extra=planted)
    assert "irp_shared.zz_pinned_family" in result.consumers
    assert "irp_shared.zz_pinned_family" not in result.offenders


def test_the_raw_read_matcher_still_sees_known_production_sites() -> None:
    """POSITIVE CONTROL against REAL sites, not a freshly authored plant.

    An empty offender list from a BROKEN matcher is indistinguishable from total compliance. These
    two modules really do query the table and really are not families; if the matcher stops seeing
    them it has broken, whatever it says about the offender set.
    """
    result = census()
    missing = KNOWN_RAW_READERS - result.raw_readers
    assert not missing, (
        f"the raw-read matcher no longer sees known production sites: {sorted(missing)} — the "
        f"matcher is broken, and a broken matcher reports total compliance"
    )
    assert not (KNOWN_RAW_READERS & result.families), (
        "a known raw reader became a governed family — that is a real offender, not a control "
        "failure, and the intersection above should have said so"
    )


def test_the_sanctioned_cut_is_LIVE_and_not_a_no_op() -> None:
    """The cut has to be removing something, or it is decoration.

    Both cut modules genuinely query the ``position`` table — that is why they are the sanctioned
    route. Proven by running the matcher over their real source, so a refactor that moves the
    reconstruction elsewhere makes this fail rather than silently widening the cut to nothing.
    """
    for module in SANCTIONED_MODULES:
        path = REPO / "packages/shared-python/src" / (module.replace(".", "/") + ".py")
        tree = ast.parse(path.read_text())
        hits = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and queries_position_table(node)
        ]
        assert hits, (
            f"{module} is cut from the raw-read graph as the sanctioned route, but no function in "
            f"it queries the `position` table — the cut is now hiding nothing, or hiding the wrong "
            f"thing"
        )
    result = census()
    assert not (SANCTIONED_MODULES & result.raw_readers)


def test_every_population_has_a_coverage_floor() -> None:
    """P6. A matcher covers only the shapes someone thought of; a floor notices coverage FALLING,
    whatever the next shape turns out to be. Measured at this slice, not guessed."""
    result = census()
    assert len(result.families) >= _MIN_FAMILIES, (
        f"the governed-family population collapsed to {len(result.families)} (floor "
        f"{_MIN_FAMILIES}) — the census has lost its subject"
    )
    assert len(result.consumers) >= _MIN_CONSUMERS, (
        f"the holdings-consuming population collapsed to {len(result.consumers)} (floor "
        f"{_MIN_CONSUMERS})"
    )
    assert len(result.raw_readers) >= _MIN_RAW_READERS, (
        f"the raw-read population collapsed to {len(result.raw_readers)} (floor "
        f"{_MIN_RAW_READERS}) — nothing left for the matcher to find means nothing proves it works"
    )


def test_the_query_matcher_distinguishes_a_read_from_a_mention() -> None:
    """The matcher's own boundary, because getting this wrong in either direction breaks the census.

    Too narrow and a real read walks past it; too wide and every module importing a name near
    ``Position`` becomes an offender, which is answered with exemptions.
    """
    reads = "session.execute(select(Position).where(Position.tenant_id == t))"
    assert queries_position_table(ast.parse(reads))
    assert queries_position_table(ast.parse("session.query(Position).all()"))
    assert queries_position_table(ast.parse('session.execute(text("SELECT id FROM position"))'))
    assert queries_position_table(
        ast.parse("session.execute(text('SELECT id FROM \"position\" WHERE id = :i'))")
    )
    # ...and these are NOT reads
    assert not queries_position_table(ast.parse("from irp_shared.position import Position\n"))
    assert not queries_position_table(ast.parse("def f(p: Position) -> None:\n    return None\n"))
    assert not queries_position_table(ast.parse("raise PositionNotVisible(pid)\n"))
    assert not queries_position_table(ast.parse("session.execute(select(Valuation)).all()\n"))


def test_the_family_matcher_needs_a_MINT_not_a_call() -> None:
    """A caller of a family is not a family. Without this the demo package joins the subject, and
    every demo stage that both runs exposure and reads the table for an oracle becomes an offender
    needing an exemption — which is how the first draft of this census went wrong."""
    result = census()
    assert "irp_shared.demo.ingest1_stage28" in result.raw_readers  # it really does read the table
    assert "irp_shared.demo.ingest1_stage28" not in result.families
    assert "irp_shared.demo.ingest1_stage28" not in result.offenders
    # ...and no demo stage is a family at all.
    assert not [m for m in result.families if m.startswith("irp_shared.demo.")]
