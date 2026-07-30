"""The DB-free concentration kernel (CON-1, OQ-CON-1-1…5).

Pure functions over SIGNED exposure atoms. The ratified semantics, in one place:

- **The LONG predicate:** long = atoms with ``exposure_amount > 0``; short = ``< 0``; zero atoms
  contribute nothing. No long/short decomposition exists upstream — the kernel computes it, and
  the decomposition is BY VALUE SIGN, not by position direction (a negative captured mark reads
  as short; declared in the registered assumptions).
- **The share:** ``share_invested_long(bucket) = bucket long / Σ long`` — one share, one basis
  (``INVESTED_LONG``); deliberately NOT any regulatory ratio.
- **Per-dimension residuals (OQ-CON-1-4):** for ISSUER, no issuer edge ⇒ UNCLASSIFIABLE; for
  classification dimensions an existing assignment ALWAYS classifies, UNCLASSIFIABLE means "no
  assignment AND no issuer edge to inherit one through". Residuals stay IN the share denominator
  and OUT of the rankings and HHI.
- **HHI over the CLASSIFIED buckets only**, fraction scale, with the tolerance identity
  ``abs(HHI − Σ_classified shareᵢ²) ≤ N_classified·10⁻⁶`` (OQ-CON-1-3).
- **Coverage pair per dimension:** ``coverage_ratio = classified / total``;
  ``coverage_classifiable = classified / (classified + UNCLASSIFIED)`` — the 0/0 book is a
  structured gap, never a division.

The kernel RETURNS structured gaps; refusal handling (post-build ``gaps`` → FAILED run) is the
binder's job. Everything here must reproduce the CON-1 record Part 2 literals exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from irp_shared.concentration.models import (
    BUCKET_UNCLASSIFIABLE,
    BUCKET_UNCLASSIFIED,
)

_ZERO = Decimal("0")
_Q6 = Decimal("0.000001")

#: CR-N cardinality is part of the metric IDENTITY (``CR_5_*``), a declared model parameter.
CR_N = 5

GAP_ZERO_INVESTED_LONG = "ZERO_INVESTED_LONG"
GAP_ALL_UNCLASSIFIABLE = "ALL_UNCLASSIFIABLE"
GAP_COVERAGE_BELOW_FLOOR = "COVERAGE_BELOW_FLOOR"
#: A DEFENCE, not a computed outcome: pinned content that violates an invariant the build already
#: enforces (a closure with no level-1 ancestor; a missing or unparseable field — the except
#: tuple covers KeyError/TypeError as well as ValueError, the shapes corrupt JSON actually
#: takes). Raised nowhere — the binder converts such breaches into this gap so the run commits
#: FAILED instead of orphaning in RUNNING (the scaffold calls compute() outside its only try).
GAP_CORRUPT_PINNED_CONTENT = "CORRUPT_PINNED_CONTENT"


def _q6(value: Decimal) -> Decimal:
    return value.quantize(_Q6, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Atom:
    """One pinned exposure atom, already resolved to its per-dimension bucket.

    ``bucket_code`` is the REAL bucket (node code / issuer-id string) or None when the atom is
    residual for this dimension; ``residual_kind`` then says which residual.
    """

    exposure_amount: Decimal
    bucket_code: str | None
    residual_kind: str | None = None  # BUCKET_UNCLASSIFIED | BUCKET_UNCLASSIFIABLE


@dataclass(frozen=True)
class Bucket:
    bucket_code: str
    is_residual: bool
    gross_amount: Decimal
    long_amount: Decimal
    short_amount: Decimal
    net_amount: Decimal
    share_invested_long: Decimal


@dataclass(frozen=True)
class DimensionResult:
    buckets: tuple[Bucket, ...]
    total_long: Decimal
    coverage_ratio: Decimal
    coverage_classifiable: Decimal
    max_share: Decimal
    hhi: Decimal
    cr_n: Decimal
    gaps: tuple[str, ...] = field(default_factory=tuple)


def decompose(atoms: list[Atom]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(gross, long, short, net) over the signed atoms — the pinned LONG predicate."""
    gross = sum((abs(a.exposure_amount) for a in atoms), _ZERO)
    long = sum((a.exposure_amount for a in atoms if a.exposure_amount > _ZERO), _ZERO)
    short = sum((a.exposure_amount for a in atoms if a.exposure_amount < _ZERO), _ZERO)
    net = sum((a.exposure_amount for a in atoms), _ZERO)
    return gross, long, short, net


def compute_dimension(atoms: list[Atom], coverage_floor: Decimal) -> DimensionResult:
    """One dimension's buckets, shares, coverage pair, and summary metrics — or its gaps.

    ``atoms`` carry this dimension's bucketing already resolved (the binder walks assignments /
    the issuer edge; the kernel never touches the DB).
    """
    total_gross, total_long, total_short, total_net = decompose(atoms)
    if total_long <= _ZERO:
        return DimensionResult(
            buckets=(),
            total_long=total_long,
            coverage_ratio=_ZERO,
            coverage_classifiable=_ZERO,
            max_share=_ZERO,
            hhi=_ZERO,
            cr_n=_ZERO,
            gaps=(GAP_ZERO_INVESTED_LONG,),
        )

    grouped: dict[tuple[str, bool], list[Atom]] = {}
    for a in atoms:
        if a.bucket_code is not None:
            key = (a.bucket_code, False)
        else:
            if a.residual_kind not in (BUCKET_UNCLASSIFIED, BUCKET_UNCLASSIFIABLE):
                raise ValueError("an atom with no bucket_code must carry a declared residual_kind")
            key = (a.residual_kind, True)
        grouped.setdefault(key, []).append(a)

    buckets: list[Bucket] = []
    raw_classified_shares: list[Decimal] = []
    for (code, is_residual), members in sorted(grouped.items()):
        gross, long, short, net = decompose(members)
        raw_share = long / total_long
        if not is_residual:
            raw_classified_shares.append(raw_share)
        buckets.append(
            Bucket(
                bucket_code=code,
                is_residual=is_residual,
                gross_amount=_q6(gross),
                long_amount=_q6(long),
                short_amount=_q6(short),
                net_amount=_q6(net),
                share_invested_long=_q6(raw_share),
            )
        )

    classified = [b for b in buckets if not b.is_residual]
    unclassified_long = sum(
        (b.long_amount for b in buckets if b.bucket_code == BUCKET_UNCLASSIFIED), _ZERO
    )
    classified_long = sum((b.long_amount for b in classified), _ZERO)

    coverage_ratio = _q6(classified_long / total_long)
    classifiable_long = classified_long + unclassified_long
    if classifiable_long <= _ZERO:
        # The 0/0 book (all-UNCLASSIFIABLE): nothing classifiable, no concentration to govern —
        # a structured gap, never a division (OQ-CON-1-4).
        return DimensionResult(
            buckets=tuple(buckets),
            total_long=_q6(total_long),
            coverage_ratio=coverage_ratio,
            coverage_classifiable=_ZERO,
            max_share=_ZERO,
            hhi=_ZERO,
            cr_n=_ZERO,
            gaps=(GAP_ALL_UNCLASSIFIABLE,),
        )
    coverage_classifiable = _q6(classified_long / classifiable_long)

    gaps: tuple[str, ...] = ()
    if coverage_classifiable < coverage_floor:
        gaps = (GAP_COVERAGE_BELOW_FLOOR,)

    # Rankings and HHI over the CLASSIFIED buckets only (a residual is not a concentration) —
    # computed from the UNROUNDED ratios then quantized (the OQ-CON-1-3 ratified convention:
    # 0.356057 from unrounded ratios vs 0.356058 from quantized shares; the identity against
    # stored shares carries the N-ulp tolerance for exactly this reason).
    shares = sorted(raw_classified_shares, reverse=True)
    max_share = _q6(shares[0]) if shares else _ZERO
    hhi = _q6(sum((s * s for s in shares), _ZERO))
    cr_n = _q6(sum(shares[:CR_N], _ZERO))

    return DimensionResult(
        buckets=tuple(buckets),
        total_long=_q6(total_long),
        coverage_ratio=coverage_ratio,
        coverage_classifiable=coverage_classifiable,
        max_share=max_share,
        hhi=hhi,
        cr_n=cr_n,
        gaps=gaps,
    )
