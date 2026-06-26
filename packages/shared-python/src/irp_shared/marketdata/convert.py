"""FX currency conversion (P2-2) — a PURE published-rate helper, NOT analytics (OD-P2-E).

``convert`` is **defined arithmetic over published rates only**: direct-pair lookup, read-time
reciprocal (1/rate), and **triangulation-through-the-configured-base** (the ratified QS-08/OD-030
mechanism — `amount × rate(from→base) × rate(base→to)`). There is **NO interpolation, NO stale-rate
fallback, NO model/curve-implied rate, NO silent 1.0**: a missing required leg **fails closed**
(``FxRateNotFound``). Read-only — emits no audit/lineage/DQ. Each leg is resolved bitemporally as-of
``(valid_at, known_at)`` at the **exact** ``rate_date == date(valid_at)`` (OD-P2-2-D); MID only
(v1).

Direction (QS-08): a stored ``base/quote`` rate means "1 base = rate quote", so converting an amount
in ``from_currency`` to ``to_currency`` MULTIPLIES by ``rate(from→to)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from irp_shared.marketdata.models import RATE_TYPE_MID
from irp_shared.marketdata.service import reconstruct_fx_rate_as_of

#: The default pivot/base currency for triangulation (QS-07; configurable per ``convert`` call).
DEFAULT_BASE = "USD"


class FxRateNotFound(Exception):
    """Raised when ``convert`` cannot resolve a required leg as-of — fails closed (never a silent
    1.0, never an interpolation/stale-rate fallback). Maps to 404/409 at the API."""

    def __init__(self, from_currency: str, to_currency: str) -> None:
        super().__init__(
            f"no published FX path {from_currency}->{to_currency} as-of (direct, reciprocal, "
            f"or triangulated-through-base)"
        )
        self.from_currency, self.to_currency = from_currency, to_currency


@dataclass(frozen=True)
class ConvertResult:
    """The outcome of a conversion: the converted amount + the published-rate legs used."""

    converted_amount: Decimal
    rate_type: str
    rate_path: list[str] = field(default_factory=list)


def _resolve_multiplier(
    session: Session,
    from_currency: str,
    to_currency: str,
    *,
    acting_tenant: str,
    valid_at: datetime,
    known_at: datetime | None,
    rate_type: str,
) -> tuple[Decimal, str] | None:
    """The ``from→to`` multiplier from a single published rate (direct or read-time reciprocal),
    with
    a human-readable leg label — or ``None`` if no direct/reciprocal rate is published as-of.
    Identity (``from == to``) is a multiplier of 1 (no lookup)."""
    if from_currency == to_currency:
        return Decimal(1), f"{from_currency}={to_currency}(identity)"
    rate_date = valid_at.date()  # exact-date matching (OD-P2-2-D)
    direct = reconstruct_fx_rate_as_of(
        session,
        acting_tenant=acting_tenant,
        base_currency=from_currency,
        quote_currency=to_currency,
        rate_date=rate_date,
        valid_at=valid_at,
        rate_type=rate_type,
        known_at=known_at,
    )
    if direct is not None:
        return direct.rate, f"{from_currency}->{to_currency} direct @{direct.rate}"
    reciprocal = reconstruct_fx_rate_as_of(
        session,
        acting_tenant=acting_tenant,
        base_currency=to_currency,
        quote_currency=from_currency,
        rate_date=rate_date,
        valid_at=valid_at,
        rate_type=rate_type,
        known_at=known_at,
    )
    if reciprocal is not None:
        return Decimal(
            1
        ) / reciprocal.rate, f"{from_currency}->{to_currency} reciprocal of {reciprocal.rate}"
    return None


def convert(
    session: Session,
    *,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    valid_at: datetime,
    acting_tenant: str,
    known_at: datetime | None = None,
    base: str = DEFAULT_BASE,
    rate_type: str = RATE_TYPE_MID,
) -> ConvertResult:
    """Convert ``amount`` from ``from_currency`` to ``to_currency`` as-of ``(valid_at, known_at)``
    using
    PUBLISHED rates only: identity → direct → reciprocal → triangulation-through-``base``. Fails
    closed
    (``FxRateNotFound``) if no path exists. Read-only (no audit/lineage/DQ)."""
    if from_currency == to_currency:
        return ConvertResult(amount, rate_type, [f"{from_currency}=={to_currency} (identity)"])

    direct = _resolve_multiplier(
        session,
        from_currency,
        to_currency,
        acting_tenant=acting_tenant,
        valid_at=valid_at,
        known_at=known_at,
        rate_type=rate_type,
    )
    if direct is not None:
        multiplier, label = direct
        return ConvertResult(amount * multiplier, rate_type, [label])

    # Triangulate through the configured base: from -> base -> to (each leg direct-or-reciprocal).
    leg1 = _resolve_multiplier(
        session,
        from_currency,
        base,
        acting_tenant=acting_tenant,
        valid_at=valid_at,
        known_at=known_at,
        rate_type=rate_type,
    )
    leg2 = _resolve_multiplier(
        session,
        base,
        to_currency,
        acting_tenant=acting_tenant,
        valid_at=valid_at,
        known_at=known_at,
        rate_type=rate_type,
    )
    if leg1 is not None and leg2 is not None:
        m1, l1 = leg1
        m2, l2 = leg2
        return ConvertResult(amount * m1 * m2, rate_type, [l1, l2])

    raise FxRateNotFound(from_currency, to_currency)
