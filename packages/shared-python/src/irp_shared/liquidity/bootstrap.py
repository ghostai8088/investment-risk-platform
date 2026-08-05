"""LQ-1 registrar — ``risk.liquidity_tiers`` with its declared parameters.

The declared methodology choices (ratified OQ-LQ-1-4/5/9/15/19) ride ``model_assumption`` TEXT rows
under declared prefixes and are parsed back by the binder with an EXACT-IDENTITY refusal.

**Why this family is model-bound at all** (the gate's sharpest cost question): the illiquid share
embeds at least four methodology choices — which tier codes count as illiquid, the denominator, the
as-of convention, and the coverage floor. Without a registered version there is nowhere to declare
them, so redefining the illiquid partition later would retroactively re-label the meaning of every
historical append-only row while the stored numbers stayed byte-identical. The parse-back below is
what makes that impossible rather than merely discouraged.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from irp_shared.classification.models import LIQUIDITY_TIER_CODES, TIER_ILLIQUID
from irp_shared.model.assumptions import load_assumption_texts
from irp_shared.model.models import ModelVersion
from irp_shared.model.service import (
    ModelVersionConflictError,
    WrongModelVersionError,
    register_model_version,
    resolve_or_register_model,
    resolve_or_register_version,
)


class LiquidityModelParameterError(ValueError):
    """A CLIENT-supplied model parameter is invalid (registration refuses).

    A dedicated type, not bare ``ValueError``: the API error map keys on exact type, so a bare
    ``ValueError`` would relabel any genuine server-side bug inside registration as a client 422
    and re-arm the API-2 MRO trap. Subclassing ``ValueError`` keeps existing callers intact.
    """


LIQUIDITY_MODEL_CODE = "risk.liquidity_tiers"
LIQUIDITY_MODEL_NAME = "Liquidity tier distribution (illiquid / highly-liquid share)"
LIQUIDITY_MODEL_TYPE = "LIQUIDITY"
LIQUIDITY_VERSION_LABEL = "v1"
#: RPT-1 (2026-08-05): was the PROSE string "docs: LQ-1 decision record Parts 1-2
#: (OQ-LQ-1-1..20)". Now a resolving path — a report renders this ref, and the census in
#: test_methodology_refs.py fails on any non-resolving one.
LIQUIDITY_METHODOLOGY_REF = "05_analytics_methodologies/liquidity_tiers_v1.md"

#: Assumption prefixes (the CON-1 / pacing convention: prefix + canonical value, one row each).
DENOMINATOR_BASIS_PREFIX = "liquidity.denominator_basis="
LONG_PREDICATE_PREFIX = "liquidity.long_predicate="
SCOPE_PREFIX = "liquidity.scope="
TIER_AS_OF_PREFIX = "liquidity.tier_as_of="
TIER_VOCABULARY_PREFIX = "liquidity.tier_vocabulary="
ILLIQUID_PARTITION_PREFIX = "liquidity.illiquid_partition="
COVERAGE_FLOOR_PREFIX = "liquidity.coverage_floor="
TIER_MAX_AGE_DAYS_PREFIX = "liquidity.tier_max_age_days="

#: The ratified fixed declarations (v1 admits exactly these values).
#:
#: ``illiquid_partition`` is a SINGLE named category, not a configurable subset — 22e-4(b)(1)(ii)
#: names four categories and exactly one of them is "illiquid investment". Declaring it as a set of
#: one rather than hard-coding it is what lets a future ladder (e.g. AIFMD's seven day-buckets)
#: declare a genuinely different partition and be refused against v1 rather than silently accepted.
_FIXED_ASSUMPTIONS: tuple[str, ...] = (
    f"{DENOMINATOR_BASIS_PREFIX}INVESTED_LONG",
    f"{LONG_PREDICATE_PREFIX}VALUE_SIGN",
    f"{SCOPE_PREFIX}EXPOSURE_RUN_SUBTREE",
    f"{TIER_AS_OF_PREFIX}BUILD",
    f"{TIER_VOCABULARY_PREFIX}SEC_22E4:" + "|".join(LIQUIDITY_TIER_CODES),
    f"{ILLIQUID_PARTITION_PREFIX}{TIER_ILLIQUID}",
)

_METHODOLOGY_TEXT = (
    "illiquid_share_invested_long = ILLIQUID long / total long, long = signed exposure_amount > 0 "
    "(VALUE SIGN, not position direction); an instrument with no current-head LIQUIDITY_TIER is "
    "UNCLASSIFIED and stays IN the denominator and IN the classifiable-coverage test; tier heads "
    "are resolved as-of BUILD and refused when older than the declared max age; shares are taken "
    "from UNROUNDED ratios then quantized HALF_UP 6dp; the run refuses below the declared "
    "coverage floor."
)

#: The ratified limitations, in the record's words. These are the rows the FE surfaces next to the
#: number (OQ-LQ-1-8) — a limitation no screen renders is not a control.
LIQUIDITY_LIMITATIONS: tuple[str, ...] = (
    "This is NOT the SEC Rule 22e-4 15% test. The rule's ratio is against NET ASSETS "
    "(17 CFR 270.22e-4(b)(1)(iv)); this denominator is the invested-long book, which excludes "
    "cash, receivables and any asset carrying no exposure row, and includes no liabilities. The "
    "reported share may OVERSTATE or UNDERSTATE the regulatory ratio depending on the book's "
    "cash, leverage and short exposure, and THE DIRECTION IS NOT DETERMINABLE without a "
    "net-assets figure. Limits are refused against this family until a NAV entity exists.",
    "Tier assignment is INSTRUMENT-grain and therefore does not reflect the fund-specific "
    "position-size determination 22e-4(b)(1)(ii)(B) requires ('the fund must determine whether "
    "trading varying portions of a position ... is reasonably expected to significantly affect "
    "its liquidity, and if so, the fund must take this determination into account'). Two funds "
    "holding the same security at very different sizes receive the same tier here.",
    "Tiers are captured judgments, not computed: the platform records an assessment and never "
    "derives one. Tier heads are resolved as-of BUILD, so a backdated exposure run is tiered by "
    "build-time heads; heads older than the declared max age refuse the run rather than pinning "
    "a stale ladder.",
    "The highly-liquid coverage figure is the ladder's first category only. It is NOT "
    "22e-4(b)(1)(iii)'s highly liquid investment minimum, which is net-assets-denominated and "
    "carries board-approval, review and shortfall-reporting obligations this platform does not "
    "implement.",
)

_DECIMAL_6DP = Decimal("0.000001")


def _canonical_floor(value: Decimal) -> str:
    return str(Decimal(str(value)).quantize(_DECIMAL_6DP))


def _assumption_rows(coverage_floor: Decimal, tier_max_age_days: int) -> tuple[str, ...]:
    return (
        *_FIXED_ASSUMPTIONS,
        f"{COVERAGE_FLOOR_PREFIX}{_canonical_floor(coverage_floor)}",
        f"{TIER_MAX_AGE_DAYS_PREFIX}{int(tier_max_age_days)}",
        _METHODOLOGY_TEXT,
    )


def register_liquidity_model(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    code_version: str,
    coverage_floor: Decimal,
    tier_max_age_days: int = 31,
    version_label: str = LIQUIDITY_VERSION_LABEL,
    actor_type: str = "user",
) -> ModelVersion:
    """Register (idempotently) the liquidity family.

    ``tier_max_age_days`` defaults to 31 because 22e-4(b)(1)(ii) requires review "at least
    monthly"; a head older than that is a defect the platform should refuse rather than silently
    pin. It is a DECLARED parameter rather than a constant so a tenant with a stricter internal
    policy can register a shorter bound and have it enforced.
    """
    if not version_label or not str(version_label).strip():
        raise LiquidityModelParameterError("version_label must be a non-empty string")

    floor = Decimal(str(coverage_floor))
    # STRICTLY positive, for the reason CON-1's review established: a zero floor is not a
    # permissive setting, it is a broken one. A wholly untiered book has coverage 0, which clears
    # a zero floor, so the run would COMPLETE and write an illiquid share of 0.000000 over a book
    # nobody has classified — an immutable IA row asserting "no illiquid holdings" about a book
    # that was never assessed. That is the single most dangerous number this family could emit.
    if not (Decimal("0") < floor <= Decimal("1")):
        raise LiquidityModelParameterError(
            f"coverage_floor must be a fraction in (0, 1], got {floor}"
        )
    if int(tier_max_age_days) <= 0:
        raise LiquidityModelParameterError(
            f"tier_max_age_days must be a positive integer, got {tier_max_age_days}"
        )

    model = resolve_or_register_model(
        session,
        tenant_id=str(tenant_id),
        code=LIQUIDITY_MODEL_CODE,
        name=LIQUIDITY_MODEL_NAME,
        model_type=LIQUIDITY_MODEL_TYPE,
        actor_id=actor_id,
        description=(
            "Liquidity tier distribution over a pinned exposure run: per-tier share detail rows "
            "over the SEC 22e-4 ladder + ILLIQUID_SHARE and HIGHLY_LIQUID_SHARE summary metrics, "
            "an UNCLASSIFIED residual that stays in the denominator, and a coverage refusal floor."
        ),
        actor_type=actor_type,
    )
    assumptions = _assumption_rows(floor, int(tier_max_age_days))
    version = resolve_or_register_version(
        session,
        model=model,
        version_label=str(version_label),
        register=lambda: register_model_version(
            session,
            model=model,
            version_label=str(version_label),
            actor_id=actor_id,
            methodology_ref=LIQUIDITY_METHODOLOGY_REF,
            code_version=str(code_version),
            status="REGISTERED",
            assumptions=assumptions,
            limitations=LIQUIDITY_LIMITATIONS,
            actor_type=actor_type,
        ),
    )
    if version.status != "REGISTERED":
        raise WrongModelVersionError(str(version.id), LIQUIDITY_MODEL_CODE)
    if version.code_version != str(code_version):
        raise ModelVersionConflictError(LIQUIDITY_MODEL_CODE, str(version_label), str(code_version))
    existing = set(load_assumption_texts(session, version))
    if existing and existing != set(assumptions):
        raise ModelVersionConflictError(LIQUIDITY_MODEL_CODE, str(version_label), str(code_version))
    return version


def declared_liquidity_parameters(session: Session, version: ModelVersion) -> tuple[Decimal, int]:
    """Parse back ``(coverage_floor, tier_max_age_days)`` with an EXACT-IDENTITY refusal.

    Any missing, extra, or changed assumption refuses the bind rather than computing under a
    silently different methodology. This is the mechanism the whole model-bound decision rests on:
    without it, editing the illiquid partition would re-label every historical row's meaning while
    the stored numbers stayed byte-identical.
    """
    texts = set(load_assumption_texts(session, version))

    floors = [t for t in texts if t.startswith(COVERAGE_FLOOR_PREFIX)]
    ages = [t for t in texts if t.startswith(TIER_MAX_AGE_DAYS_PREFIX)]
    if len(floors) != 1 or len(ages) != 1:
        raise WrongModelVersionError(str(version.id), LIQUIDITY_MODEL_CODE)

    expected = {*_FIXED_ASSUMPTIONS, floors[0], ages[0], _METHODOLOGY_TEXT}
    if texts != expected:
        raise WrongModelVersionError(str(version.id), LIQUIDITY_MODEL_CODE)

    try:
        floor = Decimal(floors[0].removeprefix(COVERAGE_FLOOR_PREFIX))
        max_age = int(ages[0].removeprefix(TIER_MAX_AGE_DAYS_PREFIX))
    except (InvalidOperation, ValueError) as exc:
        raise WrongModelVersionError(str(version.id), LIQUIDITY_MODEL_CODE) from exc

    # Re-check the RANGES on the way back out, not only on the way in. A row edited directly in the
    # database would otherwise reach the kernel as a valid-looking parameter.
    if not (Decimal("0") < floor <= Decimal("1")) or max_age <= 0:
        raise WrongModelVersionError(str(version.id), LIQUIDITY_MODEL_CODE)
    return floor, max_age
