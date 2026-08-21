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

#: THE ANSWER to question (1) — the census's SUBJECT, pinned so it cannot narrow silently. The
#: twenty-five modules that mint a governed calculation run by a DIRECT call.
EXPECTED_FAMILIES = frozenset(
    {
        "irp_shared.concentration.service",
        "irp_shared.deploy.report_identity_proof",
        "irp_shared.exposure.service",
        "irp_shared.liquidity.service",
        "irp_shared.pacing.service",
        "irp_shared.perf.benchmark_relative_service",
        "irp_shared.perf.desmoothing_service",
        "irp_shared.perf.return_service",
        "irp_shared.perf.rolling_service",
        "irp_shared.perf.sharpe_service",
        "irp_shared.report.service",
        "irp_shared.reproduction.service",
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

#: THE ANSWER to question (2), DISCOVERED and then recorded. **Exactly ONE** governed family
#: consumes holdings: the exposure family, which reads pinned ``COMPONENT_KIND_POSITION``
#: components (and calls ``build_snapshot`` on its build-in-request path). Every other governed
#: family consumes another family's pinned governed OUTPUT — factor rows, covariance rows, exposure
#: atoms, portfolio returns — never holdings.
#:
#: **This pin said TWENTY-ONE for one commit and that was a name-collision artifact**, found by a
#: different-engine review and confirmed by grep: ``covariance_service``, ``factor_service``,
#: ``perf/return_service`` and ``pacing/service`` contain ZERO references to any of the seven
#: sanctioned names. They were credited because the reachability fixed point ran over BARE function
#: names, ``exposure.service`` reaches the reconstruction through a private helper called
#: ``_compute``, and every governed family names its ``execute_governed_run`` callback ``_compute``.
#: One generic name entered the reachable set and carried twenty families with it. Reachability is
#: now module-qualified and resolved through each module's own imports.
#:
#: The corrected answer is the more useful one: REQ-PPM-002's "SINGLE source of holdings" is, today,
#: a claim about one module.
EXPECTED_HOLDINGS_CONSUMERS = frozenset({"irp_shared.exposure.service"})

#: The twenty-four families that mint governed runs and do NOT consume holdings, pinned for the
#: same reason as the consumers: if one of them starts reading holdings, that is a change to this
#: requirement's SUBJECT and must be seen rather than absorbed. They consume other families' pinned
#: governed output. (``var_service`` looks like a counter-example to a substring grep — it contains
#: ``build_snapshot_fn``, a LOCAL VARIABLE holding one of the var snapshot builders. The AST is
#: exact where grep is not, and that difference is why the census reads the AST.)
EXPECTED_NON_CONSUMERS = frozenset(
    {
        "irp_shared.concentration.service",
        "irp_shared.deploy.report_identity_proof",
        "irp_shared.liquidity.service",
        "irp_shared.pacing.service",
        "irp_shared.perf.benchmark_relative_service",
        "irp_shared.perf.desmoothing_service",
        "irp_shared.perf.return_service",
        "irp_shared.perf.rolling_service",
        "irp_shared.perf.sharpe_service",
        "irp_shared.report.service",
        "irp_shared.reproduction.service",
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

#: Known RAW readers, for the positive control. Real pre-existing sites. NONE of them is a governed
#: family, which is why the offender intersection is empty without a single exemption.
#:
#: The two SANCTIONED modules appear here too, and that is the CUT WORKING rather than failing: the
#: cut is FUNCTION-scoped, so ``holdings/service.py`` and ``position/position.py`` are still seen to
#: read the table — only propagation THROUGH the reconstruction's named entry points is stopped. The
#: cut used to be module-scoped, and a different-engine review demonstrated the escape hatch that
#: opened: any NEW helper added to either file (a debug export, a reporting shortcut) inherited
#: blanket immunity, invisible to every assertion here.
KNOWN_RAW_READERS = frozenset(
    {
        "irp_backend.api.positions",  # GET /positions — the open-head listing
        "irp_shared.demo.ingest1_stage28",  # S3a's oracle, reading the table to VERIFY the load
        "irp_shared.holdings.service",  # the set-returning as-of reconstruction itself
        "irp_shared.position.position",  # the governed binders + the single-position as-of read
        "irp_shared.ingest_mapping.service",  # the interpreter's load path
        "irp_shared.synthetic.builder",  # the deterministic test-data builder
    }
)

#: P6 floors, MEASURED at this slice. A collapse means the census lost its subject.
#:
#: ``_MIN_CONSUMERS`` is 1 and that is deliberately weak — the honest population IS one. The real
#: guard on that side is the exact-set pin above; the floor's only job here is to catch the
#: sanctioned-route arm silently matching NOTHING, which would empty the offender set for the wrong
#: reason.
_MIN_FAMILIES = 20
_MIN_CONSUMERS = 1
_MIN_RAW_READERS = 4

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


def _string_constants(node: ast.AST) -> list[str]:
    """Every string this node could produce, with concatenations and f-strings JOINED.

    A raw SQL read built as ``"SELECT ... FROM " + "position"`` parses as a ``BinOp`` of two
    ``Constant`` nodes, neither containing the marker; an f-string is a ``JoinedStr`` and is not a
    ``Constant`` at all. Both escaped the first matcher — demonstrated by execution in the
    different-engine review — so both are folded here before the markers are looked for.
    """
    out: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Add):
            parts = [
                g.value
                for g in ast.walk(child)
                if isinstance(g, ast.Constant) and isinstance(g.value, str)
            ]
            if parts:
                out.append("".join(parts))
        elif isinstance(child, ast.JoinedStr):
            out.append(
                "".join(
                    g.value
                    for g in child.values
                    if isinstance(g, ast.Constant) and isinstance(g.value, str)
                )
            )
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append(child.value)
    return out


def position_aliases(tree: ast.AST) -> frozenset[str]:
    """Every local name in this module that IS the ``Position`` ORM class.

    ``from irp_shared.position.models import Position as P`` makes ``select(P)`` a read of the
    position table, and the first matcher compared against the literal name and missed it.
    """
    names = {_POSITION_CLASS}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _POSITION_CLASS:
                    names.add(alias.asname or alias.name)
    return frozenset(names)


#: Eager-load verbs. ``joinedload(Other.position)`` pulls position ROWS through a relationship
#: without ever naming the class in the query's subject — the fifth escape the review executed.
_LOADER_CALLS = frozenset({"joinedload", "selectinload", "subqueryload", "contains_eager"})
_RELATIONSHIP_ATTRS = frozenset({"position", "positions"})


def queries_position_table(node: ast.AST, aliases: frozenset[str] | None = None) -> bool:
    """Does this node read the ``position`` table itself?

    Deliberately NOT "mentions the name Position": an import, a type annotation, or an exception
    class beside it are not reads, and treating them as reads is what turns a census into an
    exemption list.

    **Five equivalent shapes escaped the first version**, every one of them planted and executed by
    a different-engine review rather than imagined: an aliased import, ``getattr(models,
    'Position')``, concatenated raw SQL, an f-string, and an eager-load through a relationship.
    Each is handled below and each has its own assertion in
    :func:`test_the_query_matcher_distinguishes_a_read_from_a_mention`. The list is not claimed to
    be exhaustive — a matcher only covers the shapes someone thought of, which is what the coverage
    floors are for.
    """
    names = aliases or frozenset({_POSITION_CLASS})
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            call_name = (
                fn.id
                if isinstance(fn, ast.Name)
                else fn.attr
                if isinstance(fn, ast.Attribute)
                else None
            )
            if call_name in _QUERY_CALLS:
                for arg in child.args:
                    # the plain shape, and the aliased-import shape
                    if isinstance(arg, ast.Name) and arg.id in names:
                        return True
                    # `select(getattr(models, "Position"))` and anything else naming it as a string
                    if any(isinstance(g, ast.Constant) and g.value in names for g in ast.walk(arg)):
                        return True
                    if isinstance(arg, ast.Attribute) and arg.attr in names:
                        return True
            # an eager load pulls position ROWS without the class ever being the query's subject
            if call_name in _LOADER_CALLS:
                for arg in child.args:
                    if isinstance(arg, ast.Attribute) and arg.attr in _RELATIONSHIP_ATTRS:
                        return True
    return any(marker in text for text in _string_constants(node) for marker in _POSITION_SQL)


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


def _import_map(tree: ast.AST) -> dict[str, str]:
    """Local name -> the module it was imported FROM.

    This is what makes reachability MODULE-QUALIFIED, and it is the fix for a BLOCKING defect the
    first version of this census shipped. See :func:`census`.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out[(alias.asname or alias.name).split(".")[0]] = alias.name
    return out


def census(extra: dict[str, str] | None = None) -> _Census:
    """Walk the source trees and answer the census's three questions.

    ``extra`` injects synthetic module sources into the SAME analysis, so a negative control can
    plant an offender and watch this function catch it.

    **Reachability is MODULE-QUALIFIED, over ``(module, function)`` pairs resolved through each
    module's own imports.** The first version propagated over BARE function names, and a
    different-engine review reproduced what that costs: ``exposure.service`` reaches
    ``COMPONENT_KIND_POSITION`` through a private helper named ``_compute``, and every other
    governed family also names its ``execute_governed_run`` callback ``_compute``. One generic name
    entered the reachable set and credited **twenty** families as holdings consumers that contain no
    reference to any sanctioned name at all — verified by grep: ``covariance_service``,
    ``factor_service``, ``perf/return_service`` and ``pacing/service`` each have ZERO hits on all
    seven. The pin was a name-collision artifact and the census's positive claim was false.

    A call resolves to ``(this module, name)`` if the module defines it, else to
    ``(imported-from module, name)`` if the module imports it, else it does NOT resolve and does NOT
    propagate. Unresolved attribute calls (``svc.helper()``) are dropped rather than matched by
    name — deliberately, and asymmetrically justified: over-capturing on the SANCTIONED side
    silently credits a family that consumes nothing, which is the defect above, while
    under-capturing there can only turn a real consumer into a pin mismatch, which is loud.

    **The sanctioned cut is FUNCTION-scoped, not module-scoped.** It used to skip the whole of
    ``holdings/service.py`` and ``position/position.py``, so any NEW helper added to either file —
    a debug export, a reporting shortcut — would have inherited blanket immunity, and the same
    review demonstrated exactly that escape hatch. Propagation now stops AT a function named in
    ``SANCTIONED_HOLDINGS_NAMES`` and nowhere else, so a raw read added anywhere, including inside
    those two files, is still reachable.

    **Family detection is a fixed point too**, for the same reason: a family whose ``create_run``
    call sits behind one shared ``start_run(...)`` wrapper used to fall out of the census's subject
    entirely — neither consumer, nor non-consumer, nor offender.
    """
    sources: list[tuple[str, str]] = [
        (_module_name(path), path.read_text()) for path in _iter_modules()
    ]
    sources.extend((name, src) for name, src in (extra or {}).items())

    imports: dict[str, dict[str, str]] = {}
    module_names: dict[str, set[str]] = {}
    module_calls: dict[str, set[str]] = {}
    # module -> function name -> (names it mentions, does its own body query the table?)
    functions: dict[str, dict[str, tuple[set[str], bool]]] = {}

    for module, text in sources:
        tree = ast.parse(text)
        imports[module] = _import_map(tree)
        module_calls[module] = _called_names(tree)
        module_names[module] = _referenced_names(tree)
        module_aliases = position_aliases(tree)
        functions[module] = {
            node.name: (
                _referenced_names(node) | _called_names(node),
                queries_position_table(node, module_aliases),
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }

    def resolve(module: str, name: str) -> tuple[str, str] | None:
        """Which (module, function) does ``name`` mean, seen from ``module``?"""
        if name in functions.get(module, {}):
            return (module, name)
        target = imports.get(module, {}).get(name)
        if target and target in functions:
            return (target, name) if name in functions[target] else None
        return None

    def reaching(seeds: set[tuple[str, str]], *, stop_at: frozenset[str]) -> set[tuple[str, str]]:
        """Fixed point over qualified functions, never propagating THROUGH a ``stop_at`` name."""
        reach = set(seeds)
        changed = True
        while changed:
            changed = False
            for module, defs in functions.items():
                for name, (mentions, _) in defs.items():
                    if (module, name) in reach or name in stop_at:
                        continue
                    for mentioned in mentions:
                        target = resolve(module, mentioned)
                        if target is not None and target in reach:
                            reach.add((module, name))
                            changed = True
                            break
        return reach

    _NONE: frozenset[str] = frozenset()

    # (1) Governed families: modules that MINT a run, by a DIRECT call. Not the transitive closure
    #     — that was tried and it makes every demo stage calling `run_exposure` a "family", which
    #     puts the whole demo package in the subject and forces exactly the exemption list this
    #     census refuses to have. A family is the module that mints; its callers are callers.
    families = {
        module
        for module, calls in module_calls.items()
        if (calls & RUN_MINT_NAMES) and module not in CALC_MODULES
    }

    # (2) Sanctioned-route reachability. Seeded on functions that MENTION a sanctioned name, then
    #     propagated through RESOLVED calls only.
    sanct_seeds = {
        (m, n)
        for m, defs in functions.items()
        for n, (mentions, _) in defs.items()
        if mentions & SANCTIONED_HOLDINGS_NAMES
    }
    sanct_reach = reaching(sanct_seeds, stop_at=_NONE)
    consumers: set[str] = set()
    for module in families:
        if module_names[module] & SANCTIONED_HOLDINGS_NAMES:
            consumers.add(module)
            continue
        for called in module_calls[module]:
            target = resolve(module, called)
            if target is not None and target in sanct_reach:
                consumers.add(module)
                break

    # (3) Raw-read reachability, stopping AT the reconstruction's own entry points.
    raw_seeds = {(m, n) for m, defs in functions.items() for n, (_, reads) in defs.items() if reads}
    raw_reach = reaching(raw_seeds, stop_at=SANCTIONED_HOLDINGS_NAMES)
    raw_readers: set[str] = set()
    for module in functions:
        if any((module, n) in raw_reach for n in functions[module]):
            raw_readers.add(module)
            continue
        for called in module_calls[module]:
            target = resolve(module, called)
            if (
                target is not None
                and target in raw_reach
                and target[1] not in SANCTIONED_HOLDINGS_NAMES
            ):
                raw_readers.add(module)
                break

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


def test_a_MULTI_HOP_family_bypass_is_CAUGHT() -> None:
    """NEGATIVE CONTROL for the fixed point — and the FIRST version of it did not test the fixed
    point at all, which mutation ``M-S3B-7`` proved by surviving it.

    That version planted a TWO-hop chain: family -> helper -> ``select(Position)``. Two hops are
    caught by the SEEDING step alone, because the helper's own body queries the table, so its name
    is already in the raw set before a single iteration runs. Disabling the propagation loop
    entirely left the control green. It was S3a's lesson verbatim — a control asserting against the
    algorithm's parts rather than driving the thing itself — reproduced in the census written to
    apply that lesson.

    So the chain is THREE hops: only the middle link, which names nothing itself, requires
    propagation to be discovered. Both depths are asserted, because the two-hop shape is the one a
    real refactor produces and the three-hop shape is the one that proves the mechanism.
    """
    planted = {
        "irp_shared.zz_holdings_repo": (
            "from sqlalchemy import select\n"
            "from irp_shared.position.models import Position\n"
            "def fetch_book(session):\n"
            "    return session.execute(select(Position)).scalars().all()\n"
        ),
        # The MIDDLE link. It names neither `Position` nor a query — it is discovered only by
        # following `fetch_book`, which is exactly what the fixed point is for.
        "irp_shared.zz_book_facade": (
            "from irp_shared.zz_holdings_repo import fetch_book\n"
            "def current_book(session):\n"
            "    return [r for r in fetch_book(session) if r.system_to is None]\n"
        ),
        "irp_shared.zz_sneaky_family": (
            "from irp_shared.zz_book_facade import current_book\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_sneaky(session, tenant_id):\n"
            "    rows = current_book(session)\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='SNEAKY'), rows\n"
        ),
    }
    result = census(extra=planted)
    assert "irp_shared.zz_sneaky_family" in result.families
    assert "irp_shared.zz_holdings_repo" not in result.families  # the helper mints nothing...
    assert "irp_shared.zz_book_facade" not in result.families  # ...nor does the facade
    assert "irp_shared.zz_sneaky_family" in result.offenders, (
        "the THREE-hop bypass was NOT caught — the reachability fixed point is not running, and a "
        "family two refactors away from the table reports as compliant"
    )

    # ...and the ordinary two-hop shape, which a real extract-a-helper produces.
    two_hop = {
        "irp_shared.zz_holdings_repo": planted["irp_shared.zz_holdings_repo"],
        "irp_shared.zz_direct_family": (
            "from irp_shared.zz_holdings_repo import fetch_book\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_direct(session, tenant_id):\n"
            "    rows = fetch_book(session)\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='D'), rows\n"
        ),
    }
    assert "irp_shared.zz_direct_family" in census(extra=two_hop).offenders


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
    # ...and the cut is FUNCTION-scoped, which these two assertions together pin.
    #
    # The sanctioned modules ARE raw readers — they read the table, that is what they are for — and
    # an earlier version asserted the opposite, because the cut used to remove those two files from
    # the graph entirely. A different-engine review showed what that bought: any NEW helper added to
    # either file got blanket immunity from the offender check. What must be true is not that those
    # modules are invisible, but that no FAMILY reaches the table THROUGH the reconstruction's named
    # entry points.
    result = census()
    assert SANCTIONED_MODULES <= result.raw_readers, (
        "the sanctioned modules no longer read the position table — the reconstruction has moved, "
        "and the cut is now stopping propagation through functions that do not do the reading"
    )
    assert not (SANCTIONED_MODULES & result.families)
    assert not (SANCTIONED_MODULES & result.offenders)


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


def test_every_ALTERNATE_READ_SHAPE_is_caught() -> None:
    """The five bypasses a different-engine review PLANTED AND EXECUTED against the first matcher.

    Every one of them produced a module that mints a run, reads the `position` table, and was not
    an offender — while all six existing controls stayed green, because every one of them used the
    identical `select(Position)` call form. A matcher covers the shapes someone thought of; these
    are the shapes someone else thought of, and they are pinned here so they stay covered.

    Not claimed to be exhaustive. That is what the coverage floors are for.
    """
    shapes = {
        "aliased import": (
            "from sqlalchemy import select\n"
            "from irp_shared.position.models import Position as P\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_alias(session, tenant_id):\n"
            "    rows = session.execute(select(P)).scalars().all()\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='A'), rows\n"
        ),
        "getattr on the models module": (
            "from sqlalchemy import select\n"
            "from irp_shared.position import models as pm\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_getattr(session, tenant_id):\n"
            "    rows = session.execute(select(getattr(pm, 'Position'))).scalars().all()\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='G'), rows\n"
        ),
        "concatenated raw SQL": (
            "from sqlalchemy import text\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_concat(session, tenant_id):\n"
            "    sql = 'SELECT id, quantity FROM ' + 'position' + ' WHERE system_to IS NULL'\n"
            "    rows = session.execute(text(sql)).fetchall()\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='C'), rows\n"
        ),
        "f-string raw SQL": (
            "from sqlalchemy import text\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_fstring(session, tenant_id, col):\n"
            "    rows = session.execute(text(f'SELECT {col} FROM position')).fetchall()\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='F'), rows\n"
        ),
        "eager load through a relationship": (
            "from sqlalchemy import select\n"
            "from sqlalchemy.orm import joinedload\n"
            "from irp_shared.portfolio.models import Portfolio\n"
            "from irp_shared.calc.service import create_run\n"
            "def run_eager(session, tenant_id):\n"
            "    q = select(Portfolio).options(joinedload(Portfolio.positions))\n"
            "    rows = session.execute(q).unique().scalars().all()\n"
            "    return create_run(session, tenant_id=tenant_id, run_type='E'), rows\n"
        ),
    }
    escaped = []
    for label, source in shapes.items():
        module = "irp_shared.zz_shape_" + label.replace(" ", "_")
        result = census(extra={module: source})
        assert module in result.families, f"{label}: the plant did not even register as a family"
        if module not in result.offenders:
            escaped.append(label)
    assert not escaped, (
        f"these read shapes escape the matcher entirely: {escaped}. A family using any of them "
        f"assembles run inputs from raw holdings rows while the census stays green."
    )


def test_the_FAMILY_population_is_pinned_exactly() -> None:
    """The census's SUBJECT, pinned by exact set equality — so it cannot narrow silently.

    A review raised the mint-wrapper case: a shared ``start_run(...)`` convenience wrapper is an
    ordinary DRY refactor, and it would move the direct mint call out of the family modules and drop
    those families out of this census entirely — neither consumer, nor non-consumer, nor offender.
    ``_MIN_FAMILIES`` alone tolerates losing several before it notices.

    A tripwire was tried first and DISCARDED, which is worth recording. It flagged any module that
    mints a run and is imported elsewhere — and that fires on all twenty-five, because every
    family's ``run_*`` entry point mints and is imported by a demo stage or an API router. It
    cannot tell "a demo stage calling ``run_exposure``" (correct, and by design not a family) from
    "a family calling a shared helper" (the harmful case). The two are distinguished only by
    whether the CALLER is a governed family in its own right — the question being computed. A guard
    that
    fires on everything is worse than no guard: it teaches its reader to ignore it.

    So the guard is this pin instead. It is precise, mechanical, and strictly stronger for the
    stated risk: losing even ONE family to a wrapper fails here by name, and gaining one demands a
    deliberate edit.
    """
    result = census()
    assert result.families == EXPECTED_FAMILIES, (
        f"added: {sorted(result.families - EXPECTED_FAMILIES)}; "
        f"dropped: {sorted(EXPECTED_FAMILIES - result.families)}. A family dropping out is not a "
        f"pin to update — it means the module stopped minting its run directly, and every claim "
        f"this census makes about it silently stopped being made."
    )
    # ...and the two halves partition it, so no family is left unclassified.
    assert result.consumers | EXPECTED_NON_CONSUMERS == result.families
    assert not (result.consumers & EXPECTED_NON_CONSUMERS)


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
