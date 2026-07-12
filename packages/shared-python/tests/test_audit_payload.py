"""MD-H1 annex item 2: pin the ONE canonical audit-payload serializer (``audit.payload.json_safe``).

Guards against the ``str(d)`` vs ``f"{d:f}"`` Decimal-rendering drift that had crept across the ten
hand-copied ``_json_safe`` helpers — the whole reason for consolidating them. Also asserts every
binder now imports the shared helper (no local re-definition can re-introduce the drift).
"""

from __future__ import annotations

import ast
import pathlib
from datetime import UTC, date, datetime
from decimal import Decimal

from irp_shared.audit.payload import json_safe

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "irp_shared"


def test_decimal_is_canonical_fixed_point_never_scientific() -> None:
    # the drift case: str(Decimal("1E+2")) == "1E+2" (scientific), but the canonical form is "100".
    assert json_safe(Decimal("1E+2")) == "100"
    assert json_safe(Decimal("100")) == "100"
    assert json_safe(Decimal("0.750000000000")) == "0.750000000000"  # trailing zeros preserved
    assert json_safe(Decimal("-0.0123")) == "-0.0123"
    assert "E" not in json_safe(Decimal("1E-9")) and "e" not in json_safe(Decimal("1E-9"))


def test_datetime_and_date_are_isoformat() -> None:
    assert json_safe(datetime(2026, 6, 1, 12, 0, tzinfo=UTC)) == "2026-06-01T12:00:00+00:00"
    assert json_safe(date(2026, 6, 1)) == "2026-06-01"  # date-only, not a full timestamp


def test_non_serializable_types_pass_through_unchanged() -> None:
    assert json_safe("USD") == "USD"
    assert json_safe(None) is None
    assert json_safe(42) == 42


def test_no_binder_redefines_json_safe_locally() -> None:
    # Any module that defines its OWN `def _json_safe`/`def json_safe` re-opens the drift class.
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        if path.name == "payload.py":
            continue  # the canonical home
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {"_json_safe", "json_safe"}:
                offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}")
    assert not offenders, f"local _json_safe redefinitions re-open the drift: {offenders}"
