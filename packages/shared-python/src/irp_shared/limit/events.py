"""Limit/breach vocabulary + actor (LIM-1, ENT-031/033 — the limit control-plane surface).

Three GOVERNED audit codes are ACTIVATED here — `LIMIT.DEFINE` / `LIMIT.CHANGE` / `BREACH.DETECT` —
the R-07 activation of the GENESIS-reserved `LIMIT` (EVT-060) + `BREACH` (EVT-070) taxonomy rows
(OD-LIM-1-J). They are emitted by CALLING the FROZEN ``audit.service.record_event`` with the
``event_type`` parameter (the ``reference/service.py``/``scheduling`` mechanic) — the frozen append
engine is unchanged. The reserved `LIMIT.APPROVE` + the breach lifecycle codes (`.ASSIGN`/
`.1L_RESPONSE`/`.2L_REVIEW`/`.ESCALATE`/`.CLOSE`) stay RESERVED (deferred to MG-2, OQ-4=A).

A breach binds NO new snapshot/run/model — the scheduled RUNS it evaluates are already governed
(`CALC.RUN_*`); a `breach` is control-plane evidence, NOT a governed number.
"""

from __future__ import annotations

from dataclasses import dataclass

#: GOVERNED audit codes (the genesis-reserved LIMIT/EVT-060 + BREACH/EVT-070 decades), ACTIVATED by
#: LIM-1 and EMITTED for limit config changes + breach detection.
LIMIT_DEFINE_EVENT = "LIMIT.DEFINE"
LIMIT_CHANGE_EVENT = "LIMIT.CHANGE"
BREACH_DETECT_EVENT = "BREACH.DETECT"

#: The audit ``source_module`` tag for limit/breach emits.
SOURCE_MODULE_LIMIT = "limit"

#: The audit ``entity_type`` tags.
ENTITY_LIMIT_DEFINITION = "limit_definition"
ENTITY_BREACH = "breach"

#: Threshold units (controlled vocab, service-enforced) — the unit-awareness guard (OD-C): a
#: CURRENCY threshold is NEVER compared against a FRACTION metric.
THRESHOLD_UNIT_CURRENCY = "CURRENCY"
THRESHOLD_UNIT_FRACTION = "FRACTION"
THRESHOLD_UNITS = frozenset({THRESHOLD_UNIT_CURRENCY, THRESHOLD_UNIT_FRACTION})

#: The breach predicate (OD-D, the anti-inversion fix) — names the BREACH condition DIRECTLY.
#: ABOVE = breach when ``observed > threshold`` (a CEILING, the v1 default); BELOW = breach when
#: ``observed < threshold`` (a FLOOR). Strict inequality: ``observed == threshold`` is COMPLIANT.
BREACH_ABOVE = "ABOVE"
BREACH_BELOW = "BELOW"
BREACH_DIRECTIONS = frozenset({BREACH_ABOVE, BREACH_BELOW})

#: Limit kind (controlled vocab). HARD = binding (a breach is an incident); SOFT = advisory (a
#: recorded warning). ``REQ-LIM-001`` (10.3).
LIMIT_KIND_HARD = "HARD"
LIMIT_KIND_SOFT = "SOFT"
LIMIT_KINDS = frozenset({LIMIT_KIND_HARD, LIMIT_KIND_SOFT})

#: Limit lifecycle status. Only ACTIVE limits are evaluated. (No DRAFT/APPROVE gate in v1 — OQ-4=A.)
LIMIT_STATUS_ACTIVE = "ACTIVE"
LIMIT_STATUS_SUSPENDED = "SUSPENDED"
LIMIT_STATUSES = frozenset({LIMIT_STATUS_ACTIVE, LIMIT_STATUS_SUSPENDED})

#: Breach lifecycle status. v1 = DETECTED only; ASSIGN/1L/2L/ESCALATE/CLOSE are MG-2 (OQ-4=A).
BREACH_STATUS_DETECTED = "DETECTED"


@dataclass(frozen=True)
class LimitActor:
    """The principal that created/edited a limit (mirrors ``SchedulingActor``). Limit management is
    a 2L risk-manager function (OD-J); the API enforces ``limit.manage`` on ``risk_manager_2l``.
    Breach detection runs as a synthesized SYSTEM actor on the operational tick."""

    actor_id: str
    actor_type: str = "user"
