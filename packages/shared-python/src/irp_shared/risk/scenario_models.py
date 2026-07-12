"""Stress/scenario ORM models (P3-6, ENT-029 + ENT-030) — the TENTH governed number.

Three cohesive entities realizing the reserved-since-genesis scenario pair:

- ``ScenarioDefinition`` (ENT-029, **EV**) — the versioned saved scenario header (BR-8): a
  named, typed collection of factor shocks. Reference-family, entity-versioned in place
  (``record_version``, the ``factor`` EV precedent); audited ``REFERENCE.*``. A definition is BY
  the risk analyst (``risk.run``-gated), NOT vendor-captured market data.
- ``ScenarioShock`` (ENT-029 detail, **FR bitemporal**) — one signed shock per ``(definition,
  factor)``; the ``proxy_mapping`` membership protocol (capture / supersede / correct /
  reconstruct, full version history on both axes). A shock is a REVISABLE assumption —
  "what did this scenario say last quarter" is exactly the auditor question (OQ-P3-6-1).
- ``ScenarioResult`` (ENT-030 ``scenario_result``, **IA TRUE append-only**) — deterministic linear
  factor-shock P&L of a ``calculation_run``: ``pnl_i = exposure_i × shock_i`` per factor + one TOTAL
  row. RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND (the ``factor_exposure_result`` exemplar); a re-run
  is a NEW run + new rows, never an edit.

All three: PROPRIETARY, tenant-scoped, symmetric FORCE RLS — **NEVER hybrid**. Migration
``0035_scenario``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    FullReproducibleMixin,
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass

# --- controlled vocab (binder-ENFORCED, not merely doc-stated — the PA-0 fold lesson) ---
SCENARIO_TYPE_HYPOTHETICAL = "HYPOTHETICAL"
SCENARIO_TYPE_HISTORICAL = "HISTORICAL"
SCENARIO_TYPE_REGULATORY = "REGULATORY"
#: A PROVENANCE label (who/where the shock vector came from), non-load-bearing on the math.
SCENARIO_TYPES = frozenset(
    {SCENARIO_TYPE_HYPOTHETICAL, SCENARIO_TYPE_HISTORICAL, SCENARIO_TYPE_REGULATORY}
)

SHOCK_TYPE_RETURN = "RETURN"
#: v1 = a RETURN fraction (-0.10 = -10%). ABSOLUTE_BPS reserved for non-return factor families.
SHOCK_TYPES = frozenset({SHOCK_TYPE_RETURN})

#: scenario_result.metric_type vocab.
METRIC_TYPE_SCENARIO_PNL = "SCENARIO_PNL"  # one per exposed factor (shock echoed)
METRIC_TYPE_SCENARIO_PNL_TOTAL = "SCENARIO_PNL_TOTAL"  # the single factor_id-NULL total row


class ScenarioDefinition(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A versioned, named scenario definition header (ENT-029, EV; BR-8 saved assumptions).

    Entity-versioned in place (``record_version``, NOT append-only, NO system axis — the ``factor``
    EV precedent); ``REFERENCE.CREATE``/``REFERENCE.UPDATE`` audited. The shock vector lives in the
    FR ``ScenarioShock`` children. Logical identity ``(tenant_id, code)``.
    """

    __tablename__ = "scenario_definition"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_scenario_definition_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Controlled-vocab provenance label (HYPOTHETICAL/HISTORICAL/REGULATORY); binder-enforced.
    scenario_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ScenarioShock(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin, Base):
    """One signed factor shock in a scenario (ENT-029 detail, FR bitemporal).

    The ``proxy_mapping`` membership protocol: full version history on both axes, close-out
    UPDATEs (NOT append-only; content-immutability service-enforced + tested). A
    multi-row set per definition (a scenario shocks several factors). Logical key
    ``(scenario_definition_id, factor_id)``; ``shock_value`` is a signed RETURN fraction.
    """

    __tablename__ = "scenario_shock"
    __temporal_class__ = TemporalClass.FULL_REPRODUCIBLE
    __table_args__ = (
        # Exactly one OPEN shock per (definition, factor) on both axes (the FR current-head rule).
        Index(
            "uq_scenario_shock_current",
            "tenant_id",
            "scenario_definition_id",
            "factor_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL AND system_to IS NULL"),
            sqlite_where=text("valid_to IS NULL AND system_to IS NULL"),
        ),
    )

    scenario_definition_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("scenario_definition.id"), nullable=False, index=True
    )
    #: Hard FK — a live definition references live factors (the proxy_mapping precedent).
    factor_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("factor.id"), nullable=False, index=True
    )
    #: The signed shock as a canonical DECIMAL fraction (-0.10 = -10%); inert. Finiteness-guarded.
    shock_value: Mapped[Decimal] = mapped_column(PreciseDecimal(20, 12), nullable=False)
    shock_type: Mapped[str] = mapped_column(String(20), nullable=False, default=SHOCK_TYPE_RETURN)
    restatement_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("scenario_shock.id"), nullable=True
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ScenarioResult(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """Deterministic factor-shock scenario P&L of a run (ENT-030 ``scenario_result``; IA).

    **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** (the ``factor_exposure_result`` exemplar): NOT-NULL
    ``calculation_run_id`` + ``input_snapshot_id`` (a ``SCENARIO_INPUT`` snapshot pinning the
    consumed ``FACTOR_EXPOSURE`` rows + the scenario definition/shock content) + a REGISTERED
    ``model_version_id``. Grain = ``(calculation_run_id, metric_type, factor_id)`` with
    ``factor_id`` NULL exactly once (the ``SCENARIO_PNL_TOTAL`` row). Each ``SCENARIO_PNL`` row
    ECHOES its consumed ``shock_value`` + ``exposure_amount`` (auditable arithmetic). The TOTAL row
    three coverage counts (exposed / shocked / unmatched); its per-factor columns are NULL.
    ``factor_id`` is deliberately NOT a hard FK (the pinned ``COMPONENT_KIND_FACTOR`` components are
    authoritative — the ``covariance_result``/``factor_exposure_result`` precedent).
    """

    __tablename__ = "scenario_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint(
            "calculation_run_id",
            "metric_type",
            "factor_id",
            name="uq_scenario_result_run_grain",
        ),
    )

    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    model_version_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("model_version.id"), nullable=False, index=True
    )
    scenario_definition_id: Mapped[str] = mapped_column(GUID, nullable=False)
    scenario_code: Mapped[str] = mapped_column(String(150), nullable=False)
    #: SCENARIO_PNL (per exposed factor) | SCENARIO_PNL_TOTAL (the factor_id-NULL total).
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    #: NULL exactly once per run (the TOTAL row); the pinned factor otherwise (soft ref, no FK).
    factor_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    factor_code: Mapped[str | None] = mapped_column(String(150), nullable=True)
    factor_family: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: The number: pnl_i = quantize_HALF_UP(exposure_i * shock_i, 6) per factor; Σ on the TOTAL row.
    pnl: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    #: Echoed consumed inputs (per-factor rows only; NULL on the TOTAL row).
    shock_value: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 12), nullable=True)
    exposure_amount: Mapped[Decimal | None] = mapped_column(PreciseDecimal(28, 6), nullable=True)
    #: Coverage counts (the TOTAL row only; NULL on per-factor rows) — the honesty rails.
    n_factors_exposed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_factors_shocked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_shocks_unmatched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# scenario_result is IA TRUE append-only (the ORM guard paired with the migration-0035 P0001
# trigger). scenario_definition (EV) + scenario_shock (FR) are NOT append-only.
event.listen(ScenarioResult, "before_update", _block_mutation)
event.listen(ScenarioResult, "before_delete", _block_mutation)
