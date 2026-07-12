"""Shared bitemporal-supersede invariants for EVERY effective-dated (FR bitemporal) entity.

Every FR supersede is CLOSE-FIRST: it closes the current head's ``valid_to`` at the caller-supplied
``effective_at`` and opens a new version at that same instant. The ``effective_at`` must fall
strictly after the head's ``valid_from`` — otherwise the closed window inverts (``valid_to <
valid_from``) or collapses to zero width (``valid_to == valid_from``), leaving an unreconstructable
validity period. This guard is called BEFORE the close, fail-closed (MD-H1 OD-B); on violation it
raises the entity's binder-side value error (→ 422), the pre-write-refusal precedent.

Home rationale: lives in the leaf ``db`` package (zero ``irp_shared`` imports, like ``mixins``)
because the callers span BOTH the marketdata FR series (fx/price/curve/factor_return/
benchmark_level/benchmark_return/proxy_mapping/membership) AND the lower-level bitemporal entities
(``instrument_terms``/``position``/``valuation``) — a marketdata home would be a circular import
for the latter (MD-H1 Option-A extension, user-ratified 2026-07-12).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime


def _as_utc(value: datetime) -> datetime:
    """Normalize to a UTC-aware instant. A naive datetime (as SQLite returns stored ``valid_from``)
    denotes UTC by the platform convention (mirrors ``snapshot/serialize.py``); this keeps the
    comparison from raising on a naive-vs-aware mix regardless of the backend."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def assert_supersede_effective_at(
    prior_valid_from: datetime,
    effective_at: datetime,
    *,
    error: Callable[[str], Exception],
) -> None:
    """Refuse a supersede whose ``effective_at`` does not fall strictly after ``prior_valid_from``.

    Strictly-greater (MD-H1 OQ-1): a zero-width closed window is as incoherent as a negative one, so
    ``effective_at <= prior_valid_from`` is refused. ``error`` is the family's value-error class
    (a plain ``Exception`` subclass that accepts a message; maps to 422 at the endpoint).
    """
    if _as_utc(effective_at) <= _as_utc(prior_valid_from):
        raise error(
            f"effective_at {effective_at.isoformat()} must be strictly after the current version's "
            f"valid_from {prior_valid_from.isoformat()} (a supersede cannot invert or zero-width "
            f"the closed validity window)"
        )
