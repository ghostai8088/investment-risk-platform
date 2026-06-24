"""Portfolio-domain audit taxonomy constants (P1C-1 — ACTIVATES the PORTFOLIO.* block).

The ``PORTFOLIO`` category (EVT-150 block) was RESERVED at the P1C-0 ratification
(audit_event_taxonomy.md §3) — the head of the P1C domain corridor (TRANSACTION/POSITION/VALUATION
take the successive EVT-160/170/180 blocks). P1C-1 **activates** the first two as value-level
``event_type`` strings passed to the **FROZEN** ``audit.service.record_event`` (there is no central
event enum — "activation" = first emission; ``audit/service.py`` is unchanged).

- ``PORTFOLIO.CREATE`` (EVT-150) — a governed create of a portfolio hierarchy node.
- ``PORTFOLIO.UPDATE`` (EVT-151) — an in-place EV supersede (rename / re-parent / status / dates).

A ``status`` flip rides on ``PORTFOLIO.UPDATE`` (the P1B ``is_active``/status precedent), so
``PORTFOLIO.STATUS_CHANGE`` (EVT-152) is **reserved-but-not-emitted** in P1C-1 (held for a future
governed portfolio lifecycle if one is ever needed).
"""

from __future__ import annotations

#: ACTIVATED in P1C-1 (caller-side constants to the FROZEN record_event).
PORTFOLIO_CREATE_EVENT = "PORTFOLIO.CREATE"  # EVT-150
PORTFOLIO_UPDATE_EVENT = "PORTFOLIO.UPDATE"  # EVT-151
