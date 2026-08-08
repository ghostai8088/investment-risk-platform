"""REPRO-1 — the scheduled reproduction job (CTRL-018).

``events`` is the leaf vocabulary (``irp_worker`` imports it); ``models`` carries ENT-073 and the
``REPRODUCTION`` run type; ``registry`` declares which families can be re-executed and which cannot,
with a reason for every exclusion; ``service`` is the engine.
"""

from irp_shared.reproduction.events import (
    ALARM_RECIPIENT_PERMISSION,
    ALARMING_VERDICTS,
    ENTITY_REPRODUCTION_CHECK,
    VERDICT_DIVERGED,
    VERDICT_MATCH,
    VERDICT_UNREPRODUCIBLE,
    VERDICTS,
)
from irp_shared.reproduction.models import RUN_TYPE_REPRODUCTION, ReproductionCheck
from irp_shared.reproduction.registry import (
    REPRODUCIBLE_FAMILIES,
    UNREPRODUCIBLE_FAMILIES,
    ReproductionUnsupported,
)
from irp_shared.reproduction.service import (
    MAX_ALARM_ATTEMPTS,
    ReproductionInfrastructureFailure,
    ReproductionOutcome,
    alarm_for_verdict,
    run_reproduction_sweep,
    unalarmed_verdicts,
)

__all__ = [
    "ALARMING_VERDICTS",
    "ALARM_RECIPIENT_PERMISSION",
    "ENTITY_REPRODUCTION_CHECK",
    "MAX_ALARM_ATTEMPTS",
    "REPRODUCIBLE_FAMILIES",
    "RUN_TYPE_REPRODUCTION",
    "ReproductionCheck",
    "ReproductionInfrastructureFailure",
    "ReproductionOutcome",
    "ReproductionUnsupported",
    "UNREPRODUCIBLE_FAMILIES",
    "VERDICTS",
    "VERDICT_DIVERGED",
    "VERDICT_MATCH",
    "VERDICT_UNREPRODUCIBLE",
    "alarm_for_verdict",
    "run_reproduction_sweep",
    "unalarmed_verdicts",
]
