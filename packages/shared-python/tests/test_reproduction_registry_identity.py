"""REPRO-2 — a divergence label must never carry an identity the reader is excluded from.

A DIVERGED verdict names the row KEY and the field, and REPRO-2 ships that label to every
`schedule.view` holder — `auditor_3l` among them. That auditor is deliberately excluded from
issuer identity, legal-entity identity and person identity elsewhere on the platform (the CON-1
split exists for exactly this reason), so a family whose declared key included one of those
columns would route the excluded identity around the split through a divergence label.

This census is what makes that unreachable rather than merely unlikely — and it matters most for
the families NOT YET REGISTERED: sixteen adapters are the next work, each one writing a fresh key
declaration, and none of them can smuggle an identity column past this.
"""

from __future__ import annotations

from irp_shared.reproduction.registry import (
    IDENTITY_EXCLUDED_COLUMNS,
    REPRODUCIBLE_FAMILIES,
    identity_offenders,
)


def test_no_registered_family_KEYS_on_an_excluded_identity_column() -> None:
    offenders: list[str] = []
    for family_key, family in REPRODUCIBLE_FAMILIES.items():
        for column in identity_offenders(family.key_fields):
            offenders.append(f"{family_key}.key_fields includes {column!r}")
    assert not offenders, (
        f"a registered family keys on an identity column withheld from some verdict-read holder: "
        f"{offenders} — a DIVERGED label naming that key would disclose it"
    )


def test_no_registered_family_COMPARES_an_excluded_identity_column() -> None:
    """The compared fields ride the same label (`field=`), so they take the same rule."""
    offenders: list[str] = []
    for family_key, family in REPRODUCIBLE_FAMILIES.items():
        for column in identity_offenders(family.compared_fields):
            offenders.append(f"{family_key}.compared_fields includes {column!r}")
    assert not offenders, f"an identity column is compared and can be named in a label: {offenders}"


def test_every_excluded_column_states_its_PROVENANCE() -> None:
    """A list of names nobody can trace is a list nobody will maintain: each entry names the
    route gate that withholds it, so a future reader can check whether it still does."""
    for column, reason in IDENTITY_EXCLUDED_COLUMNS.items():
        assert reason.strip(), f"{column} has no provenance"
        assert (
            "." in reason or "identifying" in reason
        ), f"{column}'s provenance does not name a permission or a class: {reason!r}"


def test_the_census_ACTUALLY_CATCHES_an_excluded_column() -> None:
    """The negative control — and the battery is why it exists.

    Both census tests above pass over the CURRENT registry, and they would go on passing if their
    loops walked nothing at all: there are no offenders to find, so an empty walk and a clean walk
    are indistinguishable. That is a hollow guard, and this project has shipped three of them.

    So this plants an offender and requires the same rule to reject it. The rule is applied to a
    constructed declaration rather than to the real registry, because the census's whole value is
    for the SIXTEEN adapters not yet written.
    """
    planted_key = ("portfolio_id", "issuer_id", "as_of_date")
    offenders = identity_offenders(planted_key)
    assert offenders == ["issuer_id"], (
        "the identity rule did not catch a key declaring issuer_id — the census cannot protect "
        "the sixteen adapters it exists for"
    )


def test_the_excluded_list_is_NOT_EMPTY() -> None:
    """The floor. An empty list makes every census above vacuously green forever."""
    assert len(IDENTITY_EXCLUDED_COLUMNS) >= 4
