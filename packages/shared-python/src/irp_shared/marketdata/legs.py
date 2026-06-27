"""FX conversion-path *legs* (P2-3 support) — the published-rate path as resolvable rows.

The shipped :func:`irp_shared.marketdata.convert.convert` returns a converted amount +
human-readable
leg labels, but NOT the underlying ``fx_rate`` rows. P2-3 needs the rows in two places, sharing ONE
path algorithm (identity → direct → reciprocal → triangulation-through-base, the QS-08/OD-030
mechanism — verbatim with ``convert``) so the two ends cannot diverge:

- :func:`resolve_conversion_legs` — **live** (queries ``reconstruct_fx_rate_as_of`` at the frozen
  cutoffs): returns the ``FxRate`` rows the path traverses, so the **snapshot binder** can PIN them
  as ``COMPONENT_KIND_FX`` components (the FX-completeness gate — fails closed ``FxRateNotFound`` if
  no path). Used at snapshot-build only.
- :func:`compose_effective_rate` — **pure** (over a captured ``rate_map`` built from the pinned FX
  components): returns the **effective composite** multiplier (``Decimal``) + the ordered legs, with
  NO DB read. Used by the **exposure compute** so a base-currency exposure is reproducible from the
  snapshot alone (a later vendor correction cannot change it).

Both delegate to :func:`_resolve_path` over an injected ``get_rate(base, quote) -> (id, rate, row)``
lookup, so the live and captured ends pick the identical path. ``rate`` means "1 base = rate quote"
(QS-08); a reciprocal leg's multiplier is ``1/rate``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from irp_shared.marketdata.convert import DEFAULT_BASE, FxRateNotFound
from irp_shared.marketdata.models import RATE_TYPE_MID, FxRate
from irp_shared.marketdata.service import reconstruct_fx_rate_as_of

#: A lookup of a single published rate for an ORDERED (base, quote) pair: ``(fx_rate_id, rate,
#: row)``
#: or ``None``. ``row`` is the ``FxRate`` for the live lookup (to pin) and ``None`` for the captured
#: lookup (the row is not re-read at compute time).
RateLookup = Callable[[str, str], "tuple[str, Decimal, FxRate | None] | None"]

LEG_DIRECT = "direct"
LEG_RECIPROCAL = "reciprocal"


@dataclass(frozen=True)
class FxLeg:
    """One published-rate leg of a conversion path (the captured-path evidence stored in
    ``exposure_aggregate.fx_legs``). ``multiplier`` applies QS-08 direction: a direct leg multiplies
    by ``rate`` (1 base = rate quote), a reciprocal leg by ``1/rate``."""

    fx_rate_id: str
    base_currency: str
    quote_currency: str
    rate: Decimal
    direction: str  # LEG_DIRECT | LEG_RECIPROCAL

    @property
    def multiplier(self) -> Decimal:
        return self.rate if self.direction == LEG_DIRECT else Decimal(1) / self.rate

    def as_dict(self) -> dict[str, str]:
        """A JSON-safe leg-evidence dict (``rate`` as a string — no float)."""
        return {
            "fx_rate_id": str(self.fx_rate_id),
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
            "rate": str(self.rate),
            "direction": self.direction,
        }


def _hop(get_rate: RateLookup, a: str, b: str) -> tuple[FxLeg, FxRate | None] | None:
    """One ``a -> b`` hop via a direct published rate, else its read-time reciprocal — or
    ``None``."""
    direct = get_rate(a, b)
    if direct is not None:
        rid, rate, row = direct
        return FxLeg(rid, a, b, rate, LEG_DIRECT), row
    recip = get_rate(b, a)
    if recip is not None:
        rid, rate, row = recip
        return FxLeg(rid, b, a, rate, LEG_RECIPROCAL), row
    return None


def _resolve_path(
    get_rate: RateLookup, from_currency: str, to_currency: str, base: str
) -> list[tuple[FxLeg, FxRate | None]] | None:
    """The ordered legs ``from -> to`` (identity → direct/reciprocal → triangulation-through-base),
    or ``None`` if no published path exists. Verbatim with ``convert``'s order."""
    if from_currency == to_currency:
        return []
    leg = _hop(get_rate, from_currency, to_currency)
    if leg is not None:
        return [leg]
    if base not in (from_currency, to_currency):
        leg1 = _hop(get_rate, from_currency, base)
        leg2 = _hop(get_rate, base, to_currency)
        if leg1 is not None and leg2 is not None:
            return [leg1, leg2]
    return None


def resolve_conversion_legs(
    session: Session,
    *,
    from_currency: str,
    to_currency: str,
    valid_at: datetime,
    acting_tenant: str,
    known_at: datetime | None = None,
    base: str = DEFAULT_BASE,
    rate_type: str = RATE_TYPE_MID,
) -> list[FxRate]:
    """The distinct ``FxRate`` rows a ``from -> to`` conversion traverses as-of ``(valid_at,
    known_at)`` (exact-date; direct/reciprocal/triangulation) — for the **snapshot binder** to pin.
    Fails closed (:class:`FxRateNotFound`) if no path exists. Identity returns ``[]``."""
    rate_date = valid_at.date()  # exact-date matching (OD-P2-2-D), verbatim with convert

    def get_rate(b: str, q: str) -> tuple[str, Decimal, FxRate | None] | None:
        row = reconstruct_fx_rate_as_of(
            session,
            acting_tenant=acting_tenant,
            base_currency=b,
            quote_currency=q,
            rate_date=rate_date,
            valid_at=valid_at,
            rate_type=rate_type,
            known_at=known_at,
        )
        return (row.id, row.rate, row) if row is not None else None

    path = _resolve_path(get_rate, from_currency, to_currency, base)
    if path is None:
        raise FxRateNotFound(from_currency, to_currency)
    return [row for (_leg, row) in path if row is not None]


def compose_effective_rate(
    rate_map: dict[tuple[str, str], tuple[str, Decimal]],
    *,
    from_currency: str,
    to_currency: str,
    base: str = DEFAULT_BASE,
) -> tuple[Decimal, list[FxLeg]] | None:
    """The **effective composite** multiplier ``from -> to`` + the ordered legs, computed PURELY
    over
    ``rate_map`` (``(base, quote) -> (fx_rate_id, rate)``, built from the snapshot's pinned FX
    captured content) — NO DB read. ``None`` if the captured set has no path (the exposure compute's
    fail-closed signal). Identity returns ``(Decimal(1), [])``."""

    def get_rate(b: str, q: str) -> tuple[str, Decimal, FxRate | None] | None:
        hit = rate_map.get((b, q))
        return (hit[0], hit[1], None) if hit is not None else None

    path = _resolve_path(get_rate, from_currency, to_currency, base)
    if path is None:
        return None
    legs = [leg for (leg, _row) in path]
    effective = Decimal(1)
    for leg in legs:
        effective *= leg.multiplier
    return effective, legs
