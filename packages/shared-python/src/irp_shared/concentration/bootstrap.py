"""CON-1 registrar — ``concentration.dimensional`` with its declared parameters.

The declared methodology choices (OQ-CON-1-1/2/3/4) ride ``model_assumption`` TEXT rows under
declared prefixes and are parsed back by the binder with an EXACT-IDENTITY refusal (the
``declared_pacing_parameters`` precedent; NEVER ``assumption_set_id``, which has zero writers).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from irp_shared.model.assumptions import load_assumption_texts
from irp_shared.model.models import ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
)

CONCENTRATION_MODEL_CODE = "concentration.dimensional"
CONCENTRATION_MODEL_NAME = "Dimensional concentration (share / CR-N / HHI)"
CONCENTRATION_MODEL_TYPE = "CONCENTRATION"
CONCENTRATION_VERSION_LABEL = "v1"
CONCENTRATION_METHODOLOGY_REF = "docs: CON-1 decision record Parts 1-2 (OQ-CON-1-1..28)"

#: The assumption prefixes (the pacing convention: prefix + canonical value, one row each).
DENOMINATOR_BASIS_PREFIX = "concentration.denominator_basis="
LONG_PREDICATE_PREFIX = "concentration.long_predicate="
SCOPE_PREFIX = "concentration.scope="
CLASSIFICATION_AS_OF_PREFIX = "concentration.classification_as_of="
CR_N_PREFIX = "concentration.cr_n="
HHI_SCALE_PREFIX = "concentration.hhi_scale="
COVERAGE_FLOOR_PREFIX = "concentration.coverage_floor="

#: The ratified fixed declarations (v1 admits exactly these values).
_FIXED_ASSUMPTIONS: tuple[str, ...] = (
    f"{DENOMINATOR_BASIS_PREFIX}INVESTED_LONG",
    f"{LONG_PREDICATE_PREFIX}VALUE_SIGN",
    f"{SCOPE_PREFIX}EXPOSURE_RUN_SUBTREE",
    f"{CLASSIFICATION_AS_OF_PREFIX}BUILD",
    f"{CR_N_PREFIX}5",
    f"{HHI_SCALE_PREFIX}FRACTION",
)

#: The methodology sentence carried as an assumption row (the pacing precedent).
_METHODOLOGY_TEXT = (
    "share_invested_long(bucket) = bucket long / total long, long = signed exposure_amount > 0 "
    "(VALUE SIGN, not position direction); residuals (UNCLASSIFIED / UNCLASSIFIABLE, "
    "per-dimension predicates) stay IN the denominator and OUT of rankings and HHI; HHI/CR-5/MAX "
    "over CLASSIFIED buckets from UNROUNDED ratios then quantized HALF_UP 6dp; classifiable "
    "coverage = classified/(classified+UNCLASSIFIED) gated by the declared floor; scope = the "
    "exposure run's subtree; classification as-of BUILD."
)

#: The ratified limitation, in the record's words (OQ-CON-1-1).
CONCENTRATION_LIMITATIONS: tuple[str, ...] = (
    "share_invested_long is NOT the UCITS Art. 52, IRC 851(b)(3), Solvency II or BCBS ratio; no "
    "denominator those regimes require is computable on this schema. Regulatory-shaped limits "
    "are refused until LIM-2's basis machinery exists (no _METRIC_MAP registration in CON-1).",
    "Classification is as-of-BUILD (a backdated exposure run buckets by build-time heads); the "
    "long/short decomposition is by VALUE SIGN; HHI is downward-biased by coverage on "
    "partially-covered books (bounded by the declared coverage_floor); a refused-run streak "
    "leaves any future limit evaluating the LAST COMPLETED run (staleness routed to "
    "limit_health at LIM-2).",
)

_DECIMAL_6DP = Decimal("0.000001")


def _canonical_floor(value: Decimal) -> str:
    return str(Decimal(str(value)).quantize(_DECIMAL_6DP))


def _assumption_rows(coverage_floor: Decimal) -> tuple[str, ...]:
    return (
        *_FIXED_ASSUMPTIONS,
        f"{COVERAGE_FLOOR_PREFIX}{_canonical_floor(coverage_floor)}",
        _METHODOLOGY_TEXT,
    )


def register_concentration_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    coverage_floor: Decimal,
    version_label: str = CONCENTRATION_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the concentration family. Same-label different-declaration →
    ``ModelVersionConflictError``; a non-REGISTERED same-label twin → ``WrongModelVersionError``
    (the P3-C1 contract, the pacing registrar's tail verbatim)."""
    if not version_label or not str(version_label).strip():
        raise ValueError("version_label must be a non-empty string")
    floor = Decimal(str(coverage_floor))
    if not (Decimal("0") <= floor <= Decimal("1")):
        raise ValueError(f"coverage_floor must be a fraction in [0, 1], got {floor}")

    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=CONCENTRATION_MODEL_CODE,
        name=CONCENTRATION_MODEL_NAME,
        model_type=CONCENTRATION_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Dimensional concentration over a pinned exposure run: per-bucket "
            "share_invested_long detail rows + MAX/HHI/CR-5 summary metrics per dimension "
            "(ISSUER / SECTOR_INDUSTRY / COUNTRY_OF_RISK), per-dimension residuals, and a "
            "classifiable-coverage refusal floor."
        ),
        actor_type=actor_type,
    )
    assumptions = _assumption_rows(floor)
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=CONCENTRATION_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=assumptions,
            limitations=CONCENTRATION_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), CONCENTRATION_MODEL_CODE)
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(
            CONCENTRATION_MODEL_CODE, str(version_label), str(code_version)
        )
    existing = set(load_assumption_texts(session, version))
    if existing and existing != set(assumptions):
        raise ModelVersionConflictError(
            CONCENTRATION_MODEL_CODE, str(version_label), str(code_version)
        )
    return version


def declared_concentration_parameters(session: Session, version: ModelVersion) -> Decimal:
    """Parse back the declared ``coverage_floor`` with an EXACT-IDENTITY refusal over the full
    declared set: any missing, extra, or changed fixed assumption refuses the bind rather than
    computing under a silently different methodology. Returns the coverage floor."""
    texts = set(load_assumption_texts(session, version))
    floors = [t for t in texts if t.startswith(COVERAGE_FLOOR_PREFIX)]
    if len(floors) != 1:
        raise WrongModelVersionError(str(version.id), CONCENTRATION_MODEL_CODE)
    expected = {*_FIXED_ASSUMPTIONS, floors[0], _METHODOLOGY_TEXT}
    if texts != expected:
        raise WrongModelVersionError(str(version.id), CONCENTRATION_MODEL_CODE)
    try:
        floor = Decimal(floors[0].removeprefix(COVERAGE_FLOOR_PREFIX))
    except InvalidOperation as exc:
        raise WrongModelVersionError(str(version.id), CONCENTRATION_MODEL_CODE) from exc
    if not (Decimal("0") <= floor <= Decimal("1")):
        raise WrongModelVersionError(str(version.id), CONCENTRATION_MODEL_CODE)
    return floor
