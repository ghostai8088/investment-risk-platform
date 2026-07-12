"""MD-H1 annex item 5: the shared strict-Decimal parser for pinned-content reads.

Pins the refusal semantics (NaN/±Inf/garbage → the family 422 error, never a downstream
InvalidOperation 500 — the BT-1 HIGH class) and the optional quantize-at-parse behavior.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from irp_shared.calc.parse import parse_strict_decimal


class _Boom(Exception):
    """Stand-in for a binder value-error class."""


def test_finite_values_parse_and_optionally_quantize() -> None:
    assert parse_strict_decimal("300.330219", error=_Boom) == Decimal("300.330219")
    assert parse_strict_decimal(Decimal("1.5"), error=_Boom) == Decimal("1.5")
    # quantize-at-parse (the BT-1 echo-pinning pattern): HALF_UP at the supplied quantum.
    q = Decimal("0.000001")
    assert parse_strict_decimal("1.0000005", error=_Boom, quantum=q) == Decimal("1.000001")
    assert str(parse_strict_decimal("2", error=_Boom, quantum=q)) == "2.000000"


@pytest.mark.parametrize("raw", ["NaN", "-NaN", "Infinity", "-Infinity", "sNaN"])
def test_non_finite_is_refused_with_the_family_error(raw: str) -> None:
    with pytest.raises(_Boom) as exc:
        parse_strict_decimal(raw, error=_Boom, field="var_value")
    assert "var_value" in str(exc.value) and "finite" in str(exc.value)


@pytest.mark.parametrize("raw", ["garbage", "", None, object()])
def test_unparseable_is_refused_with_the_family_error(raw: object) -> None:
    with pytest.raises(_Boom) as exc:
        parse_strict_decimal(raw, error=_Boom, field="weight")
    assert "weight" in str(exc.value) and "parseable" in str(exc.value)


def test_nan_decimal_instance_is_refused_too() -> None:
    # a Decimal("NaN") OBJECT (not string) must not sneak past the isinstance fast path.
    with pytest.raises(_Boom):
        parse_strict_decimal(Decimal("NaN"), error=_Boom)


def test_finite_but_unquantizable_magnitude_is_refused_not_500(  # review fold (finder 3)
) -> None:
    # 1E+40 is finite and parseable, but quantizing to 6dp needs 46 digits > the default 28-digit
    # context → InvalidOperation AT quantize. That must be the family 422 error, not an escape.
    with pytest.raises(_Boom) as exc:
        parse_strict_decimal("1E+40", error=_Boom, field="var_value", quantum=Decimal("0.000001"))
    assert "column scale" in str(exc.value)
