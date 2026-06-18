"""Temporal-class markers aligned to AD-005 / BR-19.

No persistence here yet (no schema in Step 1D). This only encodes the ratified
selective-bitemporality classes so future entities can declare their temporal class.
See ``04_data_model/temporal_reproducibility_standard.md`` §2A.
"""

from __future__ import annotations

from enum import Enum


class TemporalClass(str, Enum):
    """Ratified temporal classes for persisted entities."""

    FULL_REPRODUCIBLE = "FR"  # bitemporal: valid time + system time (risk-driving inputs)
    IMMUTABLE_APPEND_ONLY = "IA"  # append-only outputs, events, audit, overrides
    EFFECTIVE_DATED = "EV"  # effective-dated versioned reference/config
