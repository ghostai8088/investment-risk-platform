"""Audit-payload JSON-safety (MD-H1 annex item 2) — ONE canonical serializer for DC-2 summaries.

The audit ``before_value``/``after_value`` summary dicts are JSON-serialized, so every value in
them must be JSON-safe. This was hand-copied as a private ``_json_safe`` in ten binders that then
DRIFTED between ``str(decimal)`` (which can emit scientific ``1E+2``) and ``f"{decimal:f}"``
(fixed-point) — so the SAME number serialized differently across audit trails, and one copy (the
PA-0 proxy_mapping binder, pre-fix) omitted Decimal handling entirely and crashed at flush. This
module is the single source of truth.

Home rationale (MD-H1 deviation from OD-MD-H1 OQ-7): the ratified home was
``snapshot/serialize.py``, but importing it pulls in ``snapshot/__init__`` -> ``snapshot.service``
-> ``marketdata``, a circular import for the marketdata binders that need this helper. ``audit``
has a cycle-free ``__init__`` (a bare docstring) and is ALREADY a dependency of every binder
(``audit.service.record_event``), so this leaf module adds no new edge. ``audit/service.py`` stays
FROZEN and is untouched.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    """Coerce ONE audit-payload value to a JSON-serializable form.

    ``Decimal`` -> canonical fixed-point string (``f"{:f}"``, NEVER scientific ``1E+2``, so the same
    number serializes identically in every audit trail); ``datetime``/``date`` -> ISO-8601;
    everything else passes through unchanged. ``datetime`` is a ``date`` subclass, so the single
    ``date`` branch renders both correctly (full timestamp vs date-only via each ``isoformat``).
    """
    if isinstance(value, Decimal):
        return f"{value:f}"
    if isinstance(value, date):
        return value.isoformat()
    return value
