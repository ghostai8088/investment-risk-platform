"""Unit tests for the shared bitemporal supersede window-coherence guard (MD-H1 OD-B + Option A).

The guard (`assert_supersede_effective_at`, home `db/bitemporal.py`) is the single place EVERY
effective-dated entity — the seven marketdata FR modules (fx/price/curve/factor/benchmark
membership/benchmark level+return/proxy_mapping) AND the three lower-level bitemporal entities
(instrument_terms/position/valuation) — enforces that a supersede's `effective_at` falls strictly
after the current head's `valid_from`; otherwise the closed validity window inverts or collapses to
zero width. The per-entity integration wirings (that each supersede path actually calls it with the
right error class) live in the entity test files; this file pins the boundary logic itself.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from irp_shared.db.bitemporal import assert_supersede_effective_at

_VF = datetime(2026, 6, 1, tzinfo=UTC)


class _Boom(Exception):
    """Stand-in for a family value-error class (a bare Exception accepting a message)."""


def test_effective_at_strictly_after_is_allowed() -> None:
    # one microsecond after valid_from is the tightest coherent window — allowed.
    assert_supersede_effective_at(
        _VF, _VF.replace(microsecond=1), error=_Boom
    )  # returns None, no raise
    assert_supersede_effective_at(_VF, datetime(2026, 6, 2, tzinfo=UTC), error=_Boom)


def test_effective_at_equal_to_valid_from_is_refused() -> None:
    # strictly-greater (OQ-1): a zero-width closed window carries no coherent validity period.
    with pytest.raises(_Boom) as exc:
        assert_supersede_effective_at(_VF, _VF, error=_Boom)
    assert "strictly after" in str(exc.value)


def test_effective_at_before_valid_from_is_refused() -> None:
    # the integrity case: a backdated supersede would invert the closed window (to < from).
    with pytest.raises(_Boom) as exc:
        assert_supersede_effective_at(_VF, datetime(2026, 5, 1, tzinfo=UTC), error=_Boom)
    assert "invert or zero-width" in str(exc.value)


def test_error_factory_receives_a_message() -> None:
    # the guard passes a human-readable message the endpoint layer surfaces in the 422 detail.
    with pytest.raises(_Boom) as exc:
        assert_supersede_effective_at(_VF, _VF, error=_Boom)
    assert _VF.isoformat() in str(exc.value)
