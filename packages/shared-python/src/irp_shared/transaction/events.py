"""Transaction-domain audit taxonomy constants (P1C-2 — ACTIVATES the TRANSACTION.* block).

The ``TRANSACTION`` category (EVT-160 block) is reserved + activated in P1C-2 — the next block in
the
P1C domain corridor after PORTFOLIO (EVT-150); POSITION (EVT-170) / VALUATION (EVT-180) follow in
their
slices. These are value-level ``event_type`` strings passed to the **FROZEN**
``audit.service.record_event``
(there is no central event enum — "activation" = first emission; ``audit/service.py`` is unchanged).

- ``TRANSACTION.RECORD`` (EVT-160) — a governed record of a new immutable transaction event.
- ``TRANSACTION.REVERSE`` (EVT-161) — a reversal record (a NEW row with ``reverses_transaction_id``;
  itself an append, never a mutation of the original).

There is **no** ``TRANSACTION.UPDATE``/``.STATUS_CHANGE`` — a transaction is immutable
(append-only), so
the only governed events are the record of a new row (a normal capture, or a reversal record).
"""

from __future__ import annotations

#: ACTIVATED in P1C-2 (caller-side constants to the FROZEN record_event).
TRANSACTION_RECORD_EVENT = "TRANSACTION.RECORD"  # EVT-160
TRANSACTION_REVERSE_EVENT = "TRANSACTION.REVERSE"  # EVT-161
