"""ENT-071 ``liquidity_result`` — the illiquid share of the invested-long book.

LQ-1's governed half. A **bucket vector** over the SEC 22e-4 liquidity ladder (ratified
OQ-LQ-1-6): one DETAIL row per tier carrying that tier's share, plus SUMMARY rows carrying the
headline metrics and the coverage pair. The scalar alternative was refused at the gate because it
has nowhere to carry the untiered residual and therefore cannot express coverage at all — which
would make the fail-closed question unanswerable.

**What this number is NOT.** It is not the Rule 22e-4 15% test. The rule's ratio is against **net
assets** (17 CFR 270.22e-4(b)(1)(iv): "more than 15% of its net assets in illiquid investments that
are assets"); this platform has no net-assets figure, so the ratified denominator is the
invested-long book. The resulting share may OVERSTATE **or UNDERSTATE** the regulatory ratio
depending on the book's cash, leverage and short exposure, and **the direction is not determinable
without a net-assets figure**. That is why the metric is named ``illiquid_share_invested_long``
rather than anything resembling "pct_illiquid": the name is the control, and it is why limits are
refused against this family until a NAV entity exists (ratified OQ-LQ-1-5 / OQ-LQ-1-7).

**Grain caveat, recorded because the rule contradicts the obvious simplification.** Tier assignment
is INSTRUMENT-grain. 22e-4(b)(1)(ii)(B) requires a fund to account for its own position size when
classifying ("the fund must determine whether trading varying portions of a position … is reasonably
expected to significantly affect its liquidity, and if so, the fund must take this determination
into account"). Instrument grain therefore cannot reflect the fund-specific determination the rule
mandates. This is a deliberate simplification ratified at OQ-LQ-1-1, not a fidelity claim, and it is
the named trigger for a future position-grain slice.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, event, text
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from irp_shared.audit.models import AppendOnlyViolation
from irp_shared.db.base import Base
from irp_shared.db.mixins import PrimaryKeyMixin, TenantMixin, TimestampMixin
from irp_shared.db.types import GUID, PreciseDecimal
from irp_shared.temporal import TemporalClass

#: Row kinds — the CON-1 DETAIL/SUMMARY grain, reused deliberately so one reader convention serves
#: both bucket-vector families.
ROW_KIND_DETAIL = "DETAIL"
ROW_KIND_SUMMARY = "SUMMARY"
ROW_KINDS: tuple[str, ...] = (ROW_KIND_DETAIL, ROW_KIND_SUMMARY)

#: The residual bucket. **UNCLASSIFIED, never UNCLASSIFIABLE** (ratified OQ-LQ-1-19): an instrument
#: in the pinned exposure set with no current-head tier assignment counts in the classifiable
#: coverage denominator and so CAN trip the floor. Routing it to an UNCLASSIFIABLE-style bucket that
#: is excluded from coverage would make the floor structurally unfireable — the vacuous-guard class
#: this platform has shipped twice and now tests against directly.
BUCKET_UNCLASSIFIED = "__UNCLASSIFIED__"
BUCKET_SUMMARY = "__SUMMARY__"
BUCKET_SENTINELS: tuple[str, ...] = (BUCKET_UNCLASSIFIED, BUCKET_SUMMARY)

#: DETAIL metric: the tier's share of the invested-long book.
METRIC_TYPE_TIER_SHARE = "TIER_SHARE"
#: SUMMARY metrics. ILLIQUID_SHARE is the headline; HIGHLY_LIQUID_SHARE discharges CAP-8.1's third
#: sub-capability, which is the ladder's FIRST category rather than an incidental extra (the rule
#: names it, 22e-4(a)(7)). Both inherit the denominator caveat in this module's docstring.
METRIC_TYPE_ILLIQUID_SHARE = "ILLIQUID_SHARE"
METRIC_TYPE_HIGHLY_LIQUID_SHARE = "HIGHLY_LIQUID_SHARE"
SUMMARY_METRIC_TYPES: tuple[str, ...] = (
    METRIC_TYPE_ILLIQUID_SHARE,
    METRIC_TYPE_HIGHLY_LIQUID_SHARE,
)
LIQUIDITY_METRIC_TYPES: tuple[str, ...] = (METRIC_TYPE_TIER_SHARE, *SUMMARY_METRIC_TYPES)

#: The run family. Declared HERE rather than in ``service.py`` deliberately: the GS2 census
#: (``test_the_run_family_is_NEVER_a_metric_type_for_ANY_family``) discovers constants by walking
#: ``*.events`` and ``*.models`` modules, so a RUN_TYPE_* declared in a service module escapes the
#: very guard that exists to catch a run family colliding with a metric name. Found by running it.
RUN_TYPE_LIQUIDITY = "LIQUIDITY"

#: The denominator, adopted from CON-1 unchanged (ratified OQ-LQ-1-5). Echoed on every row so a
#: reader never has to infer which book a share was taken against.
DENOMINATOR_BASIS_INVESTED_LONG = "INVESTED_LONG"


class LiquidityResult(PrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """IA append-only, run-bound, snapshot-gated, model-bound (AD-018 + AD-014).

    All three governance FKs are NOT NULL at the DB, not merely in the binder: a row that cannot
    name its run, its pinned inputs and its model version is not a governed number.
    """

    __tablename__ = "liquidity_result"
    __temporal_class__ = TemporalClass.IMMUTABLE_APPEND_ONLY
    __table_args__ = (
        # DETAIL: one row per (run, portfolio, tier). SUMMARY: one row per (run, portfolio, metric).
        # Both keys are fully NOT NULL — a nullable column inside a UNIQUE key is VACUOUS on
        # PostgreSQL (NULLS DISTINCT), which is how CON-1 v3 shipped a detail key that constrained
        # nothing. Declared for BOTH dialects: the unit tier builds via create_all and would not
        # otherwise exercise these at all.
        Index(
            "uq_liquidity_result_detail",
            "calculation_run_id",
            "portfolio_id",
            "bucket_code",
            unique=True,
            postgresql_where=text("row_kind = 'DETAIL'"),
            sqlite_where=text("row_kind = 'DETAIL'"),
        ),
        Index(
            "uq_liquidity_result_summary",
            "calculation_run_id",
            "portfolio_id",
            "metric_type",
            unique=True,
            postgresql_where=text("row_kind = 'SUMMARY'"),
            sqlite_where=text("row_kind = 'SUMMARY'"),
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
    #: The run's aggregation scope. A NULL-scope upstream run is refused PRE-BUILD, so the honest
    #: NULL never reaches this column.
    portfolio_id: Mapped[str] = mapped_column(GUID, nullable=False, index=True)

    # The grain.
    row_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: A tier code on DETAIL rows; a sentinel on SUMMARY rows.
    bucket_code: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)

    #: The ladder actually used, echoed so a historical row stays readable after a scheme revision.
    #: HYBRID table — NO FK (a referential check would bypass RLS; the CON-1 OQ-14 precedent).
    scheme_id: Mapped[str | None] = mapped_column(GUID, nullable=True)
    denominator_basis: Mapped[str] = mapped_column(
        String(30), nullable=False, default=DENOMINATOR_BASIS_INVESTED_LONG
    )

    # Kernel-computed evidence. long_amount is the LONG predicate (exposure_amount > 0) over the
    # pinned atoms; it is the numerator's source AND the denominator's, so both are auditable from
    # the persisted rows without re-reading the snapshot.
    long_amount: Mapped[Decimal] = mapped_column(PreciseDecimal(28, 6), nullable=False)
    #: DETAIL rows: the tier's share. SUMMARY rows: the metric value. Nullable on the other kind.
    tier_share: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 6), nullable=True)
    metric_value: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 6), nullable=True)

    #: Coverage (SUMMARY rows only). ``coverage_ratio`` = classifiable long / total long;
    #: ``coverage_classifiable`` = the classifiable long amount itself, carried so a reader can see
    #: WHAT was covered rather than only the fraction.
    coverage_ratio: Mapped[Decimal | None] = mapped_column(PreciseDecimal(20, 6), nullable=True)
    coverage_classifiable: Mapped[Decimal | None] = mapped_column(
        PreciseDecimal(28, 6), nullable=True
    )
    #: The count of pinned instruments with no current-head tier — the residual's size in NAMES
    #: rather than money, because a single large untiered holding and many small ones are different
    #: data-quality stories and the ratio alone cannot tell them apart.
    untiered_instrument_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


def _block_mutation(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    raise AppendOnlyViolation(
        f"{type(target).__name__} is append-only (AUD-01); update/delete is forbidden"
    )


event.listen(LiquidityResult, "before_update", _block_mutation)
event.listen(LiquidityResult, "before_delete", _block_mutation)
