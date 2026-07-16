"""Model-registry ORM models (ENT-035 model/model_version, ENT-036 assumption/limitation,
ENT-037 model_validation + finding/evidence).

``model`` (EV) is the mutable governance head; ``model_version`` (IA) is the immutable, durable
anchor future ``CalculationRun``/lineage bind to (TR-11, AD-006); ``model_assumption`` /
``model_limitation`` (IA) are immutable captures tied to a version. ``model_validation`` (IA,
ENT-037, VW-1) + its ``model_validation_finding`` / ``model_validation_evidence`` children are the
append-only SR 11-7 validation records at ``model_version`` grain — the latest record per version
(by ``system_from``) is operative, and a latest-outcome ``REJECTED`` refuses new governed runs at
``assert_model_version_of``. All IA tables carry an ORM append-only guard (mirroring
``audit``/``lineage``); the migration adds the equivalent PostgreSQL trigger. ``model_type`` and
the validation vocab columns are controlled-vocabulary **strings** (no enum / no CHECK) so new
values need no schema change (MG-01 genericity). Governance columns on the head are
**non-enforcing placeholders** (reserved for REQ-MDG-002/003, P7); VW-1 makes ENT-037 the
version-grain source of truth, so ``Model.validation_status`` is deprecated-in-place (neither
written nor read by the workflow).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: Non-enforcing default for the reserved validation_status placeholder (P7 advances it, not P1A-2).
#: DEPRECATED-IN-PLACE at VW-1: ENT-037 model_validation is the version-grain source of truth; this
#: head column is neither written nor read by the validation workflow.
VALIDATION_STATUS_UNVALIDATED = "UNVALIDATED"

# --- VW-1 (ENT-037) validation-record controlled vocabularies (strings, no enum / no CHECK) ---
#: Why the validation was performed (SR 26-2 §V frequency/triggers; SS1/23 P4.5). MG-1 adds
#: EXCEPTION: the per-model, TIME-BOXED use-before-validation grant (SR 26-2 §V supplies the
#: elements — limitations attention, stakeholder notice, controls; SS1/23 P5.3(a)(i) supplies
#: "temporary" and §2.13 the grant semantics: an act of the 2L control function). An EXCEPTION
#: row must be APPROVED_WITH_CONDITIONS (the conditions ARE the controls) with next_review_due =
#: the EXPIRY, may only exist where NO non-EXCEPTION validation does (it can never substitute for
#: a revalidation), and can never follow a latest-REJECTED (it cannot un-reject). Renewal by a
#: fresh EXCEPTION is the intended re-grant path — each an audited 2L act; the renewal count is
#: deliberately unbounded (recorded MG-1 limitation; a bound is the named MG-2 candidate).
VALIDATION_TYPE_INITIAL = "INITIAL"
VALIDATION_TYPE_PERIODIC = "PERIODIC"
VALIDATION_TYPE_TRIGGERED = "TRIGGERED"
VALIDATION_TYPE_EXCEPTION = "EXCEPTION"
VALIDATION_TYPES = frozenset(
    {
        VALIDATION_TYPE_INITIAL,
        VALIDATION_TYPE_PERIODIC,
        VALIDATION_TYPE_TRIGGERED,
        VALIDATION_TYPE_EXCEPTION,
    }
)
#: The validator's verdict (OSFI E-23 / SR 11-7 p.10/15 restriction-or-reject vocabulary).
VALIDATION_OUTCOME_APPROVED = "APPROVED"
VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS = "APPROVED_WITH_CONDITIONS"
VALIDATION_OUTCOME_REJECTED = "REJECTED"
VALIDATION_OUTCOMES = frozenset(
    {
        VALIDATION_OUTCOME_APPROVED,
        VALIDATION_OUTCOME_APPROVED_WITH_CONDITIONS,
        VALIDATION_OUTCOME_REJECTED,
    }
)
#: Optional severity of a validation finding (Derman-1996 failure-mode grading).
FINDING_SEVERITY_HIGH = "HIGH"
FINDING_SEVERITY_MEDIUM = "MEDIUM"
FINDING_SEVERITY_LOW = "LOW"
FINDING_SEVERITIES = frozenset(
    {FINDING_SEVERITY_HIGH, FINDING_SEVERITY_MEDIUM, FINDING_SEVERITY_LOW}
)
#: What a piece of validation evidence points at (a governed run, or an external document).
EVIDENCE_TYPE_CALCULATION_RUN = "CALCULATION_RUN"
EVIDENCE_TYPE_DOCUMENT = "DOCUMENT"
EVIDENCE_TYPES = frozenset({EVIDENCE_TYPE_CALCULATION_RUN, EVIDENCE_TYPE_DOCUMENT})

# --- MG-1 (OD-MG-1-A/D) model-tier controlled vocabularies + the cadence policy ---
#: The DUAL ratings behind a tier — deliberately TWO axes because the two texts define two
#: different things (the MG-1 doctrine census): SR 26-2 materiality = model EXPOSURE + PURPOSE
#: ONLY ("Model purpose, together with model exposure, determines model materiality" — complexity
#: belongs to INHERENT RISK, a separate axis); SS1/23 P1.3(a)'s tier = "a risk-based materiality
#: and complexity rating". Recording both and DERIVING the tier is the only shape both texts
#: cover verbatim. Strings, service-guarded, deliberately NO DB CHECK (the MG-01 genericity
#: posture — see the module note above).
MATERIALITY_HIGH = "HIGH"
MATERIALITY_MEDIUM = "MEDIUM"
MATERIALITY_LOW = "LOW"
MATERIALITY_RATINGS = frozenset({MATERIALITY_HIGH, MATERIALITY_MEDIUM, MATERIALITY_LOW})
COMPLEXITY_RATINGS = frozenset({MATERIALITY_HIGH, MATERIALITY_MEDIUM, MATERIALITY_LOW})

MODEL_TIER_1 = "TIER_1"
MODEL_TIER_2 = "TIER_2"
MODEL_TIER_3 = "TIER_3"
MODEL_TIERS = frozenset({MODEL_TIER_1, MODEL_TIER_2, MODEL_TIER_3})

#: The tier→max-review-interval policy (calendar days), enforced as a CEILING on an approving
#: validation's next_review_due (OD-MG-1-D; CLOSES OD-032/OD-033). HONEST SOURCING — the MG-1
#: census's decisive negative fact is that NO citable source anywhere prescribes a multi-year
#: tier cadence (SR 26-2 deleted SR 11-7's "at least annually" WITHOUT replacement; SS1/23 and
#: OSFI E-23 give no numbers): TIER_1 = 365 is anchored on ECB EGIM market-risk §4.2 ¶90
#: ("at least annually", the model class our flagship belongs to — adopted voluntarily; we are
#: outside EGIM's scope like all these texts) + SS1/23 P4.5(b) ("frequency ... consistent with
#: the model tier"); TIER_2/TIER_3 = 730/1095 are HOUSE POLICY, stated as such everywhere they
#: appear. An UNTIERED model gets the TIER_1 bound — the direct continuation of VW-1's ratified
#: fail-safe ("while NO model carries a tier, every model is potentially Tier-1").
MODEL_TIER_REVIEW_MAX_DAYS: dict[str, int] = {
    MODEL_TIER_1: 365,
    MODEL_TIER_2: 730,
    MODEL_TIER_3: 1095,
}


def derive_model_tier(materiality_rating: str, complexity_rating: str) -> str:
    """The ratified MG-1 house matrix (OD-MG-1-A — HOUSE POLICY, not externally sourced):
    TIER_1 = HIGH materiality; TIER_2 = MEDIUM materiality, or LOW materiality with HIGH
    complexity (complexity can escalate one step, never de-escalate); TIER_3 = the rest.
    Ratings must be pre-validated against the vocabularies by the caller (the service verb)."""
    if materiality_rating == MATERIALITY_HIGH:
        return MODEL_TIER_1
    if materiality_rating == MATERIALITY_MEDIUM:
        return MODEL_TIER_2
    if complexity_rating == MATERIALITY_HIGH:
        return MODEL_TIER_2
    return MODEL_TIER_3


class Model(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """Model inventory head (ENT-035, EV). Governance columns (tier/validation_status/approved_use/
    restricted_use/owner/developer) and the DR-P1-3 maker-checker hooks are **non-enforcing**
    placeholders reserved for the P7 validation/approval workflow — P1A-2 gates on none of them."""

    __tablename__ = "model"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_model_tenant_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Controlled-vocab string (NO enum / NO CHECK) — new model families register by value (MG-01).
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Non-enforcing governance placeholders — reserved for REQ-MDG-002/003 (P7); gate nothing.
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    developer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    validation_status: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default=VALIDATION_STATUS_UNVALIDATED
    )
    approved_use: Mapped[str | None] = mapped_column(String(500), nullable=True)
    restricted_use: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    restriction_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # DR-P1-3 maker-checker hooks — nullable, non-enforcing (P6).
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    made_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ModelVersion(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable model version (ENT-035, IA) — the stable referent for future
    ``CalculationRun.model_version_id`` and run->result lineage (change = new version, MG-10)."""

    __tablename__ = "model_version"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "model_id", "version_label", name="uq_model_version_tenant_model_label"
        ),
    )

    model_id: Mapped[str] = mapped_column(GUID, ForeignKey("model.id"), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    methodology_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Version status (e.g. DRAFT/REGISTERED). ENFORCING at the RISK bind since P3-C1
    # (risk.bootstrap.assert_model_version_of requires 'REGISTERED'); still NOT a validation
    # gate (P7) and non-enforcing for generic registry consumers.
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ModelAssumption(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable assumption tied to a version (ENT-036, IA)."""

    __tablename__ = "model_assumption"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    assumption_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # MG-05 attribution: free string accepting a human OR an AI-agent principal id.
    authored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ModelLimitation(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Immutable limitation tied to a version (ENT-036, IA; BX-LIM/CTRL-014)."""

    __tablename__ = "model_limitation"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    limitation_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ModelValidation(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """An SR 11-7 validation record at ``model_version`` grain (ENT-037, IA; VW-1).

    A point-in-time human governance judgment — the capture-side pattern, NOT a governed number
    (it binds no snapshot / no run / no methodology model_version). The LATEST record per version
    (by ``system_from``, PK-tiebroken) is operative; a latest-outcome ``REJECTED`` refuses new
    governed runs on the version at ``assert_model_version_of`` (CTRL-022). ``conditions`` is
    required iff ``outcome == APPROVED_WITH_CONDITIONS``; ``next_review_due`` is required for the
    two approving outcomes and refused for ``REJECTED`` — both binder-side fail-closed guards."""

    __tablename__ = "model_validation"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    #: The latest-read (WHERE tenant_id=? AND model_version_id=? ORDER BY system_from DESC, id DESC
    #: LIMIT 1) that OD-B's gate and the readers run — a composite serving both the point query and
    #: the per-version listing (the FK column is not separately indexed; this covers it). The id
    #: leg is a DETERMINISM tiebreaker (stable plan), not write-order recency — see
    #: ``validation.latest_validation``.
    __table_args__ = (
        Index("ix_model_validation_latest", "tenant_id", "model_version_id", "system_from"),
    )

    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False
    )
    validation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    conditions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    report_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_review_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    validated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class ModelValidationFinding(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """An append-only finding on a validation record (ENT-037, IA; VW-1). Severity is optional —
    an unranked observation is a legitimate record (Derman-1996)."""

    __tablename__ = "model_validation_finding"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    validation_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_validation.id"), nullable=False, index=True
    )
    finding_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ModelValidationEvidence(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """An append-only evidence citation on a validation record (ENT-037, IA; VW-1). A
    ``CALCULATION_RUN`` row hard-FKs the cited governed run (re-resolved tenant-visible + COMPLETED
    pre-stamp — the PA-3 precedent), so a BT-1 backtest becomes first-class outcomes-analysis
    evidence (FRTB MAR32). A ``DOCUMENT`` row carries a free-text ``reference`` instead."""

    __tablename__ = "model_validation_evidence"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY

    validation_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_validation.id"), nullable=False, index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=True, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(500), nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# model is EV (mutable) — only the IA tables get the ORM append-only guard.
for _ia_model in (
    ModelVersion,
    ModelAssumption,
    ModelLimitation,
    ModelValidation,
    ModelValidationFinding,
    ModelValidationEvidence,
):
    event.listen(_ia_model, "before_update", _block_mutation)
    event.listen(_ia_model, "before_delete", _block_mutation)
