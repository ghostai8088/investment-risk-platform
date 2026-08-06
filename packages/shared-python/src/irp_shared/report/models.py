"""ENT-072 ``report_generation`` — the durable record of one generated risk report (RPT-1).

**The design decision worth stating: a report binds ONE SNAPSHOT, not a bindings table.**

A report covers several governed families (v1: total VaR + ES, concentration, liquidity, rolling
risk/Sharpe), so the obvious shape is a child table with one row per bound run. That was refused.
The platform already has a rail whose entire purpose is "pin the exact inputs a governed act
consumed, immutably, so the act can be re-performed" — ``dataset_snapshot`` +
``dataset_snapshot_component``. A report is that act. Minting a parallel bindings table would have
been a second pinning mechanism with its own drift, its own reconstruction semantics and its own
bugs, next to a shipped one that has carried twenty-four families.

So a ``REPORT_INPUT`` snapshot pins the family results, and this row binds that snapshot. The
consequences fall out rather than being engineered:

- **I1 (bound at generation time, never re-derived at render time)** — the renderer reads pinned
  component content only, the same AD-014 / TR-09 discipline every kernel follows.
- **I2 (byte-identical regeneration)** — same snapshot + same renderer version ⇒ same bytes, and
  ``content_hash`` is the check rather than a promise.
- **I3 (a superseded input regenerates the ORIGINAL)** — snapshot components are immutable, so a
  later correction upstream cannot reach a historical report. This is inherited, not re-argued.

``content_hash`` is stored, not merely computed on demand, because the interesting failure is
"regeneration produced something different" — and detecting that requires the original hash to have
survived independently of the code that regenerates it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: The v1 report's registered identity (ratified OQ-RPT-1-1: the §2.1 spine).
REPORT_CODE_RISK_SUMMARY = "report.risk_summary"
REPORT_VERSION_LABEL_V1 = "v1"

#: The rendering format (ratified OQ-RPT-1-2: HTML print-clean; no PDF pipeline in v1). Stored on
#: the row because the hash is over the RENDERED bytes — a format change is a different artifact,
#: and a regeneration that silently switched format would otherwise look like a hash mismatch of
#: unknown cause.
RENDER_FORMAT_HTML = "HTML"
RENDER_FORMATS: tuple[str, ...] = (RENDER_FORMAT_HTML,)

#: The run family (declared HERE, in models, not in service.py — the GS2 census walks ``*.events``
#: and ``*.models`` modules, so a RUN_TYPE_* declared in a service module escapes the very guard
#: that exists to catch a run family colliding with a metric name; LQ-1 found this by running it).
RUN_TYPE_REPORT = "REPORT"


class ReportGeneration(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """IA append-only: one row per generated report, run-bound and snapshot-gated.

    A generated report is governed EVIDENCE — what was shown to whom, on what basis, when. Mutating
    or deleting one would defeat the purpose, so the same append-only bar every other governed
    artifact carries applies here.
    """

    __tablename__ = "report_generation"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # One generation per (run, portfolio). The run is the act; a second row against the same run
        # would mean the same generation produced two records. Fully NOT NULL — a nullable column
        # inside a UNIQUE key is VACUOUS on PostgreSQL (NULLS DISTINCT), the defect CON-1 shipped.
        # Declared for BOTH dialects: the unit tier builds via create_all and would not otherwise
        # exercise this at all.
        Index(
            "uq_report_generation_run_portfolio",
            "calculation_run_id",
            "portfolio_id",
            unique=True,
        ),
        Index("ix_report_generation_lookup", "tenant_id", "report_code", "as_of_date"),
    )

    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    #: The REPORT_INPUT snapshot pinning every family result this report renders. NOT NULL: a
    #: report that cannot name its pinned inputs is not reproducible, which is the whole claim.
    input_snapshot_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("dataset_snapshot.id"), nullable=False, index=True
    )
    portfolio_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("portfolio.id"), nullable=False, index=True
    )

    #: The portfolio code AS RENDERED, pinned at generation (RPT-1 pre-merge audit, B1).
    #:
    #: The first version left this to the caller at BOTH generate and regenerate, and stored it
    #: nowhere. It is rendered into the ``<h1>`` and therefore into the hashed bytes, so a report
    #: was reproducible only by a caller who remembered the exact string — and ``portfolio.code`` is
    #: an effective-dated, MUTABLE field, so after a rename nobody could. The asymmetry was the
    #: tell: ``as_of_date``, the other report-level rendered value, was already read back here.
    #: Everything the bytes depend on is pinned, or the identity claim is conditional on memory.
    portfolio_code: Mapped[str] = mapped_column(String(150), nullable=False)

    report_code: Mapped[str] = mapped_column(String(100), nullable=False)
    report_version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    render_format: Mapped[str] = mapped_column(String(20), nullable=False)

    #: The as-of date the report speaks about — distinct from ``generated_at``, which is when it was
    #: produced. Conflating them is how a backdated report silently becomes a current one.
    as_of_date: Mapped[date] = mapped_column(nullable=False)

    #: SHA-256 over the rendered bytes. The identity proof's stored side (see the module docstring).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    #: When the report was produced, as ASSERTED BY THE CALLER (pre-merge audit, N3).
    #:
    #: Deliberately a parameter, so a batch regenerating last quarter's pack can state the economic
    #: production time rather than the wall clock of the backfill. The honest consequence, recorded
    #: rather than left for a reader to discover: on a governed evidence artifact this field is a
    #: CLAIM, not a measurement. The DB-stamped ``system_from`` from ``ImmutableAppendOnlyMixin`` is
    #: the knowledge time nobody can assert, and the two are separate columns precisely so a
    #: disagreement between them is visible. **Before any API exposes this verb, decide whether an
    #: external caller may set it at all** — an HTTP client asserting when its own evidence was
    #: created is a different trust posture from an in-process batch doing so.
    generated_at: Mapped[datetime] = mapped_column(nullable=False)
    generated_by: Mapped[str] = mapped_column(String(200), nullable=False)


@event.listens_for(ReportGeneration, "before_update", propagate=True)
def _refuse_report_generation_update(
    _mapper: Mapper[Any], _connection: Any, _target: ReportGeneration
) -> None:
    """ORM-side append-only guard (the DB trigger is the real fence; this is the fast, local one).

    Defence in depth, deliberately: the migration installs ``irp_prevent_mutation`` so a raw SQL
    UPDATE is refused by PostgreSQL regardless of the application. This listener catches the ORM
    path early with a clearer message, and — the reason it earns its place — makes the refusal
    testable on the SQLite tier, where no trigger exists.
    """
    raise AppendOnlyViolation("report_generation is IMMUTABLE_APPEND_ONLY — UPDATE refused")


@event.listens_for(ReportGeneration, "before_delete", propagate=True)
def _refuse_report_generation_delete(
    _mapper: Mapper[Any], _connection: Any, _target: ReportGeneration
) -> None:
    raise AppendOnlyViolation("report_generation is IMMUTABLE_APPEND_ONLY — DELETE refused")


__all__ = [
    "RENDER_FORMATS",
    "RENDER_FORMAT_HTML",
    "REPORT_CODE_RISK_SUMMARY",
    "REPORT_VERSION_LABEL_V1",
    "RUN_TYPE_REPORT",
    "ReportGeneration",
]
