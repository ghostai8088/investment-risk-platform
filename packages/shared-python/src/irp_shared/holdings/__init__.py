"""Holdings read-composition package (P1C-5) — read-only as-of holdings / portfolio views.

The platform's first **read-model** package: it owns NO entity, NO migration, NO governed write. It
COMPOSES the shipped captured FR reads — ``reconstruct_position_as_of`` (set-generalized into the
as-of holdings set), ``reconstruct_valuation_as_of`` (display-only marks, opt-in), and the bounded
``resolve_descendants`` (subtree composition) — into read DTOs. No ``models.py`` / ``events.py`` /
``service.py`` write paths: ``service.py`` here is read-only.

Capture-only (AD-017): no aggregation, no market value, no ``quantity x mark_value``, no exposure,
no ``dataset_snapshot``, no risk/pricing/valuation model, no derivation. Subtree traversal is read
composition, not ABAC enforcement (anchor-not-enforce, OD-P1C-A / OD-P1C-B).

One-way: ``holdings -> {portfolio, position, valuation, reference, rails}``; nothing imports it.
"""

from __future__ import annotations

from irp_shared.holdings.service import (
    HoldingRow,
    HoldingWithMark,
    MarkView,
    attach_marks_as_of,
    reconstruct_holdings_as_of,
    reconstruct_subtree_holdings_as_of,
)

__all__ = [
    "HoldingRow",
    "MarkView",
    "HoldingWithMark",
    "reconstruct_holdings_as_of",
    "reconstruct_subtree_holdings_as_of",
    "attach_marks_as_of",
]
