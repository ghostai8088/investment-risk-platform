"""The DB-free liquidity kernel (LQ-1).

Pure functions over SIGNED exposure atoms plus an instrument→tier map. The ratified semantics:

- **The LONG predicate**, identical to CON-1's: long = atoms with ``exposure_amount > 0``. The
  decomposition is BY VALUE SIGN, not by position direction. Reused rather than re-derived so two
  bucket-vector families cannot drift apart on what "invested long" means.
- **The share:** ``tier_share(tier) = tier long / Σ long``, basis ``INVESTED_LONG``.
- **The residual is UNCLASSIFIED** (ratified OQ-LQ-1-19): a pinned instrument with no current-head
  tier lands here, stays IN the denominator, and COUNTS toward the classifiable-coverage test — so
  it can trip the floor. There is deliberately NO UNCLASSIFIABLE bucket: unlike CON-1's issuer
  dimension, there is no upstream edge whose absence makes an instrument structurally
  unclassifiable. Every instrument CAN carry a tier; if it does not, that is a gap in the book, not
  a property of the instrument.
- **Coverage:** ``coverage_ratio = tiered long / total long``. Because every non-tiered atom is
  UNCLASSIFIED by construction, coverage_ratio IS the classifiable ratio here — CON-1's second
  coverage figure has no distinct meaning on this dimension, so it carries the classifiable AMOUNT
  instead of a second ratio, which is information the ratio alone cannot give.
- **The floor** is enforced by the BINDER, not here. The kernel reports; the caller refuses.

The kernel RETURNS structured gaps and never raises for data reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from irp_shared.classification.models import (
    LIQUIDITY_TIER_CODES,
    TIER_HIGHLY_LIQUID,
    TIER_ILLIQUID,
)
from irp_shared.liquidity.models import BUCKET_UNCLASSIFIED

#: The only bucket codes the emitted vector carries. Anything else is off-vocabulary.
_KNOWN_BUCKETS: frozenset[str] = frozenset({*LIQUIDITY_TIER_CODES, BUCKET_UNCLASSIFIED})

_ZERO = Decimal("0")
_Q6 = Decimal("0.000001")


def _q6(value: Decimal) -> Decimal:
    return value.quantize(_Q6, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Atom:
    """One pinned exposure atom. ``tier`` is None when the instrument carries no current head."""

    instrument_id: str
    exposure_amount: Decimal
    tier: str | None


@dataclass(frozen=True)
class TierBucket:
    bucket_code: str
    is_residual: bool
    long_amount: Decimal
    tier_share: Decimal


@dataclass(frozen=True)
class LiquidityBreakdown:
    buckets: tuple[TierBucket, ...]
    total_long: Decimal
    illiquid_share: Decimal
    highly_liquid_share: Decimal
    coverage_ratio: Decimal
    coverage_classifiable: Decimal
    untiered_instrument_count: int
    gaps: tuple[str, ...]


def compute_liquidity(atoms: tuple[Atom, ...]) -> LiquidityBreakdown:
    """Bucket the long book by liquidity tier and derive the two headline shares.

    Returns a breakdown with ``gaps`` populated instead of raising: an empty book and a wholly
    short book are both legitimate states of the world, and it is the binder's job to decide that
    they mean a FAILED run.
    """
    longs = [a for a in atoms if a.exposure_amount > _ZERO]
    total_long = sum((a.exposure_amount for a in longs), _ZERO)

    untiered_ids = {a.instrument_id for a in longs if a.tier is None}

    if total_long <= _ZERO:
        # No invested-long book: every share would be 0/0. A structured gap, never a division.
        return LiquidityBreakdown(
            buckets=(),
            total_long=_ZERO,
            illiquid_share=_ZERO,
            highly_liquid_share=_ZERO,
            coverage_ratio=_ZERO,
            coverage_classifiable=_ZERO,
            untiered_instrument_count=len(untiered_ids),
            gaps=("no invested-long exposure: every liquidity share would be 0/0",),
        )

    # An OFF-VOCABULARY tier code must never silently vanish. The emitted vector is fixed to the
    # declared ladder plus the residual, so a code outside that set would be summed into a bucket
    # nothing emits — deleting real long money from the vector while total_long still counted it,
    # so the shares would no longer sum to 1 and the illiquid share would be understated. Unknown
    # codes fold into UNCLASSIFIED (they are, by definition, not a tier this model knows) AND
    # raise a gap, so the run refuses rather than reporting a quietly wrong number.
    by_bucket: dict[str, Decimal] = {}
    off_vocabulary: set[str] = set()
    for atom in longs:
        code = atom.tier if atom.tier is not None else BUCKET_UNCLASSIFIED
        if code not in _KNOWN_BUCKETS:
            off_vocabulary.add(code)
            code = BUCKET_UNCLASSIFIED
        by_bucket[code] = by_bucket.get(code, _ZERO) + atom.exposure_amount

    # Every declared tier is emitted even at zero, so a reader can tell "no illiquid holdings" from
    # "the illiquid bucket was never computed". A vector with holes is not a vector.
    ordered = [*LIQUIDITY_TIER_CODES, BUCKET_UNCLASSIFIED]
    buckets = tuple(
        TierBucket(
            bucket_code=code,
            is_residual=code == BUCKET_UNCLASSIFIED,
            long_amount=_q6(by_bucket.get(code, _ZERO)),
            tier_share=_q6(by_bucket.get(code, _ZERO) / total_long),
        )
        for code in ordered
    )

    # POST-CONDITION: every long unit is in exactly one bucket. This is the invariant the
    # off-vocabulary defect broke, asserted structurally rather than trusted.
    bucketed = sum((b.long_amount for b in buckets), _ZERO)
    if bucketed != _q6(total_long):
        gaps_prefix = (
            f"bucket vector lost long money: bucketed {bucketed} != total {_q6(total_long)}"
        )
    else:
        gaps_prefix = ""

    tiered_long = sum(
        (b.long_amount for b in buckets if not b.is_residual),
        _ZERO,
    )
    coverage_ratio = _q6(tiered_long / total_long)

    def _share(code: str) -> Decimal:
        return next(b.tier_share for b in buckets if b.bucket_code == code)

    # NOTE, deliberately NOT a gap. An untiered instrument is a NORMAL state of the book — it is
    # the entire reason the UNCLASSIFIED residual and the coverage ratio exist. An earlier draft
    # returned it as a gap, and because the binder refuses on ANY gap, every book containing a
    # single unassessed holding FAILED: the coverage floor became unreachable and the residual
    # bucket became dead code. Found by running the demo stage, which is exactly the book this
    # would break. The count and the coverage ratio already carry the information; refusal is the
    # FLOOR's job, and the floor is a declared, versioned parameter rather than a hidden absolute.
    gaps: list[str] = []
    if off_vocabulary:
        gaps.append(
            f"pinned tier code(s) outside the declared ladder: {sorted(off_vocabulary)} — folded "
            f"into UNCLASSIFIED and refusing, because a code this model does not know cannot be "
            f"scored against a partition it is not in"
        )

    if gaps_prefix:
        gaps.insert(0, gaps_prefix)

    return LiquidityBreakdown(
        buckets=buckets,
        total_long=_q6(total_long),
        illiquid_share=_share(TIER_ILLIQUID),
        highly_liquid_share=_share(TIER_HIGHLY_LIQUID),
        coverage_ratio=coverage_ratio,
        coverage_classifiable=_q6(tiered_long),
        untiered_instrument_count=len(untiered_ids),
        gaps=tuple(gaps),
    )
