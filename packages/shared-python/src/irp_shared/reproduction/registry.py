"""The per-family reproducer registry (REPRO-1) — what can be re-executed, and what cannot.

**Coverage is a census, never a silence (remit I5).** Every governed run family is in exactly one
of two declarations below: ``REPRODUCIBLE_FAMILIES`` (it has a reproducer) or
``UNREPRODUCIBLE_FAMILIES`` (it does not, with the reason written down). A census test asserts the
union equals the platform's whole run-type vocabulary and that the two sets are disjoint, so a
family landing in neither fails the suite rather than being quietly unchecked. Partial coverage is
honest; unenumerated partial coverage is a control that lies about its own reach.

**Why re-execute the BINDER rather than the kernel.** Eighteen service modules accept a
consume-existing ``snapshot_id``, so a historical run's own pinned snapshot can be fed straight back
through the real production path. A kernel-only re-derivation would prove strictly less — it could
not see a change in a binder's adjudication — and CTRL-018's wording is "re-runs historical runs".

**Why ``run_type`` cannot pick the binder.** Seven registered models write ``var_result`` under the
single run type ``VAR``, across three different entry points (``run_var``, ``run_var_unified``,
``run_var_historical``). Dispatching on ``run_type`` alone would run the wrong kernel and report a
confident, wrong verdict. RPT-1 already solved this shape — resolve the bound model code from the
run's own rows against a DECLARED allowlist — and this module reuses that allowlist rather than
re-deriving a second one that can drift from it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.exposure.events import RUN_TYPE_EXPOSURE_AGGREGATE
from irp_shared.exposure.models import ExposureAggregate
from irp_shared.model.models import Model, ModelVersion
from irp_shared.report.models import RUN_TYPE_REPORT, ReportGeneration
from irp_shared.risk.bootstrap import (
    ES_HS_MODEL_CODE,
    ES_MODEL_CODE,
    ES_TOTAL_MODEL_CODE,
    VAR_HS_MODEL_CODE,
    VAR_MODEL_CODE,
    VAR_TOTAL_MODEL_CODE,
    VAR_UNIFIED_MODEL_CODE,
)
from irp_shared.risk.events import RUN_TYPE_VAR
from irp_shared.risk.models import VarResult


class ReproductionUnsupported(Exception):
    """The recompute could not be PERFORMED — not that it produced a different answer.

    Its own class, deliberately. "We could not check" and "we checked and the platform's promise
    broke" are different facts that call for different responses, and a single failure channel
    would make the second indistinguishable from the first (the RPT-2 identity-failure-versus-
    ordinary-500 lesson, applied one layer down).
    """


@dataclass(frozen=True)
class ComparableRow:
    """One stored-or-recomputed result row, reduced to what a reproduction may legitimately compare.

    ``key`` is the row's natural key WITHIN a run — never the row id, which is a fresh uuid on
    every execution and would make every comparison trivially divergent. ``values`` excludes ids,
    ``system_from`` and the run FKs for the same reason: a reproduction asks whether the ARITHMETIC
    reproduced, not whether two executions were the same execution.
    """

    key: tuple[str, ...]
    values: dict[str, Any]


@dataclass(frozen=True)
class ReproducibleFamily:
    """One family the sweep can re-execute.

    ``compared_fields`` is declared rather than derived from the model, because "every column"
    would sweep in the id, the timestamps and the run FKs, and a comparison that quietly dropped
    them would be doing this selection anyway — undeclared.

    **The first draft made that claim and nothing backed it, which the adversarial review proved by
    execution.** ``_VAR_COMPARED`` silently omitted `z_score`, `n_factors`, `residual_variance`,
    `private_variance` and `estimate_age_days`; ``_EXPOSURE_COMPARED`` omitted `fx_legs`. A planted
    change to `n_factors` produced `verdict=MATCH, rows_diverged=0` — the durable ENT-073 row, the
    artifact CTRL-018 cites as evidence, recording a pass for a stored governed row that
    demonstrably did not reproduce. The module's own header says "unenumerated partial coverage is
    a control that lies about its own reach", and the field level was exactly that.

    So the tuples now cover every column, and ``model`` + ``uncompared`` make the split
    MECHANICALLY CHECKED: a census asserts ``key_fields | compared_fields | uncompared`` equals the
    model's full column set, so a newly-added result column fails the suite until someone decides
    which side it belongs on. That is what "a visible decision rather than a silent omission"
    has to mean if it is to mean anything.
    """

    family_key: str
    key_fields: tuple[str, ...]
    compared_fields: tuple[str, ...]
    read_stored: Callable[[Session, str, CalculationRun], list[ComparableRow]]
    recompute: Callable[[Session, str, CalculationRun, str], list[ComparableRow]]
    #: The ORM model whose columns the census partitions. Declared so the census cannot drift into
    #: agreeing with whatever the reader happens to select.
    model: Any = None
    #: Columns DELIBERATELY not compared, **each mapped to the REASON it is excluded**.
    #:
    #: A mapping rather than a tuple, because the pre-merge audit proved the tuple form tolerated
    #: SHRINKAGE. **The precise claim, corrected after the re-audit refuted a looser earlier
    #: wording** — this is what was actually executed: moving ``sigma`` out does NOT go unnoticed
    #: (eight tests fail, because the plant helper targets that exact column), but moving
    #: ``z_score``, ``n_factors``, ``residual_variance``, ``private_variance`` and
    #: ``estimate_age_days`` out DID keep every test green — and those five are precisely what the
    #: review's HIGH was about.
    #:
    #: The reason floor alone does not close it either: the ``_WHY_*`` constants below are
    #: module-level and reusable, so an exclusion can be added without writing anything. What
    #: actually closes it is the ``_MUST_COMPARE`` pin in the test suite, which names the governed
    #: columns so a REMOVAL fails loudly. This census covers additions; that pin covers removals.
    #: The project's own words for what was here before: "a census that tolerates shrinkage is a
    #: floor wearing a census's name".
    uncompared: dict[str, str] = field(default_factory=dict)


def _rows_of(
    instances: list[Any], key_fields: tuple[str, ...], compared_fields: tuple[str, ...]
) -> list[ComparableRow]:
    """Project ORM instances onto ComparableRows.

    Called on the recompute side while the objects are still live — a rolled-back SAVEPOINT expires
    them, so the projection must happen BEFORE the discard, not after.
    """
    return [
        ComparableRow(
            key=tuple(str(getattr(inst, f)) for f in key_fields),
            values={f: getattr(inst, f) for f in compared_fields},
        )
        for inst in instances
    ]


def _resolve_model_code(session: Session, run: CalculationRun, *, acting_tenant: str) -> str:
    """The registered model code behind a run's ``model_version_id``, tenant-fenced.

    Both tenant fences are load-bearing and neither is redundant with RLS: ``model_version`` and
    ``model`` are separate tables and a cross-tenant version id supplied by a caller must not
    resolve. The refusal is ``ReproductionUnsupported``, not a crash — an unresolvable model means
    the check cannot be performed, which is a verdict, not an outage.
    """
    if run.model_version_id is None:
        raise ReproductionUnsupported(
            f"run {run.run_id} binds no model_version, so its binder cannot be identified"
        )
    version = session.execute(
        select(ModelVersion).where(
            ModelVersion.id == str(run.model_version_id),
            ModelVersion.tenant_id == acting_tenant,
        )
    ).scalar_one_or_none()
    if version is None:
        raise ReproductionUnsupported(
            f"model_version {run.model_version_id} is not visible to this tenant"
        )
    model = session.execute(
        select(Model).where(Model.id == str(version.model_id), Model.tenant_id == acting_tenant)
    ).scalar_one_or_none()
    if model is None:
        raise ReproductionUnsupported(f"model {version.model_id} is not visible to this tenant")
    return str(model.code)


#: The three reasons a column is legitimately outside the comparison. Named constants rather than
#: repeated literals so the census's reason check stays substantive without 170-character lines,
#: and so a new exclusion has to pick one of these or write a genuinely new justification.
_WHY_ROW_IDENTITY = (
    "differs by construction on any re-execution: this is the row's own identity / knowledge time, "
    "not the arithmetic it recorded"
)
_WHY_EXECUTION_FK = (
    "differs by construction on any re-execution: it names THIS execution's run, snapshot or model "
    "version rather than the values that were computed"
)
_WHY_RENDER_INPUT = (
    "an INPUT that regenerate_report reads FROM THE ROW in order to re-render, so comparing it "
    "would compare a value against itself and always pass — vacuous by construction"
)
_WHY_GENERATION_EVENT = (
    "describes the GENERATION EVENT rather than the artifact's content; a re-render is a different "
    "event by definition, so comparing it would diverge on every single run"
)


# --------------------------------------------------------------------------------- VAR family ----
_VAR_KEY = ("metric_type",)
#: EVERY governed column on `var_result`, not a hand-picked subset. The five that were missing —
#: `z_score`, `n_factors`, `residual_variance`, `private_variance`, `estimate_age_days` — are each
#: a real reproduction signal: `residual_variance`/`private_variance` are PPF-3's decomposition
#: evidence, so a regression that repartitions variance between them while leaving `sigma` intact
#: is invisible without them; `estimate_age_days` is BT-2's staleness evidence.
_VAR_COMPARED = (
    "sigma",
    "var_value",
    "confidence_level",
    "horizon_days",
    "base_currency",
    "n_observations",
    "window_start",
    "window_end",
    "z_score",
    "n_factors",
    "residual_variance",
    "private_variance",
    "estimate_age_days",
)
_VAR_UNCOMPARED = {
    "id": _WHY_ROW_IDENTITY,
    "tenant_id": _WHY_ROW_IDENTITY,
    "system_from": _WHY_ROW_IDENTITY,
    "calculation_run_id": _WHY_EXECUTION_FK,
    "input_snapshot_id": _WHY_EXECUTION_FK,
    "model_version_id": _WHY_EXECUTION_FK,
    "exposure_run_id": _WHY_EXECUTION_FK,
    "covariance_run_id": _WHY_EXECUTION_FK,
    "private_covariance_run_id": _WHY_EXECUTION_FK,
}


def _read_stored_var(
    session: Session, acting_tenant: str, run: CalculationRun
) -> list[ComparableRow]:
    rows = (
        session.execute(
            select(VarResult)
            .where(
                VarResult.calculation_run_id == str(run.run_id),
                VarResult.tenant_id == acting_tenant,
            )
            .order_by(VarResult.metric_type)
        )
        .scalars()
        .all()
    )
    return _rows_of(list(rows), _VAR_KEY, _VAR_COMPARED)


def _recompute_var(
    session: Session, acting_tenant: str, run: CalculationRun, code_version: str
) -> list[ComparableRow]:
    """Re-execute the VaR/ES family over the subject run's OWN pinned snapshot.

    The binder is chosen by the run's bound MODEL CODE, never by its run type — see the module
    docstring. An unlisted code raises ``ReproductionUnsupported`` rather than defaulting to
    ``run_var``: guessing here would produce a confident wrong verdict, which is worse than
    reporting that the family could not be checked.
    """
    from irp_shared.risk.events import VarActor
    from irp_shared.risk.var_hs_service import run_var_historical
    from irp_shared.risk.var_service import run_var, run_var_unified

    binders: dict[str, Any] = {
        VAR_MODEL_CODE: run_var,
        VAR_TOTAL_MODEL_CODE: run_var,
        ES_MODEL_CODE: run_var,
        ES_TOTAL_MODEL_CODE: run_var,
        VAR_UNIFIED_MODEL_CODE: run_var_unified,
        VAR_HS_MODEL_CODE: run_var_historical,
        ES_HS_MODEL_CODE: run_var_historical,
    }
    code = _resolve_model_code(session, run, acting_tenant=acting_tenant)
    binder = binders.get(code)
    if binder is None:
        raise ReproductionUnsupported(
            f"model code {code!r} writes var_result but has no declared reproduction binder — "
            "refusing to guess which kernel produced this run"
        )
    if run.input_snapshot_id is None:
        raise ReproductionUnsupported(
            f"run {run.run_id} has no input_snapshot_id, so there is nothing to re-execute against"
        )
    result = binder(
        session,
        acting_tenant=acting_tenant,
        actor=VarActor(actor_id="reproduction", actor_type="SYSTEM"),
        code_version=code_version,
        environment_id=run.environment_id or "reproduction",
        model_version_id=str(run.model_version_id),
        snapshot_id=str(run.input_snapshot_id),
    )
    return _rows_of(list(result.rows), _VAR_KEY, _VAR_COMPARED)


# ------------------------------------------------------------------- EXPOSURE_AGGREGATE family ---
_EXPOSURE_KEY = ("portfolio_id", "instrument_id", "base_currency")
#: `fx_legs` joined at the review fold: it is the ORDERED pinned conversion path, so a change in
#: leg selection or ordering that lands on the same composite rate is a real behavioural change
#: the row records and the comparison must see.
_EXPOSURE_COMPARED = (
    "signed_quantity",
    "mark_value",
    "fx_rate",
    "exposure_amount",
    "mark_currency",
    "exposure_type",
    "fx_legs",
)
_EXPOSURE_UNCOMPARED = {
    "id": _WHY_ROW_IDENTITY,
    "tenant_id": _WHY_ROW_IDENTITY,
    "system_from": _WHY_ROW_IDENTITY,
    "calculation_run_id": _WHY_EXECUTION_FK,
    "input_snapshot_id": _WHY_EXECUTION_FK,
}


def _stored_exposure_rows(
    session: Session, acting_tenant: str, run: CalculationRun
) -> list[ExposureAggregate]:
    return list(
        session.execute(
            select(ExposureAggregate)
            .where(
                ExposureAggregate.calculation_run_id == str(run.run_id),
                ExposureAggregate.tenant_id == acting_tenant,
            )
            .order_by(
                ExposureAggregate.portfolio_id,
                ExposureAggregate.instrument_id,
                ExposureAggregate.base_currency,
            )
        )
        .scalars()
        .all()
    )


def _read_stored_exposure(
    session: Session, acting_tenant: str, run: CalculationRun
) -> list[ComparableRow]:
    return _rows_of(
        _stored_exposure_rows(session, acting_tenant, run), _EXPOSURE_KEY, _EXPOSURE_COMPARED
    )


def _recompute_exposure(
    session: Session, acting_tenant: str, run: CalculationRun, code_version: str
) -> list[ComparableRow]:
    """Re-execute the exposure rollup over the subject run's own snapshot.

    **``base_currency`` is read back off the stored rows, never defaulted.** ``run_exposure``'s
    consume path silently falls back to ``DEFAULT_BASE`` when the caller omits it, so a reproducer
    that passed only ``snapshot_id`` would recompute a EUR-denominated book in USD and report every
    row divergent — a false alarm indistinguishable from a real one. This is RPT-1's B1 defect
    exactly (a value that reaches the output but is supplied by the caller rather than pinned), and
    the fix is the same: take it from the stored artifact.
    """
    from irp_shared.exposure.events import ExposureActor
    from irp_shared.exposure.service import run_exposure

    stored = _stored_exposure_rows(session, acting_tenant, run)
    if not stored:
        raise ReproductionUnsupported(
            f"run {run.run_id} has no stored exposure rows to recover base_currency from"
        )
    bases = {str(row.base_currency) for row in stored}
    if len(bases) != 1:
        raise ReproductionUnsupported(
            f"run {run.run_id} spans {len(bases)} base currencies ({sorted(bases)}) — the binder "
            "takes exactly one, so this run cannot be re-executed as a single call"
        )
    if run.input_snapshot_id is None:
        raise ReproductionUnsupported(
            f"run {run.run_id} has no input_snapshot_id, so there is nothing to re-execute against"
        )
    result = run_exposure(
        session,
        acting_tenant=acting_tenant,
        actor=ExposureActor(actor_id="reproduction", actor_type="SYSTEM"),
        code_version=code_version,
        environment_id=run.environment_id or "reproduction",
        snapshot_id=str(run.input_snapshot_id),
        base_currency=bases.pop(),
    )
    return _rows_of(list(result.rows), _EXPOSURE_KEY, _EXPOSURE_COMPARED)


# ------------------------------------------------------------------------------ REPORT family ----
_REPORT_KEY = ("portfolio_id",)
#: The hash is over the RENDERED BYTES, so it already covers every rendered value. It is the ONLY
#: recomputed quantity for this family, and that is a real asymmetry with the other two.
_REPORT_COMPARED = ("content_hash",)
#: Everything else on the row is an INPUT that ``regenerate_report`` READS FROM THE ROW in order to
#: re-render — `report_code`, `render_format`, `as_of_date`, `portfolio_code` and the version label
#: are what make the regeneration parameter-free (RPT-1's B1 fix). Comparing them would compare a
#: value against ITSELF and always pass: vacuous by construction, which is precisely the shape this
#: slice keeps removing. The review fold briefly added them to `compared`, and the deployed proof
#: caught it within one run — the recompute does not carry them, so every report diverged.
#: `generated_at`/`generated_by` describe the GENERATION EVENT rather than the artifact, and a
#: re-render is a different event by definition.
_REPORT_UNCOMPARED = {
    "id": _WHY_ROW_IDENTITY,
    "tenant_id": _WHY_ROW_IDENTITY,
    "system_from": _WHY_ROW_IDENTITY,
    "calculation_run_id": _WHY_EXECUTION_FK,
    "input_snapshot_id": _WHY_EXECUTION_FK,
    "generated_at": _WHY_GENERATION_EVENT,
    "generated_by": _WHY_GENERATION_EVENT,
    "report_code": _WHY_RENDER_INPUT,
    "report_version_label": _WHY_RENDER_INPUT,
    "render_format": _WHY_RENDER_INPUT,
    "as_of_date": _WHY_RENDER_INPUT,
    "portfolio_code": _WHY_RENDER_INPUT,
}


def _read_stored_report(
    session: Session, acting_tenant: str, run: CalculationRun
) -> list[ComparableRow]:
    rows = (
        session.execute(
            select(ReportGeneration)
            .where(
                ReportGeneration.calculation_run_id == str(run.run_id),
                ReportGeneration.tenant_id == acting_tenant,
            )
            .order_by(ReportGeneration.portfolio_id)
        )
        .scalars()
        .all()
    )
    return _rows_of(list(rows), _REPORT_KEY, _REPORT_COMPARED)


def _recompute_report(
    session: Session, acting_tenant: str, run: CalculationRun, code_version: str
) -> list[ComparableRow]:
    """Re-render each report the run generated, from its id alone, and take the fresh hash.

    This family is the cheapest honest reproduction in the platform: ENT-072 stores the hash and
    not the body, so ``regenerate_report`` re-derives the bytes from the pinned snapshot every
    time. Note it REFUSES on divergence rather than returning a different hash — so a divergence
    here surfaces as ``ReproductionUnsupported``'s sibling path below, and the verdict is still
    DIVERGED because the comparison never gets a matching value to record.
    """
    from irp_shared.report.service import ReportIdentityError, regenerate_report

    out: list[ComparableRow] = []
    rows = (
        session.execute(
            select(ReportGeneration)
            .where(
                ReportGeneration.calculation_run_id == str(run.run_id),
                ReportGeneration.tenant_id == acting_tenant,
            )
            .order_by(ReportGeneration.portfolio_id)
        )
        .scalars()
        .all()
    )
    for row in rows:
        try:
            rendered = regenerate_report(
                session, report_id=str(row.id), acting_tenant=acting_tenant
            )
        except ReportIdentityError:
            # The regeneration itself detected the divergence and refused. Record a value that
            # cannot equal any stored hash, so the comparison reports DIVERGED on the right row
            # rather than the whole family collapsing to UNREPRODUCIBLE.
            out.append(
                ComparableRow(
                    key=(str(row.portfolio_id),), values={"content_hash": "IDENTITY-FAILURE"}
                )
            )
            continue
        out.append(
            ComparableRow(
                key=(str(row.portfolio_id),), values={"content_hash": rendered.content_hash}
            )
        )
    return out


# ------------------------------------------------------------------------------ the declarations --
REPRODUCIBLE_FAMILIES: dict[str, ReproducibleFamily] = {
    RUN_TYPE_VAR: ReproducibleFamily(
        family_key=RUN_TYPE_VAR,
        key_fields=_VAR_KEY,
        compared_fields=_VAR_COMPARED,
        read_stored=_read_stored_var,
        recompute=_recompute_var,
        model=VarResult,
        uncompared=_VAR_UNCOMPARED,
    ),
    RUN_TYPE_EXPOSURE_AGGREGATE: ReproducibleFamily(
        family_key=RUN_TYPE_EXPOSURE_AGGREGATE,
        key_fields=_EXPOSURE_KEY,
        compared_fields=_EXPOSURE_COMPARED,
        read_stored=_read_stored_exposure,
        recompute=_recompute_exposure,
        model=ExposureAggregate,
        uncompared=_EXPOSURE_UNCOMPARED,
    ),
    RUN_TYPE_REPORT: ReproducibleFamily(
        family_key=RUN_TYPE_REPORT,
        key_fields=_REPORT_KEY,
        compared_fields=_REPORT_COMPARED,
        read_stored=_read_stored_report,
        recompute=_recompute_report,
        model=ReportGeneration,
        uncompared=_REPORT_UNCOMPARED,
    ),
}

#: Every governed family with NO reproducer, and WHY. This is the half of the census that keeps the
#: control honest: a family here is unchecked and says so, rather than being unchecked silently.
#:
#: The reasons fall into three kinds, and the distinction matters for what would fix them:
#:   (1) "no consume path" — the binder rebuilds its snapshot unconditionally, so re-running it
#:       re-pins TODAY's inputs and any legitimate edit since shows up as a false divergence;
#:   (2) "wall clock in the compute" — the result is not a function of pinned content alone, so a
#:       once-passing run legitimately stops reproducing as time passes;
#:   (3) "not yet adapted" — the binder has a consume path and the family is reproducible in
#:       principle; only the per-family key/field declaration and its parameter read-back are
#:       missing. These are the cheap ones, and they are the next slice's work.
UNREPRODUCIBLE_FAMILIES: dict[str, str] = {
    "CONCENTRATION": (
        "no consume path: run_concentration takes no snapshot_id and build_concentration_snapshot "
        "pins CURRENT-HEAD classification assignments, so any legitimate classification edit since "
        "the original run would be reported as a divergence in the numbers"
    ),
    "LIQUIDITY": (
        "wall clock in the compute: liquidity/service.py measures "
        "datetime.now(UTC) - oldest_assignment_at against the model's declared tier_max_age_days, "
        "so a run that was fresh when it ran legitimately stops reproducing as its ladder ages — "
        "it would fail with zero rows, which naively reads as total divergence. Re-anchoring that "
        "gate on pinned content (the var_service precedent) is a change to a shipped governed "
        "refusal and therefore a model-identity question, not a reproduction-slice decision"
    ),
    "COVARIANCE": "not yet adapted (has a consume path; needs its key/field declaration)",
    "COVARIANCE_PRIVATE": (
        "not yet adapted (shares covariance_result with COVARIANCE; needs binder resolution "
        "by model code)"
    ),
    "FACTOR_EXPOSURE": "not yet adapted (has a consume path; needs its key/field declaration)",
    "SENSITIVITY": "not yet adapted (has a consume path; needs its key/field declaration)",
    "SCENARIO": "not yet adapted (has a consume path; needs its key/field declaration)",
    "ACTIVE_RISK": "not yet adapted (has a consume path; needs its key/field declaration)",
    "VAR_BACKTEST": (
        "not yet adapted (shares var_backtest_result with ES_BACKTEST; needs binder "
        "resolution by model code)"
    ),
    "ES_BACKTEST": (
        "not yet adapted (shares var_backtest_result with VAR_BACKTEST; needs binder "
        "resolution by model code)"
    ),
    "PORTFOLIO_RETURN": "not yet adapted (has a consume path; needs its key/field declaration)",
    "BENCHMARK_RELATIVE": (
        "not yet adapted (needs return_basis + benchmark_id read back off the stored rows)"
    ),
    "DESMOOTHED_RETURN": "not yet adapted (has a consume path; needs its key/field declaration)",
    "ROLLING_RISK": "not yet adapted (needs window_months read back off rolling_risk_result)",
    "SHARPE": "not yet adapted (needs window_months read back off sharpe_ratio_result)",
    "PROXY_WEIGHT_ESTIMATE": (
        "not yet adapted (two binders — proxy_weight vs residual_shrinkage; needs binder "
        "resolution by model code)"
    ),
    "PURE_PRIVATE_FACTOR": "not yet adapted (has a consume path; needs its key/field declaration)",
    "PACING_PROJECTION": "not yet adapted (has a consume path; needs its key/field declaration)",
}


def normalize(value: Any) -> Any:
    """Reduce a compared value to the form equality should be judged on.

    ``Decimal`` compares NUMERICALLY (``Decimal('500.0') == Decimal('500.000000')``), which is the
    intended contract: the platform quantizes to declared scales, and a difference in trailing
    zeros between a stored column and a freshly-computed value is a representation artifact, not a
    change in the number. Everything else compares by value after a string reduction, so a uuid
    object and its string form do not read as a divergence.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return None
    if isinstance(value, int | float | bool):
        return value
    return str(value)


__all__ = [
    "REPRODUCIBLE_FAMILIES",
    "UNREPRODUCIBLE_FAMILIES",
    "ComparableRow",
    "ReproducibleFamily",
    "ReproductionUnsupported",
    "normalize",
]
