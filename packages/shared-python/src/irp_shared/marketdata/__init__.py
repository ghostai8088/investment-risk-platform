"""Market-data package (P2-2+) — captured, FR market data + pure published-rate helpers.

FX is the first tenant (``fx_rate``, ENT-024); **price history (``price_point``, ENT-020) is the
second (P2-4)**; P2-5 curves / P2-6 benchmark join additively. Leaf domain package: imports
``{reference, lineage, dq, audit, db}`` one-way; imports **no** ``calc``/``snapshot``/``exposure``
symbol. Captured market data ONLY — no analytics, no exposure, no ``calculation_run`` (OD-P2-E/F/G).
(P2-3: the ``snapshot`` binder + the ``exposure`` compute import the PURE leg helpers
``resolve_conversion_legs`` / ``compose_effective_rate`` — a one-way ``{snapshot, exposure} ->
marketdata`` dependency; ``marketdata`` still imports neither.)
"""

from __future__ import annotations

from irp_shared.marketdata.convert import DEFAULT_BASE, ConvertResult, FxRateNotFound, convert
from irp_shared.marketdata.curve import (
    MARKET_CURVE_CORRECTION_EVENT,
    MARKET_CURVE_CREATE_EVENT,
    MARKET_CURVE_UPDATE_EVENT,
    VENDOR_CURVE_SOURCE_CODE,
    CurveActor,
    CurveNode,
    CurveNotVisible,
    CurveValueError,
    NoCurrentCurve,
    capture_curve,
    correct_curve,
    list_curve_points,
    reconstruct_curve_as_of,
    resolve_curve,
    supersede_curve,
)
from irp_shared.marketdata.events import (
    MARKET_FX_CORRECTION_EVENT,
    MARKET_FX_CREATE_EVENT,
    MARKET_FX_UPDATE_EVENT,
    FxRateActor,
    ensure_vendor_source,
)
from irp_shared.marketdata.legs import (
    FxLeg,
    compose_effective_rate,
    resolve_conversion_legs,
)
from irp_shared.marketdata.models import (
    CURVE_TYPES,
    CURVE_VALUE_TYPES,
    FX_RATE_TYPES,
    PRICE_TYPE_CLOSE,
    PRICE_TYPE_MID,
    PRICE_TYPE_NAV,
    PRICE_TYPES,
    RATE_TYPE_MID,
    REFERENCE_KEY_NONE,
    Curve,
    CurvePoint,
    FxRate,
    PricePoint,
)
from irp_shared.marketdata.price import (
    MARKET_PRICE_CORRECTION_EVENT,
    MARKET_PRICE_CREATE_EVENT,
    MARKET_PRICE_UPDATE_EVENT,
    VENDOR_PRICE_SOURCE_CODE,
    NoCurrentPrice,
    PriceActor,
    PriceNotVisible,
    PriceValueError,
    capture_price,
    correct_price,
    reconstruct_price_as_of,
    resolve_price,
    supersede_price,
)
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
    "resolve_conversion_legs",
    "compose_effective_rate",
    "FxLeg",
    "PricePoint",
    "PRICE_TYPES",
    "PRICE_TYPE_CLOSE",
    "PRICE_TYPE_MID",
    "PRICE_TYPE_NAV",
    "PriceActor",
    "MARKET_PRICE_CREATE_EVENT",
    "MARKET_PRICE_UPDATE_EVENT",
    "MARKET_PRICE_CORRECTION_EVENT",
    "VENDOR_PRICE_SOURCE_CODE",
    "capture_price",
    "supersede_price",
    "correct_price",
    "reconstruct_price_as_of",
    "resolve_price",
    "PriceValueError",
    "PriceNotVisible",
    "NoCurrentPrice",
    "Curve",
    "CurvePoint",
    "CurveNode",
    "CURVE_TYPES",
    "CURVE_VALUE_TYPES",
    "REFERENCE_KEY_NONE",
    "CurveActor",
    "MARKET_CURVE_CREATE_EVENT",
    "MARKET_CURVE_UPDATE_EVENT",
    "MARKET_CURVE_CORRECTION_EVENT",
    "VENDOR_CURVE_SOURCE_CODE",
    "capture_curve",
    "supersede_curve",
    "correct_curve",
    "reconstruct_curve_as_of",
    "resolve_curve",
    "list_curve_points",
    "CurveValueError",
    "CurveNotVisible",
    "NoCurrentCurve",
]
