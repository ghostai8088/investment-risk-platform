"""THE PLATFORM-WIDE ROUTE→PERMISSION CENSUS (P11 as ratified; built at RPT-2, OQ-W16P-1..7).

P11 (Wave-14 close): *"a permission mint needs its holder-set pin, route census, and SoD row"* — and
its own evidence clause records that until this file existed, NO platform-wide census did. Every
prior slice pinned only its own router (concentration is the exemplar), so a route added to any
OTHER router without a guard, or a code minted and never routed, was invisible to every shipped
test. LQ-1's two codes were mutation-proven blind in exactly that hole.

**The vacuous-walk trap is real and was re-measured while building this.** A naive ``app.routes``
walk yields ZERO ``APIRoute`` objects on this app — the routers arrive wrapped in
``_IncludedRouter`` — so a census without an anti-vacuity floor passes green over NOTHING. That
exact bug shipped in ``test_schedules_endpoint.py`` (fixed alongside this file, P10: the fold
applies to the class). This census therefore pins the EXACT route count: silence can never again
read as coverage, and a slice that adds routes moves the number consciously, like the run-type
census.

Three global properties, each an exact set (the P7 hierarchy — exact census > floor > matcher):

1. **Every route demands at least one permission**, except the EXACT anonymous allowlist.
2. **Every minted code is demanded by at least one route**, except the EXACT forward-gate list —
   each entry carrying its recorded reason, so an unrouted code is a visible commitment, not a
   silent one (the liquidity.run lesson: a dead guard reads as protection, but an unlisted
   unrouted code reads as ROUTED to anyone auditing the catalog).
3. **The count itself is pinned**, so the walker breaking (returning fewer routes than exist) is
   indistinguishable from routes disappearing — and both are loud.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute

os.environ.setdefault("IRP_AUTH_MODE", "dev_header")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from irp_backend.main import app

from irp_shared.entitlement.bootstrap import ALL_CODES
from irp_shared.entitlement.platform_catalog import PLATFORM_CODES

#: ONBOARD-1a: the census must walk BOTH catalogs.
#:
#: ``tenant.create`` lives in ``PLATFORM_PERMISSIONS``, deliberately outside ``PERMISSIONS`` (a
#: code in ``PERMISSIONS`` enters ``ALL_CODES`` → the ``platform_admin`` template → every tenant's
#: clones). That separation is the design; the consequence is that an ``ALL_CODES``-only census
#: cannot see platform codes at all — proven by execution at planning, where the platform code was
#: invisible to this file and to the P17 delivery gate simultaneously. A census blind to a whole
#: catalog is not a census for it, so the union is the population from here on.
MINTED_CODES: set[str] = set(ALL_CODES) | set(PLATFORM_CODES)

#: Routes that are DELIBERATELY anonymous. Exact set — a new anonymous route is a decision.
ANONYMOUS_ROUTES: set[tuple[str, str]] = {
    ("GET", "/health"),  # liveness — the deploy script and compose healthcheck probe it pre-auth
    ("GET", "/version"),  # build identity — same class
}

#: Minted codes with NO route today — each a recorded forward-gate, not an oversight. Exact set:
#: adding a code here is a visible commitment with a reason; removing one means its route landed.
UNROUTED_FORWARD_GATES: dict[str, str] = {
    "liquidity.run": "LQ-1 ships four READS; a run endpoint MUST carry this code when it lands "
    "(the catalog comment at entitlement/bootstrap.py is the binding record)",
    "lineage.source.manage": "lineage sources are managed via ingestion bootstrap only; no HTTP "
    "maker verb has ever shipped",
    "ops.audit.verify": "consumed by the audit_verify ops CLI, not by an HTTP route — the one "
    "deliberately non-HTTP code in the catalog",
    "reference.identifier.view": "the identifier read rides reference.identifier.resolve on the "
    "resolve endpoint; a plain listing view has never shipped",
}

#: The measured route count at RPT-2 (2026-08-07). Moves CONSCIOUSLY with each slice that adds or
#: removes routes — the point is that it can never silently be zero (the vacuous-walk trap) or
#: silently shrink (a router falling out of main.py, the CI-allowlist drift class).
# +1 ONBOARD-1a; +8 ONBOARD-1b; +1 ALERT-1; +4 REPRO-2 (3 schedule writes + the verdict read);
# +1 STRUCT-2 (GET /exposure/latest/sum — the Wave-18 close repaired this line's arithmetic:
# the visible sum read 305+2 while the pin was 308); +2 STRUCT-3; +0 STRUCT-4.
# +3 W19-S3a: GET /ingest/mappings, GET /ingest/mappings/{id}, GET /ingest/mappings/{id}/batches.
# READS ONLY — the propose/ratify verbs land at S3b with their own minted codes (DS3a-1), so all
# three sit behind the existing `data.upload` rather than a governed act sharing an upload code.
# +3 W19-S3b: POST /ingest/mappings (propose), POST .../ratify, POST .../withdraw. The three S3a
# READS also MOVED from `data.upload` onto the new `ingest.mapping.view` code — a re-gating, not a
# count change, so it does not appear in this arithmetic. (Those two backticked names were EMPTY in
# this comment for one commit: the block was written through a shell heredoc and the backticks were
# eaten as command substitution. Same class as the standing rule against backticks in `git commit
# -m`, in a place the rule did not name.)
# +1 W19-S3b: GET /lineage/targets/{type}/{id} — the by-target lineage read. `/lineage` had exactly
# one endpoint, keyed on an edge id NO endpoint returned and NO listing produced: a surface that was
# live, permission-gated, in `API_PREFIXES` and the nginx alternation, and unreachable in practice.
# Re-derived rather than incremented: this comment block had its sum repaired once already at the
# Wave-18 close.
EXPECTED_ROUTE_COUNT = 315  # W19-S3b: +3 mapping lifecycle verbs, +1 by-target lineage read


def _api_routes(routes: Any) -> Iterator[APIRoute]:
    """Recurse through the ``_IncludedRouter`` wrappers. The naive ``app.routes`` walk sees ZERO
    APIRoutes on this app — that is the measured trap this census exists to survive."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from _api_routes(r.original_router.routes)


def _permission_codes(route: APIRoute) -> set[str]:
    codes: set[str] = set()
    for dep in route.dependant.dependencies:
        fn: Any = dep.call
        if fn is None or getattr(fn, "__name__", "") != "_dependency" or fn.__closure__ is None:
            continue
        for cell in fn.__closure__:
            if isinstance(cell.cell_contents, str):
                codes.add(cell.cell_contents)
    return codes


def _census() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for route in _api_routes(app.routes):
        for method in route.methods - {"HEAD"}:
            out[(method, route.path)] = _permission_codes(route)
    return out


def test_the_census_sees_the_whole_surface() -> None:
    """The anti-vacuity pin. If the walker breaks, this fails at the COUNT — it cannot quietly
    census nothing (the shipped test_schedules_endpoint walker did exactly that until this fold)."""
    census = _census()
    assert len(census) == EXPECTED_ROUTE_COUNT, (
        f"route count moved: {len(census)} != {EXPECTED_ROUTE_COUNT}. If a slice added or removed "
        "routes, move this pin CONSCIOUSLY in the same commit; if not, the walker or a router "
        "registration broke."
    )


def test_every_route_demands_a_permission_except_the_declared_anonymous_set() -> None:
    census = _census()
    unguarded = {(m, p) for (m, p), codes in census.items() if not codes}
    assert unguarded == ANONYMOUS_ROUTES, (
        "unguarded routes drifted from the declared anonymous set: "
        f"extra={sorted(unguarded - ANONYMOUS_ROUTES)} "
        f"missing={sorted(ANONYMOUS_ROUTES - unguarded)}"
    )


def test_every_minted_code_is_routed_except_the_declared_forward_gates() -> None:
    census = _census()
    demanded: set[str] = set().union(*census.values())
    unrouted = MINTED_CODES - demanded
    assert unrouted == set(UNROUTED_FORWARD_GATES), (
        f"unrouted codes drifted from the declared forward-gate list: "
        f"extra={sorted(unrouted - set(UNROUTED_FORWARD_GATES))} "
        f"resolved={sorted(set(UNROUTED_FORWARD_GATES) - unrouted)} — a resolved entry means the "
        "route landed: DELETE the entry (and celebrate); an extra one means a code was minted "
        "without a route or a forward-gate record"
    )


def test_every_demanded_code_is_actually_minted() -> None:
    """The reverse direction: a route guarded by a TYPO'd code would deny everyone forever and
    read as 'protected' — the strictest possible fail-closed, which is exactly why nothing else
    would ever notice it."""
    census = _census()
    demanded: set[str] = set().union(*census.values())
    ghosts = demanded - MINTED_CODES
    assert not ghosts, f"routes demand codes that are not in the catalog: {sorted(ghosts)}"
