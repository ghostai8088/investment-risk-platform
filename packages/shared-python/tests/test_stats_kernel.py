"""RM-1 OD-RM-1-M — the domain-neutral estimator lift, pinned.

``mean_return``/``sample_stdev`` were born inside ``benchmark_relative_kernel`` (P3-8) and had
already been borrowed cross-family by ``desmoothing_service`` (DS-2) before RM-1 became the third
consumer. The lift moves ONE implementation into ``perf/stats_kernel.py`` with a neutral error
class and neutral messages, and leaves each family re-wrapping at its own boundary.

A refactor of a SHIPPED governed estimator is only safe if it provably changed no value, so these
tests pin three things: the exact outputs on fixed vectors (values already asserted by P3-8's own
suite, restated here against the neutral module), the bit-identity of the delegating path, and the
error-contract split — neutral errors from the neutral module, family errors at the family
boundary, with P3-8's shipped message text unchanged.
"""

from __future__ import annotations

import statistics
from decimal import Decimal

import pytest

from irp_shared.perf.benchmark_relative_kernel import (
    BenchmarkRelativeKernelError,
)
from irp_shared.perf.benchmark_relative_kernel import (
    mean_return as br_mean_return,
)
from irp_shared.perf.benchmark_relative_kernel import (
    sample_stdev as br_sample_stdev,
)
from irp_shared.perf.stats_kernel import (
    StatsKernelError,
    mean_return,
    sample_stdev,
)

#: THE vector P3-8's own suite pins (`test_benchmark_relative.py::test_kernel_goldens_...`), copied
#: verbatim so the lift is checked against SHIPPED expectations rather than freshly-invented ones.
#: The active series of portfolio [0.03, -0.02, 0.01] vs benchmark [0.025, -0.015, 0.005].
_ACTIVE = [Decimal("0.005"), Decimal("-0.005"), Decimal("0.005")]


def test_the_lifted_estimators_reproduce_the_shipped_values_exactly() -> None:
    """The values P3-8 has been emitting since it shipped. If the lift moved a quantize boundary or
    changed the accumulation precision, these strings change."""
    assert str(mean_return(_ACTIVE)) == "0.001666666667"
    assert str(sample_stdev(_ACTIVE)) == "0.005773502692"


def test_the_delegating_boundary_is_bit_identical_to_the_neutral_module() -> None:
    """P3-8's functions are now thin wrappers. Equality of the Decimal is not enough — a differing
    exponent would still compare equal — so the STRING form is compared, which distinguishes
    ``0.005773502692`` from ``0.00577350269200``."""
    assert str(br_mean_return(_ACTIVE)) == str(mean_return(_ACTIVE))
    assert str(br_sample_stdev(_ACTIVE)) == str(sample_stdev(_ACTIVE))


def test_the_estimator_still_agrees_with_the_stdlib() -> None:
    """An independent check that the n-1 denominator and arithmetic centring survived the move."""
    floats = [float(v) for v in _ACTIVE]
    assert abs(float(sample_stdev(_ACTIVE)) - statistics.stdev(floats)) < 1e-9
    assert abs(float(mean_return(_ACTIVE)) - statistics.fmean(floats)) < 1e-9


def test_a_constant_series_has_zero_dispersion_not_an_error() -> None:
    """Zero is a LEGITIMATE value here — which is exactly why RM-1's result table cannot use 0 as a
    suppression sentinel (the ENT-064 nullable-value design)."""
    assert sample_stdev([Decimal("0.01")] * 5) == Decimal("0.000000000000")


# --- the error-contract split ---------------------------------------------------------------


def test_the_neutral_module_raises_a_neutral_error_naming_no_metric() -> None:
    """The whole point of the lift: RM-1 must not receive an exception that talks about *tracking
    error* over *sub-period observations* — a metric it does not compute, on a grain it has
    deliberately abandoned."""
    with pytest.raises(StatsKernelError) as caught:
        sample_stdev([Decimal("0.01")])
    message = str(caught.value)
    assert "needs >= 2 observations" in message
    for foreign in ("tracking", "sub-period", "active", "benchmark"):
        assert foreign not in message.lower()

    with pytest.raises(StatsKernelError) as empty:
        mean_return([])
    assert "empty series" in str(empty.value)


def test_p3_8_keeps_its_own_error_type_and_its_shipped_message_verbatim() -> None:
    """The lift must be invisible to P3-8's callers and tests: same exception TYPE, same text."""
    with pytest.raises(BenchmarkRelativeKernelError) as caught:
        br_sample_stdev([Decimal("0.01")])
    assert str(caught.value) == "tracking error needs >= 2 sub-period observations (got 1)"

    with pytest.raises(BenchmarkRelativeKernelError) as empty:
        br_mean_return([])
    assert str(empty.value) == "no values to average"


def test_the_neutral_error_is_not_an_arithmetic_error() -> None:
    """Deliberate (see the module docstring): DS-2's ``except ArithmeticError`` idiom must NOT
    swallow a structural input error and turn it into a silent suppression. Structural errors are
    the binder's job to prevent, not the caller's to absorb."""
    assert issubclass(StatsKernelError, ValueError)
    assert not issubclass(StatsKernelError, ArithmeticError)


def test_desmoothing_no_longer_borrows_the_benchmark_relative_kernel() -> None:
    """The cross-family borrow the lift exists to remove — pinned so it cannot come back."""
    import ast
    import pathlib

    import irp_shared.perf.desmoothing_service as ds

    tree = ast.parse(pathlib.Path(ds.__file__).read_text())
    borrowed = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and "benchmark_relative" in node.module
    ]
    assert borrowed == [], f"desmoothing_service still borrows: {borrowed}"


def test_the_rewrap_diagnoses_an_OVERFLOW_correctly_not_as_a_sample_size_error() -> None:
    """``StatsKernelError`` covers BOTH the structural n<2 case and a quantize-magnitude overflow,
    so a blanket re-wrap misdiagnosed the latter as "tracking error needs >= 2 sub-period
    observations (got 2)" — self-contradictory, since there ARE two.

    It matters beyond tidiness: P3-8's binder PERSISTS this string into committed DQ gap evidence,
    so an extreme-pin FAILED run would have committed a lying explanation of its own failure.
    """
    huge = [Decimal("9.9E+48"), Decimal("-9.9E+48")]
    with pytest.raises(BenchmarkRelativeKernelError) as caught:
        br_sample_stdev(huge)
    assert str(caught.value) == "result magnitude out of range"
    assert "sub-period observations" not in str(caught.value)

    # ...and the structural case still reports the structural message, unchanged.
    with pytest.raises(BenchmarkRelativeKernelError) as small:
        br_sample_stdev([Decimal("0.01")])
    assert str(small.value) == "tracking error needs >= 2 sub-period observations (got 1)"
