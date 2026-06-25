"""Valuation-domain audit taxonomy constants (P1C-4 — ACTIVATES the VALUATION.* block).

The ``VALUATION`` category (EVT-180 block) is reserved-by-corridor and activated in P1C-4 — the next
domain block after PORTFOLIO (EVT-150), TRANSACTION (EVT-160), and POSITION (EVT-170). These are
value-level ``event_type`` strings passed to the **FROZEN** ``audit.service.record_event`` (no
central
event enum — "activation" = first emission; ``audit/service.py`` is unchanged).

- ``VALUATION.CREATE`` (EVT-180) — a captured new mark version (initial capture, and the new open
row
  of a valid-time supersede / re-mark).
- ``VALUATION.UPDATE`` (EVT-181) — a close-out of a prior head (the ``valid_to``/``system_to`` stamp
on
  a supersede/correction); no new lineage edge.
- ``VALUATION.CORRECTION`` (EVT-182) — an as-known restatement (a corrected NEW row over the same
valid
  period + same ``valuation_date``; carries ``restatement_reason`` TR-08 + ``supersedes_id``).
  Distinct
  code, mirroring the FR ``position``/``POSITION.CORRECTION`` (EVT-172) precedent (OD-P1C4-1).

There is no ``VALUATION.DELETE`` — a valuation is never deleted; a wrong mark is corrected via an
as-known restatement (a new version), and the prior version's content is never mutated.
"""

from __future__ import annotations

#: ACTIVATED in P1C-4 (caller-side constants to the FROZEN record_event).
VALUATION_CREATE_EVENT = "VALUATION.CREATE"  # EVT-180
VALUATION_UPDATE_EVENT = "VALUATION.UPDATE"  # EVT-181
VALUATION_CORRECTION_EVENT = "VALUATION.CORRECTION"  # EVT-182
