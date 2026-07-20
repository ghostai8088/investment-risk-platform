"""Governed registration of the pacing model (CC-2, ENT-059 — the commitment-pacing projection).

The pacing projection is a **registered model** (the risk/perf-family precedent, but its OWN peer
family — ``pacing``, neither ``risk`` nor ``perf``): the registrar inventories the ``model`` head +
an immutable ``model_version`` through the governed model service, emitting
``MODEL.REGISTER``/``MODEL.VERSION``. **The FIVE declared parameters ARE the version identity**
(rate-of-contribution schedule, fund life, bow, growth, yield floor) — recorded as
``model_assumption`` rows and parsed back by the binder via ``declared_pacing_parameters``; a
same-label re-register with a different declaration is a governed 409 (mint a new label). **NO
numeric constant is minted from Takahashi-Alexander** — only the FUNCTIONAL FORM is TA's, recorded
as the ``functional_form=TAKAHASHI_ALEXANDER`` identity assumption. ``Model.validation_status``
stays ``UNVALIDATED`` (recorded, non-enforcing until a 2L validator records an outcome; VW-1).

One-way imports: ``pacing.bootstrap -> {model, pacing.kernel}`` only; imports NO ``risk``/``perf``/
``private_capital`` symbol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from irp_shared.model.assumptions import load_assumption_texts, sole_declared
from irp_shared.model.models import ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
)
from irp_shared.pacing.pacing_kernel import (
    PacingAnchor,
    PacingKernelError,
    PacingParams,
    project_commitment,
)

#: The per-tenant inventory identity of the pacing model (OD-CC-2-B).
PACING_MODEL_CODE = "pacing.commitment_projection"
PACING_MODEL_NAME = "Commitment-pacing projection (Takahashi-Alexander, v1)"
PACING_MODEL_TYPE = "PACING_PROJECTION"
PACING_VERSION_LABEL = "v1"
PACING_METHODOLOGY_REF = "05_analytics_methodologies/pacing_commitment_projection_v1.md"

#: The declared-parameter assumption prefixes (the version identity). Each declared exactly once;
#: parsed back fail-closed by the binder (a generically-minted version can stamp anything).
RC_SCHEDULE_PREFIX = "rc_schedule="
FUND_LIFE_PREFIX = "fund_life="
BOW_PREFIX = "bow="
GROWTH_PREFIX = "growth="
YIELD_FLOOR_PREFIX = "yield_floor="
#: The functional-form identity marker (a string, NOT a number — nothing minted from TA).
FUNCTIONAL_FORM_PREFIX = "functional_form="
FUNCTIONAL_FORM_TA = "TAKAHASHI_ALEXANDER"

#: Strict patterns. Rates canonicalize to a fixed 6dp form so 0.25 vs 0.250 cannot mint distinct
#: identities (the ES-HS-1 confidence_key precedent). A rate is in [0,1]; the schedule is a
#: non-empty comma-separated list; life a positive integer; bow/growth signed decimals; yield [0,1].
_RATE = r"(?:0(?:\.[0-9]{1,6})?|1(?:\.0{1,6})?)"
_RC_SCHEDULE_PATTERN = re.compile(rf"{_RATE}(?:,{_RATE})*")
_INT_PATTERN = re.compile(r"[1-9][0-9]{0,3}")
_SIGNED_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,12})?")
_YIELD_PATTERN = re.compile(_RATE)


def _canonical_rate(text: str) -> str:
    """Canonicalize one rate to a fixed 6dp string (identity-stable)."""
    return f"{Decimal(text).quantize(Decimal('0.000001')):f}"


def _canonical_rc_schedule(rates: list[str]) -> str:
    return ",".join(_canonical_rate(r) for r in rates)


def _canonical_decimal(value: Decimal) -> str:
    """Canonicalize a signed decimal parameter (bow/growth) to a stable fixed-point string —
    trailing zeros removed so ``2`` and ``2.0`` mint one identity; the ``:f`` spec always yields
    plain fixed-point (never E-notation), so an integer normalizes to e.g. ``2`` not ``2E+0``."""
    return f"{value.normalize():f}"


@dataclass(frozen=True)
class PacingParamsRequest:
    """The caller-supplied declared parameters (validated + canonicalized at registration)."""

    rc_schedule: list[Decimal]
    fund_life: int
    bow: Decimal
    growth: Decimal
    yield_floor: Decimal


def declared_pacing_parameters(session: Session, version: ModelVersion) -> PacingParams:
    """Parse the five declared parameters + the TA form marker from ``version``'s assumption rows
    (exactly ONE strictly-well-formed declaration of each). Malformed/absent/ambiguous -> the
    fail-closed :class:`WrongModelVersionError` (the generic endpoint can mint anything). Returns a
    kernel-ready :class:`PacingParams`; the kernel re-checks the domains (defense-in-depth)."""
    texts = load_assumption_texts(session, version)
    rc_text = sole_declared(texts, RC_SCHEDULE_PREFIX)
    life_text = sole_declared(texts, FUND_LIFE_PREFIX)
    bow_text = sole_declared(texts, BOW_PREFIX)
    growth_text = sole_declared(texts, GROWTH_PREFIX)
    yield_text = sole_declared(texts, YIELD_FLOOR_PREFIX)
    form_text = sole_declared(texts, FUNCTIONAL_FORM_PREFIX)
    if (
        rc_text is None
        or life_text is None
        or bow_text is None
        or growth_text is None
        or yield_text is None
        or form_text != FUNCTIONAL_FORM_TA
        or _RC_SCHEDULE_PATTERN.fullmatch(rc_text) is None
        or _INT_PATTERN.fullmatch(life_text) is None
        or _SIGNED_DECIMAL.fullmatch(bow_text) is None
        or _SIGNED_DECIMAL.fullmatch(growth_text) is None
        or _YIELD_PATTERN.fullmatch(yield_text) is None
    ):
        raise WrongModelVersionError(str(version.id), PACING_MODEL_CODE)
    try:
        params = PacingParams(
            rc_schedule=tuple(Decimal(r) for r in rc_text.split(",")),
            fund_life=int(life_text),
            bow=Decimal(bow_text),
            growth=Decimal(growth_text),
            yield_floor=Decimal(yield_text),
        )
        # Domain + cross-field (len <= L, ranges): re-use the kernel's own validation by a probe
        # projection over a trivial anchor — it raises PacingKernelError on any domain breach.
        project_commitment(
            params,
            _probe_anchor(params.fund_life),
        )
    except (InvalidOperation, PacingKernelError) as exc:
        raise WrongModelVersionError(str(version.id), PACING_MODEL_CODE) from exc
    return params


def _probe_anchor(fund_life: int) -> PacingAnchor:
    # current_age = fund_life -> zero periods, so the probe validates the params WITHOUT projecting.
    return PacingAnchor(current_age=fund_life, unfunded=Decimal("0"), nav=Decimal("0"))


#: The declared model assumptions (the FIVE parameters + the TA form + the recursion statement).
def _assumption_rows(req: PacingParamsRequest) -> tuple[str, ...]:
    return (
        f"{FUNCTIONAL_FORM_PREFIX}{FUNCTIONAL_FORM_TA}",
        f"{RC_SCHEDULE_PREFIX}{_canonical_rc_schedule([str(r) for r in req.rc_schedule])}",
        f"{FUND_LIFE_PREFIX}{int(req.fund_life)}",
        f"{BOW_PREFIX}{_canonical_decimal(req.bow)}",
        f"{GROWTH_PREFIX}{_canonical_decimal(req.growth)}",
        f"{YIELD_FLOOR_PREFIX}{_canonical_rate(str(req.yield_floor))}",
        "The Takahashi-Alexander deterministic commitment-pacing recursion (JPM 28(2):90-100, "
        "2002), verified via reproduction (the primary is gated - the ES-HS-1/AS-2014 precedent): "
        "per fund AGE t = current_age+1..L, C(t)=RC(t)*Unfunded(t-1); RD(t)=max(Y,(t/L)^B); "
        "D(t)=RD(t)*NAV(t-1)*(1+G); NAV(t)=NAV(t-1)*(1+G)+C(t)-D(t). FUTURE-ONLY from the pinned "
        "as-of age; QUANTIZE-THEN-ROLL at 6dp; ANNUAL periodicity; NO optimizer, NO randomness.",
    )


#: The recorded scope-outs (mirrored into model_limitation rows; OD-CC-2-B).
PACING_LIMITATIONS: tuple[str, ...] = (
    "SINGLE deterministic path - no scenarios, no randomness. The declared parameters propagate "
    "one-for-one into every projected value (a mis-declared growth/bow biases the whole series); "
    "the stochastic Jeet (SSRN 4819761) enhancement is the recorded v2. VALIDATION honesty: this "
    "is a projection under declared assumptions, NOT a forecast of realized cashflows.",
    "MID-LIFE RE-ANCHORING is OUR adaptation: for an already-called commitment the projection "
    "seeds Unfunded(0)/NAV(0) from REALIZED actuals (Sum of calls; Sum of recallable "
    "distributions restoring unfunded; the latest pinned mark) and projects only FUTURE ages "
    "t=current_age+1..L. The R1/R2 reproductions verify the from-inception recursion; the "
    "re-anchoring is a documented CC-2 extension, not attested by the sources.",
    "ANNUAL periodicity in v1 (quarterly = the recorded v2). All captured call types "
    "(DRAWDOWN/EQUALIZATION/FEE) consume unfunded - the fees-inside-commitment convention; "
    "fee-outside-commitment treatment is a recorded variant. A recallable distribution restores "
    "unfunded (uncapped up to the anchor-coherence bound Unfunded(0) in [0, committed]).",
    "NAV ANCHOR: NAV(0) = the latest pinned current-head valuation mark for the (portfolio, "
    "instrument) pair (max valuation_date), whose currency MUST equal the commitment's - else the "
    "run is REFUSED pre-create (never a fabricated anchor). MARK STALENESS is v1-DISCLOSED, not "
    "gated (the mark's valuation_date is in the pin; the HG-1-style opt-in age gate is the v2). "
    "A funded book with no pinned mark is REFUSED; a new (uncalled) commitment anchors NAV(0)=0.",
    "PER-(portfolio, instrument) PAIR at ANNUAL periodicity; a portfolio-level unfunded ROLLUP "
    "across pairs (the REQ-PRV-001 'aggregated' clause) is the NAMED v2. RD(L)=max(Y,1)=1 so the "
    "final age fully distributes the grown NAV. A commitment past fund life (current_age >= L) "
    "is REFUSED pre-create (nothing to project).",
    "validation_status UNVALIDATED - recorded, non-enforcing until a 2L validator records an "
    "outcome (VW-1); a REJECTED latest outcome (or an EXPIRED use-before-validation exception, "
    "MG-1) refuses every new bind at the shared seam.",
)

_PACING_DESCRIPTION = (
    "Deterministic Takahashi-Alexander commitment-pacing projection over the CC-1 captured "
    "substrate (commitment + capital_call/distribution events + the latest valuation mark) - the "
    "SEVENTEENTH governed number (pacing.commitment_projection, ENT-059). NO optimizer."
)


def register_pacing_projection_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    rc_schedule: list[Decimal],
    fund_life: int,
    bow: Decimal,
    growth: Decimal,
    yield_floor: Decimal,
    version_label: str = PACING_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the pacing model family (CC-2, OD-CC-2-B): identity =
    (code_version, rc_schedule, fund_life, bow, growth, yield_floor, functional_form). Same-label
    different-declaration -> :class:`ModelVersionConflictError`; a non-REGISTERED same-label twin ->
    :class:`WrongModelVersionError` (the P3-C1 contract). Domains are validated here AND re-checked
    at bind by the kernel (defense-in-depth). NO TA constant is minted - only the form marker."""
    if not version_label or not str(version_label).strip():
        raise ValueError(
            "version_label must be a non-empty string (MF-1: the label IS the identity)"
        )
    req = PacingParamsRequest(
        rc_schedule=[Decimal(str(r)) for r in rc_schedule],
        fund_life=int(fund_life),
        bow=Decimal(str(bow)),
        growth=Decimal(str(growth)),
        yield_floor=Decimal(str(yield_floor)),
    )
    # Validate the domains up-front via the kernel (raises PacingKernelError -> ValueError 422).
    try:
        kernel_params = PacingParams(
            rc_schedule=tuple(req.rc_schedule),
            fund_life=req.fund_life,
            bow=req.bow,
            growth=req.growth,
            yield_floor=req.yield_floor,
        )
        project_commitment(kernel_params, _probe_anchor(req.fund_life))
    except PacingKernelError as exc:
        raise ValueError(f"invalid pacing parameters: {exc}") from exc

    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=PACING_MODEL_CODE,
        name=PACING_MODEL_NAME,
        model_type=PACING_MODEL_TYPE,
        actor_id=actor_id,
        description=_PACING_DESCRIPTION,
        actor_type=actor_type,
    )
    assumptions = _assumption_rows(req)
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=PACING_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=assumptions,
            limitations=PACING_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), PACING_MODEL_CODE)
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(PACING_MODEL_CODE, str(version_label), str(code_version))
    # A same-label re-register that changed a declared parameter is a conflict (the assumptions
    # would differ) — caught by comparing the canonical assumption set of the resolved version.
    existing = set(load_assumption_texts(session, version))
    if existing and existing != set(assumptions):
        raise ModelVersionConflictError(PACING_MODEL_CODE, str(version_label), str(code_version))
    return version
