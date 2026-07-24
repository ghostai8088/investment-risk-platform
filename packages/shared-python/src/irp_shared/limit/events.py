"""Limit/breach vocabulary + actor (LIM-1, ENT-031/033 — the limit control-plane surface).

Three GOVERNED audit codes were ACTIVATED at LIM-1 — `LIMIT.DEFINE` / `LIMIT.CHANGE` / `BREACH.DETECT`
— the R-07 activation of the GENESIS-reserved `LIMIT` (EVT-060) + `BREACH` (EVT-070) taxonomy rows
(OD-LIM-1-J). **MG-2 ACTIVATES the five reserved breach LIFECYCLE codes** — `BREACH.ASSIGN` /
`BREACH.1L_RESPONSE` / `BREACH.2L_REVIEW` / `BREACH.ESCALATE` / `BREACH.CLOSE` (the DEP-WFL breach
remediation state machine over ENT-034 ``breach_action``). All are emitted by CALLING the FROZEN
``audit.service.record_event`` with the ``event_type`` parameter — the frozen append engine is
unchanged; every lifecycle event uses ``action=ACTION_RECORD`` (an append-only transition record).
The reserved `LIMIT.APPROVE` stays RESERVED (the maker-checker approve-gate — deferred to MG-3).

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

#: Breach lifecycle status (the LIM-1 `breach.status` column — frozen at DETECTED at detection).
#: DEPRECATED-IN-PLACE for lifecycle purposes at MG-2: `breach.status` can never change (breach is
#: IA append-only), so the OPERATIVE lifecycle state is the recency-derived latest `breach_action`
#: (`current_breach_state`), NEVER this column. Retained only as the detection-genesis marker.
BREACH_STATUS_DETECTED = "DETECTED"

# --- MG-2: the breach remediation lifecycle (DEP-WFL over ENT-034 breach_action) ---

#: The five reserved BREACH lifecycle audit codes, ACTIVATED by MG-2 (genesis EVT-070 decade).
BREACH_ASSIGN_EVENT = "BREACH.ASSIGN"
BREACH_1L_RESPONSE_EVENT = "BREACH.1L_RESPONSE"
BREACH_2L_REVIEW_EVENT = "BREACH.2L_REVIEW"
BREACH_ESCALATE_EVENT = "BREACH.ESCALATE"
BREACH_CLOSE_EVENT = "BREACH.CLOSE"

#: The audit ``entity_type`` tag for breach-action emits.
ENTITY_BREACH_ACTION = "breach_action"

#: Breach lifecycle STATES (the operative state = the latest `breach_action.to_state`; genesis is
#: DETECTED, which has no action row). ESCALATED is reachable from ASSIGNED/RESPONDED when overdue.
BREACH_STATE_DETECTED = "DETECTED"
BREACH_STATE_ASSIGNED = "ASSIGNED"
BREACH_STATE_RESPONDED = "RESPONDED"
BREACH_STATE_REVIEWED = "REVIEWED"
BREACH_STATE_ESCALATED = "ESCALATED"
BREACH_STATE_CLOSED = "CLOSED"
BREACH_STATES = frozenset(
    {
        BREACH_STATE_DETECTED,
        BREACH_STATE_ASSIGNED,
        BREACH_STATE_RESPONDED,
        BREACH_STATE_REVIEWED,
        BREACH_STATE_ESCALATED,
        BREACH_STATE_CLOSED,
    }
)

#: Breach action TYPES (the transition verb; DETECTED is the breach's genesis, not an action).
BREACH_ACTION_ASSIGN = "ASSIGN"
BREACH_ACTION_1L_RESPONSE = "1L_RESPONSE"
BREACH_ACTION_2L_REVIEW = "2L_REVIEW"
BREACH_ACTION_ESCALATE = "ESCALATE"
BREACH_ACTION_CLOSE = "CLOSE"
BREACH_ACTION_TYPES = frozenset(
    {
        BREACH_ACTION_ASSIGN,
        BREACH_ACTION_1L_RESPONSE,
        BREACH_ACTION_2L_REVIEW,
        BREACH_ACTION_ESCALATE,
        BREACH_ACTION_CLOSE,
    }
)

#: The audit ``event_type`` for each action (used by the lifecycle emitter).
BREACH_ACTION_EVENTS = {
    BREACH_ACTION_ASSIGN: BREACH_ASSIGN_EVENT,
    BREACH_ACTION_1L_RESPONSE: BREACH_1L_RESPONSE_EVENT,
    BREACH_ACTION_2L_REVIEW: BREACH_2L_REVIEW_EVENT,
    BREACH_ACTION_ESCALATE: BREACH_ESCALATE_EVENT,
    BREACH_ACTION_CLOSE: BREACH_CLOSE_EVENT,
}

#: 2L review outcome — ACCEPT advances RESPONDED→REVIEWED; REJECT sends it back to ASSIGNED.
BREACH_REVIEW_ACCEPT = "ACCEPT"
BREACH_REVIEW_REJECT = "REJECT"
BREACH_REVIEW_OUTCOMES = frozenset({BREACH_REVIEW_ACCEPT, BREACH_REVIEW_REJECT})

#: Line-of-defense tags stamped on a breach_action (derived from the gating permission).
BREACH_LINE_1L = "1L"
BREACH_LINE_2L = "2L"
BREACH_LINE_SYSTEM = "SYS"

#: The SYSTEM actor type for auto-escalation (BR-15: AI/automation is never an approver — a SYSTEM
#: escalation is an alarm, never a sign-off; every HUMAN transition asserts actor_type == "user").
BREACH_SYSTEM_ACTOR_TYPE = "SYSTEM"

#: Response-deadline SLA (days from ASSIGN) by limit_kind — the OQ-4 hardcoded map v1 (a per-limit
#: configurable SLA column is a recorded v2). A HARD breach (an incident) gets a tight clock.
BREACH_SLA_DAYS = {LIMIT_KIND_HARD: 1, LIMIT_KIND_SOFT: 5}


@dataclass(frozen=True)
class LimitActor:
    """The principal that created/edited a limit (mirrors ``SchedulingActor``). Limit management is
    a 2L risk-manager function (OD-J); the API enforces ``limit.manage`` on ``risk_manager_2l``.
    Breach detection runs as a synthesized SYSTEM actor on the operational tick."""

    actor_id: str
    actor_type: str = "user"


@dataclass(frozen=True)
class BreachActor:
    """The principal performing a breach lifecycle action (MG-2). A 1L responder (``breach.respond``)
    or a 2L reviewer/closer (``breach.review``); ``actor_type`` MUST be ``user`` for every human
    transition (BR-15). Auto-escalation synthesizes a SYSTEM actor on the operational tick."""

    actor_id: str
    actor_type: str = "user"
