"""Aggregator that imports every ORM model so ``Base.metadata`` is fully populated.

Used by tests (``create_all``) and by Alembic (``target_metadata``).
"""

from __future__ import annotations

from irp_shared.audit.models import AuditCheckpoint, AuditEvent
from irp_shared.calc.models import CalculationRun
from irp_shared.db.base import Base
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.entitlement.models import (
    AppUser,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from irp_shared.ingestion.models import IngestionBatch, IngestionStagedRecord
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.model.models import Model, ModelAssumption, ModelLimitation, ModelVersion

metadata = Base.metadata

__all__ = [
    "Base",
    "metadata",
    "AuditEvent",
    "AuditCheckpoint",
    "CalculationRun",
    "AppUser",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "DataSource",
    "LineageEdge",
    "Model",
    "ModelVersion",
    "ModelAssumption",
    "ModelLimitation",
    "DataQualityRule",
    "DataQualityResult",
    "IngestionBatch",
    "IngestionStagedRecord",
]
