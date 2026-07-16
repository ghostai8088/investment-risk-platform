"""Factor-exposure binder (P3-3 allocation v1 + PA-2 proxy projection, ENT-028 family).

``run_factor_exposure`` produces ``factor_exposure_result`` rows ONLY when bound to a
``dataset_snapshot`` (``FACTOR_EXPOSURE_INPUT``) + a complete ``calculation_run`` + a **REGISTERED
``model_version`` of ONE OF THE THREE factor-exposure model families** (AD-014 / FW-RUN / TR-15 /
CTRL-003) — the ONE binder DISPATCHES on the bound model's code via the ``_EXPOSURE_FAMILIES``
registry map (PA-2, OD-PA-2-A; the registry-map form is FL-1, OD-FL-1-D):

- **``risk.factor_exposure.allocation`` v1 (P3-3):** the deterministic indicator-loading
  allocation (``irp_shared.risk.factor_kernel``): CURRENCY family, matched on the atom's captured
  ``mark_currency``; contributions sum to the pinned input total EXACTLY (ε = 0, REQ-MKT-003).
  Pins: ``COMPONENT_KIND_EXPOSURE`` + ``COMPONENT_KIND_FACTOR``.
- **``risk.factor_exposure.proxy`` v1 (PA-2):** proxied-else-indicator over a MIXED book — an
  atom whose instrument has pinned CURRENT ``proxy_mapping`` rows allocates
  ``quantize_HALF_UP(weight × atom, 6)`` per proxy factor (``loading`` = the captured weight,
  signed; an explicit ZERO weight is a captured "no loading on this leg" — no row, never the
  indicator fallback); every other atom follows the allocation-v1 rule. Adds
  ``COMPONENT_KIND_PROXY_MAPPING`` pins + the ``...+proxy-rows`` binding predicate.
  The partial-proxy residual stays unmodeled; the sum-to-total identity holds per-UNPROXIED-atom.
- **``risk.factor_exposure.loadings`` v1 (FL-1):** the proxy projection GENERALIZED — fractional
  signed multi-factor loadings over the WIDENED admitted families (``LOADING_FACTOR_FAMILIES``;
  OTHER/unknown refused), the loading rows sourced from the same widened ENT-019 ``proxy_mapping``.
  Same ``weight × atom`` arithmetic, but with the COVERAGE GATE: every pinned atom MUST carry >= 1
  loading row (an unloaded atom refuses the run closed — NO indicator fallback, no silent zero).
  Adds the ``...+loading-rows`` binding predicate. The projection replaces the partition identity
  (Σ exposure ≠ Σ atoms in general; the loaded-atom residual is honestly unmodeled).

The three predicates give a 3×3 refusal symmetry: each family requires EXACTLY its own predicate
and refuses the other two (a wrong bind would silently discard rows or degrade the rule).

Reproducibility (the AD-014 invariant): the compute reads **ONLY the snapshot's pinned captured
content** — it makes **NO** live exposure/factor/proxy read, so a later factor-definition amend,
exposure re-run, or proxy-weight supersede cannot change a historical factor exposure.

Failure model (the P2-3/P3-1 precedent, split by timing — and, post the 2026-07 adversarial
review, UNIFORM across BOTH entry paths):
- **Pre-create refusal** (missing ``code_version``/``environment_id``/initiator/
  ``model_version_id``; an unregistered or WRONG-MODEL model_version; a non-COMPLETED /
  cross-tenant / empty exposure run; a wrong-purpose snapshot; **pinned content that is not a
  well-formed v1 input** — zero pinned atoms, zero pinned factors, a non-CURRENCY family, a
  NULL ``currency_code`` scope, or a duplicate ``currency_code`` (an ambiguous partition);
  **a proxy-mode input that is ill-formed** — an unpinned proxy factor, a proxy pin matching
  no atom, a duplicate (instrument, factor) proxy pin, a non-finite weight, or a
  predicate/model mismatch in EITHER direction):
  **raise BEFORE ``create_run``** ⇒ ZERO run + ZERO rows + ZERO run-audit. Both the
  build-in-request AND consume-existing (``snapshot_id``) paths adjudicate the PINNED content
  pre-create through the same kernel rules, so a snapshot minted by any other builder cannot
  smuggle an ill-formed input past the gate.
- **Post-create FAILED** (the DQ gate failing AFTER RUNNING — an unmapped atom, OD-P3-3-N; or a
  proxied product beyond the ``Numeric(28,6)`` envelope, ``|weight × atom| >= 1E21``): mark
  the run FAILED (``outcome='failure'``) and **return** ⇒ a committed FAILED run +
  ``CALC.RUN_STATUS_CHANGE`` + a ``DATA.VALIDATE`` DQ record + ZERO result rows (durable refusal
  evidence; the returned ``failure_reason`` names the unmapped atoms/currencies).
- **Emit-path** raises propagate ⇒ the whole unit rolls back co-transactionally (CTRL-032).

One-way imports: ``risk -> {snapshot, marketdata(constants), exposure(read-only run resolution),
calc, model, lineage, dq, audit, db}``; imports NO live exposure/factor resolver into the COMPUTE
path; imports no covariance/VaR/ES/scenario/stress/regression symbol; nothing imports ``risk``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus
from irp_shared.calc.runs import resolve_run_of_type
from irp_shared.calc.scaffold import execute_governed_run
from irp_shared.exposure.service import resolve_run as resolve_exposure_run
from irp_shared.marketdata.models import FACTOR_FAMILY_CURRENCY, LOADING_FACTOR_FAMILIES
from irp_shared.model.models import ModelVersion
from irp_shared.model.service import WrongModelVersionError
from irp_shared.risk.bootstrap import (
    FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
    FACTOR_EXPOSURE_MODEL_CODE,
    FACTOR_EXPOSURE_PROXY_MODEL_CODE,
    assert_model_version_of,
)
from irp_shared.risk.events import RUN_TYPE_FACTOR_EXPOSURE, FactorExposureActor
from irp_shared.risk.factor_kernel import (
    RESULT_QUANTUM,
    AtomPin,
    FactorKernelError,
    FactorPin,
    allocate_atom,
    build_factor_index,
)
from irp_shared.risk.models import FactorExposureResult
from irp_shared.snapshot import (
    COMPONENT_KIND_EXPOSURE,
    COMPONENT_KIND_FACTOR,
    COMPONENT_KIND_PROXY_MAPPING,
    FACTOR_EXPOSURE_BINDING_PREDICATE,
    FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE,
    FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE,
    PURPOSE_FACTOR_EXPOSURE_INPUT,
    SnapshotActor,
    build_factor_exposure_snapshot,
    list_components,
    resolve_snapshot,
)

#: The v1 supported mapping families (OD-P3-3-C; anything else is a pre-create refusal — enforced
#: on the PINNED factor content for both entry paths). The allocation + proxy families stay
#: CURRENCY-only (the indicator kernel structurally requires a currency partition); the LOADINGS
#: family (FL-1) admits the wider ``LOADING_FACTOR_FAMILIES`` — a per-family gate, OD-FL-1-E.
SUPPORTED_FACTOR_FAMILIES = (FACTOR_FAMILY_CURRENCY,)


@dataclass(frozen=True)
class _ExposureFamily:
    """Which of the THREE factor-exposure model codes a run bound, decomposed onto the axes the
    binder branches on (FL-1, OD-FL-1-D — the ES-1 ``_resolve_var_family`` registry-map precedent;
    a three-arm try/except is past the chain's readability bar).

    ``pins_rows``         = the snapshot pins ``COMPONENT_KIND_PROXY_MAPPING`` rows (proxy +
                            loadings; the allocation family pins none).
    ``coverage_required`` = every pinned atom MUST carry >= 1 loading row — an unloaded atom
                            REFUSES the run closed, no indicator fallback (loadings only; the proxy
                            family falls back to the indicator rule for unproxied atoms).
    ``predicate``         = the REQUIRED binding predicate (the 3x3 symmetry: each family requires
                            exactly its own predicate and refuses the other two).
    ``factor_families``   = the admitted factor families for the pinned factor content.
    """

    code: str
    pins_rows: bool
    coverage_required: bool
    predicate: str
    factor_families: tuple[str, ...]


#: The three families, in DISPATCH order. Order matters only for cost (each miss is a failed
#: assert), not correctness — the codes are mutually exclusive, so at most one matches a version.
_EXPOSURE_FAMILIES: tuple[_ExposureFamily, ...] = (
    _ExposureFamily(
        code=FACTOR_EXPOSURE_MODEL_CODE,
        pins_rows=False,
        coverage_required=False,
        predicate=FACTOR_EXPOSURE_BINDING_PREDICATE,
        factor_families=SUPPORTED_FACTOR_FAMILIES,
    ),
    _ExposureFamily(
        code=FACTOR_EXPOSURE_PROXY_MODEL_CODE,
        pins_rows=True,
        coverage_required=False,
        predicate=FACTOR_EXPOSURE_PROXY_BINDING_PREDICATE,
        factor_families=SUPPORTED_FACTOR_FAMILIES,
    ),
    _ExposureFamily(
        code=FACTOR_EXPOSURE_LOADINGS_MODEL_CODE,
        pins_rows=True,
        coverage_required=True,
        predicate=FACTOR_EXPOSURE_LOADINGS_BINDING_PREDICATE,
        factor_families=LOADING_FACTOR_FAMILIES,
    ),
)
#: Per-tenant governed completeness DQ rule (resolve-or-register; the sensitivity pattern).
_COMPLETENESS_RULE_CODE = "risk.factor_exposure.completeness"
#: How many unmapped-atom identifiers the FAILED ``failure_reason`` names (evidence, bounded).
_MAX_GAPS_IN_REASON = 10


class FactorExposureInputError(Exception):
    """A missing/invalid prerequisite detected BEFORE the run is created — pre-create refusal (no
    run, no result, no run-audit). Maps to 422."""


class FactorExposureNotVisible(Exception):
    """Raised when a ``factor_exposure_result`` id is not visible in the acting tenant scope."""

    def __init__(self, factor_exposure_id: str) -> None:
        super().__init__(
            f"factor_exposure_result {factor_exposure_id} is not visible in the current tenant"
        )
        self.factor_exposure_id = str(factor_exposure_id)


class FactorExposureRunNotVisible(Exception):
    """Raised when a factor-exposure ``calculation_run`` id is not visible in the acting
    tenant."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"factor-exposure run {run_id} is not visible in the current tenant")
        self.run_id = str(run_id)


#: The proxied-row envelope: Numeric(28,6) holds |value| < 1E22; the gate sits one order inside
#: (the P3-6/BT-1/P3-8 echo-overflow class — the FIRST unguarded multiply on this table without it
#: would detonate quantize AFTER the run is RUNNING; review fold).
_MAX_RESULT_ABS = Decimal("1E21")


@dataclass(frozen=True)
class ProxyPin:
    """One pinned ``proxy_mapping`` FR row (PA-2): the captured weight of a private instrument on
    a public factor."""

    instrument_id: str
    factor_id: str
    weight: Decimal


@dataclass(frozen=True)
class FactorExposureRunResult:
    """The outcome of ``run_factor_exposure``: the ``calculation_run`` + status + the rows
    produced. ``status`` is ``COMPLETED`` (with ``rows``) or ``FAILED`` (a post-create gate
    failure: a committed FAILED run + ZERO rows + ``failure_reason`` naming the unmapped
    atoms)."""

    run: CalculationRun
    status: str
    rows: list[FactorExposureResult] = field(default_factory=list)
    failure_reason: str | None = None


def _parse_pins(comps: list[Any]) -> tuple[list[AtomPin], list[FactorPin], list[ProxyPin]]:
    """Parse the pinned ``captured_content`` into kernel pins (PURE — no live read; the AD-014
    invariant)."""
    atoms: list[AtomPin] = []
    factors: list[FactorPin] = []
    proxies: list[ProxyPin] = []
    for comp in comps:
        data = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_PROXY_MAPPING:
            proxies.append(
                ProxyPin(
                    instrument_id=str(data["private_instrument_id"]).lower(),
                    factor_id=str(data["factor_id"]).lower(),
                    weight=Decimal(data["weight"]),
                )
            )
        elif comp.component_kind == COMPONENT_KIND_EXPOSURE:
            atoms.append(
                AtomPin(
                    id=data["id"],
                    portfolio_id=data["portfolio_id"],
                    instrument_id=data["instrument_id"],
                    base_currency=data["base_currency"],
                    mark_currency=data["mark_currency"],
                    exposure_amount=Decimal(data["exposure_amount"]),
                )
            )
        elif comp.component_kind == COMPONENT_KIND_FACTOR:
            factors.append(
                FactorPin(
                    id=data["id"],
                    factor_code=data["factor_code"],
                    factor_family=data["factor_family"],
                    currency_code=data["currency_code"],
                )
            )
    return atoms, factors, proxies


def _resolve_exposure_family(
    session: Session, model_version_id: str, *, acting_tenant: str
) -> tuple[ModelVersion, _ExposureFamily]:
    """Inventory-before-use + model identity (CTRL-003 / BR-3), dispatching on the bound model's
    code across the three factor-exposure families (PA-2's OD-PA-2-A dispatch, extended by FL-1 to
    the registry map — the ES-1 ``_resolve_var_family`` shape).

    An UNREGISTERED version raises :class:`UnregisteredModelError` from the first assert (not a
    family question); a version of NONE of the three families raises the FIRST
    :class:`WrongModelVersionError` — the one naming the ALLOCATION code (the canonical
    first-registered family, the one a caller passing an unrelated version most likely meant; NB
    this changed the message vs the pre-PA-2 two-arm form, which surfaced the proxy-code error —
    same exception class, a clearer message)."""
    first_error: WrongModelVersionError | None = None
    for family in _EXPOSURE_FAMILIES:
        try:
            version = assert_model_version_of(
                session,
                str(model_version_id),
                tenant_id=acting_tenant,
                expected_model_code=family.code,
            )
        except WrongModelVersionError as exc:
            if first_error is None:  # the ALLOCATION-code miss — the pre-PA-2 message, preserved
                first_error = exc
            continue
        return version, family
    assert first_error is not None  # the loop is non-empty, so a full miss always set it
    raise first_error


def _adjudicate_pins(
    atoms: list[AtomPin], factors: list[FactorPin], family: _ExposureFamily
) -> dict[str, FactorPin]:
    """PRE-CREATE adjudication of the pinned input (both entry paths; the 2026-07 review
    hardening): ≥1 atom, ≥1 factor, every factor family admitted for THIS model family, and — for
    the indicator-using families (allocation/proxy) — a well-formed currency partition (the kernel
    is the single rule source; NULL scope / duplicate ``currency_code`` refuse). The LOADINGS
    family matches factors by id, not by a currency partition, so it does NOT build the index (a
    non-CURRENCY factor legitimately has no ``currency_code``). Raises
    :class:`FactorExposureInputError`; returns the allocation index (empty for loadings)."""
    if not atoms:
        raise FactorExposureInputError(
            "the snapshot pins no exposure atoms (COMPONENT_KIND_EXPOSURE) — not a "
            "factor-exposure input"
        )
    if not factors:
        raise FactorExposureInputError(
            "the snapshot pins no factor definitions (COMPONENT_KIND_FACTOR) — not a "
            "factor-exposure input"
        )
    # A DUPLICATE (portfolio, instrument) atom pin would double-write the 4-tuple result grain (an
    # IntegrityError mid-run — the same threat the proxy-pin duplicate gate closes, FL-1 review
    # fold). Impossible on the governed build path (exposure atoms are unique per (run, portfolio,
    # instrument, base_currency) + the uniform-base gate below), but a hand-minted snapshot is
    # inside the declared trust boundary; refuse pre-create for all three families.
    seen_atoms: set[tuple[str, str]] = set()
    for a in atoms:
        key = (str(a.portfolio_id), str(a.instrument_id))
        if key in seen_atoms:
            raise FactorExposureInputError(
                f"duplicate exposure atom for (portfolio {a.portfolio_id}, instrument "
                f"{a.instrument_id}) — refused (it would double-write the result grain)"
            )
        seen_atoms.add(key)
    base_currencies = {a.base_currency for a in atoms}
    if len(base_currencies) != 1:
        # P3-C1 (OD-H): base is run-uniform by construction on the governed path, but a
        # hand-minted snapshot could pin mixed-base atoms — the recorded latent hole, closed
        # at the adjudication (the P3-5 twin check); the 4-tuple grain is unchanged.
        raise FactorExposureInputError(
            f"the pinned atoms carry mixed base currencies {sorted(base_currencies)} — refused"
        )
    base_currency = next(iter(base_currencies))
    if not isinstance(base_currency, str) or len(base_currency) != 3:
        # A uniformly-NULL or non-3-letter base_currency ({None} / {"USDX"} pass the set-of-one
        # check) would otherwise reach the NOT-NULL varchar(3) result column as a post-create 500
        # (P3-C3 binder-consistency pass — the active-risk/VaR twin).
        raise FactorExposureInputError(
            "the pinned atoms' base_currency is not a 3-letter code — refused"
        )
    for pin in factors:
        if pin.factor_family not in family.factor_families:
            raise FactorExposureInputError(
                f"factor {pin.factor_code!r} family {pin.factor_family!r} is not admitted for the "
                f"{family.code} family (admitted: {family.factor_families})"
            )
    if family.coverage_required:
        # The loadings family projects by factor id (no currency partition) — skip the index.
        return {}
    try:
        return build_factor_index(factors)
    except FactorKernelError as exc:
        raise FactorExposureInputError(str(exc)) from exc


def _adjudicate_proxies(
    proxies: list[ProxyPin], factors: list[FactorPin], atoms: list[AtomPin]
) -> dict[str, list[ProxyPin]]:
    """PA-2 (OD-PA-2-B) pre-create adjudication of the pinned proxy rows (the same trust boundary
    ``_adjudicate_pins`` defends: consume-existing accepts ANY snapshot, so a hand-minted pin set
    must not smuggle an ill-formed input past the gate — review fold). Fail-closed gates:

    - every proxy factor MUST be in the pinned factor list (no silent dropping);
    - every proxy instrument MUST have a pinned atom (a pin applied to nothing is ill-formed);
    - a DUPLICATE (instrument, factor) pin refuses (it would double-write the 4-tuple grain —
      an IntegrityError mid-run, or a double-counted exposure; the var_service duplicate-pin twin);
    - a non-finite weight refuses.

    A weight of EXACTLY ZERO is a legitimate CAPTURED judgment ("no loading on this leg" — the
    natural way to retire one leg; capture validates finiteness only, PA-0 OD-D) — the pin is kept
    so the instrument STAYS proxied, and ``_build_rows`` emits no row for it (never a fallback to
    the indicator rule; review fold — the earlier refusal both bricked the whole book on one
    zero-weight head row AND mis-claimed a capture-side gate that does not exist).

    Returns ``{instrument_id: [ProxyPin, ...]}`` (empty when no proxies — the whole book then
    follows the indicator rule)."""
    pinned_factor_ids = {f.id.lower() for f in factors}
    atom_instrument_ids = {str(a.instrument_id).lower() for a in atoms}
    seen_pairs: set[tuple[str, str]] = set()
    by_instrument: dict[str, list[ProxyPin]] = {}
    for pin in proxies:
        if pin.factor_id not in pinned_factor_ids:
            raise FactorExposureInputError(
                f"proxy factor {pin.factor_id} (instrument {pin.instrument_id}) is not in the "
                f"pinned factor list — include it in factor_ids; refused (no silent dropping)"
            )
        if pin.instrument_id not in atom_instrument_ids:
            raise FactorExposureInputError(
                f"proxy pin for instrument {pin.instrument_id} matches no pinned atom — refused"
            )
        pair = (pin.instrument_id, pin.factor_id)
        if pair in seen_pairs:
            raise FactorExposureInputError(
                f"duplicate proxy pin for (instrument {pin.instrument_id}, factor "
                f"{pin.factor_id}) — refused (it would double-count the exposure)"
            )
        seen_pairs.add(pair)
        if not pin.weight.is_finite():
            raise FactorExposureInputError(
                f"proxy weight {pin.weight} (instrument {pin.instrument_id}) is not a finite "
                f"loading — refused"
            )
        by_instrument.setdefault(pin.instrument_id, []).append(pin)
    return by_instrument


def _assert_full_coverage(
    atoms: list[AtomPin], proxies_by_instrument: dict[str, list[ProxyPin]]
) -> None:
    """FL-1 (OD-FL-1-D) — the LOADINGS-family coverage gate: every pinned atom MUST carry >= 1
    loading row. An UNLOADED atom refuses the run CLOSED — no indicator fallback (the loadings
    family has none, unlike the proxy family) and no silent zero (a silently-dropped atom would
    UNDER-COUNT the downstream VaR). A captured zero-weight row IS coverage (a declared "this atom
    projects to nothing" — its exposure is the honest residual); only the total ABSENCE of rows is
    the refusal."""
    unloaded = sorted(
        {
            str(a.instrument_id)
            for a in atoms
            if not proxies_by_instrument.get(str(a.instrument_id).lower())
        }
    )
    if unloaded:
        shown = "; ".join(unloaded[:_MAX_GAPS_IN_REASON])
        more = (
            f" (+{len(unloaded) - _MAX_GAPS_IN_REASON} more)"
            if len(unloaded) > _MAX_GAPS_IN_REASON
            else ""
        )
        raise FactorExposureInputError(
            f"the loadings family requires every atom to carry >= 1 loading row — these "
            f"instruments have none: {shown}{more} (an unloaded atom is refused, never dropped)"
        )


def _build_rows(
    atoms: list[AtomPin],
    index: dict[str, FactorPin],
    *,
    run: CalculationRun,
    snapshot_id: str,
    model_version_id: str,
    acting_tenant: str,
    proxies_by_instrument: dict[str, list[ProxyPin]] | None = None,
    factor_by_id: dict[str, FactorPin] | None = None,
) -> tuple[list[FactorExposureResult], list[str]]:
    """Allocate each pinned atom (the pure kernel over pre-adjudicated pins only). A PROXIED
    instrument's atoms allocate ``weight × atom`` per pinned proxy leg (replace-not-add; zero
    weights emit no row; the raw product is envelope-gated at ``_MAX_RESULT_ABS`` → FAILED);
    every other atom follows the indicator rule. Returns ``(rows, gaps)`` — one gap per unmapped
    atom or out-of-envelope product (the fail-closed DQ signal; rows are NOT written when gaps
    exist)."""
    rows: list[FactorExposureResult] = []
    gaps: list[str] = []
    proxies_by_instrument = proxies_by_instrument or {}
    factor_by_id = factor_by_id or {}
    for atom in atoms:
        # PA-2 (OD-PA-2-B): a proxied instrument's rows REPLACE its indicator row — allocate
        # exposure x weight per pinned proxy factor (loading = the captured weight, signed).
        proxy_pins = proxies_by_instrument.get(str(atom.instrument_id).lower())
        if proxy_pins:
            for pin in proxy_pins:
                if pin.weight == 0:
                    continue  # an explicit captured zero = "no loading on this leg" (no row;
                    # the instrument STAYS proxied — never the indicator fallback)
                factor = factor_by_id[pin.factor_id]  # presence adjudicated pre-create
                # Multiply at 50-digit precision (the serializer's widened-context twin — the
                # default 28-digit context would silently HALF_EVEN-pre-round a large product
                # before the declared HALF_UP quantize), then gate the RAW product BEFORE
                # quantizing (>= 1E22 raises InvalidOperation AFTER the run is RUNNING — the
                # P3-6/BT-1 echo-overflow class; a committed FAILED run, never a raw 500).
                with localcontext() as ctx:
                    ctx.prec = 50
                    raw = pin.weight * atom.exposure_amount
                if abs(raw) >= _MAX_RESULT_ABS:
                    gaps.append(
                        f"magnitude-out-of-range:loading:{atom.instrument_id}:{pin.factor_id}"
                    )
                    return [], gaps
                rows.append(
                    FactorExposureResult(
                        tenant_id=str(acting_tenant),
                        calculation_run_id=run.run_id,
                        input_snapshot_id=str(snapshot_id),
                        model_version_id=str(model_version_id),
                        portfolio_id=atom.portfolio_id,
                        instrument_id=atom.instrument_id,
                        factor_id=factor.id,
                        factor_code=factor.factor_code,
                        factor_family=factor.factor_family,
                        base_currency=atom.base_currency,
                        mark_currency=atom.mark_currency,
                        loading=pin.weight,
                        exposure_amount=raw.quantize(RESULT_QUANTUM, rounding=ROUND_HALF_UP),
                    )
                )
            continue
        allocated = allocate_atom(atom, index)
        if allocated is None:
            gaps.append(f"unmapped-atom:{atom.id}:{atom.mark_currency}")
            continue
        rows.append(
            FactorExposureResult(
                tenant_id=str(acting_tenant),
                calculation_run_id=run.run_id,
                input_snapshot_id=str(snapshot_id),
                model_version_id=str(model_version_id),
                portfolio_id=atom.portfolio_id,
                instrument_id=atom.instrument_id,
                factor_id=allocated.factor.id,
                factor_code=allocated.factor.factor_code,
                factor_family=allocated.factor.factor_family,
                base_currency=atom.base_currency,
                mark_currency=atom.mark_currency,
                loading=allocated.loading,
                exposure_amount=allocated.exposure_amount,
            )
        )
    return rows, gaps


def run_factor_exposure(
    session: Session,
    *,
    acting_tenant: str,
    actor: FactorExposureActor,
    code_version: str,
    environment_id: str,
    model_version_id: str,
    exposure_run_id: str | None = None,
    factor_ids: list[str] | None = None,
    snapshot_id: str | None = None,
) -> FactorExposureRunResult:
    """Run a governed factor-exposure allocation. Build-in-request (default — ``exposure_run_id``
    + ``factor_ids``: builds a ``FACTOR_EXPOSURE_INPUT`` snapshot pinning the atoms + factors) or
    consume-existing (``snapshot_id``). BOTH paths adjudicate the pinned content pre-create. See
    the module docstring for the failure model + the AD-014 / CTRL-003 invariants."""

    # --- Pre-create prerequisite gate (raise BEFORE create_run ⇒ zero run/result/run-audit) ---
    if not code_version:
        raise FactorExposureInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise FactorExposureInputError("environment_id is required (FW-RUN/TR-15)")
    if actor is None or not actor.actor_id:
        raise FactorExposureInputError("initiator is required (FW-RUN/TR-15)")
    if not model_version_id:
        raise FactorExposureInputError(
            "model_version_id is required (CTRL-003 inventory-before-use)"
        )
    if snapshot_id is not None and (exposure_run_id is not None or factor_ids is not None):
        # P3-C1 (OD-G): passing BOTH input modes previously preferred snapshot_id SILENTLY —
        # an ambiguous request must be refused, never guessed.
        raise FactorExposureInputError(
            "ambiguous input — pass either snapshot_id or the build arguments "
            "(exposure_run_id/factor_ids), not both"
        )
    # Inventory-before-use + model identity (CTRL-003 / BR-3): the version must be REGISTERED and
    # belong to ONE of the THREE factor-exposure model families (PA-2's OD-PA-2-A dispatch on the
    # bound model's code, extended by FL-1 to the registry map — allocation indicator / proxy
    # projection / loadings projection). An unregistered version raises from the FIRST assert
    # (UnregisteredModelError); a version of NONE of the three raises WrongModelVersionError.
    _version, family = _resolve_exposure_family(
        session, str(model_version_id), acting_tenant=acting_tenant
    )
    is_proxy = family.code == FACTOR_EXPOSURE_PROXY_MODEL_CODE
    is_loadings = family.coverage_required

    # --- Bind the atoms+factors snapshot (cross-tenant/unknown/ill-formed ⇒ pre-create refusal) --
    if snapshot_id is not None:
        snapshot = resolve_snapshot(session, snapshot_id, acting_tenant=acting_tenant)
        if snapshot.purpose != PURPOSE_FACTOR_EXPOSURE_INPUT:
            raise FactorExposureInputError(
                f"snapshot {snapshot_id} purpose {snapshot.purpose!r} "
                f"!= {PURPOSE_FACTOR_EXPOSURE_INPUT}"
            )
        if snapshot.binding_predicate_version != family.predicate:
            # The 3x3 symmetry (PA-2's OD-PA-2-C both-ways refusal generalized by FL-1): each
            # family requires EXACTLY its own predicate. Binding the wrong family over a snapshot
            # would either silently discard the pinned rows (allocation over a proxy/loading
            # snapshot) or degrade to a different rule (proxy/loadings over a plain one) — two
            # materially different governed numbers from ONE snapshot; refuse.
            raise FactorExposureInputError(
                f"snapshot {snapshot_id} predicate {snapshot.binding_predicate_version!r} does "
                f"not match the bound {family.code} model (requires {family.predicate!r})"
            )
    else:
        if not exposure_run_id or not factor_ids:
            raise FactorExposureInputError(
                "exposure_run_id + factor_ids are required to build a factor-exposure snapshot"
            )
        # The consumed exposure run must be a COMPLETED own-tenant EXPOSURE_AGGREGATE run (a
        # FAILED run has zero rows; RUNNING output is not a governed input). The builder itself
        # fail-closes on an empty atom set / empty factor list BEFORE any write.
        exposure_run = resolve_exposure_run(
            session, str(exposure_run_id), acting_tenant=acting_tenant
        )
        if exposure_run.status != RunStatus.COMPLETED.value:
            raise FactorExposureInputError(
                f"exposure run {exposure_run_id} status {exposure_run.status!r} != COMPLETED"
            )
        snapshot = build_factor_exposure_snapshot(
            session,
            acting_tenant=acting_tenant,
            actor=SnapshotActor(actor_id=actor.actor_id, actor_type=actor.actor_type),
            exposure_run_id=str(exposure_run_id),
            factor_ids=[str(fid) for fid in factor_ids],
            include_proxy_rows=is_proxy,
            loadings_family=is_loadings,
        )

    # --- Adjudicate the PINNED content pre-create (uniform for both paths; kernel-rule-sourced):
    # zero atoms / zero factors / unsupported family / NULL scope / duplicate currency all refuse
    # HERE — before a run (or any run-audit) can exist.
    try:
        atoms, factors, proxies = _parse_pins(
            list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant)
        )
        index = _adjudicate_pins(atoms, factors, family)
        # CONTENT-based family fence (FL-1 review fold): the 3x3 predicate gate keys on the
        # binding-predicate STRING, but a hand-minted snapshot (inside the declared trust
        # boundary) could pin proxy/loading rows under the ALLOCATION predicate — the allocation
        # binder would then COMPLETE while silently discarding those rows (a different governed
        # number from the same content). The allocation family pins NO rows, so any pinned
        # PROXY_MAPPING content under it is ill-formed; refuse on the CONTENT, not just the string.
        if not family.pins_rows and proxies:
            raise FactorExposureInputError(
                f"snapshot pins {len(proxies)} proxy/loading row(s) but the bound {family.code} "
                f"family consumes none — they would be silently discarded; bind the proxy or "
                f"loadings model instead"
            )
        # Proxy AND loadings both adjudicate the pinned rows (the same trust boundary); the
        # loadings family ADDITIONALLY requires full coverage — every atom carries >= 1 loading
        # row (no indicator fallback; OD-FL-1-D).
        proxies_by_instrument = (
            _adjudicate_proxies(proxies, factors, atoms) if family.pins_rows else {}
        )
        if family.coverage_required:
            _assert_full_coverage(atoms, proxies_by_instrument)
        factor_by_id = {f.id.lower(): f for f in factors}
    except FactorExposureInputError:
        raise
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        # Structurally malformed pinned content (missing keys, non-decimal/JSON-null values,
        # non-object captured_content) is the SAME refusal class as a semantically ill-formed input
        # — a governed 422, never a raw parse 500. This wrapper was ABSENT here while its VaR/
        # active-risk siblings had it (P3-C3 binder-consistency pass, OD-A Part 3 — the third
        # same-class gap, folded on discovery).
        raise FactorExposureInputError(
            f"pinned content is not a well-formed v1 input ({type(exc).__name__})"
        ) from exc

    # --- The shared governed-run lifecycle (P3-C1 scaffold; behavior-preserving) ---
    def _compute(run: CalculationRun) -> tuple[list[FactorExposureResult], list[str]]:
        return _build_rows(
            atoms,
            index,
            run=run,
            snapshot_id=snapshot.id,
            model_version_id=str(model_version_id),
            acting_tenant=acting_tenant,
            proxies_by_instrument=proxies_by_instrument,
            factor_by_id=factor_by_id,
        )

    def _format_reason(gate: Exception, gaps: list[str]) -> str:  # verbatim P3-3 format
        # Name the unmapped atoms/currencies in the reason (bounded) — the review finding: the
        # computed gap identifiers must not be discarded.
        detail = "; ".join(gaps[:_MAX_GAPS_IN_REASON])
        more = (
            f" (+{len(gaps) - _MAX_GAPS_IN_REASON} more)" if len(gaps) > _MAX_GAPS_IN_REASON else ""
        )
        return f"{gate} — {detail}{more}"

    outcome = execute_governed_run(
        session,
        acting_tenant=str(acting_tenant),
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        run_type=RUN_TYPE_FACTOR_EXPOSURE,
        snapshot_id=snapshot.id,
        model_version_id=str(model_version_id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=_COMPLETENESS_RULE_CODE,
        rule_name=(
            "Factor-exposure run mapping completeness (every atom maps to exactly one factor)"
        ),
        rule_target_entity_type="factor_exposure_result",
        result_entity_type="factor_exposure_result",
        compute=_compute,
        format_reason=_format_reason,
    )
    return FactorExposureRunResult(
        run=outcome.run,
        status=outcome.status,
        rows=outcome.rows,
        failure_reason=outcome.failure_reason,
    )


def list_factor_exposures(
    session: Session, *, run_id: str, acting_tenant: str
) -> list[FactorExposureResult]:
    """The factor-exposure rows of a run (tenant-scoped, stable order)."""
    return list(
        session.execute(
            select(FactorExposureResult)
            .where(
                FactorExposureResult.calculation_run_id == str(run_id),
                FactorExposureResult.tenant_id == str(acting_tenant),
            )
            .order_by(
                FactorExposureResult.factor_id,
                FactorExposureResult.portfolio_id,
                FactorExposureResult.instrument_id,
            )
        )
        .scalars()
        .all()
    )


def resolve_factor_exposure_run(
    session: Session, run_id: str, *, acting_tenant: str
) -> CalculationRun:
    """Resolve a FACTOR_EXPOSURE ``calculation_run`` by ``run_id`` with an EXPLICIT tenant
    predicate + ``run_type`` filter (fail-closed). Surfaces a committed FAILED run (the durable
    refusal evidence). Raises :class:`FactorExposureRunNotVisible` on a hidden/unknown id or a
    non-factor-exposure run."""
    return resolve_run_of_type(
        session,
        run_id,
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_FACTOR_EXPOSURE,
        not_visible=FactorExposureRunNotVisible,
    )


def resolve_factor_exposure(
    session: Session, factor_exposure_id: str, *, acting_tenant: str
) -> FactorExposureResult:
    """Resolve one ``factor_exposure_result`` row by id with an EXPLICIT tenant predicate."""
    row = session.execute(
        select(FactorExposureResult).where(
            FactorExposureResult.id == str(factor_exposure_id),
            FactorExposureResult.tenant_id == str(acting_tenant),
        )
    ).scalar_one_or_none()
    if row is None:
        raise FactorExposureNotVisible(str(factor_exposure_id))
    return row
