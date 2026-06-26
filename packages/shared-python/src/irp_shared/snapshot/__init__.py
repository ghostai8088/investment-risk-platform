"""Reproducible input-snapshot package (P2-1, ENT-049/050 — the AD-014 reproducibility primitive).

Leaf tooling: ``snapshot -> {portfolio, position, valuation, holdings, lineage, dq, audit, db}``;
nothing imports ``snapshot``. Imports NO ``calc`` symbol (readiness, not wiring); produces NO
derived number (no ``quantity x mark``, no exposure).
"""

from __future__ import annotations

from irp_shared.snapshot.events import SNAPSHOT_CREATE_EVENT, SnapshotActor, record_snapshot_create
from irp_shared.snapshot.models import (
    SNAPSHOT_COMPONENT_KINDS,
    SNAPSHOT_PURPOSES,
    DatasetSnapshot,
    DatasetSnapshotComponent,
)
from irp_shared.snapshot.service import (
    DEFAULT_BINDING_PREDICATE,
    EmptySnapshotError,
    SnapshotNotFound,
    SnapshotPurposeError,
    VerifyResult,
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
    "SnapshotActor",
    "SNAPSHOT_CREATE_EVENT",
    "record_snapshot_create",
    "build_snapshot",
    "verify_snapshot",
    "resolve_snapshot",
    "list_components",
    "VerifyResult",
    "DEFAULT_BINDING_PREDICATE",
    "SnapshotPurposeError",
    "EmptySnapshotError",
    "SnapshotNotFound",
]
