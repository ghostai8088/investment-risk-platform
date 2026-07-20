"""Governed commitment-pacing projection (CC-2, ENT-059) — the SEVENTEENTH governed number.

The deterministic Takahashi-Alexander pacing recursion (JPM 28(2):90-100, 2002) projects a
private-fund commitment's future capital calls, distributions, and NAV from the CC-1 captured
substrate (commitment + calls + distributions + the latest valuation mark). NO optimizer, NO
randomness — a closed-form deterministic linear system. The five model inputs (rate-of-contribution
schedule, fund life, bow, growth, yield floor) are DECLARED per-version parameters; only the
FUNCTIONAL FORM is Takahashi-Alexander's (no constant is minted from the paper). See
``05_analytics_methodologies/pacing_commitment_projection_v1.md``.
"""

from __future__ import annotations

from irp_shared.pacing.bootstrap import (
    PACING_MODEL_CODE,
    PACING_MODEL_NAME,
    PACING_VERSION_LABEL,
    declared_pacing_parameters,
    register_pacing_projection_model,
)
from irp_shared.pacing.events import (
    RUN_TYPE_PACING_PROJECTION,
    PacingActor,
)
from irp_shared.pacing.models import PacingProjectionResult
from irp_shared.pacing.pacing_kernel import (
    PacingAnchor,
    PacingKernelError,
    PacingParams,
    PacingPeriod,
    anniversary_window,
    project_commitment,
)

__all__ = [
    "PACING_MODEL_CODE",
    "PACING_MODEL_NAME",
    "PACING_VERSION_LABEL",
    "PacingActor",
    "PacingAnchor",
    "PacingKernelError",
    "PacingParams",
    "PacingPeriod",
    "PacingProjectionResult",
    "RUN_TYPE_PACING_PROJECTION",
    "anniversary_window",
    "declared_pacing_parameters",
    "project_commitment",
    "register_pacing_projection_model",
]
