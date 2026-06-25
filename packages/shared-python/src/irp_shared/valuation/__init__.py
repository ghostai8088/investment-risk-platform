"""Valuation domain package (P1C-4) — the captured bitemporal mark history.

``valuation`` (ENT-013) is the platform's second **FR domain** entity (third bitemporal entity,
after
the P1B-3 ``instrument_terms`` + the P1C-3 ``position``): a fully-reproducible mark history keyed to
a
``portfolio`` + an ``instrument`` + a ``valuation_date``. **Captured marks** (OD-P1C-F) — values
supplied to the platform, **never computed** by a valuation/pricing model and **never derived** from
positions (no ``position`` FK, no ``quantity × mark`` market-value rollup, no price lookup, no
market-data ingestion, no exposure aggregation, no holdings view, no corporate-action application).
**NOT append-only** (no ``irp_prevent_mutation`` trigger) — the FR protocol requires close-out
UPDATEs; prior-version content immutability is service-enforced + tested.

Depends one-way on two upstream packages — ``resolve_portfolio`` (from ``portfolio``) +
``resolve_instrument`` (from ``reference``) + the rails (lineage/audit/db); it never imports
``position``, ``irp_backend``, or ``irp_shared.models`` (the aggregator) — enforced by an
import-direction test. One-way: ``valuation -> {portfolio, reference, rails}``.
"""

from __future__ import annotations

from irp_shared.valuation.events import (
    VALUATION_CORRECTION_EVENT,
    VALUATION_CREATE_EVENT,
    VALUATION_UPDATE_EVENT,
)
from irp_shared.valuation.models import Valuation
from irp_shared.valuation.service import ValuationActor
from irp_shared.valuation.valuation import (
    NoCurrentValuation,
    ValuationNotVisible,
    correct_valuation,
    create_valuation,
    reconstruct_valuation_as_of,
    resolve_valuation,
    supersede_valuation,
)

__all__ = [
    "Valuation",
    "ValuationActor",
    "ValuationNotVisible",
    "NoCurrentValuation",
    "VALUATION_CREATE_EVENT",
    "VALUATION_UPDATE_EVENT",
    "VALUATION_CORRECTION_EVENT",
    "create_valuation",
    "supersede_valuation",
    "correct_valuation",
    "reconstruct_valuation_as_of",
    "resolve_valuation",
]
