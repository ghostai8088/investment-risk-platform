"""STRUCT-2 (REQ-PPM-009) — the portfolio-name census, MECHANICAL discovery + the pinned taxonomy.

The row: "No computation reads the name field: this is checked by a census of the code paths that
read it, and a read anywhere outside display code FAILS." The ratified DP-8 taxonomy is
three-way — DISPLAY / PROVENANCE_CAPTURE (recorded and byte-compared, never interpreted) /
COMPUTATION — with only COMPUTATION forbidden, because a display-only rule would fail a CORRECT
design: the snapshot pin includes the name deliberately, so an EV amend moves the hash (TR-09).

Discovery is repo-wide and mechanical (the review's V-009-1 fold — classification without
discovery finds nothing new):

- every ``.name`` ATTRIBUTE read (Load context) across the three Python source trees, keyed by
  (module, enclosing function, receiver expression) — receiver-text keys, never line numbers;
- every ``getattr`` call site (the dynamic reads a literal grep cannot see) — the full site list
  is pinned, and the two portfolio-relevant loops' key constants are asserted to still carry
  "name" so the classification cannot silently detach from the code;
- the frontend ``.ts``/``.tsx`` trees, where the file-level hit set is pinned (zero portfolio
  reads exist; the walk resolves the demo book by ``code``).

EXACT set equality throughout: a NEW name read anywhere fails until classified here.
"""

from __future__ import annotations

import ast
import pathlib
import re

_REPO = pathlib.Path(__file__).resolve().parents[3]
_PY_ROOTS = (
    _REPO / "packages/shared-python/src/irp_shared",
    _REPO / "apps/backend/src/irp_backend",
    _REPO / "apps/worker/src/irp_worker",
)

D = "DISPLAY"
V = "PROVENANCE_CAPTURE"
O = "OTHER_ENTITY"  # noqa: E741 - a taxonomy code: the .name of a non-portfolio entity
B = "REQUEST_BODY"  # a Pydantic request field pass-through, not an entity read
E = "ENGINE_INTERNAL"  # SQLAlchemy dialect/column machinery
# COMPUTATION is deliberately ABSENT from the allowlist below: a site classified COMPUTATION has
# no legal value, so the only way to add one is to change this file — in review, with the row's
# "a read anywhere outside display code FAILS" staring back.

#: (module tail, function, receiver) -> class. Portfolio sites are the census's subject; every
#: other hit is pinned so the DISCOVERY set stays exact (a receiver named to dodge a classifier
#: is a new key and fails).
_NAME_READS: dict[tuple[str, str, str], str] = {
    # --- the TWO production portfolio-name reads ---
    ("irp_backend.api.portfolios", "_out", "node"): D,
    ("irp_shared.snapshot.serialize", "portfolio_content", "row"): V,
    # --- request-body pass-throughs (Pydantic field access, not entity reads) ---
    ("irp_backend.api.portfolios", "create_portfolio_endpoint", "body"): B,
    ("irp_backend.api.dq", "create_rule", "body"): B,
    ("irp_backend.api.limits", "create", "body"): B,
    ("irp_backend.api.models", "create_model", "body"): B,
    ("irp_backend.api.reference", "create_calendar_endpoint", "body"): B,
    ("irp_backend.api.reference", "create_currency_endpoint", "body"): B,
    ("irp_backend.api.reference", "create_rating_scale_endpoint", "body"): B,
    ("irp_backend.api.reference_entities", "create_legal_entity_endpoint", "body"): B,
    ("irp_backend.api.reference_instruments", "create_instrument_endpoint", "body"): B,
    ("irp_backend.api.risk", "create_scenario", "body"): B,
    ("irp_backend.api.risk", "update_scenario", "body"): B,
    ("irp_backend.api.schedule_admin", "create", "payload"): B,
    # --- other entities' names (factors, scenarios, calendars, limits, schedules, ...) ---
    ("irp_backend.api.classification", "_node_out", "n"): O,
    ("irp_backend.api.classification", "_scheme_out", "s"): O,
    ("irp_backend.api.dq", "_rule_out", "rule"): O,
    ("irp_backend.api.dq", "list_rules", "r"): O,
    ("irp_backend.api.limits", "_limit_out", "limit"): O,
    ("irp_backend.api.models", "get_model", "model"): O,
    ("irp_backend.api.models", "list_models", "m"): O,
    ("irp_backend.api.reference", "_calendar_detail", "calendar"): O,
    ("irp_backend.api.reference", "_calendar_detail", "h"): O,
    ("irp_backend.api.reference", "_calendar_out", "c"): O,
    ("irp_backend.api.reference", "_currency_out", "c"): O,
    ("irp_backend.api.reference", "_rating_scale_detail", "scale"): O,
    ("irp_backend.api.reference", "_rating_scale_out", "s"): O,
    ("irp_backend.api.reference", "create_calendar_endpoint", "h"): O,
    ("irp_backend.api.reference", "refresh_calendar_holidays_endpoint", "h"): O,
    ("irp_backend.api.reference_entities", "_legal_entity_out", "le"): O,
    ("irp_backend.api.reference_entities", "get_counterparty", "core"): O,
    ("irp_backend.api.reference_entities", "get_issuer", "core"): O,
    ("irp_backend.api.reference_instruments", "_instrument_out", "i"): O,
    ("irp_backend.api.risk", "_definition_out", "row"): O,
    ("irp_backend.api.schedule_admin", "_out", "schedule"): O,
    ("irp_backend.api.schedules", "_schedule_out", "s"): O,
    ("irp_backend.api.tenant_admin", "list_roles", "r"): O,
    ("irp_shared.reference.calendar", "create_calendar", "spec"): O,
    ("irp_shared.reference.calendar", "refresh_calendar_holidays", "spec"): O,
    ("irp_shared.reproduction.families", "_compared", "c"): E,  # SQLAlchemy Column.name
    ("irp_shared.risk.scenario", "_def_summary", "row"): O,
    ("irp_shared.snapshot.serialize", "instrument_content", "row"): O,
    # --- engine internals (dialect names, type machinery) ---
    ("irp_worker.audit_verify", "main", "engine.dialect"): E,
    ("irp_shared.audit.service", "_lock_chain", "session.get_bind().dialect"): E,
    ("irp_shared.db.session", "make_engine", "engine.dialect"): E,
    ("irp_shared.db.tenant", "_is_postgres", "session.get_bind().dialect"): E,
    ("irp_shared.db.tenant", "_rearm", "connection.dialect"): E,
    ("irp_shared.db.tenant", "attach_tenant_reset", "engine.dialect"): E,
    ("irp_shared.db.types", "load_dialect_impl", "dialect"): E,
    ("irp_shared.db.types", "process_bind_param", "dialect"): E,
    ("irp_shared.entitlement.admin_service", "_lock_tenant", "session.bind.dialect"): E,
    ("irp_shared.entitlement.sync", "sync_catalog", "bind.dialect"): E,
    ("irp_shared.limit.lifecycle", "select_overdue_breaches", "session.get_bind().dialect"): E,
}


def _mod_tail(path: pathlib.Path) -> str:
    s = str(path)
    for marker in ("irp_shared", "irp_backend", "irp_worker"):
        i = s.find(marker)
        if i >= 0:
            return s[i:-3].replace("/", ".")
    raise AssertionError(s)


def _scan_names(mod: str, tree: ast.AST, hits: dict[tuple[str, str, str], int]) -> None:
    stack = ["<module>"]

    class A(ast.NodeVisitor):
        def visit_FunctionDef(self, node):  # noqa: ANN001, ANN202
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Attribute(self, node):  # noqa: ANN001, ANN202
            if node.attr == "name" and isinstance(node.ctx, ast.Load):
                key = (mod, stack[-1], ast.unparse(node.value))
                hits[key] = hits.get(key, 0) + 1
            self.generic_visit(node)

        def visit_Subscript(self, node):  # noqa: ANN001, ANN202
            # x["name"] — the dict-key read the attribute sweep cannot see (review fold: the
            # canonical compute-input path parses captured_content into DICTS, so a name read
            # there would be a Subscript, not an Attribute).
            if (
                isinstance(node.ctx, ast.Load)
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == "name"
            ):
                key = (mod, stack[-1], f'{ast.unparse(node.value)}["name"]')
                hits[key] = hits.get(key, 0) + 1
            self.generic_visit(node)

        def visit_Call(self, node):  # noqa: ANN001, ANN202
            # x.get("name") and getattr(x, "name") — the two remaining literal dynamic shapes.
            fn = node.func
            if (
                isinstance(fn, ast.Attribute)
                and fn.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "name"
            ):
                key = (mod, stack[-1], f'{ast.unparse(fn.value)}.get("name")')
                hits[key] = hits.get(key, 0) + 1
            if (
                isinstance(fn, ast.Name)
                and fn.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "name"
            ):
                key = (mod, stack[-1], f'getattr({ast.unparse(node.args[0])}, "name")')
                hits[key] = hits.get(key, 0) + 1
            self.generic_visit(node)

    A().visit(tree)


def _sweep_name_reads() -> dict[tuple[str, str, str], int]:
    hits: dict[tuple[str, str, str], int] = {}
    for root in _PY_ROOTS:
        for py in sorted(root.rglob("*.py")):
            _scan_names(_mod_tail(py), ast.parse(py.read_text()), hits)
    return hits


def _scan_getattrs(mod: str, tree: ast.AST, sites: set[tuple[str, str]]) -> None:
    stack = ["<module>"]

    class G(ast.NodeVisitor):
        def visit_FunctionDef(self, node):  # noqa: ANN001, ANN202
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):  # noqa: ANN001, ANN202
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                sites.add((mod, stack[-1]))
            self.generic_visit(node)

    G().visit(tree)


def _sweep_getattr_sites() -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    for root in _PY_ROOTS:
        for py in sorted(root.rglob("*.py")):
            _scan_getattrs(_mod_tail(py), ast.parse(py.read_text()), sites)
    return sites


def test_name_census_every_static_read_is_classified() -> None:
    """A NEW ``.name`` read anywhere in the three Python trees fails until classified — and
    COMPUTATION has no allowlist code, so classifying one means editing this file in review."""
    discovered = set(_sweep_name_reads())
    allow = set(_NAME_READS)
    assert discovered == allow, (
        f"portfolio-name census drift — unclassified: {sorted(discovered - allow)}; "
        f"vanished: {sorted(allow - discovered)}"
    )


def test_name_census_exactly_two_portfolio_reads_and_their_classes() -> None:
    """The census's subject, pinned by exact set: TWO production portfolio-name reads exist —
    the display serializer and the provenance pin (recorded and byte-compared, never
    interpreted; TR-09 amend detection is the DESIGN, DP-8)."""
    portfolio_sites = {
        k: v
        for k, v in _NAME_READS.items()
        if k
        in {
            ("irp_backend.api.portfolios", "_out", "node"),
            ("irp_shared.snapshot.serialize", "portfolio_content", "row"),
        }
    }
    assert portfolio_sites == {
        ("irp_backend.api.portfolios", "_out", "node"): D,
        ("irp_shared.snapshot.serialize", "portfolio_content", "row"): V,
    }


def test_name_census_dynamic_reads_are_pinned() -> None:
    """The reads a literal grep cannot see. The sweep itself now catches every LITERAL dynamic
    shape — x["name"], x.get("name"), getattr(x, "name") — as census keys (zero exist, proven
    above by exact equality, not assumed). What remains invisible is a KEY-VARIABLE loop
    (getattr(x, k) where k iterates a constant): the two portfolio-path loops are pinned here by
    their key CONSTANTS, so the classification cannot silently detach from the code."""
    sites = _sweep_getattr_sites()
    assert ("irp_shared.portfolio.portfolio", "update_portfolio") in sites
    assert ("irp_backend.api.portfolios", "attr_changes") in sites
    from irp_backend.api.portfolios import _AMENDABLE
    from irp_shared.portfolio.portfolio import _UPDATABLE

    assert "name" in _UPDATABLE  # audit before/after payload: recorded, never interpreted
    assert "name" in _AMENDABLE  # request-body pass-through


def test_name_census_frontend_has_zero_portfolio_reads() -> None:
    """The frontend resolves the demo book by ``code``; its only ``.name`` property reads are a
    schedule-create input and a limit label — pinned by FILE so a new frontend name read
    surfaces here."""
    fe = _REPO / "apps/frontend/src"
    hits = set()
    for f in sorted(fe.rglob("*.ts")) + sorted(fe.rglob("*.tsx")):
        rel = str(f.relative_to(fe))
        if ".test." in rel or rel.startswith("api/generated"):
            continue
        for line in f.read_text().splitlines():
            if re.search(r"\.name\b", line):
                hits.add(rel)
    assert hits == {"api/writes.ts", "views/ops/LimitHealth.tsx"}


# ---------- REQ-PPM-009: the rename regression (DP-8's output definition) ----------


def test_contradictory_rename_changes_no_computed_value() -> None:
    """Rename a portfolio to something CONTRADICTORY, re-run the governed families FRESH (new
    snapshots — the reproduction sweep alone is vacuous here: old pins cannot see a rename), and
    compare computed VALUES row-for-row. Snapshot content hashes are EXCLUDED by design: the
    portfolio EV pin moves on any amend (TR-09) and asserting otherwise would fail correct code.

    The row's own honesty note stands: nothing reads the name today, so this passes with no code
    written — it is the REGRESSION GUARD half; the census above is the half with teeth."""
    import uuid

    from test_exposure import _bond, _ccy, _pf, _pos, _run, _val  # noqa: F401
    from test_exposure import session as _mk

    from irp_shared.portfolio import PortfolioActor, resolve_portfolio, update_portfolio
    from irp_shared.reproduction.events import VERDICT_MATCH
    from irp_shared.reproduction.service import run_reproduction_sweep

    gen = _mk.__wrapped__()  # the fixture function, used directly (no pytest request here)
    db = next(gen)
    try:
        tenant = str(uuid.uuid4())
        _ccy(db, "USD")
        pf = _pf(db, tenant)
        inst = _bond(db, tenant, "UST-2034", face_value="1000.0000")
        _pos(db, tenant, pf, inst, "25")
        _val(db, tenant, pf, inst, "988.00", "USD")
        db.flush()

        def _values(result):  # noqa: ANN001, ANN202
            return {
                (r.portfolio_id, r.instrument_id, r.exposure_type): (
                    r.exposure_amount,
                    r.signed_quantity,
                    r.mark_value,
                    r.fx_rate,
                )
                for r in result.rows
            }

        before = _run(db, tenant, pf, "USD")
        assert before.status == "COMPLETED"

        node = resolve_portfolio(db, pf, acting_tenant=tenant)
        update_portfolio(
            db,
            node,
            actor=PortfolioActor(actor_id="steward"),
            name="Distressed Credit Special Situations",  # contradicts an off-par UST book
        )
        db.flush()

        after = _run(db, tenant, pf, "USD")
        assert after.status == "COMPLETED"
        assert _values(before) == _values(after)  # computed VALUES identical, per DP-8
        assert before.run.input_snapshot_id != after.run.input_snapshot_id  # genuinely fresh

        # A SECOND family fresh through build+compute (review fold: breadth). Full-breadth —
        # every governed family re-run post-rename — is CARRIED to STRUCT-3's three-level book,
        # named on its roadmap row (P19).
        from test_exposure import T0

        from irp_shared.marketdata.factor import FactorActor, capture_factor
        from irp_shared.risk.bootstrap import register_factor_exposure_model
        from irp_shared.risk.events import FactorExposureActor
        from irp_shared.risk.factor_service import run_factor_exposure

        factor = capture_factor(
            db,
            factor_code="FX_USD",
            factor_source="VENDOR_F",
            factor_family="CURRENCY",
            currency_code="USD",
            acting_tenant=tenant,
            actor=FactorActor(actor_id="s"),
            valid_from=T0,
        ).id
        mv_id = register_factor_exposure_model(
            db, tenant_id=tenant, actor_id="analyst", code_version="risk-v1"
        ).id

        def _factor_values(run_id: str):  # noqa: ANN202
            from sqlalchemy import select

            from irp_shared.risk.models import FactorExposureResult

            return {
                (r.instrument_id, r.factor_id): r.exposure_amount
                for r in db.execute(
                    select(FactorExposureResult).where(
                        FactorExposureResult.calculation_run_id == run_id
                    )
                )
                .scalars()
                .all()
            }

        fe_after_rename = run_factor_exposure(
            db,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv_id,
            exposure_run_id=after.run.run_id,
            factor_ids=[factor],
        )
        assert fe_after_rename.status == "COMPLETED"
        fe_on_prerename_run = run_factor_exposure(
            db,
            acting_tenant=tenant,
            actor=FactorExposureActor(actor_id="a"),
            code_version="risk-v1",
            environment_id="ci",
            model_version_id=mv_id,
            exposure_run_id=before.run.run_id,
            factor_ids=[factor],
        )
        assert fe_on_prerename_run.status == "COMPLETED"
        assert _factor_values(fe_after_rename.run.run_id) == _factor_values(
            fe_on_prerename_run.run.run_id
        )

        # The weak-half regression guard, honestly labeled: the sweep re-executes the stored
        # runs over their PINNED content and must still MATCH after the rename.
        outcome = run_reproduction_sweep(
            db, acting_tenant=tenant, actor_id="t", code_version="v1", environment_id="ci"
        )
        by_family = {c.family_key: c.verdict for c in outcome.checks}
        assert by_family.get("EXPOSURE_AGGREGATE") == VERDICT_MATCH
    finally:
        gen.close()
