"""SQLite-local unit/behavior tests for ES-1 parametric Expected Shortfall (the 14th governed
number; ENT-027 `var_result`'s 5th realization — `ES_PARAMETRIC`, NO migration).

**The registered constants ARE this slice**, so they are the subject of the heaviest tests here:
`k_c` is re-derived BYTE-EXACTLY with `z` inverted IN-TEST by bisection (a tolerance check against
the pre-rounded registered `z` cannot pin the 12th dp — its noise floor exceeds the quantum), plus
an INDEPENDENT tail-integration leg that checks the FORMULA rather than the transcription (the
two-leg discipline of `test_var.py`'s z test). The `ES_97.5/VaR_99` invariant is asserted where it
is genuinely exact and genuinely portfolio-independent — at the CONSTANTS level, with no fixture —
and only quantum-bounded on the persisted rows (sigma cancels in exact arithmetic ONLY; two
independently 6dp-quantized rows do not preserve the ratio — the `test_var.py:211` lesson).

Also here: the hand-reference ES goldens through the full governed consume path (sigma = 500 and
sigma = 7 EXACTLY — `test_var.py`'s rational constructions, reused so the ES golden inherits an
exact sigma); the CONFIDENCE-convention golden (`ES_c = VaR_99` at c = 0.974232 — the one test
that fails if the convention silently flips to the tail-probability reading); the declared
`es_multiplier` identity gate; the plain/total byte-exact INVARIANCE regression (the dispatch grew
two branches — OD-ES-1-G's central claim); the deliberate backtest fence (OD-ES-1-F); and the
ES-total leg over the PA-4 chain (in `test_var_total.py`, which owns that chain's fixtures).
"""

from __future__ import annotations

import math
import uuid
from decimal import ROUND_HALF_UP, Decimal, localcontext
from statistics import NormalDist

import pytest
from sqlalchemy.orm import Session

from irp_shared.risk.bootstrap import (
    ES_METHODOLOGY_REF,
    ES_MODEL_CODE,
    ES_VERSION_LABEL,
    VAR_ES_MULTIPLIERS,
    VAR_Z_SCORES,
    WrongModelVersionError,
    declared_es_multiplier,
    register_var_parametric_es_model,
)
from irp_shared.risk.es_kernel import EsKernelError, compute_parametric_es
from irp_shared.risk.events import METRIC_TYPE_ES_PARAMETRIC, METRIC_TYPES

# ---------------------------------------------------------------------------------------------
# (1) THE CONSTANTS — the deliverable. Byte-exact, two independent legs, no tolerance.
# ---------------------------------------------------------------------------------------------

_Q12 = Decimal("1E-12")
#: prec 40 with 100 bisection steps resolves z to ~2e-30 (the interval halves from 10, so 100
#: steps give 10/2^100 ~ 8e-30, floored by the prec-40 arithmetic). k's sensitivity is
#: dk/dz = -z*phi(z)/(1-c), which is 3.4-6.2 across the vocabulary, so k resolves to ~1e-29 —
#: about 17 orders of headroom over the 1e-12 quantum being pinned, and the nearest 12dp
#: rounding boundary is >=3e-13 away (a ~1e15x safety factor). Fast enough for `make check`.
#: (The first draft of this comment claimed "~20 orders" from a stated "~1e-25" resolution —
#: which does not even follow from its own premises (6 * 1e-25 -> ~12 orders). Corrected at the
#: ES-1 numeric review: this slice struck an over-claim of exactly this class in OD-B, and it
#: would be absurd for the comment justifying the precision of the test that pins the constants
#: to be the one place the over-claiming survived.)
_PREC = 40
_BISECT_STEPS = 100


def _pi(prec: int = _PREC) -> Decimal:
    """pi via Machin's formula — `decimal` ships none (which is itself part of OD-ES-1-B's
    rationale), and the test must not borrow `math.pi` (float, ~16 digits: too coarse to pin
    12dp). Cached: it is a constant, and recomputing it per call dominated the runtime."""
    cached = _PI_CACHE.get(prec)
    if cached is not None:
        return cached
    with localcontext() as ctx:
        ctx.prec = prec + 10

        def atan_inv(x: int) -> Decimal:
            xd = Decimal(x)
            term = 1 / xd
            total = term
            n = 1
            sign = -1
            while True:
                n += 2
                term = term / (xd * xd)
                delta = term / n
                if delta == 0:
                    break
                total += sign * delta
                sign = -sign
            return total

        value = +(16 * atan_inv(5) - 4 * atan_inv(239))
    _PI_CACHE[prec] = value
    return value


_PI_CACHE: dict[int, Decimal] = {}


def _phi(z: Decimal, prec: int = _PREC) -> Decimal:
    """The standard-normal PDF in Decimal. Test-local by design: the SHIPPED code computes no
    normal function of any kind (that is the whole point of registering k_c), so the check must
    bring its own."""
    with localcontext() as ctx:
        ctx.prec = prec
        return +((-z * z / 2).exp() / (2 * _pi(prec)).sqrt())


def _erf(z: Decimal, prec: int = _PREC) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = prec + 15
        total = Decimal(0)
        fact = Decimal(1)
        n = 0
        while n < 200:
            term = Decimal((-1) ** n) * z ** (2 * n + 1) / (fact * (2 * n + 1))
            total += term
            if n > 5 and abs(term) < Decimal(10) ** -(prec + 5):
                break
            n += 1
            fact *= n
        return +(2 / _pi(prec).sqrt() * total)


def _Phi(z: Decimal, prec: int = _PREC) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = prec
        return +((1 + _erf(z / Decimal(2).sqrt(), prec)) / 2)


def _inv_Phi(c: Decimal, prec: int = _PREC) -> Decimal:
    """Invert Phi by bisection IN-TEST. This is the load-bearing detail: feeding the registered
    12dp z back in would inject dk = -z*phi(z)*dz/(1-c) — a ~2e-12 noise floor, TWICE the 1e-12
    quantum the assertion exists to guard, and no tolerance then both passes the true constant and
    catches a last-digit typo."""
    with localcontext() as ctx:
        ctx.prec = prec
        lo, hi = Decimal(0), Decimal(10)
        for _ in range(_BISECT_STEPS):
            mid = (lo + hi) / 2
            if _Phi(mid, prec) < c:
                lo = mid
            else:
                hi = mid
        return +((lo + hi) / 2)


def test_es_multipliers_are_byte_exact_from_first_principles() -> None:
    # LEG 1 of 2: k_c = phi(Phi^-1(c))/(1-c), with z derived here by bisection and pi by Machin.
    # BYTE-EXACT, no tolerance — the 12 registered digits are pinned exactly (cf. the z test's
    # own two-leg bisection+erf discipline, which this mirrors properly).
    assert set(VAR_ES_MULTIPLIERS) == {"0.9500", "0.9750", "0.9900"}
    for confidence_key, registered in VAR_ES_MULTIPLIERS.items():
        c = Decimal(confidence_key)
        z = _inv_Phi(c)
        k = _phi(z) / (1 - c)
        assert k.quantize(_Q12, rounding=ROUND_HALF_UP) == Decimal(registered), confidence_key


def test_es_multipliers_match_an_independent_tail_integration() -> None:
    # LEG 2 of 2: the alpha-TAIL-MEAN INTEGRAL, computed by composite Simpson with NO closed form.
    # Leg 1 could only catch a transcription error; this one checks the FORMULA — it independently
    # confirms that k_c IS the tail mean (OD-ES-1-A's definitional claim), not merely asserted to
    # be. Float-precision, so tolerance-based: it is the formula check, not the digit check.
    for confidence_key, registered in VAR_ES_MULTIPLIERS.items():
        c = float(confidence_key)
        z_c = NormalDist().inv_cdf(c)
        upper = z_c + 40.0  # phi is ~1e-300 out here; the tail beyond is numerically nil
        n = 20_000  # even, for Simpson
        h = (upper - z_c) / n

        def integrand(x: float) -> float:
            return x * math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)

        total = integrand(z_c) + integrand(upper)
        for i in range(1, n):
            total += (4.0 if i % 2 else 2.0) * integrand(z_c + i * h)
        tail_mean = (h / 3.0) * total / (1.0 - c)
        assert abs(tail_mean - float(registered)) < 1e-9, confidence_key


def test_es_over_var_invariant_is_exact_at_the_constants_level() -> None:
    # OD-ES-1-E's invariant, asserted where it is TRUE: sigma cancels in EXACT arithmetic, so the
    # claim is about the CONSTANTS, not about any portfolio. No fixture — this is the point.
    #
    # It is deliberately NOT asserted row-wise: `var_value` and `sigma` are quantized to 6dp
    # INDEPENDENTLY and the rounding residuals do not cancel, so `ES_97.5/VaR_99 == <literal>` is
    # false at EVERY sigma (verified at planning: 0 hits in a 200,000-sigma scan; on this repo's
    # own sigma=500 fixture the row ratio is 1.004923991862..., not ...931). See
    # `test_var.py::test_es_dispatch_leaves_the_plain_var_row_byte_identical` for the honest
    # row-level form (a DERIVED quantum bound over real rows, never a bare `==` on the ratio).
    ratio = Decimal(VAR_ES_MULTIPLIERS["0.9750"]) / Decimal(VAR_Z_SCORES["0.9900"])
    assert ratio.quantize(_Q12, rounding=ROUND_HALF_UP) == Decimal("1.004923991931")


def test_es_exceeds_var_at_every_confidence() -> None:
    # k_c > z_c at every c — structurally guaranteed by the Mills-ratio inequality
    # phi(z)/(1-Phi(z)) > z, so this holds for ANY vocabulary we ever add, not just these three.
    for confidence_key, k in VAR_ES_MULTIPLIERS.items():
        assert Decimal(k) > Decimal(VAR_Z_SCORES[confidence_key]), confidence_key


def test_the_confidence_convention_is_pinned_by_the_crossover() -> None:
    # THE convention test (OD-ES-1-A). Every k*sigma golden in this file would still pass if the
    # convention silently flipped to the tail-probability reading; this one would not. ES_c meets
    # VaR_99 at c* = 0.974232 (6dp) — an identity of the CONFIDENCE reading only. Portfolio-
    # independent and free.
    #
    # Float via stdlib NormalDist here, deliberately: 6dp is far inside float's range, nesting a
    # Decimal bisection inside a Decimal bisection is ~44k erf evaluations for no added rigour,
    # and NormalDist.inv_cdf is Wichura AS241 — a genuinely DIFFERENT algorithm from the bisection
    # the byte-exact test above uses, so the two legs stay independent.
    z99 = float(VAR_Z_SCORES["0.9900"])

    def k_of(c: float) -> float:
        z = NormalDist().inv_cdf(c)
        return math.exp(-z * z / 2.0) / math.sqrt(2.0 * math.pi) / (1.0 - c)

    lo, hi = 0.90, 0.999
    for _ in range(200):
        mid = (lo + hi) / 2
        if k_of(mid) < z99:
            lo = mid
        else:
            hi = mid
    c_star = Decimal(repr((lo + hi) / 2))
    assert c_star.quantize(Decimal("1E-6"), rounding=ROUND_HALF_UP) == Decimal("0.974232")


def test_the_z_vocabulary_gained_only_0975_and_the_existing_entries_are_unmoved() -> None:
    # OD-ES-1-E's blast radius, pinned: the SHARED table gained exactly one entry and moved none.
    # (0.9750's z is auto-covered by test_var.py's erf/bisection loop over VAR_Z_SCORES.)
    assert VAR_Z_SCORES == {
        "0.9500": "1.644853626951",
        "0.9750": "1.959963984540",
        "0.9900": "2.326347874041",
    }


# ---------------------------------------------------------------------------------------------
# (2) THE KERNEL — pure, and deliberately trivial
# ---------------------------------------------------------------------------------------------


def test_kernel_is_the_multiplier_times_sigma() -> None:
    es = compute_parametric_es(Decimal(500), es_multiplier=Decimal(VAR_ES_MULTIPLIERS["0.9750"]))
    assert es == Decimal("2.337802792201") * Decimal(500)


def test_kernel_refuses_negative_sigma_and_non_positive_multiplier() -> None:
    # Defense-in-depth: binder-unreachable (sigma comes from a .sqrt(), k from the registered
    # table), so these are unit-tested standalone — the PA-4 defensive-gate precedent.
    with pytest.raises(EsKernelError) as e1:
        compute_parametric_es(Decimal("-1"), es_multiplier=Decimal(2))
    assert e1.value.reason == "negative-sigma"
    with pytest.raises(EsKernelError) as e2:
        compute_parametric_es(Decimal(1), es_multiplier=Decimal(0))
    assert e2.value.reason == "non-positive-multiplier"


def test_kernel_is_exact_at_zero_sigma() -> None:
    assert compute_parametric_es(Decimal(0), es_multiplier=Decimal(2)) == Decimal(0)


# ---------------------------------------------------------------------------------------------
# (3) THE DECLARED-PARAMETER IDENTITY (OD-ES-1-B)
# ---------------------------------------------------------------------------------------------


def _es_model(
    db: Session, tenant: str, code_version: str = "risk-v1", confidence: str = "0.975"
) -> str:
    return register_var_parametric_es_model(
        db,
        tenant_id=tenant,
        actor_id="analyst",
        code_version=code_version,
        confidence_level=confidence,
    ).id


def test_es_model_declares_its_multiplier_and_it_is_identity_checked(session: Session) -> None:
    from irp_shared.model.models import ModelVersion

    tenant = str(uuid.uuid4())
    mv_id = _es_model(session, tenant, confidence="0.975")
    version = session.get(ModelVersion, mv_id)
    assert version is not None
    assert version.methodology_ref == ES_METHODOLOGY_REF
    assert version.version_label == ES_VERSION_LABEL
    k = declared_es_multiplier(session, version, code=ES_MODEL_CODE)
    assert k == Decimal("2.337802792201")


def test_off_vocabulary_confidence_refuses(session: Session) -> None:
    tenant = str(uuid.uuid4())
    # 0.98 is unregistered. NOTE 0.975 is NOT the probe here — ES-1 admitted it (OQ-ES-1-4).
    with pytest.raises(ValueError):
        _es_model(session, tenant, confidence="0.98")
    with pytest.raises(ValueError):
        _es_model(session, tenant, confidence="0.94995")  # near-vocabulary: refused, not coerced
    with pytest.raises(ValueError):
        _es_model(session, tenant, confidence="abc")  # malformed: ValueError, never a crash


def test_tampered_absent_or_duplicated_multiplier_refuses_not_500(session: Session) -> None:
    # THE identity gate, against the REAL threat model (the P3-4 lesson, mirroring
    # `test_var.py::test_malformed_declared_parameters_refused_not_500`): an ES version minted via
    # the GENERIC registration path — same permission, arbitrary assumptions — must not be able to
    # pair one confidence with another's multiplier and emit a governed number that is neither.
    #
    # NOTE the assumptions are minted wrong at CREATION, never mutated: `model_assumption` is
    # append-only (AUD-01), so a "tamper the row" test would fail on the audit guard rather than
    # on the gate under test — and a real attacker mints, they do not UPDATE.
    from irp_shared.model.models import ModelVersion
    from irp_shared.model.service import register_model, register_model_version

    tenant = str(uuid.uuid4())
    model = register_model(
        session,
        tenant_id=tenant,
        code=ES_MODEL_CODE,
        name="generic",
        model_type="VAR",
        actor_id="a",
    )
    z975 = VAR_Z_SCORES["0.9750"]
    z99 = VAR_Z_SCORES["0.9900"]
    k95 = VAR_ES_MULTIPLIERS["0.9500"]
    k975 = VAR_ES_MULTIPLIERS["0.9750"]
    cases = (
        # c=0.99 declared with the 0.95 multiplier — the headline: a number that is neither.
        (
            "v1",
            ["confidence_level=0.9900", "horizon_days=1", f"z_score={z99}", f"es_multiplier={k95}"],
        ),
        # ABSENT: no legitimate ungated ES version exists (contrast BT-2's grandfathered max-age).
        ("v2", ["confidence_level=0.9750", "horizon_days=1", f"z_score={z975}"]),
        # DUPLICATED: must refuse, never silently pick one (the sole_declared fail-OPEN trap).
        (
            "v3",
            [
                "confidence_level=0.9750",
                "horizon_days=1",
                f"z_score={z975}",
                f"es_multiplier={k975}",
                f"es_multiplier={k95}",
            ],
        ),
        # MALFORMED: a parse crash would be a 500; this must be a governed identity refusal.
        (
            "v4",
            ["confidence_level=0.9750", "horizon_days=1", f"z_score={z975}", "es_multiplier=abc"],
        ),
        # A plausible-looking but UNREGISTERED multiplier (hand-computed, 13dp) — refused: the
        # value must be the registered constant EXACTLY, not merely close.
        (
            "v5",
            [
                "confidence_level=0.9750",
                "horizon_days=1",
                f"z_score={z975}",
                "es_multiplier=2.3378027922014",
            ],
        ),
    )
    for label, assumptions in cases:
        version = register_model_version(
            session,
            model=model,
            version_label=label,
            actor_id="a",
            methodology_ref=ES_METHODOLOGY_REF,
            code_version="risk-v1",
            status="REGISTERED",
            assumptions=assumptions,
        )
        resolved = session.get(ModelVersion, version.id)
        assert resolved is not None
        with pytest.raises(WrongModelVersionError):
            declared_es_multiplier(session, resolved, code=ES_MODEL_CODE)


# ---------------------------------------------------------------------------------------------
# (4) THE RATIFIED SCOPE FENCE (OD-ES-1-F/G)
# ---------------------------------------------------------------------------------------------


def test_es_is_deliberately_absent_from_the_backtestable_vocabulary() -> None:
    # OD-ES-1-F is a DELIBERATE omission, so it gets a test — a future maintainer must not
    # "complete the vocabulary" here. The reason is FRTB precedent + parametric redundancy, NOT
    # non-elicitability (that claim is false — Acerbi-Szekely 2014; Fissler-Ziegel 2016).
    assert METRIC_TYPE_ES_PARAMETRIC not in METRIC_TYPES
