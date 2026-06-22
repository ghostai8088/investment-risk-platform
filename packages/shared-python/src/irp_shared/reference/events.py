"""Reference-data audit taxonomy constants (P1B-1 — ACTIVATES the REFERENCE.* block).

The ``REFERENCE`` category (EVT-140 block) was reserved at P1B-0 (audit_event_taxonomy.md §3).
P1B-1 **activates** the first two as value-level ``event_type`` strings passed to the FROZEN
``audit.service.record_event`` (there is no central event enum — "activation" = first emission).

- ``REFERENCE.CREATE`` (EVT-140) — a governed create of a reference head (children fold in).
- ``REFERENCE.UPDATE`` (EVT-141) — an effective-dated supersede / attribute change of a head.

``REFERENCE.CORRECTION`` (EVT-142) and ``REFERENCE.STATUS_CHANGE`` (EVT-143) remain **reserved and
NOT emitted** in P1B-1; ``is_active`` flips ride on ``REFERENCE.UPDATE`` (no STATUS_CHANGE). The
constants are declared so the reservation is explicit in code and a scope-fence test can assert they
are never written.
"""

from __future__ import annotations

#: ACTIVATED in P1B-1.
REFERENCE_CREATE_EVENT = "REFERENCE.CREATE"  # EVT-140
REFERENCE_UPDATE_EVENT = "REFERENCE.UPDATE"  # EVT-141

#: RESERVED — declared for the taxonomy block, intentionally NOT emitted in P1B-1.
REFERENCE_CORRECTION_EVENT = "REFERENCE.CORRECTION"  # EVT-142 (reserved)
REFERENCE_STATUS_CHANGE_EVENT = "REFERENCE.STATUS_CHANGE"  # EVT-143 (reserved)
