"""Pure factor-exposure allocation kernel (P3-3, ENT-028 family — allocation v1).

NO DB, NO I/O, NO estimation, NO regression, NO covariance, NO factor-return consumption — a
deterministic **indicator-loading allocation** (the fundamental-factor-model membership-exposure
form, OD-P3-3-A/C/J): each pinned exposure atom maps to **exactly one** factor of the run's pinned
CURRENCY-family factor set by exact match of the atom's captured ``mark_currency`` against the
factor's ``currency_code`` scope; ``loading = 1``;
``factor_exposure = quantize_HALF_UP(loading * exposure_amount, 6)`` (idempotent on the already-6dp
atom — exact by construction, the QS-04 registered HALF_UP exception). Signs are preserved (a short
atom allocates negative exposure — QS-22, no abs/gross/net coercion). Because the mapping is a
partition (an unmapped atom fails the run, OD-P3-3-N), **contributions sum to the pinned input
total exactly (ε = 0)** — the REQ-MKT-003 acceptance for the allocation leg.

The kernel is dimension-generic by construction (the index key is data, not structure): a v2
family adds an attribute correspondence, not a redesign. v1 wires CURRENCY only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

#: The v1 indicator loading (membership; fractional/beta loadings are the deferred v2 seam).
#: Pinned to the loading column quantum Numeric(20,12) (the bump_bps precedent) so the
#: in-memory value and the DB-roundtripped value serialize IDENTICALLY (review finding).
INDICATOR_LOADING = Decimal("1.000000000000")
#: Result quantum: HALF_UP to 6dp = the ``factor_exposure_result.exposure_amount`` Numeric(28,6)
#: scale (the ``exposure_aggregate.exposure_amount`` precedent).
_RESULT_QUANTUM = Decimal(1).scaleb(-6)


class FactorKernelError(ValueError):
    """Raised for an ill-formed factor set (a NULL mapping attribute or a duplicate attribute value
    — an ambiguous partition). Defense-in-depth: the binder refuses these PRE-CREATE; the kernel
    re-checks so the pure function is safe standalone."""


@dataclass(frozen=True)
class FactorPin:
    """One pinned ``factor`` EV definition (parsed from a ``COMPONENT_KIND_FACTOR`` component)."""

    id: str
    factor_code: str
    factor_family: str
    currency_code: str | None


@dataclass(frozen=True)
class AtomPin:
    """One pinned ``exposure_aggregate`` atom (parsed from a ``COMPONENT_KIND_EXPOSURE``
    component)."""

    id: str
    portfolio_id: str
    instrument_id: str
    base_currency: str
    mark_currency: str
    exposure_amount: Decimal


@dataclass(frozen=True)
class AllocatedExposure:
    """One atom's allocation to one factor: ``amount = quantize_HALF_UP(loading * atom, 6)``."""

    factor: FactorPin
    loading: Decimal
    exposure_amount: Decimal


def build_factor_index(factors: list[FactorPin]) -> dict[str, FactorPin]:
    """Index the pinned CURRENCY-family factor set by its ``currency_code`` mapping attribute
    (exact captured string). A NULL attribute or a duplicate value raises
    :class:`FactorKernelError` — an ambiguous partition must never allocate."""
    index: dict[str, FactorPin] = {}
    for pin in factors:
        if pin.currency_code is None:
            raise FactorKernelError(f"factor {pin.factor_code!r} has no currency_code scope")
        if pin.currency_code in index:
            raise FactorKernelError(
                f"duplicate currency_code {pin.currency_code!r} in the factor set "
                f"({index[pin.currency_code].factor_code!r} vs {pin.factor_code!r})"
            )
        index[pin.currency_code] = pin
    return index


def allocate_atom(atom: AtomPin, index: dict[str, FactorPin]) -> AllocatedExposure | None:
    """Allocate one pinned atom to the factor matching its ``mark_currency`` (exact match;
    ``loading = 1``). Returns ``None`` on no match — the caller records a fail-closed gap
    (OD-P3-3-N; no silent residual bucket in v1)."""
    factor = index.get(atom.mark_currency)
    if factor is None:
        return None
    amount = (INDICATOR_LOADING * atom.exposure_amount).quantize(
        _RESULT_QUANTUM, rounding=ROUND_HALF_UP
    )
    return AllocatedExposure(factor=factor, loading=INDICATOR_LOADING, exposure_amount=amount)
