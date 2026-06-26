"""Market-data package (P2-2+) — captured, FR market data + pure published-rate helpers.

FX is the first tenant (``fx_rate``, ENT-024); P2-4 price / P2-5 curves / P2-6 benchmark join
additively. Leaf domain package: imports ``{reference, lineage, dq, audit, db}`` one-way; imports
**no** ``calc`` / ``snapshot`` / ``exposure`` symbol; nothing imports ``marketdata``. Captured
market
data ONLY — no analytics, no exposure, no ``calculation_run`` (OD-P2-E/F/G).
"""

from __future__ import annotations

from irp_shared.marketdata.convert import DEFAULT_BASE, ConvertResult, FxRateNotFound, convert
from irp_shared.marketdata.events import (
    MARKET_FX_CORRECTION_EVENT,
    MARKET_FX_CREATE_EVENT,
    MARKET_FX_UPDATE_EVENT,
    FxRateActor,
    ensure_vendor_source,
)
from irp_shared.marketdata.models import FX_RATE_TYPES, RATE_TYPE_MID, FxRate
from irp_shared.marketdata.service import (
    FxRateNotVisible,
    FxRateValueError,
    NoCurrentFxRate,
    capture_fx_rate,
    correct_fx_rate,
    reconstruct_fx_rate_as_of,
    resolve_fx_rate,
    supersede_fx_rate,
)

__all__ = [
    "FxRate",
    "FX_RATE_TYPES",
    "RATE_TYPE_MID",
    "FxRateActor",
    "MARKET_FX_CREATE_EVENT",
    "MARKET_FX_UPDATE_EVENT",
    "MARKET_FX_CORRECTION_EVENT",
    "ensure_vendor_source",
    "capture_fx_rate",
    "supersede_fx_rate",
    "correct_fx_rate",
    "reconstruct_fx_rate_as_of",
    "resolve_fx_rate",
    "FxRateValueError",
    "FxRateNotVisible",
    "NoCurrentFxRate",
    "convert",
    "ConvertResult",
    "FxRateNotFound",
    "DEFAULT_BASE",
]
