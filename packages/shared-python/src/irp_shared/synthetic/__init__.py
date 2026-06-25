"""Synthetic dataset package (P1C-6) — deterministic, labeled, NEVER-AUTO-RUN seed tooling.

A test/demo/UI enabler (OD-P1C-L): ``build_synthetic_dataset`` composes the governed binders into a
fixed, reproducible demo dataset under the reserved SYNTHETIC tenant. **Not** wired to migrations or
app startup; it refuses to run without an explicit confirmation + a non-production env gate, and can
only ever write to the SYNTHETIC tenant. Deterministic ``uuid5`` ids + a fixed seed clock (no
wall-clock/random — AST-fenced). Capture-only: it computes nothing (no market value / exposure).

One-way imports: ``synthetic → {portfolio, position, valuation, transaction, reference, db}``;
nothing
imports ``synthetic`` (it is leaf tooling).
"""

from __future__ import annotations

from irp_shared.synthetic.builder import (
    ALLOW_SYNTHETIC_SEED_ENV,
    SyntheticDatasetSummary,
    SyntheticSeedRefused,
    build_synthetic_dataset,
)
from irp_shared.synthetic.ids import (
    SEED_EPOCH,
    SYNTHETIC_ACTOR_ID,
    SYNTHETIC_TENANT_ID,
    SeedClock,
    business_date,
    synthetic_id,
)

__all__ = [
    "build_synthetic_dataset",
    "SyntheticDatasetSummary",
    "SyntheticSeedRefused",
    "ALLOW_SYNTHETIC_SEED_ENV",
    "synthetic_id",
    "SeedClock",
    "business_date",
    "SEED_EPOCH",
    "SYNTHETIC_TENANT_ID",
    "SYNTHETIC_ACTOR_ID",
]
