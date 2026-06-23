"""Reference-data audit taxonomy constants (P1B-1 — ACTIVATES the REFERENCE.* block).

The ``REFERENCE`` category (EVT-140 block) was reserved at P1B-0 (audit_event_taxonomy.md §3).
P1B-1 **activates** the first two as value-level ``event_type`` strings passed to the FROZEN
``audit.service.record_event`` (there is no central event enum — "activation" = first emission).

- ``REFERENCE.CREATE`` (EVT-140) — a governed create of a reference head (children fold in).
- ``REFERENCE.UPDATE`` (EVT-141) — an effective-dated supersede / attribute change of a head.

``REFERENCE.CORRECTION`` (EVT-142) is **ACTIVATED in P1B-3** (R-07 sign-off, OQ-7) for the FR
``instrument_terms`` as-known restatement path — emitted caller-side via
``reference.service.record_reference_correction`` (the FROZEN ``audit.service.record_event`` is
unchanged), carrying the TR-08 ``restatement_reason`` (on ``justification``) + ``supersedes_id``.
``REFERENCE.STATUS_CHANGE`` (EVT-143) is **ACTIVATED in P1B-4** (R-07 sign-off, OQ-1) for the
`corporate_action` status-lifecycle transitions (ANNOUNCED → CONFIRMED → CANCELLED) — emitted
caller-side via ``reference.service.record_reference_status_change`` (the FROZEN
``audit.service.record_event`` is unchanged). For the P1B-1/P1B-2/P1B-3 entities, ``is_active``
flips
still ride on ``REFERENCE.UPDATE`` (no STATUS_CHANGE) — EVT-143 is used ONLY for corporate_action
transitions, and the existing reservation tests stay green (they never create a corporate_action).
"""

from __future__ import annotations

#: ACTIVATED in P1B-1.
REFERENCE_CREATE_EVENT = "REFERENCE.CREATE"  # EVT-140
REFERENCE_UPDATE_EVENT = "REFERENCE.UPDATE"  # EVT-141

#: EVT-142 ACTIVATED P1B-3 (instrument_terms restatement); EVT-143 ACTIVATED P1B-4
# (corporate_action).
REFERENCE_CORRECTION_EVENT = "REFERENCE.CORRECTION"  # EVT-142 (activated P1B-3)
REFERENCE_STATUS_CHANGE_EVENT = "REFERENCE.STATUS_CHANGE"  # EVT-143 (activated P1B-4)
