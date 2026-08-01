"""Limit/breach ORM models (LIM-1, ENT-031 `limit_definition` + ENT-033 `breach`).

- ``LimitDefinition`` (ENT-031, **EV**) — the governed limit CONFIG header, entity-versioned in
  place (``record_version``, the ``Schedule``/``scenario_definition`` EV precedent);
  ``LIMIT.DEFINE``/``LIMIT.CHANGE`` audited (a 2L risk-manager function). A threshold + a
  ``(target_run_type, metric_type, benchmark_id?)`` metric-selector + an exact-match
  ``scope_portfolio_id`` + a ``breach_direction`` predicate + a ``limit_kind`` (HARD/SOFT). Logical
  identity ``(tenant_id, code)``.
- ``Breach`` (ENT-033, **IA TRUE append-only**) — one row per detected breach, SELF-DESCRIBING: it
  echoes the metric IDENTITY (``target_run_type``/``metric_type``/``benchmark_id``) AND the
  comparison arithmetic (``observed_value``/``threshold_value``/``threshold_unit``/
  ``breach_direction``/``limit_kind``) at detection, and FKs the evaluated governed
  ``calculation_run`` (Fable demand #1). ``UniqueConstraint(limit_definition_id,
  calculation_run_id)`` = the per-(limit, run) idempotency backstop. NOT a governed number: binds
  NO ``input_snapshot_id``/``model_version_id`` of its own (OD-B).

Both PROPRIETARY, tenant-scoped, symmetric FORCE RLS — NEVER hybrid. Migration ``0050_limit_breach``
(``limit_definition`` gets RLS only; ``breach`` gets RLS + the append-only trigger). NO ops grant.

Threshold/observed values are ``PreciseDecimal(34, 12)`` — unit-agnostic: 34-12 = 22 integer digits
match the source ``var_value`` ``(28, 6)`` range (NO overflow even in a low-unit currency), 12 scale
holds the ``te_value`` fraction — BOTH without loss (OD-C; the 4-finder overflow fold).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
    ImmutableAppendOnlyMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass


class LimitDefinition(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, TimestampMixin, Base):
    """A governed limit CONFIG header (ENT-031, EV entity-versioned in place)."""

    __tablename__ = "limit_definition"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_limit_definition_tenant_code"),
        # --- LIM-2: this table's FIRST CHECK constraints (migration 0058) ---
        # Names are SUFFIX-ONLY: `ck` is the only NAMING_CONVENTION entry keyed on
        # %(constraint_name)s, so it expands `ck_limit_definition_<name>` itself. Passing an
        # expanded name here yields `ck_limit_definition_ck_limit_definition_<name>` — the CON-1
        # 0057 defect. `test_limit_constraint_names_match_the_ORM_exactly` reads the LIVE
        # pg_constraint catalog rather than comparing this text to the migration's text, because
        # text-vs-text comparison is exactly what missed it three times.
        #
        # The dimension columns exist iff this is a concentration limit — total enumeration in
        # BOTH directions, so no other family can carry a stray dimension.
        CheckConstraint(
            "(target_run_type = 'CONCENTRATION' AND dimension_kind IS NOT NULL"
            " AND denominator_basis IS NOT NULL)"
            " OR (target_run_type <> 'CONCENTRATION' AND dimension_kind IS NULL"
            " AND bucket_code IS NULL AND issuer_id IS NULL AND scheme_family IS NULL"
            " AND authored_scheme_id IS NULL AND denominator_basis IS NULL)",
            name="concentration_shape",
        ),
        # The DISCLOSURE fence, structural. Issuer identity may live ONLY on an ISSUER-dimension
        # row — which is what makes the read fence enforceable, since the limit and breach reads
        # exclude on `issuer_id IS NOT NULL` for a caller without `concentration.issuer.view`.
        # CON-1 learned this shape the hard way: only binder discipline kept the analogous row
        # class nonexistent on `concentration_result` until its review fold made it structural.
        CheckConstraint(
            "issuer_id IS NULL OR dimension_kind = 'ISSUER'",
            name="issuer_only",
        ),
        # A classification dimension carries its scheme family; ISSUER never does.
        CheckConstraint(
            "dimension_kind IS NULL"
            " OR ((dimension_kind IN ('SECTOR_INDUSTRY', 'COUNTRY_OF_RISK'))"
            " = (scheme_family IS NOT NULL))",
            name="scheme_by_dimension",
        ),
        # VOCABULARY (a recorded Genericity departure — see the 0058 docstring): the
        # DEFINITION-TIME half of the basis discipline. A limit declaring a NAV basis is refused
        # because no such value exists; the EVALUATION-TIME half (the resolved row's basis must
        # equal this one) lives in the resolver, because a run does not exist at definition time.
        CheckConstraint(
            "denominator_basis IS NULL OR denominator_basis IN ('INVESTED_LONG')",
            name="denominator_basis_vocab",
        ),
        # VOCABULARY (same departure): total enumeration, failing CLOSED on an unenumerated kind.
        CheckConstraint(
            "dimension_kind IS NULL"
            " OR dimension_kind IN ('ISSUER', 'SECTOR_INDUSTRY', 'COUNTRY_OF_RISK')",
            name="dimension_kind_vocab",
        ),
    )

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The metric-selector (OD-C): the governed family + flavor a limit thresholds.
    target_run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    #: REQUIRED for benchmark-relative families (ACTIVE_RISK); NULL otherwise. A nullable HARD FK to
    #: ``benchmark.id`` (parity with ``active_risk_result.benchmark_id``); the selector is
    #: (run_type, metric_type, benchmark_id?).
    benchmark_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("benchmark.id"), nullable=True, index=True
    )
    #: The WITHIN-TENANT portfolio scope; bound by EXACT ``scope_portfolio_id`` match
    #: (OD-E). A hard FK — a limit targets a real book.
    scope_portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )
    #: The threshold (unit-agnostic precision) + its unit (CURRENCY/FRACTION — the guard, OD-C).
    threshold_value: Mapped[Decimal] = mapped_column(PreciseDecimal(34, 12), nullable=False)
    threshold_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The BREACH predicate (OD-D): ABOVE = breach when observed > threshold (ceiling, the default);
    #: BELOW = breach when observed < threshold (floor). Strict boundary.
    breach_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    #: HARD (binding — a breach is an incident) | SOFT (advisory — a recorded warning).
    limit_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Lifecycle status (only ACTIVE is evaluated).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- LIM-2: the dimensional selector (migration 0058). All FROZEN identity — absent from
    # `_UPDATABLE`, so a re-target is a NEW limit and a breach's echo stays meaningful (OD-I).
    # All nullable: a VaR limit has no dimension, and NULL is the honest value for it.
    #: ISSUER | SECTOR_INDUSTRY | COUNTRY_OF_RISK; NULL for a non-concentration limit.
    dimension_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: The named bucket this limit thresholds. **NULL means a RUN-LEVEL (summary-metric) limit** —
    #: the distinction between "tech <= 20%" and "max sector share <= 20%".
    bucket_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: The named issuer, when one is named. Doubles as the disclosure-fence predicate (the reads
    #: exclude on `issuer_id IS NOT NULL`). A hard FK is legal here because `issuer` is same-tenant
    #: proprietary — the `concentration_result.issuer_id` reasoning.
    issuer_id: Mapped[str | None] = mapped_column(
        GUID, ForeignKey("issuer.id"), nullable=True, index=True
    )
    #: The BINDING selector (OQ-LIM-2-1=C): the taxonomy FAMILY, not a version. A scheme revision
    #: mints a new `scheme_id`, so binding to one would silently decommission every sector limit
    #: the day a tenant adopts the next revision.
    scheme_family: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: The scheme VERSION the threshold was authored against — recorded, never bound. When the
    #: resolved run's scheme differs, `limit_health` reports drift instead of either silently
    #: re-anchoring the threshold or silently ceasing to evaluate. **No FK**:
    #: `classification_scheme` is hybrid and a PG referential check bypasses RLS, so an FK would
    #: let this proprietary row reference a scheme its own USING clause cannot see (OQ-CON-1-14).
    authored_scheme_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    #: The denominator the threshold was WRITTEN AGAINST. Half of the basis discipline; the other
    #: half is the resolver's equality check against the row actually resolved.
    denominator_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)


class Breach(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One detected breach of a limit (ENT-033, IA TRUE append-only, self-describing)."""

    __tablename__ = "breach"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        UniqueConstraint("limit_definition_id", "calculation_run_id", name="uq_breach_limit_run"),
    )

    limit_definition_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("limit_definition.id"), nullable=False, index=True
    )
    #: The evaluated governed run (Fable demand #1 — a breach FKs the run it adjudicated).
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    #: The wall-clock detection instant (operational evidence).
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The metric IDENTITY echo (OD-F) — makes the breach self-describing from its own row.
    target_run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    benchmark_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    #: The comparison ARITHMETIC echo (OD-F) — reproduces the breach from its own row.
    observed_value: Mapped[Decimal] = mapped_column(PreciseDecimal(34, 12), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(PreciseDecimal(34, 12), nullable=False)
    threshold_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    breach_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    limit_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: SOFT (advisory) | HARD (incident) — echoes ``limit_kind``.
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Breach lifecycle status (v1 = DETECTED; the lifecycle states are MG-2).
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # --- LIM-2 echoes (migration 0058). Additive-nullable with NO backfill: `breach` carries the
    # P0001 append-only trigger, so any UPDATE raises. Pre-LIM-2 rows keep NULL, which is the
    # HONEST value — they are VAR/ACTIVE_RISK breaches and have no dimension. The `var_result`
    # precedent (0038/0040/0048) is the same discipline on the same trigger.
    dimension_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bucket_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: No FK: `breach` is IA append-only evidence and echoes identity rather than referencing it
    #: (the `benchmark_id` echo precedent two fields up).
    issuer_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    scheme_family: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: The scheme the EVALUATED run actually used — deliberately NOT the limit's
    #: `authored_scheme_id`. The pair is what makes a scheme-drift breach PROVABLE from the rows
    #: alone, rather than only flagged live in `limit_health`.
    resolved_scheme_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    denominator_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: The portfolio the limit was scoped to. Pays a pre-existing gap (wave-14 planning fact 4):
    #: `breach` echoed the metric identity but never the scope, so the row was not fully
    #: self-describing against the doctrine this module's docstring states.
    scope_portfolio_id: Mapped[str | None] = mapped_column(GUID, nullable=True)


class BreachAction(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """One transition of a breach's remediation lifecycle (ENT-034, IA TRUE append-only, MG-2).

    The DEP-WFL state machine over ``breach``: ``DETECTED → ASSIGNED → RESPONDED(1L) → REVIEWED(2L)
    → CLOSED`` with an orthogonal ``ESCALATED``. The breach's OPERATIVE current state is the
    ``to_state`` of the latest action by ``seq`` (recency-derived — the VW-1 ``model_validation``
    pattern; NEVER a mutated flag, since this table is append-only). ``breach.status`` is frozen at
    ``DETECTED`` and is NOT the lifecycle source of truth (OD deprecation).
    """

    __tablename__ = "breach_action"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # per-breach monotonic ordering key (app-assigned under the parent-breach FOR UPDATE lock
        # as max(seq)+1 — race-free BECAUSE the lock serializes appends; SQLite serializes all
        # writes globally, so cross-tier without a PG-only IDENTITY). Recency = ORDER BY seq DESC.
        UniqueConstraint("breach_id", "seq", name="uq_breach_action_seq"),
        # escalate AT MOST ONCE per deadline epoch: a partial-unique index over ESCALATE rows keyed
        # by the (breach, epoch_seq) being escalated — a long-overdue breach re-selects each
        # the second insert is a benign dedup; a post-recovery ASSIGN (a NEW governing action with a
        # new seq) opens a fresh epoch so a legitimate re-escalation is admitted. The epoch key
        # governing ASSIGN action's monotonic `seq` (NOT the derived `response_due` timestamp — two
        # distinct epochs could compute the same due-time under an injected/coarse `now`, which
        # silently suppress a real escalation; VERIFIER-F1-MED1). Enforced on BOTH tiers.
        Index(
            "uq_breach_escalation",
            "breach_id",
            "epoch_seq",
            unique=True,
            postgresql_where=text("action_type = 'ESCALATE'"),
            sqlite_where=text("action_type = 'ESCALATE'"),
        ),
    )

    breach_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("breach.id"), nullable=False, index=True
    )
    #: per-breach monotonic sequence (1-based), the deterministic recency key (VERIFIER-B1).
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The transition verb ∈ BREACH_ACTION_TYPES (ASSIGN/1L_RESPONSE/2L_REVIEW/ESCALATE/CLOSE).
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The recorded transition (both stored — the log is self-describing AND the allowed-transition
    #: guard checks the observed pre-state; the LIM-1 self-describing-echo doctrine).
    from_state: Mapped[str] = mapped_column(String(20), nullable=False)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)
    #: The human principal who performed the action (the person-level SoD source); SYSTEM for
    #: auto-escalate.
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Line-of-defense tag (1L/2L/SYS) — derived from the gating permission.
    actor_line: Mapped[str] = mapped_column(String(4), nullable=False)
    #: The 1L owner assigned (populated on ASSIGN).
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: The response deadline stamped at ASSIGN (a FIXED timestamp; echoed onto the ESCALATE row as
    #: evidence of which deadline was escalated). Compared ``< now`` to decide overdue, NOT a grid.
    response_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The governing ASSIGN action's ``seq`` — the escalation epoch key (populated on ESCALATE rows
    #: only; ``uq_breach_escalation`` = one per epoch). A true monotonic id, not a derived
    #: timestamp (VERIFIER-F1-MED1).
    epoch_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The 1L remediation response / 2L review note / closure rationale.
    narrative: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    #: On 2L_REVIEW ∈ {ACCEPT, REJECT} (ACCEPT→REVIEWED, REJECT→ASSIGNED).
    review_outcome: Mapped[str | None] = mapped_column(String(10), nullable=True)
    #: Closure-evidence pointer — REQUIRED on CLOSE (REQ-BRC-003).
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: The action's wall-clock (tick ``now`` for SYSTEM; request time for humans) — evidence, NOT
    #: the recency key (``seq`` is).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


# breach + breach_action are IA TRUE append-only (the ORM guard paired with the P0001 DB triggers,
# migrations 0050/0051). limit_definition (EV) is edited in place (record_version) and is NOT.
event.listen(Breach, "before_update", _block_mutation)
event.listen(Breach, "before_delete", _block_mutation)
event.listen(BreachAction, "before_update", _block_mutation)
event.listen(BreachAction, "before_delete", _block_mutation)
