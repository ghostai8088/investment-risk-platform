"""Parametric Expected Shortfall (ES-1, ENT-027 consumer — pure math, no I/O, no ORM).

Under the zero-mean delta-normal model the platform already ships, ES collapses to a multiple of
the SAME sigma the VaR leg computes:

    ES_c = k_c * sigma_p,   k_c := phi(Phi^-1(c)) / (1 - c)

with ``c`` the CONFIDENCE level (0.9750 -> tail mass 0.0250), losses loss-POSITIVE and zero-mean —
consistent with the shipped ``VaR_c = z_c * sigma_p``. This is the Landsman-Valdez (2003) elliptical
closed form at ``mu = 0``. The convention is pinned HERE and in ``bootstrap.VAR_ES_MULTIPLIERS``
because the recorded P3-5 seam (``ES = sigma*phi(z)/(1-alpha)``) never defined ``alpha`` and the
literature is genuinely split on that symbol (Acerbi-Tasche: TAIL probability; Gneiting:
CONFIDENCE). Do not rely on the symbol; rely on the definition above.

**This module is deliberately trivial, and that is the design.** ``k_c`` is a REGISTERED constant
from an enumerated vocabulary, so there is NO quantile function and NO runtime normal function of
ANY kind here — not the inverse CDF (barred since P3-5: capability-is-not-evidence) and not the
forward PDF phi. The tail arithmetic lives in the registered constant, under model governance,
where it is declared, versioned and reproducible; it does not live in code.

Definitional guard for later legs: ES is the alpha-TAIL-MEAN INTEGRAL, never ``E[L | L > VaR]``
(that is TCE, which is NOT coherent for discontinuous distributions — Acerbi-Tasche Example 5.4).
They coincide for continuous distributions (Cor. 5.3(i)), so the distinction costs nothing under
normality — but an ES-over-historical-simulation leg is discrete and MUST inherit the tail-mean
estimator. Concretely (Acerbi-Tasche 2002 Prop. 4.1), with ``a = 1-c`` the TAIL probability and
``L_(1) >= L_(2) >= ...`` the losses sorted worst-first::

    ES_a = ( SUM_{i <= floor(n*a)} L_(i) + (n*a - floor(n*a)) * L_(floor(n*a)+1) ) / (n*a)

— a FLOOR count plus a FRACTIONAL weight on the boundary observation. **It is NOT "the mean of the
worst ceil(n*a) losses"**: for an untied sample that quantity is exactly ``E[L | L >= VaR]``, i.e.
the TCE this guard forbids, and it UNDERSTATES ES whenever ``n*a`` is not an integer (~14% at
n=41 — this platform's own HS adequacy floor at c=0.975). The two coincide only when ``n*a`` is an
integer. Stating the estimator wrongly here would have handed the future HS leg the forbidden one.

Raw prec-50 out; the binder gates magnitudes and quantizes (``ES`` -> 6dp ``Numeric(28,6)``, the
base-currency scale). Fail-closed on a negative sigma or a non-positive multiplier — both are
DEFENSE-IN-DEPTH and binder-unreachable through the governed path (sigma comes from a ``.sqrt()``
and ``k`` from the registered vocabulary, whose declared-parameter identity is checked at bind);
kernel-unit-tested standalone, the PA-4 defensive-gate precedent.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

_CTX_PRECISION = 50


class EsKernelError(ValueError):
    """A structural ES failure (a negative sigma, a non-positive multiplier). The binder maps it to
    a post-create committed FAILED run (the DQ-gap mechanism); binder-unreachable through the
    governed path — see the module docstring. ``reason`` is a stable short slug."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def compute_parametric_es(sigma: Decimal, *, es_multiplier: Decimal) -> Decimal:
    """``ES = k_c * sigma`` at prec 50, raw (the binder gates + quantizes).

    ``sigma`` is the portfolio volatility — the plain ``sigma_p`` or PA-4's ``sigma_total``; the
    arithmetic is identical over either (a sigma-multiple is exactly as honest as its sigma, which
    is why the ES-total leg inherits BT-2's smoothing doctrine verbatim). ``es_multiplier`` is the
    REGISTERED ``k_c`` for the version's declared confidence — never computed here.
    """
    if sigma < 0:
        raise EsKernelError(
            "negative-sigma",
            f"sigma {sigma} < 0 — refused (ES is a non-negative multiple of a volatility)",
        )
    if es_multiplier <= 0:
        raise EsKernelError(
            "non-positive-multiplier",
            f"ES multiplier {es_multiplier} is non-positive — refused",
        )
    with localcontext() as ctx:
        ctx.prec = _CTX_PRECISION
        return es_multiplier * sigma
