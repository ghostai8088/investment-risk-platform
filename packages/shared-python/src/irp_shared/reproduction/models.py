"""ENT-073 ``reproduction_check`` — the durable verdict of one reproduction attempt (REPRO-1).

**What this row is, and what it deliberately is not.** It is CONTROL-PLANE EVIDENCE about an
already-audited governed run: "on this night, we re-executed run X over its own pinned snapshot and
the numbers came back the same." It binds no ``dataset_snapshot`` and no ``model_version`` of its
own, exactly as ``breach`` / ``breach_action`` do — those reference the already-audited
``CALC.RUN_*`` run rather than re-pinning its inputs. A verdict is not a governed derived number,
so it does not carry the three-way bind that AD-014 requires of one.

It DOES bind a ``calculation_run`` of run type ``REPRODUCTION`` — the reproduction sweep itself is a
computation with a ``code_version`` and an ``environment_id``, and the scheduler's ratified
invariant (OQ-SCH-2-8) is that a schedule's family key IS a real ``calculation_run.run_type``, not a
parallel vocabulary. That reproduction run's ``input_snapshot_id`` is NULL and honestly so: one
sweep consumes many subject runs' snapshots, and each one is named on its own verdict row via
``subject_run_id`` rather than smeared into a single binding.

**Why the divergence detail names fields and keys but never VALUES.** ``first_divergence`` records
WHICH row and WHICH field disagreed, never the two numbers. The moment a read surface is added over
this table it will be gated by some permission — and the obvious candidate, ``schedule.view``, is
held by ``auditor_3l``, which holds no ``valuation.view`` / ``position.view`` / ``marketdata.view``.
Writing governed values into a control-plane table now would plant exactly the disclosure RPT-2's
pre-merge audit found through a different door (a report surface serving issuer rows that
``concentration.issuer.view`` exists to withhold). The field name and the natural key are enough to
investigate; the values are one authorised query away for whoever is entitled to them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import ImmutableAppendOnlyMixin, PrimaryKeyMixin, TenantMixin
from irp_shared.db.types import GUID
from irp_shared.temporal import TemporalClass

#: The reproduction sweep's own run family (declared HERE, in ``models``, not in ``service`` — the
#: GS2 run-type census walks ``*.events`` and ``*.models`` only, so a ``RUN_TYPE_*`` declared in a
#: service module escapes the guard that exists to catch a run family colliding with a metric name.
#: RPT-1 learned this by running the census; REPRO-1 does not re-learn it.)
RUN_TYPE_REPRODUCTION = "REPRODUCTION"


class ReproductionCheck(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base):
    """IA append-only: one verdict per (reproduction run, subject run).

    Append-only for the ordinary reason every governed-evidence table is: a verdict that could be
    edited after the fact is not evidence. The DB trigger is the real fence; the ORM listeners
    below make the refusal testable on the SQLite tier, where no trigger exists.
    """

    __tablename__ = "reproduction_check"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # One verdict per (sweep, subject). A second row against the same pair would mean one sweep
        # reached two conclusions about one run. Both columns NOT NULL — a nullable column inside a
        # UNIQUE key is VACUOUS on PostgreSQL (NULLS DISTINCT), the defect CON-1 shipped and CAL-1b
        # re-found. Declared for BOTH dialects: the unit tier builds via create_all.
        Index(
            "uq_reproduction_check_sweep_subject",
            "calculation_run_id",
            "subject_run_id",
            unique=True,
        ),
        Index("ix_reproduction_check_lookup", "tenant_id", "family_key", "verdict"),
    )

    #: The REPRODUCTION sweep run that produced this verdict.
    calculation_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    #: The governed run that was re-executed. A hard FK: a verdict about a run that does not exist
    #: is not evidence of anything.
    subject_run_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("calculation_run.run_id"), nullable=False, index=True
    )
    #: The subject's ``run_type`` — echoed so the row is self-describing without a join, and so the
    #: per-family coverage of a night's sweep is readable directly.
    family_key: Mapped[str] = mapped_column(String(100), nullable=False)

    #: MATCH | DIVERGED | UNREPRODUCIBLE (``events.VERDICTS``).
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)

    #: How many stored rows were compared, and how many disagreed. ``rows_compared == 0`` with a
    #: MATCH verdict is impossible by construction (the engine refuses it) — a comparison that
    #: compared nothing has proven nothing, and reporting it as a pass is how a control becomes
    #: decorative.
    rows_compared: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_diverged: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The first disagreement, as ``<natural key> :: <field>`` — never the values (see the
    #: module docstring).
    #: On UNREPRODUCIBLE this carries the REASON the recompute could not run, redacted like
    #: ``scheduling.service.redact_failure_reason`` does for the same class of operator-facing text.
    first_divergence: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NOTE: there is deliberately NO ``alarm_delivered`` column here, and the reason is structural
    # rather than aesthetic. This table is append-only, so a delivery outcome learned AFTER the
    # verdict was written could never be recorded on it — which would force delivery to happen
    # inside the sweep's transaction, and that transaction holds the per-tenant audit advisory lock
    # (``record_event`` takes it, held to top-level COMMIT). Calling a network sink there is the
    # API-2b lock-across-I/O anti-pattern that NOTIF-1's phase-A/phase-B split exists to prevent.
    # So alarm delivery is its own tick phase, after the phases-1-2 commit, and its durable
    # evidence is a ``NOTIFY.DISPATCH`` audit event against ``entity_type='reproduction_check'``.
    # "Has this verdict been alarmed?" is then answered by that event's EXISTENCE — a per-row
    # question with no cursor to get wrong (NOTIF-1's own lesson: a derived MAX cursor cannot
    # represent a gap).


@event.listens_for(ReproductionCheck, "before_update", propagate=True)
def _refuse_reproduction_check_update(
    _mapper: Mapper[Any], _connection: Any, _target: ReproductionCheck
) -> None:
    raise AppendOnlyViolation("reproduction_check is IMMUTABLE_APPEND_ONLY — UPDATE refused")


@event.listens_for(ReproductionCheck, "before_delete", propagate=True)
def _refuse_reproduction_check_delete(
    _mapper: Mapper[Any], _connection: Any, _target: ReproductionCheck
) -> None:
    raise AppendOnlyViolation("reproduction_check is IMMUTABLE_APPEND_ONLY — DELETE refused")


__all__ = ["RUN_TYPE_REPRODUCTION", "ReproductionCheck"]
