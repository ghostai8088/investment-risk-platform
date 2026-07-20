"""Audit-event constants for the private-capital capture family (CC-1, OD-CC-1-F).

The ``PRIVATE.*`` family — the EVT-240 decade, ACTIVATED at CC-1 under the governed R-07
mint (BC-04 Private Assets is its own audit domain, distinct from MARKET/EVT-200:
proxy_mapping joined MARKET because it IS marketdata-shaped; commitments are not). SEVEN
caller-side constants; ``audit/service.py`` stays FROZEN — services pass these to the
frozen ``record_event``.

Per-op event grain (the MARKET/POSITION taxonomy precedent): FR commitment capture emits
ONE CREATE; supersede emits UPDATE (close-out) + CREATE (new version); correct emits
UPDATE + CORRECTION with ``action="correct"`` and a before/after-SYMMETRIC payload (the
two PA-0 review-fold lessons, test-pinned). IA event rows are create-only; a REVERSAL is
itself an append and emits the distinct ``*_REVERSE`` verb (the TRANSACTION.REVERSE/
EVT-161 precedent — a correction indistinguishable from an ordinary capture at the
event_type grain would hide corrections from audit queries); its payload carries
``reverses_id``. DC-2 metadata-only payloads; no event on read.
"""

from __future__ import annotations

PRIVATE_COMMITMENT_CREATE_EVENT = "PRIVATE.COMMITMENT_CREATE"
PRIVATE_COMMITMENT_UPDATE_EVENT = "PRIVATE.COMMITMENT_UPDATE"
PRIVATE_COMMITMENT_CORRECTION_EVENT = "PRIVATE.COMMITMENT_CORRECTION"
PRIVATE_CAPITAL_CALL_CREATE_EVENT = "PRIVATE.CAPITAL_CALL_CREATE"
PRIVATE_CAPITAL_CALL_REVERSE_EVENT = "PRIVATE.CAPITAL_CALL_REVERSE"
PRIVATE_DISTRIBUTION_CREATE_EVENT = "PRIVATE.DISTRIBUTION_CREATE"
PRIVATE_DISTRIBUTION_REVERSE_EVENT = "PRIVATE.DISTRIBUTION_REVERSE"

ENTITY_COMMITMENT = "commitment"
ENTITY_CAPITAL_CALL = "capital_call"
ENTITY_DISTRIBUTION = "distribution"
SOURCE_MODULE = "private_capital"
