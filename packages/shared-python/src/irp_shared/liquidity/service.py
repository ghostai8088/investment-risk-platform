"""LQ-1 binder — the 24th governed number family (ENT-071), computed ONLY from pinned content.

The run reads the ``LIQUIDITY_INPUT`` snapshot and nothing else: exposure atoms and current-head
``LIQUIDITY_TIER`` assignments. An instrument with no pinned assignment is UNCLASSIFIED, which is
a fact about the book rather than an error, and it stays in the denominator.

**The coverage floor is the fail-closed gate.** Below it the run commits FAILED with zero rows and
a named reason. That direction matters: the alternative — completing with a low-coverage number —
would emit an immutable row asserting an illiquid share about a book nobody has classified.

**The staleness refusal** (ratified OQ-LQ-1-9 arm C) is enforced here rather than at build, because
it needs the run's own clock. 22e-4(b)(1)(ii) requires review at least monthly; a tier head older
than the declared bound refuses rather than silently pinning a stale ladder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.calc.scaffold import GovernedRunOutcome, execute_governed_run
from irp_shared.liquidity.bootstrap import (
    LIQUIDITY_MODEL_CODE,
    declared_liquidity_parameters,
)
from irp_shared.liquidity.kernel import Atom, compute_liquidity
from irp_shared.liquidity.models import (
    BUCKET_SUMMARY,
    DENOMINATOR_BASIS_INVESTED_LONG,
    METRIC_TYPE_HIGHLY_LIQUID_SHARE,
    METRIC_TYPE_ILLIQUID_SHARE,
    METRIC_TYPE_TIER_SHARE,
    ROW_KIND_DETAIL,
    ROW_KIND_SUMMARY,
    RUN_TYPE_LIQUIDITY,
    LiquidityResult,
)
from irp_shared.model.models import ModelVersion
from irp_shared.snapshot.models import (
    COMPONENT_KIND_CLASSIFICATION,
    COMPONENT_KIND_EXPOSURE,
    PURPOSE_LIQUIDITY_INPUT,
)

RESULT_ENTITY_TYPE = "liquidity_result"
RULE_CODE = "liquidity.required_fields"
RULE_NAME = "Liquidity result required fields"

GAP_CORRUPT_PINNED_CONTENT = "corrupt pinned content"
GAP_BELOW_COVERAGE_FLOOR = "classifiable coverage below the declared floor"
GAP_STALE_TIERS = "tier heads older than the declared maximum age"


class LiquidityInputError(ValueError):
    """Pinned content that violates an invariant the build should already have enforced."""


@dataclass
class _PinnedContent:
    atoms: list[dict[str, Any]] = field(default_factory=list)
    tier_by_instrument: dict[str, str] = field(default_factory=dict)
    #: The OLDEST pinned assignment clock — the staleness probe's input. (An earlier draft also
    #: tracked the newest and never read it; a field nothing consumes is a claim nothing checks.)
    oldest_assignment_at: datetime | None = None
    #: Pinned assignments carrying no clock at all. Non-zero refuses: unknown age is not fresh.
    undateable_assignments: int = 0


def _parse_pins(components: list[Any]) -> _PinnedContent:
    pinned = _PinnedContent()
    for comp in components:
        content = json.loads(comp.captured_content)
        if comp.component_kind == COMPONENT_KIND_EXPOSURE:
            pinned.atoms.append(content)
        elif comp.component_kind == COMPONENT_KIND_CLASSIFICATION:
            pinned.tier_by_instrument[content["entity_id"]] = _level1_code(content)
            # The tier's age comes from the COMPONENT COLUMN, not from the captured JSON.
            #
            # The first version read content["system_from"], which the assignment serializer does
            # NOT emit — it emits exactly nine keys and that is not one of them. So
            # oldest_assignment_at was always None, the staleness guard never entered its body, and
            # the ratified OQ-LQ-1-9 refusal was STRUCTURALLY UNFIREABLE while a registered model
            # limitation told every reader the platform would refuse a stale ladder. Four review
            # lanes found it independently; an end-to-end probe ran a 3,650-day-old ladder against
            # a declared 31-day bound and the run COMPLETED.
            #
            # pinned_system_from is populated for every one of these components and is NOT an input
            # to content_hash/manifest_hash, so reading it here moves no historical pin.
            stamped = getattr(comp, "pinned_system_from", None)
            if stamped is None:
                # A component with no clock cannot be aged. Fail CLOSED: record it so the binder
                # refuses, rather than silently treating "unknown age" as "fresh".
                pinned.undateable_assignments += 1
            else:
                when = stamped if stamped.tzinfo else stamped.replace(tzinfo=UTC)
                if pinned.oldest_assignment_at is None or when < pinned.oldest_assignment_at:
                    pinned.oldest_assignment_at = when
    return pinned


def _level1_code(assignment: dict[str, Any]) -> str:
    """The tier code. The 22e-4 ladder is FLAT — every node is level 1 — so the level-1 ancestor
    IS the tier. Reading the closure rather than ``node_code`` keeps this correct if a future
    ladder nests (AIFMD's day buckets could), and matches CON-1's reader so the two families
    cannot drift on what a pinned assignment means."""
    for node in assignment["closure"]:
        if node["level"] == 1:
            return str(node["code"])
    raise LiquidityInputError(
        f"pinned closure for assignment {assignment['id']} carries no level-1 ancestor — the "
        "fail-closed ancestor walk should have refused this at build"
    )


def _rows(
    *,
    run: Any,
    snapshot_id: str,
    model_version_id: str,
    portfolio_id: str,
    tenant_id: str,
    scheme_id: str | None,
    breakdown: Any,
) -> list[LiquidityResult]:
    common = {
        "tenant_id": tenant_id,
        "calculation_run_id": str(run.run_id),
        "input_snapshot_id": snapshot_id,
        "model_version_id": model_version_id,
        "portfolio_id": portfolio_id,
        "scheme_id": scheme_id,
        "denominator_basis": DENOMINATOR_BASIS_INVESTED_LONG,
    }
    rows: list[LiquidityResult] = [
        LiquidityResult(
            **common,
            row_kind=ROW_KIND_DETAIL,
            bucket_code=bucket.bucket_code,
            metric_type=METRIC_TYPE_TIER_SHARE,
            long_amount=bucket.long_amount,
            tier_share=bucket.tier_share,
        )
        for bucket in breakdown.buckets
    ]
    for metric, value in (
        (METRIC_TYPE_ILLIQUID_SHARE, breakdown.illiquid_share),
        (METRIC_TYPE_HIGHLY_LIQUID_SHARE, breakdown.highly_liquid_share),
    ):
        rows.append(
            LiquidityResult(
                **common,
                row_kind=ROW_KIND_SUMMARY,
                bucket_code=BUCKET_SUMMARY,
                metric_type=metric,
                long_amount=breakdown.total_long,
                metric_value=value,
                coverage_ratio=breakdown.coverage_ratio,
                coverage_classifiable=breakdown.coverage_classifiable,
                untiered_instrument_count=breakdown.untiered_instrument_count,
            )
        )
    return rows


def run_liquidity(
    session: Session,
    *,
    acting_tenant: str,
    actor_id: str,
    actor_type: str,
    exposure_run_id: str,
    scheme_id: str,
    model_version: ModelVersion,
    code_version: str,
    environment_id: str,
) -> GovernedRunOutcome:
    """Run a governed liquidity calculation: build the ``LIQUIDITY_INPUT`` snapshot over the
    EXPLICITLY SELECTED exposure run, then compute from the pinned content.

    The entry shape matches ``run_concentration`` deliberately — one call builds and computes. An
    earlier draft took a pre-built snapshot, which pushed snapshot construction onto every caller
    and made it possible to hand this verb another family's pins.
    """
    from irp_shared.calc.runs import resolve_completed_run_of_type
    from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE
    from irp_shared.snapshot.events import SnapshotActor
    from irp_shared.snapshot.service import build_liquidity_snapshot, list_components

    # --- Pre-create prerequisite gate (raise BEFORE any write => zero run, zero snapshot) ---
    if not code_version:
        raise LiquidityInputError("code_version is required (FW-RUN/TR-15)")
    if not environment_id:
        raise LiquidityInputError("environment_id is required (FW-RUN/TR-15)")
    if not actor_id:
        raise LiquidityInputError("initiator is required (FW-RUN/TR-15)")
    if model_version is None:
        raise LiquidityInputError("model_version is required (CTRL-003)")
    if not scheme_id:
        raise LiquidityInputError("a liquidity-tier scheme is required")

    # CTRL-003 with model-identity — the gate the ratified record required (Part 3 item 4) and the
    # first implementation OMITTED. The Wave-14 close found it by execution: a REJECTED model
    # version bound and wrote seven immutable rows, because the parse-back below checks the
    # assumption TEXTS and never the version's STATUS. LQ-1 was the only one of twenty-four
    # governed families missing this call — which is why P8 (the governed-binder conformance
    # census) now exists. Placed BEFORE the parse-back and BEFORE any write, matching every other
    # binder's pre-create gate.
    from irp_shared.model.service import assert_model_version_of

    assert_model_version_of(
        session,
        str(model_version.id),
        tenant_id=acting_tenant,
        expected_model_code=LIQUIDITY_MODEL_CODE,
    )

    # The SCOPE IS DERIVED, never supplied. An earlier draft took portfolio_id as a free parameter
    # and stamped it onto immutable governed rows and onto calculation_run.scope_portfolio_id
    # without ever resolving the upstream run — so a caller could label a run with a portfolio it
    # did not compute over, in an append-only table, and every downstream read filtering by
    # portfolio would silently return another book's number. Four review lanes found it. CON-1's
    # shape is adopted verbatim: resolve the upstream run, refuse a NULL scope, derive from it.
    upstream = resolve_completed_run_of_type(
        session,
        str(exposure_run_id),
        acting_tenant=acting_tenant,
        run_type=RUN_TYPE_EXPOSURE_AGGREGATE,
        label="exposure",
        error=LiquidityInputError,
    )
    if not upstream.scope_portfolio_id:
        raise LiquidityInputError(
            f"exposure run {exposure_run_id} has a NULL scope_portfolio_id — a liquidity result "
            f"cannot honestly name a portfolio the upstream run did not scope to"
        )
    portfolio_id = str(upstream.scope_portfolio_id)

    # Parsed BEFORE the snapshot is built: an edited or unregistered model version must refuse
    # without leaving a committed snapshot behind.
    coverage_floor, tier_max_age_days = declared_liquidity_parameters(session, model_version)

    snapshot = build_liquidity_snapshot(
        session,
        acting_tenant=acting_tenant,
        actor=SnapshotActor(actor_id=actor_id, actor_type=actor_type),
        exposure_run_id=str(exposure_run_id),
        scheme_id=str(scheme_id),
    )
    if snapshot.purpose != PURPOSE_LIQUIDITY_INPUT:  # pragma: no cover - defence in depth
        raise LiquidityInputError(
            f"snapshot {snapshot.id} has purpose {snapshot.purpose!r}, expected "
            f"{PURPOSE_LIQUIDITY_INPUT!r}"
        )

    # Pins are read and parsed OUTSIDE the compute zone, matching the shipped concentration
    # binder. Parsing inside would mislabel a DATABASE error as "corrupt pinned content" and turn
    # it into a committed FAILED run, when it is neither the data's fault nor a governed outcome.
    pinned = _parse_pins(
        list(list_components(session, snapshot_id=snapshot.id, acting_tenant=acting_tenant))
    )

    def compute(run: Any) -> tuple[list[Any], list[str]]:
        gaps: list[str] = []
        # The compute zone is INSIDE the run: the scaffold calls compute() outside its only try,
        # so ANY raise here would leave an orphaned RUNNING run with a committed snapshot (the
        # BT-1 orphan class). Corrupt pinned bytes are reported as a GAP — a committed FAILED run
        # with zero rows and a named reason — never as an exception. KeyError/TypeError are the
        # archetypal corrupt-content shapes (a missing content field, Decimal(None)).
        try:
            atoms = tuple(
                Atom(
                    instrument_id=str(a["instrument_id"]),
                    exposure_amount=Decimal(str(a["exposure_amount"])),
                    tier=pinned.tier_by_instrument.get(str(a["instrument_id"])),
                )
                for a in pinned.atoms
            )
            breakdown = compute_liquidity(atoms)
        except (LiquidityInputError, ValueError, ArithmeticError, KeyError, TypeError) as exc:
            return [], [f"{GAP_CORRUPT_PINNED_CONTENT} ({exc})"]

        # Staleness: enforced against the run's clock, which is why it lives here and not at build.
        if pinned.undateable_assignments:
            gaps.append(
                f"{GAP_STALE_TIERS}: {pinned.undateable_assignments} pinned tier assignment(s) "
                f"carry no system clock, so their age cannot be established — refusing rather "
                f"than treating unknown age as fresh"
            )
        if pinned.oldest_assignment_at is not None:
            age = datetime.now(UTC) - pinned.oldest_assignment_at
            if age > timedelta(days=tier_max_age_days):
                gaps.append(
                    f"{GAP_STALE_TIERS}: oldest pinned tier is {age.days}d old, declared maximum "
                    f"is {tier_max_age_days}d — refusing rather than reporting a share computed "
                    f"from a ladder nobody has reviewed"
                )

        if breakdown.gaps:
            gaps.extend(breakdown.gaps)

        # The floor. Checked AFTER the kernel so the reason can quote the measured coverage, and
        # BEFORE row construction so a below-floor run writes nothing at all.
        if breakdown.total_long > 0 and breakdown.coverage_ratio < coverage_floor:
            gaps.append(
                f"{GAP_BELOW_COVERAGE_FLOOR}: coverage {breakdown.coverage_ratio} < floor "
                f"{coverage_floor} ({breakdown.untiered_instrument_count} untiered instrument(s))"
            )

        if gaps:
            return [], gaps

        return (
            _rows(
                run=run,
                snapshot_id=str(snapshot.id),
                model_version_id=str(model_version.id),
                portfolio_id=str(portfolio_id),
                tenant_id=acting_tenant,
                scheme_id=scheme_id,
                breakdown=breakdown,
            ),
            [],
        )

    def format_reason(exc: Exception | None, gaps: list[str]) -> str:
        if gaps:
            return "; ".join(gaps)[:500]
        return f"{LIQUIDITY_MODEL_CODE}: {exc}"[:500]

    return execute_governed_run(
        session,
        acting_tenant=acting_tenant,
        actor_id=actor_id,
        actor_type=actor_type,
        run_type=RUN_TYPE_LIQUIDITY,
        snapshot_id=str(snapshot.id),
        model_version_id=str(model_version.id),
        code_version=code_version,
        environment_id=environment_id,
        rule_code=RULE_CODE,
        rule_name=RULE_NAME,
        rule_target_entity_type=RESULT_ENTITY_TYPE,
        result_entity_type=RESULT_ENTITY_TYPE,
        compute=compute,
        format_reason=format_reason,
        scope_portfolio_id=str(portfolio_id),
    )


# --- Rule-7 reads (every governed number ships entity/time reads in-slice) ---


def list_liquidity_results(
    session: Session,
    *,
    acting_tenant: str,
    portfolio_id: str | None = None,
    row_kind: str | None = None,
    metric_type: str | None = None,
    bucket_code: str | None = None,
    as_of: datetime | None = None,
) -> list[LiquidityResult]:
    """Entity/time-centric read across COMPLETED liquidity runs. Silent-empty on a foreign id.

    No structural exclusion applies here, unlike concentration's issuer split: no column on this
    table carries an identity that a narrower permission withholds. The whole row set is
    ``liquidity.view`` content.
    """
    from irp_shared.calc.reads import list_governed_results

    return list_governed_results(
        session,
        LiquidityResult,
        acting_tenant=acting_tenant,
        filters=[
            (LiquidityResult.portfolio_id, portfolio_id),
            (LiquidityResult.row_kind, row_kind),
            (LiquidityResult.metric_type, metric_type),
            (LiquidityResult.bucket_code, bucket_code),
        ],
        run_type=RUN_TYPE_LIQUIDITY,
        as_of=as_of,
        order_by=(
            LiquidityResult.row_kind,
            LiquidityResult.metric_type,
            LiquidityResult.bucket_code,
        ),
    )


def latest_liquidity(
    session: Session, *, acting_tenant: str, portfolio_id: str | None = None
) -> list[LiquidityResult]:
    """The latest COMPLETED run's rows (the latest-resolver; empty when none)."""
    from irp_shared.calc.reads import latest_run_rows

    return latest_run_rows(
        list_liquidity_results(session, acting_tenant=acting_tenant, portfolio_id=portfolio_id)
    )


def list_liquidity_runs(
    session: Session,
    *,
    acting_tenant: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Any]:
    """The tenant's LIQUIDITY runs, newest first."""
    from sqlalchemy import select

    from irp_shared.calc.models import CalculationRun

    stmt = (
        select(CalculationRun)
        .where(
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_LIQUIDITY,
        )
        .order_by(CalculationRun.created_at.desc(), CalculationRun.run_id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(CalculationRun.status == status)
    return list(session.execute(stmt).scalars().all())


def liquidity_run_head(session: Session, *, acting_tenant: str, run_id: str) -> Any | None:
    """ONE tenant-owned LIQUIDITY run head by id, or ``None``.

    A POINT SELECT, deliberately — CON-1's read surface once resolved a run by listing the newest
    1000 and filtering in Python, so a tenant past its 1000th run got a spurious 404 on every
    older run. These are scheduled per tenant per portfolio, so that ceiling is reachable.
    """
    from sqlalchemy import select

    from irp_shared.calc.models import CalculationRun

    return session.execute(
        select(CalculationRun).where(
            CalculationRun.tenant_id == str(acting_tenant),
            CalculationRun.run_type == RUN_TYPE_LIQUIDITY,
            CalculationRun.run_id == str(run_id),
        )
    ).scalar_one_or_none()


def liquidity_rows_for_run(
    session: Session, *, acting_tenant: str, run_id: str
) -> list[LiquidityResult]:
    """Every row of ONE run, tenant-scoped. The run-detail read."""
    from sqlalchemy import select

    return list(
        session.execute(
            select(LiquidityResult)
            .where(
                LiquidityResult.tenant_id == str(acting_tenant),
                LiquidityResult.calculation_run_id == str(run_id),
            )
            .order_by(
                LiquidityResult.row_kind,
                LiquidityResult.metric_type,
                LiquidityResult.bucket_code,
            )
        )
        .scalars()
        .all()
    )
