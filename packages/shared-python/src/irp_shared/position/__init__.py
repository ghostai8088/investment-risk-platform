"""Position domain package (P1C-3) — the captured bitemporal holdings master.

``position`` (ENT-011) is the platform's first **FR domain** entity (second bitemporal entity, after
the P1B-3 ``instrument_terms``): a fully-reproducible holdings record keyed to a ``portfolio`` + an
``instrument``. **Captured directly** (OD-P1C-E) — a holding supplied to the platform, **never
derived** from the transaction log (no ``transaction`` FK, no derivation engine, no cashflow engine,
no valuation, no exposure aggregation, no corporate-action application). **NOT append-only** (no
``irp_prevent_mutation`` trigger) — the FR protocol requires close-out UPDATEs; prior-version
content
immutability is service-enforced + tested.

Depends one-way on two upstream packages — ``resolve_portfolio`` (from ``portfolio``) +
``resolve_instrument`` (from ``reference``) + the rails (lineage/audit/db); it never imports
``irp_backend`` or ``irp_shared.models`` (the aggregator) — enforced by an import-direction test.
One-way: ``position -> {portfolio, reference, rails}``.
"""

from __future__ import annotations

from irp_shared.position.events import (
    POSITION_CORRECTION_EVENT,
    POSITION_CREATE_EVENT,
    POSITION_UPDATE_EVENT,
)
from irp_shared.position.models import Position
from irp_shared.position.position import (
    NoCurrentPosition,
    PositionNotVisible,
    correct_position,
    create_position,
    reconstruct_position_as_of,
    resolve_position,
    supersede_position,
)
from irp_shared.position.service import PositionActor

__all__ = [
    "Position",
    "PositionActor",
    "PositionNotVisible",
    "NoCurrentPosition",
    "POSITION_CREATE_EVENT",
    "POSITION_UPDATE_EVENT",
    "POSITION_CORRECTION_EVENT",
    "create_position",
    "supersede_position",
    "correct_position",
    "reconstruct_position_as_of",
    "resolve_position",
]
