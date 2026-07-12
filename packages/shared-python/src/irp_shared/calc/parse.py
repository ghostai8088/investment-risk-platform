"""Strict Decimal parsing for pinned-content reads (MD-H1 annex item 5).

Every governed binder re-parses Decimal values out of pinned JSON (``captured_content``) inside its
pre-create adjudication. A hostile or hand-minted value (``"NaN"``, ``"Infinity"``, garbage) must be
a governed 422 refusal, never a downstream ``InvalidOperation`` 500 — the BT-1 HIGH: a hand-minted
NaN ``var_value`` detonated as a raw 500 AND left a RUNNING orphan until the quantize-at-parse fold.
This helper makes that fold reusable: parse + explicit NaN/±Inf refusal (+ optional quantize to the
column scale) in one call, raising the family's binder-side value error.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


def parse_strict_decimal(
    raw: Any,
    *,
    error: Callable[[str], Exception],
    field: str = "value",
    quantum: Decimal | None = None,
) -> Decimal:
    """Parse ``raw`` as a FINITE Decimal, refusing NaN/±Inf/garbage with the family's 422 error.

    ``quantum`` (optional) additionally quantizes HALF_UP to the column scale — the BT-1 pattern
    that pins the stored echo byte-identical across engines. ``error`` is the binder's value-error
    class (a bare ``Exception`` accepting a message; maps to 422 at the endpoint).
    """
    try:
        value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise error(f"{field} {raw!r} is not a parseable decimal — refused") from None
    if not value.is_finite():  # NaN / +Inf / -Inf
        raise error(f"{field} {raw!r} is not a finite number — refused")
    if quantum is not None:
        try:
            # INSIDE the refusal envelope (review fold): a finite-but-huge value (e.g. 1E+40 at a
            # 6dp quantum under the default 28-digit context) raises InvalidOperation AT quantize —
            # that too must be the family 422, never an escaping 500 (the BT-1 class end to end).
            value = value.quantize(quantum, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            raise error(
                f"{field} {raw!r} does not fit the column scale {quantum} — refused"
            ) from None
    return value
