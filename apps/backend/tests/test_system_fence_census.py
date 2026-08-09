"""The SYSTEM-fence census (ONBOARD-1a remit: 'the census walks all paths and fails if a router
escapes classification').

The fence is an allow-list of path prefixes. An allow-list's failure mode is not letting the wrong
thing in — it is the list drifting from the surface it governs: a provisioning route MOVING (the
fence then refuses the operator everywhere, and provisioning is dead with every test green that
doesn't drive it), or the list growing a prefix nothing uses (dead scope that reads as intent).
This census pins both directions against the REAL app surface, the same walked route set the
route→permission census pins, so the fence and its proof look at the same thing.
"""

from __future__ import annotations

import os
import warnings

from fastapi.routing import APIRoute

os.environ.setdefault("IRP_AUTH_MODE", "dev_header")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from irp_backend.main import app

from irp_backend.deps import SYSTEM_TENANT_ALLOWED_PREFIXES  # noqa: E402


def _paths() -> set[str]:
    def walk(routes):  # noqa: ANN001, ANN202
        for r in routes:
            if isinstance(r, APIRoute):
                yield r.path
            elif hasattr(r, "original_router"):
                yield from walk(r.original_router.routes)

    return set(walk(app.routes))


def _allowed(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in SYSTEM_TENANT_ALLOWED_PREFIXES)


def test_every_allowed_prefix_matches_a_REAL_route() -> None:
    """A prefix matching nothing is dead scope: authority granted to a surface that moved."""
    paths = _paths()
    dead = [
        p
        for p in SYSTEM_TENANT_ALLOWED_PREFIXES
        if not any(_allowed(x) for x in paths if x == p or x.startswith(p + "/"))
    ]
    assert not dead, (
        f"fence prefixes matching NO route: {dead} — the provisioning surface moved and the fence "
        "now refuses the operator everywhere (provisioning is dead, silently)"
    )


def test_the_allowed_surface_is_EXACTLY_the_provisioning_router() -> None:
    """Exact set: a route joining the allowed surface is a decision, never an accident."""
    allowed = sorted(p for p in _paths() if _allowed(p))
    # ONBOARD-1b added eight TENANT-LOCAL routes and this list did NOT move — which is the
    # assertion, not an omission: a tenant admin's surface must never become SYSTEM-reachable.
    assert allowed == ["/tenants"], (
        f"the SYSTEM-reachable surface drifted: {allowed}. Every entry must be a provisioning "
        "route somebody decided a SYSTEM principal may reach."
    )


def test_the_census_walks_a_real_surface() -> None:
    """The anti-vacuity floor (P6): a walker returning nothing certifies nothing."""
    assert len(_paths()) > 200
