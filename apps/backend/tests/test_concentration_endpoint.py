"""CON-1 route-level permission assertions (OQ-CON-1-25's mandatory route test).

The per-code ``_holders`` pins alone cannot catch a MIS-SCOPED ROUTE (REF-1's own finding) — a
correct holder set behind the wrong guard still leaks. These tests introspect the LIVE app's
dependency closures per route, so moving an issuer-bearing endpoint onto the wrong code fails
here by name.
"""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute

from irp_backend.api.concentration import router


def _permission_codes(route: APIRoute) -> set[str]:
    """The permission codes demanded by a route, recovered by walking EVERY dependency in the
    route's dependant tree (the guards arrive via parameter defaults, which FastAPI flattens into
    ``dependant.dependencies``) and reading the ``require_permission`` closure cell."""
    codes: set[str] = set()
    for dep in route.dependant.dependencies:
        fn: Any = dep.call
        if fn is None or getattr(fn, "__name__", "") != "_dependency" or fn.__closure__ is None:
            continue
        for cell in fn.__closure__:
            if isinstance(cell.cell_contents, str):
                codes.add(cell.cell_contents)
    return codes


def _concentration_routes() -> dict[tuple[str, str], set[str]]:
    """The router's own routes (the APIRouter prefix is applied per route), independent of the
    app's mounting machinery — the guard census is per route either way, and the app inclusion is
    covered by the main-module smoke import + the generated OpenAPI contract."""
    out: dict[tuple[str, str], set[str]] = {}
    for route in router.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                if method != "HEAD":
                    out[(method, route.path)] = _permission_codes(route)
    return out


def test_every_concentration_route_is_guarded_by_the_ratified_code() -> None:
    """The EXACT route→code census (a new unguarded or re-guarded route fails by name)."""
    routes = _concentration_routes()
    assert routes == {
        ("POST", "/concentration/models/dimensional"): {"model.inventory.register"},
        ("POST", "/concentration/runs"): {"concentration.run"},
        ("GET", "/concentration/runs"): {"concentration.view"},
        ("GET", "/concentration/runs/{run_id}"): {"concentration.view"},
        ("GET", "/concentration/results"): {"concentration.view"},
        ("GET", "/concentration/results/latest"): {"concentration.view"},
        ("GET", "/concentration/results/issuers"): {"concentration.issuer.view"},
    }


def test_the_issuer_bearing_route_demands_the_issuer_code_specifically() -> None:
    """The OQ-CON-1-25 assertion in its own name: the ONLY route returning issuer identity
    demands ``concentration.issuer.view`` — never the broader ``.view`` an auditor holds."""
    routes = _concentration_routes()
    issuer_codes = routes[("GET", "/concentration/results/issuers")]
    assert issuer_codes == {"concentration.issuer.view"}
    assert "concentration.view" not in issuer_codes
