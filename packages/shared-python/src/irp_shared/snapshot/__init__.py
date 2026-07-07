"""Reproducible input-snapshot package (P2-1, ENT-049/050 — the AD-014 reproducibility primitive).

Leaf tooling: ``snapshot -> {portfolio, position, valuation, holdings, marketdata, lineage, dq,
audit, db}``; nothing imports ``snapshot``. Imports NO ``calc`` symbol (readiness, not wiring);
produces NO derived number (no ``quantity x mark``, no exposure computed). P2-3 pins FX legs (via
the ``marketdata`` pure leg helper) for ``EXPOSURE_INPUT`` snapshots — still no ``calculation_run``.
P3-3 pins already-computed IMMUTABLE ``exposure_aggregate`` atoms (a models-only, function-local
read — the ``exposure`` SERVICE is never imported, it imports ``snapshot``) + ``factor`` EV
definitions for ``FACTOR_EXPOSURE_INPUT`` snapshots — pinning outputs-as-inputs, computing nothing.
"""

from __future__ import annotations

from irp_shared.snapshot.events import SNAPSHOT_CREATE_EVENT, SnapshotActor, record_snapshot_create
from irp_shared.snapshot.models import (
    COMPONENT_KIND_CURVE,
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_FX,
    COMPONENT_KIND_POSITION,
    COMPONENT_KIND_VALUATION,
    PURPOSE_FACTOR_EXPOSURE_INPUT,
    PURPOSE_SENSITIVITY_INPUT,
    SNAPSHOT_COMPONENT_KINDS,
    SNAPSHOT_PURPOSES,
    DatasetSnapshot,
    DatasetSnapshotComponent,
)
from irp_shared.snapshot.service import (
    DEFAULT_BINDING_PREDICATE,
    CurveSelector,
    CurveSnapshotError,
    EmptySnapshotError,
    FactorExposureSnapshotError,
    SnapshotNotFound,
    SnapshotPurposeError,
    VerifyResult,
    build_curve_snapshot,
    build_factor_exposure_snapshot,
    build_snapshot,
    list_components,
    resolve_snapshot,
    verify_snapshot,
)

__all__ = [
    "DatasetSnapshot",
    "DatasetSnapshotComponent",
    "SNAPSHOT_PURPOSES",
    "SNAPSHOT_COMPONENT_KINDS",
    "COMPONENT_KIND_FX",
    "COMPONENT_KIND_CURVE",
    "COMPONENT_KIND_POSITION",
    "COMPONENT_KIND_VALUATION",
    "PURPOSE_SENSITIVITY_INPUT",
    "SnapshotActor",
    "SNAPSHOT_CREATE_EVENT",
    "record_snapshot_create",
    "build_snapshot",
    "build_curve_snapshot",
    "CurveSelector",
    "CurveSnapshotError",
    "verify_snapshot",
    "resolve_snapshot",
    "list_components",
    "VerifyResult",
    "DEFAULT_BINDING_PREDICATE",
    "SnapshotPurposeError",
    "EmptySnapshotError",
    "SnapshotNotFound",
    "COMPONENT_KIND_EXPOSURE",
    "COMPONENT_KIND_FACTOR",
    "PURPOSE_FACTOR_EXPOSURE_INPUT",
    "build_factor_exposure_snapshot",
    "FactorExposureSnapshotError",
]
