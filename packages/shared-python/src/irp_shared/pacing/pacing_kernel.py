"""Pure commitment-pacing kernel (CC-2, ENT-059 — the Takahashi-Alexander projection).

NO DB, NO I/O — the deterministic TA recursion over declared parameters + a pinned anchor state.
Per period t (t = fund AGE in ANNUAL periods), for t running FUTURE-ONLY from ``current_age + 1``
to ``L`` (realized history is NEVER re-projected — the anchor already nets it):

    C(t)   = RC(t) * Unfunded(t-1)                        (capital call: a scheduled fraction of
                                                            remaining uncalled commitment)
    RD(t)  = max(Y, (t / L) ** B)                         (distribution rate: the yield-floored
                                                            "bow" curve; RD(L) = max(Y, 1) = 1)
    D(t)   = RD(t) * NAV(t-1) * (1 + G)                   (distribution: the rate on grown NAV)
    NAV(t) = NAV(t-1) * (1 + G) + C(t) - D(t)             (value roll-forward)
    Unfunded(t) = Unfunded(t-1) - C(t)

Verified via reproduction (the primary JPM is gated — the AS-2014 precedent): R1 Jaeckel + R2
Tamarix concordant on the core recursion; the yield floor is R2's single equation-level route
(corroborated by R4's input list, absent from R1); R3 the structural attribution. The ADOPTED
``max(Y, (t/L)^B)`` grouping (vs ``max(Y, (t/L))^B`` — a paywalled-render ambiguity of the BT-3
'+1' class; the two coincide at t=L, diverge mid-life) is pinned by a discriminating golden.

**QUANTIZE-THEN-ROLL** (the value-affecting convention, verifier F6): each period's C/D/NAV is
quantized to the 6dp money quantum AS COMPUTED, and the next period rolls forward from the
QUANTIZED values — so the persisted rows satisfy ``NAV(t) = NAV(t-1)(1+G) + C(t) - D(t)`` EXACTLY
at 6dp (row-level re-auditability). Computed in ``Decimal`` at 50-digit context precision; the
``(t/L)**B`` power is deterministic for identical inputs+context (the spec grades non-integral
power "almost always correctly rounded" (<=1 ulp) — determinism, not correct rounding, is the
TR-09 requirement; the residual cross-library caveat is near-surely absorbed by the 6dp quantize).

The domain preconditions (L >= 1; B > 0; G > -1; each RC in [0,1]; 0 <= Y <= 1; the anchor
coherence) are the BINDER's PRE-create refusals; the kernel re-checks so the pure function is safe
standalone (defense-in-depth).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as dt_date
from decimal import ROUND_HALF_UP, Decimal, localcontext

#: Money quantum: HALF_UP to 6dp = the ``pacing_projection_result`` money-column
#: PreciseDecimal(28,6) scale. QUANTIZE-THEN-ROLL applies this to every persisted period value.
_MONEY_QUANTUM = Decimal(1).scaleb(-6)
#: Compute precision for the recursion + the power (the risk/perf kernel precedent).
_COMPUTE_PREC = 50


class PacingKernelError(ValueError):
    """Raised for an out-of-domain parameter or an incoherent anchor. Defense-in-depth: the binder
    adjudicates the declared params + pinned anchor PRE-create, making this unreachable through the
    governed path. Carries a stable ``reason`` slug for the binder's failure-reason mapping."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class PacingParams:
    """The five declared model parameters (the model version's identity). ``rc_schedule`` is the
    per-age call-rate tuple (the LAST value applies to all ages beyond its length); ``fund_life``
    is L in ANNUAL periods; ``bow`` is B; ``growth`` is per-period G; ``yield_floor`` is Y."""

    rc_schedule: tuple[Decimal, ...]
    fund_life: int
    bow: Decimal
    growth: Decimal
    yield_floor: Decimal


@dataclass(frozen=True)
class PacingAnchor:
    """The projection-start state, all derived FROM THE PIN. ``current_age`` = complete ANNUAL
    periods elapsed from the commitment (vintage) date to the snapshot's pinned as-of — the
    deterministic age anchor (a wall-clock age would break pin-reproducibility). ``unfunded`` and
    ``nav`` are the coherent book state at that age (calls/distributions/recallable already netted;
    the latest pinned mark or 0 for a new commitment)."""

    current_age: int
    unfunded: Decimal
    nav: Decimal


@dataclass(frozen=True)
class PacingPeriod:
    """One projected future period. ``period_index`` = fund AGE (t), never a step counter."""

    period_index: int
    projected_call: Decimal
    projected_distribution: Decimal
    projected_nav: Decimal
    unfunded_end: Decimal


def _anniversary(vintage: dt_date, years: int) -> dt_date:
    """The ``years``-th anniversary of ``vintage``, clamping a Feb-29 vintage to Feb-28 in a
    non-leap target year (the deterministic leap-day convention)."""
    try:
        return vintage.replace(year=vintage.year + years)
    except ValueError:  # Feb 29 -> non-leap year
        return vintage.replace(year=vintage.year + years, day=28)


def anniversary_window(vintage: dt_date, age: int) -> tuple[dt_date, dt_date]:
    """The half-open anniversary window ``[vintage + (age-1) yr, vintage + age yr)`` for fund age
    ``t = age`` — the persisted ``period_start``/``period_end`` of an age-t projection row."""
    return (_anniversary(vintage, age - 1), _anniversary(vintage, age))


def _rc_for_age(rc_schedule: Sequence[Decimal], age: int) -> Decimal:
    """RC(age): the schedule position by AGE (1-indexed), the last value applying to later ages."""
    idx = min(age, len(rc_schedule)) - 1
    return rc_schedule[idx]


def _q(value: Decimal) -> Decimal:
    """Quantize a money value HALF_UP to 6dp; normalize -0 -> +0 (the PreciseDecimal convention)."""
    out = value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return out if out != 0 else Decimal("0.000000")


def project_commitment(params: PacingParams, anchor: PacingAnchor) -> tuple[PacingPeriod, ...]:
    """Project future periods ``t = current_age + 1 .. L``. Returns an empty tuple ONLY if the
    caller passes ``current_age >= L`` (the binder refuses that PRE-create — "nothing to project");
    the kernel returns ``()`` rather than raising so the pure function is total on a coherent
    domain.
    """
    _validate(params, anchor)
    with localcontext() as ctx:
        ctx.prec = _COMPUTE_PREC
        one = Decimal(1)
        gross = one + params.growth  # (1 + G)
        life = Decimal(params.fund_life)
        unfunded = anchor.unfunded
        nav = anchor.nav
        rows: list[PacingPeriod] = []
        for t in range(anchor.current_age + 1, params.fund_life + 1):
            rc = _rc_for_age(params.rc_schedule, t)
            call = _q(rc * unfunded)
            # RD(t) = max(Y, (t/L)^B) — the adopted grouping (max over the powered fraction).
            frac_pow = (Decimal(t) / life) ** params.bow
            rd = params.yield_floor if params.yield_floor > frac_pow else frac_pow
            grown_nav = nav * gross
            dist = _q(rd * grown_nav)
            # Quantize-then-roll: NAV(t) rolls from the QUANTIZED call/dist over the (already
            # exact-in-Decimal) grown NAV, then itself quantizes — so the persisted identity
            # NAV(t) = quantize(NAV(t-1)(1+G)) ... holds. Grow on the quantized prior NAV.
            nav = _q(grown_nav + call - dist)
            unfunded = _q(unfunded - call)
            rows.append(
                PacingPeriod(
                    period_index=t,
                    projected_call=call,
                    projected_distribution=dist,
                    projected_nav=nav,
                    unfunded_end=unfunded,
                )
            )
    return tuple(rows)


def _validate(params: PacingParams, anchor: PacingAnchor) -> None:
    if params.fund_life < 1:
        raise PacingKernelError(
            f"fund_life must be >= 1 (got {params.fund_life})", reason="FUND_LIFE_DOMAIN"
        )
    if not params.rc_schedule:
        raise PacingKernelError("rc_schedule must be non-empty", reason="RC_SCHEDULE_EMPTY")
    if len(params.rc_schedule) > params.fund_life:
        raise PacingKernelError("rc_schedule length exceeds fund_life", reason="RC_SCHEDULE_LENGTH")
    for rate in params.rc_schedule:
        if not rate.is_finite() or rate < 0 or rate > 1:
            raise PacingKernelError(
                f"each rc_schedule rate must be in [0,1] (got {rate})", reason="RC_RATE_DOMAIN"
            )
    if not params.bow.is_finite() or params.bow <= 0:
        raise PacingKernelError(f"bow must be > 0 (got {params.bow})", reason="BOW_DOMAIN")
    if not params.growth.is_finite() or params.growth <= -1:
        raise PacingKernelError(
            f"growth must be > -1 (got {params.growth})", reason="GROWTH_DOMAIN"
        )
    if not params.yield_floor.is_finite() or params.yield_floor < 0 or params.yield_floor > 1:
        raise PacingKernelError(
            f"yield_floor must be in [0,1] (got {params.yield_floor})", reason="YIELD_DOMAIN"
        )
    if anchor.current_age < 0:
        raise PacingKernelError(
            f"current_age must be >= 0 (got {anchor.current_age})", reason="AGE_DOMAIN"
        )
    for name, value in (("unfunded", anchor.unfunded), ("nav", anchor.nav)):
        if not value.is_finite() or value < 0:
            raise PacingKernelError(
                f"anchor {name} must be a finite non-negative Decimal (got {value})",
                reason="ANCHOR_DOMAIN",
            )
