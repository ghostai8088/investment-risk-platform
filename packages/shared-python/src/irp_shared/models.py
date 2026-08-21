"""Aggregator that imports every ORM model so ``Base.metadata`` is fully populated.

Used by tests (``create_all``) and by Alembic (``target_metadata``).
"""

from __future__ import annotations

from irp_shared.audit.models import AuditCheckpoint, AuditEvent
from irp_shared.calc.models import CalculationRun
from irp_shared.classification.models import (
    ClassificationAssignment,
    ClassificationNode,
    ClassificationScheme,
)
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.db.base import Base
from irp_shared.dq.models import DataQualityResult, DataQualityRule
from irp_shared.entitlement.models import (
    AppUser,
    Permission,
    Role,
    RolePermission,
    RolePermissionRevocation,
    UserRole,
)
from irp_shared.entitlement.request_models import EntitlementRequest
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.ingest_mapping.models import IngestionMappingVersion
from irp_shared.ingestion.models import IngestionBatch, IngestionStagedRecord
from irp_shared.limit.models import Breach, LimitDefinition
from irp_shared.lineage.models import DataSource, LineageEdge
from irp_shared.liquidity.models import LiquidityResult
from irp_shared.marketdata.models import (
    BenchmarkLevel,
    BenchmarkReturn,
    Curve,
    CurvePoint,
    Factor,
    FactorReturn,
    FxRate,
    PricePoint,
    ProxyMapping,
)
from irp_shared.model.models import (
    Model,
    ModelAssumption,
    ModelLimitation,
    ModelValidation,
    ModelValidationEvidence,
    ModelValidationFinding,
    ModelVersion,
)
from irp_shared.notification.models import BreachNotification
from irp_shared.pacing.models import PacingProjectionResult
from irp_shared.perf.models import (
    BenchmarkRelativeResult,
    DesmoothedReturnResult,
    PortfolioReturnResult,
    RollingRiskResult,
    SharpeRatioResult,
)
from irp_shared.portfolio.models import Portfolio
from irp_shared.position.models import Position
from irp_shared.private_capital.models import CapitalCall, Commitment, Distribution
from irp_shared.reference.models import (
    Calendar,
    CalendarHoliday,
    CorporateAction,
    Counterparty,
    Currency,
    IdentifierXref,
    Instrument,
    InstrumentTerms,
    Issuer,
    LegalEntity,
    RatingGrade,
    RatingScale,
)
from irp_shared.report.models import ReportGeneration
from irp_shared.reproduction.models import ReproductionCheck
from irp_shared.risk.models import (
    ActiveRiskResult,
    CovarianceResult,
    FactorExposureResult,
    SensitivityResult,
    VarBacktestResult,
    VarResult,
)
from irp_shared.risk.scenario_models import (
    ScenarioDefinition,
    ScenarioResult,
    ScenarioShock,
)
from irp_shared.scheduling.models import Schedule, ScheduledRun
from irp_shared.snapshot.models import DatasetSnapshot, DatasetSnapshotComponent
from irp_shared.tenancy.models import Tenant
from irp_shared.transaction.models import Transaction
from irp_shared.valuation.models import Valuation

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
    "RolePermissionRevocation",
    "EntitlementRequest",
    "Tenant",
    "UserRole",
    "DataSource",
    "LineageEdge",
    "BreachNotification",
    "Model",
    "ModelVersion",
    "ModelAssumption",
    "ModelLimitation",
    "ModelValidation",
    "ModelValidationFinding",
    "ModelValidationEvidence",
    "DataQualityRule",
    "DataQualityResult",
    "IngestionBatch",
    "IngestionMappingVersion",
    "IngestionStagedRecord",
    "Currency",
    "Calendar",
    "CalendarHoliday",
    "RatingScale",
    "RatingGrade",
    "ClassificationScheme",
    "ClassificationNode",
    "ClassificationAssignment",
    "LegalEntity",
    "Issuer",
    "Counterparty",
    "Instrument",
    "InstrumentTerms",
    "IdentifierXref",
    "CorporateAction",
    "Portfolio",
    "Commitment",
    "CapitalCall",
    "Distribution",
    "PacingProjectionResult",
    "Transaction",
    "Position",
    "Valuation",
    "DatasetSnapshot",
    "DatasetSnapshotComponent",
    "FxRate",
    "PricePoint",
    "Curve",
    "CurvePoint",
    "Factor",
    "FactorReturn",
    "BenchmarkLevel",
    "BenchmarkReturn",
    "ProxyMapping",
    "ExposureAggregate",
    "ConcentrationResult",
    "LiquidityResult",
    "SensitivityResult",
    "FactorExposureResult",
    "CovarianceResult",
    "VarBacktestResult",
    "VarResult",
    "ActiveRiskResult",
    "ScenarioDefinition",
    "ScenarioShock",
    "ScenarioResult",
    "PortfolioReturnResult",
    "ReportGeneration",
    "ReproductionCheck",
    "RollingRiskResult",
    "SharpeRatioResult",
    "BenchmarkRelativeResult",
    "DesmoothedReturnResult",
    "Schedule",
    "ScheduledRun",
    "LimitDefinition",
    "Breach",
]
