"""Risk package (P3-1, ENT-028) — the first reproducible governed risk number (analytic
sensitivities: curve-node DV01 / spread-DV01).

Leaf domain package: ``risk -> {snapshot, marketdata(constants/kernel), calc, model, lineage, dq,
audit, db}``; nothing imports ``risk``. Every compute reads ONLY snapshot-pinned captured content
(never a live curve/exposure/factor/return read) and imports no VaR/ES/scenario/stress symbol.
Run-bound + snapshot-gated + **model_version-bound** (AD-014 / FW-RUN / TR-15 / CTRL-003) — no
risk number escapes the model inventory. P3-1 analytic sensitivities (curve-intrinsic — NO
instrument/position attribution, NO interpolation, NO pricing engine); P3-3 indicator-loading
factor-exposure allocation; P3-4 equal-weighted unbiased sample covariance (ENT-051 — NO
shrinkage/EWMA/correlation output; the window is version identity; **numpy is TEST-ONLY, never a
runtime import**).
"""

from __future__ import annotations

from irp_shared.risk.bootstrap import (
    COVARIANCE_METHODOLOGY_REF,
    COVARIANCE_MODEL_CODE,
    FACTOR_EXPOSURE_METHODOLOGY_REF,
    FACTOR_EXPOSURE_MODEL_CODE,
    SENSITIVITY_METHODOLOGY_REF,
    SENSITIVITY_MODEL_CODE,
    WINDOW_ASSUMPTION_PREFIX,
    ModelVersionConflictError,
    WrongModelVersionError,
    assert_model_version_of,
    declared_window_observations,
    register_covariance_model,
    register_factor_exposure_model,
    register_sensitivity_model,
)
from irp_shared.risk.covariance_kernel import (
    CovarianceKernelError,
    FactorSeriesPin,
    estimate_covariance,
)
from irp_shared.risk.covariance_service import (
    CovarianceInputError,
    CovarianceNotVisible,
    CovarianceRunNotVisible,
    CovarianceRunResult,
    list_covariances,
    resolve_covariance,
    resolve_covariance_run,
    run_covariance,
)
from irp_shared.risk.events import (
    RISK_COVARIANCE_CREATE_EVENT_RESERVED,
    RISK_FACTOR_EXPOSURE_CREATE_EVENT_RESERVED,
    RISK_SENSITIVITY_CREATE_EVENT_RESERVED,
    RUN_TYPE_COVARIANCE,
    RUN_TYPE_FACTOR_EXPOSURE,
    RUN_TYPE_SENSITIVITY,
    SENSITIVITY_TYPE_DV01,
    SENSITIVITY_TYPE_SPREAD_DV01,
    SENSITIVITY_TYPES,
    STATISTIC_TYPE_COVARIANCE,
    STATISTIC_TYPES,
    CovarianceActor,
    FactorExposureActor,
    SensitivityActor,
)
from irp_shared.risk.factor_kernel import FactorKernelError
from irp_shared.risk.factor_service import (
    SUPPORTED_FACTOR_FAMILIES,
    FactorExposureInputError,
    FactorExposureNotVisible,
    FactorExposureRunNotVisible,
    FactorExposureRunResult,
    list_factor_exposures,
    resolve_factor_exposure,
    resolve_factor_exposure_run,
    run_factor_exposure,
)
from irp_shared.risk.kernel import SensitivityKernelError, node_dv01, node_spread_dv01
from irp_shared.risk.models import CovarianceResult, FactorExposureResult, SensitivityResult
from irp_shared.risk.service import (
    SensitivityInputError,
    SensitivityNotVisible,
    SensitivityRunNotVisible,
    SensitivityRunResult,
    list_sensitivities,
    resolve_run,
    resolve_sensitivity,
    run_sensitivities,
)

__all__ = [
    "SensitivityResult",
    "SensitivityActor",
    "RUN_TYPE_SENSITIVITY",
    "RISK_SENSITIVITY_CREATE_EVENT_RESERVED",
    "SENSITIVITY_TYPE_DV01",
    "SENSITIVITY_TYPE_SPREAD_DV01",
    "SENSITIVITY_TYPES",
    "node_dv01",
    "node_spread_dv01",
    "SensitivityKernelError",
    "run_sensitivities",
    "list_sensitivities",
    "resolve_run",
    "resolve_sensitivity",
    "SensitivityRunResult",
    "SensitivityInputError",
    "SensitivityNotVisible",
    "SensitivityRunNotVisible",
    "register_sensitivity_model",
    "SENSITIVITY_MODEL_CODE",
    "SENSITIVITY_METHODOLOGY_REF",
    "FactorExposureResult",
    "FactorExposureActor",
    "RUN_TYPE_FACTOR_EXPOSURE",
    "RISK_FACTOR_EXPOSURE_CREATE_EVENT_RESERVED",
    "FactorKernelError",
    "run_factor_exposure",
    "list_factor_exposures",
    "resolve_factor_exposure_run",
    "resolve_factor_exposure",
    "FactorExposureRunResult",
    "FactorExposureInputError",
    "FactorExposureNotVisible",
    "FactorExposureRunNotVisible",
    "SUPPORTED_FACTOR_FAMILIES",
    "register_factor_exposure_model",
    "FACTOR_EXPOSURE_MODEL_CODE",
    "FACTOR_EXPOSURE_METHODOLOGY_REF",
    "WrongModelVersionError",
    "ModelVersionConflictError",
    "assert_model_version_of",
    "CovarianceResult",
    "CovarianceActor",
    "RUN_TYPE_COVARIANCE",
    "RISK_COVARIANCE_CREATE_EVENT_RESERVED",
    "STATISTIC_TYPE_COVARIANCE",
    "STATISTIC_TYPES",
    "CovarianceKernelError",
    "FactorSeriesPin",
    "estimate_covariance",
    "run_covariance",
    "list_covariances",
    "resolve_covariance_run",
    "resolve_covariance",
    "CovarianceRunResult",
    "CovarianceInputError",
    "CovarianceNotVisible",
    "CovarianceRunNotVisible",
    "register_covariance_model",
    "declared_window_observations",
    "COVARIANCE_MODEL_CODE",
    "COVARIANCE_METHODOLOGY_REF",
    "WINDOW_ASSUMPTION_PREFIX",
]
