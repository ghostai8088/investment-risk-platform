"""Audit-event ``action`` vocabulary (MD-H1 annex item 3) — constants, not raw string literals.

The ``action`` field on an audit event is a query axis (e.g. "every restatement" =
``action == ACTION_CORRECT``). It was raw string literals at ~60 call sites, where a convention miss
is invisible until review — the PA-0 incident: a proxy-mapping correction emitted ``"update"`` where
the sibling FR binders emit ``"correct"``, so an ``action=="correct"`` restatement query would have
silently missed proxy restatements. Constants make the vocabulary discoverable and a typo a
NameError; the conformance test (``test_audit_actions.py``) refuses any new raw-literal ``action=``.

``audit/service.py`` stays FROZEN — it takes ``action`` as an opaque string and needs no change.
"""

from __future__ import annotations

#: A new entity/version/row came into being (incl. the new open row minted by a supersede).
ACTION_CREATE = "create"
#: A mutable-by-design column changed (an EV content update, or an FR close-out stamp).
ACTION_UPDATE = "update"
#: An as-known (system-time) restatement — the FR correction convention (TR-08).
ACTION_CORRECT = "correct"
#: A calculation_run lifecycle transition (CREATED/RUNNING/COMPLETED/FAILED).
ACTION_STATUS_CHANGE = "status_change"
#: A data-quality gate execution (DATA.VALIDATE).
ACTION_VALIDATE = "validate"
#: An append-only reversal record (transaction).
ACTION_REVERSE = "reverse"
#: An append-only capture record (transaction).
ACTION_RECORD = "record"
#: An entitlement grant.
ACTION_GRANT = "grant"
