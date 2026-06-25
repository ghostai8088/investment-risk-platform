"""Position-domain audit taxonomy constants (P1C-3 — ACTIVATES the POSITION.* block).

The ``POSITION`` category (EVT-170 block) is reserved-by-corridor and activated in P1C-3 — the next
domain block after PORTFOLIO (EVT-150) and TRANSACTION (EVT-160); VALUATION (EVT-180) follows in
P1C-4. These are value-level ``event_type`` strings passed to the **FROZEN**
``audit.service.record_event`` (no central event enum — "activation" = first emission;
``audit/service.py`` is unchanged).

- ``POSITION.CREATE`` (EVT-170) — a captured new position version (initial capture, and the new open
  row of a valid-time supersede).
- ``POSITION.UPDATE`` (EVT-171) — a close-out of a prior head (the ``valid_to``/``system_to`` stamp
on
  a supersede/correction); no new lineage edge.
- ``POSITION.CORRECTION`` (EVT-172) — an as-known restatement (a corrected NEW row over the same
valid
  period; carries ``restatement_reason`` TR-08 + ``supersedes_id``). Distinct code, mirroring the FR
  ``instrument_terms``/``REFERENCE.CORRECTION`` (EVT-142) precedent (OD-P1C3-1).

There is no ``POSITION.DELETE``/``.REVERSE`` — a position is never deleted; a wrong value is
corrected
via an as-known restatement (a new version), and the prior version's content is never mutated.
"""

from __future__ import annotations

#: ACTIVATED in P1C-3 (caller-side constants to the FROZEN record_event).
POSITION_CREATE_EVENT = "POSITION.CREATE"  # EVT-170
POSITION_UPDATE_EVENT = "POSITION.UPDATE"  # EVT-171
POSITION_CORRECTION_EVENT = "POSITION.CORRECTION"  # EVT-172
