"""The DB-free liquidity kernel (LQ-1).

Reference values are hand-computed and stated in each test, per the gate commitment that reference
literals are independently computed rather than recorded from a first run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from irp_shared.classification.models import LIQUIDITY_TIER_CODES
from irp_shared.liquidity.kernel import Atom, compute_liquidity
from irp_shared.liquidity.models import BUCKET_UNCLASSIFIED


def _d(v: str) -> Decimal:
    return Decimal(v)


def test_shares_are_taken_against_the_long_book_and_sum_to_one() -> None:
    """Hand-computed: long = 600 + 300 + 100 = 1000; the -50 short is EXCLUDED.

    illiquid 300/1000 = 0.3 · highly liquid 600/1000 = 0.6 · untiered 100/1000 = 0.1.
    """
    r = compute_liquidity(
        (
            Atom("a", _d("600"), "HIGHLY_LIQUID"),
            Atom("b", _d("300"), "ILLIQUID"),
            Atom("c", _d("100"), None),
            Atom("d", _d("-50"), "ILLIQUID"),
        )
    )
    assert r.total_long == _d("1000.000000")
    assert r.illiquid_share == _d("0.300000")
    assert r.highly_liquid_share == _d("0.600000")
    assert r.coverage_ratio == _d("0.900000")
    assert sum(b.tier_share for b in r.buckets) == _d("1.000000")


def test_a_short_position_never_reduces_the_illiquid_share() -> None:
    """The LONG predicate is by VALUE SIGN. Netting a short against a long would let a book hide
    illiquidity by adding shorts — so the short must be invisible, not subtracted."""
    longs_only = compute_liquidity((Atom("a", _d("100"), "ILLIQUID"),))
    with_short = compute_liquidity(
        (Atom("a", _d("100"), "ILLIQUID"), Atom("b", _d("-90"), "HIGHLY_LIQUID"))
    )
    assert longs_only.illiquid_share == with_short.illiquid_share == _d("1.000000")


def test_every_declared_tier_is_emitted_even_at_zero() -> None:
    """A vector with holes is not a vector: a reader must be able to tell 'no illiquid holdings'
    from 'the illiquid bucket was never computed'."""
    r = compute_liquidity((Atom("a", _d("100"), "HIGHLY_LIQUID"),))
    codes = [b.bucket_code for b in r.buckets]
    assert codes == [*LIQUIDITY_TIER_CODES, BUCKET_UNCLASSIFIED]
    assert r.illiquid_share == _d("0.000000")


def test_untiered_exposure_stays_in_the_denominator() -> None:
    """The ratified OQ-LQ-1-19 semantics. Dropping the residual would SHRINK the denominator and
    inflate every reported share — the failure CON-1 recorded and this family inherits."""
    r = compute_liquidity(
        (Atom("a", _d("50"), "ILLIQUID"), Atom("b", _d("50"), None)),
    )
    # 50/100, NOT 50/50.
    assert r.illiquid_share == _d("0.500000")
    assert r.coverage_ratio == _d("0.500000")
    assert r.untiered_instrument_count == 1
    # NOT a gap: an untiered holding is a normal state of the book. Refusal is the declared
    # coverage FLOOR's job, enforced in the binder. An earlier draft returned a gap here, and
    # because the binder refuses on ANY gap, every book with one unassessed holding FAILED.
    assert r.gaps == ()


def test_a_fully_untiered_book_reports_zero_coverage_and_does_not_divide_by_zero() -> None:
    """Coverage 0 is the floor's whole purpose: the binder must be able to SEE an ungoverned book
    rather than receive a confident 0% illiquid."""
    r = compute_liquidity((Atom("a", _d("100"), None), Atom("b", _d("40"), None)))
    assert r.coverage_ratio == _d("0.000000")
    assert r.illiquid_share == _d("0.000000")
    assert r.untiered_instrument_count == 2
    # Still not a gap even at zero coverage — the binder's floor is what refuses this book, and
    # it must be able to SEE coverage 0.0 in order to do so.
    assert r.gaps == ()
    assert r.coverage_ratio == _d("0.000000")


def test_an_empty_or_wholly_short_book_is_a_structured_gap_not_a_division() -> None:
    for atoms in ((), (Atom("a", _d("-10"), "ILLIQUID"),)):
        r = compute_liquidity(atoms)
        assert r.total_long == _d("0")
        assert r.gaps, "a 0/0 book must report a gap for the binder to refuse on"
        assert r.buckets == ()


def test_untiered_count_is_by_INSTRUMENT_not_by_atom() -> None:
    """One instrument appearing in several pinned atoms is ONE data-quality problem, not three.
    Counting atoms would overstate the size of the gap in exactly the reports meant to size it."""
    r = compute_liquidity(
        (
            Atom("same", _d("10"), None),
            Atom("same", _d("20"), None),
            Atom("other", _d("30"), None),
        )
    )
    assert r.untiered_instrument_count == 2


@pytest.mark.parametrize(
    ("amount", "expected"),
    [("1", "0.333333"), ("2", "0.666667")],
)
def test_shares_round_half_up_at_six_places(amount: str, expected: str) -> None:
    """1/3 and 2/3 against a 3-unit book — the platform's ROUND_HALF_UP 6dp convention."""
    r = compute_liquidity(
        (Atom("a", _d(amount), "ILLIQUID"), Atom("b", _d(str(3 - int(amount))), "HIGHLY_LIQUID"))
    )
    assert r.illiquid_share == _d(expected)


# --- the staleness refusal (ratified OQ-LQ-1-9 arm C) ---


class _StubComponent:
    """A pinned component with only what ``_parse_pins`` reads."""

    def __init__(self, kind: str, content: str, stamped: object) -> None:
        self.component_kind = kind
        self.captured_content = content
        self.pinned_system_from = stamped


def _assignment_content(instrument: str, tier: str) -> str:
    import json

    return json.dumps(
        {
            "id": "x",
            "entity_id": instrument,
            "entity_type": "instrument",
            "dimension_kind": "LIQUIDITY_TIER",
            "basis": "NOT_APPLICABLE",
            "node_code": tier,
            "scheme_id": "s",
            "tenant_id": "t",
            "closure": [{"code": tier, "level": 1}],
        }
    )


def test_the_staleness_probe_reads_the_component_column_not_the_json() -> None:
    """The defect four review lanes found INDEPENDENTLY.

    The first implementation read ``content["system_from"]``. The assignment serializer emits nine
    keys and that is not one of them, so ``oldest_assignment_at`` was always None, the guard never
    entered its body, and the ratified staleness refusal was STRUCTURALLY UNFIREABLE — while a
    registered model limitation told every reader the platform would refuse a stale ladder. An
    end-to-end probe ran a 3,650-day-old ladder against a declared 31-day bound and it COMPLETED.

    This asserts the parse reads ``pinned_system_from``, which is a COLUMN on the component and is
    not an input to the content hash — so reading it moves no historical pin.
    """
    from datetime import UTC, datetime, timedelta

    from irp_shared.liquidity.service import _parse_pins

    old = datetime.now(UTC) - timedelta(days=400)
    pinned = _parse_pins(
        [_StubComponent("CLASSIFICATION", _assignment_content("i1", "ILLIQUID"), old)]
    )
    assert pinned.oldest_assignment_at == old, "the probe read nothing — the refusal is dead again"
    assert pinned.tier_by_instrument == {"i1": "ILLIQUID"}
    assert pinned.undateable_assignments == 0


def test_a_component_with_no_clock_REFUSES_rather_than_reading_as_fresh() -> None:
    """Unknown age is not freshness. A component carrying no clock must make the binder refuse."""
    from irp_shared.liquidity.service import _parse_pins

    pinned = _parse_pins(
        [_StubComponent("CLASSIFICATION", _assignment_content("i1", "ILLIQUID"), None)]
    )
    assert pinned.undateable_assignments == 1
    assert pinned.oldest_assignment_at is None
