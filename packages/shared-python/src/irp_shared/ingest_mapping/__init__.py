"""INGEST-1 mapping spine (W19-S3a, REQ-INT-001) — ENT-077 + the closed-set interpreter.

*The AI proposes a mapping. A human ratifies it. The platform executes the ratified version
deterministically, forever, and every loaded row records which version loaded it.* (INGEST-1,
ratified 2026-08-12.)

**Why this is its own package and not a module inside ``irp_shared.ingestion``.** The ingestion
package's import-direction fence forbids it from importing ``irp_shared.model``, and a mapping
proposal must bind the drafting ModelVersion. Rather than widen a shipped scope fence, the spine
lives here with its OWN fence: ``ingest_mapping -> {ingestion, position, portfolio, reference,
model, lineage, audit, db, temporal}``, one-way, and nothing imports it back.

Dependency direction, stated because it is the thing a future refactor will get wrong:
``ingest_mapping`` imports ``position``; ``position`` must NEVER import ``ingest_mapping`` (its own
fence forbids it), which is why S3b's ``position.ingestion_mapping_version_id`` FK is spelled as a
literal table-name string rather than a Python reference.
"""

from __future__ import annotations

from irp_shared.ingest_mapping.errors import (
    MappingContentImmutableError,
    MappingError,
    MappingLifecycleError,
    MappingNotVisible,
    OverlappingLoadError,
    SelfRatificationError,
    UnratifiedMappingError,
    UnsupportedOperationError,
)
from irp_shared.ingest_mapping.events import ENTITY_MAPPING_VERSION, MAPPING_EVENT
from irp_shared.ingest_mapping.models import IngestionMappingVersion
from irp_shared.ingest_mapping.operations import OPERATIONS
from irp_shared.ingest_mapping.service import (
    LoadResult,
    load_batch,
    propose_mapping_version,
    ratified_mapping_for,
    ratify_mapping_version,
    resolve_mapping_version,
)

__all__ = [
    "ENTITY_MAPPING_VERSION",
    "MAPPING_EVENT",
    "OPERATIONS",
    "IngestionMappingVersion",
    "LoadResult",
    "MappingContentImmutableError",
    "MappingError",
    "MappingLifecycleError",
    "MappingNotVisible",
    "OverlappingLoadError",
    "SelfRatificationError",
    "UnratifiedMappingError",
    "UnsupportedOperationError",
    "load_batch",
    "propose_mapping_version",
    "ratified_mapping_for",
    "ratify_mapping_version",
    "resolve_mapping_version",
]
