"""Consumed-measure declarations (STRUCT-1, REQ-PPM-006) — the contract module's first tenant.

**What this is.** Every governed family that consumes ``exposure_aggregate`` rows declares HERE
which exposure measure it reads. The declaration is LOAD-BEARING, not descriptive: the snapshot
pin builders filter atoms through :func:`consumed_exposure_measure` (a family's pins contain ONLY
its declared measure), and every family's pin parser refuses a foreign-measure atom that reaches
it anyway (defense in depth — see the family services). A mutation test proves the wiring: flipping
a declaration below changes the built pin set and makes the parser refusal fire. STRUCT-2 (REQ-
PPM-007) extends this module with the per-field aggregation operators; the shape here is the final
home, not a way-station.

**Why consumers declare ONE measure each today.** All four shipped consumers are market-value
semantics (factor allocation, BMV/EMV returns, concentration buckets, liquidity buckets) — a
NOTIONAL row summed into any of them is an economic category error, which is exactly the
double-count the REQ-PPM-006 amendment exists to prevent.

**Refusals.** :class:`UndeclaredConsumerError` — a family with no declaration asked for exposure
atoms (the census failure, fail-closed). :class:`ForeignMeasureError` — an atom of a measure the
family did not declare reached its parser. Both are P9-governed: each is named in a test that makes
it FIRE.
"""

from __future__ import annotations

from irp_shared.exposure.models import EXPOSURE_TYPE_MARKET_VALUE

#: run_type -> the exposure measure that family consumes. Keys are the CONSUMER families'
#: run-type strings (string literals, not imports: this module must stay import-light — the
#: consumers import it, and importing their events modules back would cycle. The literal-vs-
#: constant drift is pinned by test_aggregation_contracts asserting each key equals the family's
#: RUN_TYPE_* constant).
EXPOSURE_CONSUMER_MEASURES: dict[str, str] = {
    "FACTOR_EXPOSURE": EXPOSURE_TYPE_MARKET_VALUE,
    "PORTFOLIO_RETURN": EXPOSURE_TYPE_MARKET_VALUE,
    "CONCENTRATION": EXPOSURE_TYPE_MARKET_VALUE,
    "LIQUIDITY": EXPOSURE_TYPE_MARKET_VALUE,
}


class UndeclaredConsumerError(Exception):
    """A family requested exposure atoms without a consumed-measure declaration (REQ-PPM-006:
    "a consumer that declares nothing fails the census"). Fail-closed."""

    def __init__(self, run_type: str) -> None:
        super().__init__(
            f"run_type {run_type!r} consumes exposure but declares no measure in "
            "irp_shared.aggregation.contracts.EXPOSURE_CONSUMER_MEASURES"
        )
        self.run_type = str(run_type)


class ForeignMeasureError(Exception):
    """An exposure atom of an undeclared measure reached a family's pin parser (REQ-PPM-006:
    "must REFUSE a row of any other measure")."""

    def __init__(self, *, run_type: str, declared: str, found: str) -> None:
        super().__init__(
            f"run_type {run_type!r} declares measure {declared!r} and was given an atom of "
            f"measure {found!r} — refused, never converted"
        )
        self.run_type = str(run_type)
        self.declared = str(declared)
        self.found = str(found)


def consumed_exposure_measure(run_type: str) -> str:
    """The measure ``run_type`` declared, or :class:`UndeclaredConsumerError` (fail-closed —
    never a default)."""
    try:
        return EXPOSURE_CONSUMER_MEASURES[str(run_type)]
    except KeyError:
        raise UndeclaredConsumerError(str(run_type)) from None


def refuse_foreign_measure(run_type: str, atom_content: dict) -> None:
    """The parser-side refusal (defense in depth behind the builder filter): raise
    :class:`ForeignMeasureError` when a pinned exposure atom's ``exposure_type`` is not the
    measure ``run_type`` declared. An atom whose content carries NO ``exposure_type`` key is
    refused the same way (an unlabeled measure is not the declared one)."""
    declared = consumed_exposure_measure(run_type)
    found = atom_content.get("exposure_type")
    if found != declared:
        raise ForeignMeasureError(run_type=run_type, declared=declared, found=str(found))
