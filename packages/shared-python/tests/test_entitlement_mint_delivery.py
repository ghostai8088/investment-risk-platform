"""P17's mechanical gate — a minted permission must be DELIVERABLE to a running database.

Permissions live in ``bootstrap.PERMISSIONS``, which migration ``0002`` live-imports and seeds into
a database built from empty. A database already running never sees a code appended afterwards, so
appending to the constant is a mint for FUTURE deployments only: ``require_permission`` is
deny-by-default, so in production the new surface 403s every holder, while every unit test, the
fresh-database smoke and CI all pass — each of them builds its database from empty. That was true
of every code minted between P0.5 and RPT-2's migration ``0064``, across many waves, and nothing
caught it. The defect is invisible to exactly the tests a new permission ships with.

**The rule is this test, not the paragraph above (P7).** A migration that syncs the catalog
declares the codes it delivers in a literal ``DELIVERS`` tuple; this gate asserts the catalog is
covered by the union of those declarations. Append a code to ``bootstrap.py`` and this reddens
until a migration ships it — by construction, whether or not anyone remembers P17.

**Why DELIVERS is a literal and not an import.** ``0064`` syncs the WHOLE catalog by importing it,
so a declaration that also imported it would be true forever and the gate would be vacuous forever:
the very growth it exists to notice would keep it green. The literal is a snapshot of what a
revision shipped, which is the only thing a running database can be told about.
"""

from __future__ import annotations

import ast
import pathlib

from irp_shared.entitlement.bootstrap import ALL_CODES
from irp_shared.entitlement.platform_catalog import PLATFORM_CODES

_MIGRATIONS = pathlib.Path(__file__).resolve().parents[3] / "migrations" / "versions"


def _declared_platform_deliveries() -> dict[str, tuple[str, ...]]:
    """The platform arm of the same reader (ONBOARD-1a). Same AST rules, different tuple name."""
    return _declared(name="DELIVERS_PLATFORM")


def _declared_deliveries() -> dict[str, tuple[str, ...]]:
    """Every migration's literal ``DELIVERS`` tuple, read from the AST.

    The AST rather than an import for two reasons: importing a migration module executes it under
    an alembic context it does not have, and a literal read cannot be satisfied by a computed value
    — which is precisely the vacuity this gate is guarding against.
    """
    return _declared(name="DELIVERS")


def _declared(*, name: str) -> dict[str, tuple[str, ...]]:
    declared: dict[str, tuple[str, ...]] = {}
    for path in sorted(_MIGRATIONS.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in tree.body:
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
            )
            if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
                continue
            value = node.value
            if not isinstance(value, ast.Tuple | ast.List):
                continue
            codes = tuple(
                e.value
                for e in value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            )
            if len(codes) != len(value.elts):
                raise AssertionError(
                    f"{path.name}: {name} must be a tuple of STRING LITERALS — a computed or "
                    "imported element makes the gate vacuous (see this module's docstring)"
                )
            declared[path.name] = codes
    return declared


def test_every_minted_permission_is_delivered_by_a_migration() -> None:
    """THE GATE. Fires on the next mint that ships without a sync migration."""
    declared = _declared_deliveries()
    delivered = {code for codes in declared.values() for code in codes}
    undelivered = sorted(set(ALL_CODES) - delivered)
    assert not undelivered, (
        "permission codes exist in entitlement/bootstrap.py but NO migration declares delivering "
        "them, so they will never reach a database that already exists — deny-by-default then "
        "403s every holder in production while every from-empty test passes (P17). Ship a sync "
        f"migration declaring them in a literal DELIVERS tuple: {undelivered}"
    )


def test_the_gate_would_fire_for_an_undelivered_code() -> None:
    """The discriminating control: prove the matcher can tell covered from uncovered.

    Without this, ``test_every_minted_permission_is_delivered_by_a_migration`` could be passing
    because the delivered set happened to be enormous, or because the reader returned everything
    it saw. Here the catalog is mutated by one synthetic code and the same set arithmetic must
    report exactly that code — the shape a bare "it passes" cannot distinguish.
    """
    declared = _declared_deliveries()
    delivered = {code for codes in declared.values() for code in codes}
    synthetic = "synthetic.never.minted"
    assert synthetic not in delivered
    undelivered = sorted(({*ALL_CODES, synthetic}) - delivered)
    assert undelivered == [synthetic]


def test_declarations_are_non_vacuous_and_name_real_codes() -> None:
    """P6 floor: an enumerated guard ships a floor that fails when its population collapses.

    A ``DELIVERS`` reader that silently found nothing would make the gate above pass for a database
    with nothing delivered at all. And a declaration naming a code the catalog does not contain is
    a stale claim about what a revision shipped — worth failing on, because the next reader would
    take it as coverage.
    """
    declared = _declared_deliveries()
    assert declared, "no migration declares a DELIVERS tuple — the delivery gate is unpopulated"
    assert (
        sum(len(c) for c in declared.values()) >= 60
    ), f"the declared population collapsed to {sum(len(c) for c in declared.values())} codes"
    catalog = set(ALL_CODES)
    stale = {
        name: sorted(set(codes) - catalog)
        for name, codes in declared.items()
        if set(codes) - catalog
    }
    assert not stale, f"migrations declare delivering codes absent from the catalog: {stale}"


def test_no_migration_declares_a_code_twice_within_itself() -> None:
    """A duplicated entry inflates the floor above without delivering anything extra."""
    dupes = {
        name: sorted({c for c in codes if codes.count(c) > 1})
        for name, codes in _declared_deliveries().items()
        if len(set(codes)) != len(codes)
    }
    assert not dupes, f"DELIVERS tuples contain duplicate codes: {dupes}"


def test_every_PLATFORM_permission_is_delivered_by_a_migration() -> None:
    """The same gate for the SECOND catalog — ONBOARD-1a, and it is not a formality.

    ``PLATFORM_PERMISSIONS`` exists precisely because a code in ``PERMISSIONS`` reaches every
    tenant's cloned ``platform_admin`` role. The consequence nobody would have noticed: the gate
    above walks ``ALL_CODES``, which is derived from ``PERMISSIONS``, so a platform code is
    **invisible to it** — measured by execution while building this slice, not reasoned. A mint
    discipline that silently exempts the most privileged catalog on the platform is worse than no
    discipline, because the record would say the gate covers everything.

    Platform codes are declared in a separate ``DELIVERS_PLATFORM`` tuple for the same reason the
    catalogs are separate: a single tuple would have to be checked against a single population,
    and the whole point is that there are two.
    """
    declared = _declared_platform_deliveries()
    delivered = {code for codes in declared.values() for code in codes}
    undelivered = sorted(set(PLATFORM_CODES) - delivered)
    assert not undelivered, (
        "PLATFORM permission codes exist in entitlement/platform_catalog.py but NO migration "
        "declares delivering them (P17). Ship a migration declaring them in a literal "
        f"DELIVERS_PLATFORM tuple: {undelivered}"
    )


def test_the_two_catalogs_are_DISJOINT() -> None:
    """The structural guarantee the platform catalog exists to provide.

    If a code ever appears in both, it enters ``ALL_CODES`` → the ``platform_admin`` template →
    every tenant's clones, and the separation that keeps ``tenant.create`` out of customer tenants
    silently stops existing. Five independent verifier lanes converged on that composition in the
    slice's first design draft; this is the assertion that makes the fix structural rather than
    remembered.
    """
    overlap = sorted(set(ALL_CODES) & set(PLATFORM_CODES))
    assert not overlap, (
        f"codes appear in BOTH catalogs: {overlap}. A platform code in PERMISSIONS reaches every "
        "tenant through the platform_admin template clone — the exact escalation the split "
        "prevents."
    )


def test_platform_declarations_are_non_vacuous() -> None:
    """P6 floor for the platform arm: a reader finding nothing makes its gate pass over nothing."""
    declared = _declared_platform_deliveries()
    assert (
        declared
    ), "no migration declares a DELIVERS_PLATFORM tuple — the platform gate is unpopulated"
    assert set(PLATFORM_CODES), "the platform catalog is empty — the gate above is vacuous"
