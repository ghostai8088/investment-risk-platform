"""Demo stage 7 (BT-3, OD-BT-3-F): the ES backtest + the Christoffersen leg, LIVE on the
living tenant — **the DOMAIN-GATE HONESTY demo, deliberately NOT a verdict**.

What this stage adds (additive; every prior stage byte-untouched; refuse-not-skip on its own
footprint):

1. Registers the two 0.9750 sibling forecast versions of EXISTING codes — `risk.var.historical`
   ``v1-c975`` + `risk.var.historical_es` ``v1-c975`` (0.9750 = the externally-anchored ES
   confidence, MAR33.3; window 41 = the 0.9750 adequacy neighborhood) — via the existing
   registrars' new caller-suppliable ``version_label`` (the MF-1 ``v1-alpha1`` precedent).
2. Runs a THREE-pair sibling forecast series at consecutive as-ofs (2026-05-21/22/23) on the
   flagship book: per as-of ONE ``VAR_HS_INPUT`` snapshot (window 41, the bitemporal valid_at
   cut) feeds BOTH families — the shared-``input_snapshot_id`` pairing design input, live per
   pair. **ZERO new market data**: the campaign's valuations, boundary exposure runs, daily
   factor returns (2026-04-01..05-25 covers every 41-observation window), and DIETZ series are
   the substrate; the designed 2026-05-22→23 drawdown supplies the genuine exception
   (fixture-searched at planning: the ~-4% equity move breaches the small-daily-cycle 0.9750
   VaR; the drift tripwire below refuses loudly if the seeded arithmetic ever moves it).
3. Registers `risk.es_backtest` v1 (the 19th code — the SIXTEENTH governed number) + the
   `risk.var_backtest` ``v2-christoffersen`` version, then runs BOTH backtests over the series:
   the ES backtest persists the Z evidence rows + ``ES_PAIR_COUNT`` and — at T=3, OFF the
   (0.9750, 250) verdict domain — **NO verdict** (a short-series verdict would be numerically
   WRONG by the criticals' T-dependence; the honest absence IS the demonstration; the unit
   suite proves the verdict leg at the full domain on deterministic fixtures); the
   Christoffersen v2 emits LIVE ``LR_IND``/``LR_CC`` verdicts (its [0,1,0] exception series is
   non-degenerate, and the chi-square domain is not T-bound).
4. Files the FOUR INITIAL AWCs (the RS-1 new-version precedent applied UNIFORMLY — the Wave-7
   close verifier's fold): `risk.es_backtest` v1 (TIER_1-matrix-derived tier via its OWN
   separate dossier constant, never in ``TIER_DOSSIERS``), the var_backtest v2, and the two
   ``v1-c975`` forecast versions. **NO TRIGGERED re-validation** — census-proved: no existing
   validation condition names the ES-backtest gap as closable (the ES-HS INITIAL's conditions
   are tail-resolution + factor-substrate); forcing one is the OQ-5-barred false ceremony
   (the DS-2 honesty pattern, recorded).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun
from irp_shared.db.tenant import persistent_tenant_context
from irp_shared.demo.campaign import DEMO_TENANT_ID
from irp_shared.demo.dossiers import (
    BT3_ES_BACKTEST_INITIAL,
    BT3_ES_BACKTEST_TIER,
    BT3_ESHS_C975_INITIAL,
    BT3_VARHS_C975_INITIAL,
    BT3_VB_V2_INITIAL,
)
from irp_shared.model.models import (
    VALIDATION_TYPE_INITIAL,
    Model,
    ModelLimitation,
    ModelVersion,
)
from irp_shared.model.service import assign_model_tier
from irp_shared.model.validation import (
    ModelValidationActor,
    RecordValidationRequest,
    ValidationEvidenceInput,
    ValidationFindingInput,
    record_validation,
)
from irp_shared.risk import (
    EsBacktestActor,
    VarActor,
    VarBacktestActor,
    register_es_backtest_model,
    register_historical_var_es_model,
    register_historical_var_model,
    register_var_backtest_christoffersen_model,
    run_es_backtest,
    run_var_backtest,
    run_var_historical,
)
from irp_shared.risk.bootstrap import ES_BACKTEST_MODEL_CODE, ES_HS_MODEL_CODE, VAR_HS_MODEL_CODE
from irp_shared.risk.events import (
    METRIC_TYPE_AS_Z1,
    METRIC_TYPE_AS_Z2,
    METRIC_TYPE_ES_PAIR_COUNT,
    METRIC_TYPE_LR_CC,
    METRIC_TYPE_LR_IND,
    METRIC_TYPE_VAR_HISTORICAL,
    RUN_TYPE_ES_BACKTEST,
)
from irp_shared.risk.models import VarResult
from irp_shared.snapshot import SnapshotActor, build_var_hs_snapshot

_CODE_VERSION = "demo-bt3"
_ENVIRONMENT_ID = "demo"
_ACTOR_ID = "demo-bt3-runner"
_REPORT_REF = "10_delivery_backlog/bt_3_decision_record.md"

#: The three consecutive as-ofs (inside the campaign's boundary/factor-return calendar; the
#: middle pair spans the designed 2026-05-22→23 drawdown — the genuine exception).
_AS_OFS: tuple[date, ...] = (date(2026, 5, 21), date(2026, 5, 22), date(2026, 5, 23))
#: The 0.9750 window (the adequacy floor at 0.9750 is 41: n*(1-c) > 1).
_C975 = "0.9750"
_WINDOW = 41
_VERSION_LABEL_C975 = "v1-c975"


class DemoBt3PrereqError(RuntimeError):
    """A stage-7 prerequisite is missing (run the prior stages first) or a tripwire fired."""


class DemoBt3AlreadySeededError(RuntimeError):
    """Stage 7's own footprint already exists — refuse-not-skip (the per-stage tolerated
    refusal class the cumulative suite fixtures catch)."""


@dataclass(frozen=True)
class Bt3Stage7Summary:
    es_backtest_run_id: str
    christoffersen_run_id: str
    var_hs_run_ids: tuple[str, ...]
    es_hs_run_ids: tuple[str, ...]
    n_pairs: int
    n_exceptions: int
    z2_value: Decimal
    z2_decision: str | None
    z1_value: Decimal | None
    lr_ind_decision: str
    lr_cc_decision: str
    initials_filed: int


def _dt(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=UTC)


# Small helpers DUPLICATED from the prior stages, not imported — those modules are byte-frozen
# fences and the raising helpers must raise stage-7-typed errors (the recorded MF-1
# adjudication, applied at every stage since).
def _resolve_principal(session: Session, role_code: str, label: str) -> str:
    from irp_shared.entitlement.models import AppUser, Role, UserRole

    rows = session.execute(
        select(AppUser.id)
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(AppUser.tenant_id == DEMO_TENANT_ID, Role.code == role_code)
    ).all()
    if len(rows) != 1:
        raise DemoBt3PrereqError(
            f"the demo tenant holds {len(rows)} {label} principal(s) — expected exactly one "
            f"from the MG-1 campaign; run it first"
        )
    return str(rows[0][0])


def _registered_limitations(session: Session, version_id: str) -> list[str]:
    return [
        r[0]
        for r in session.execute(
            select(ModelLimitation.limitation_text).where(
                ModelLimitation.model_version_id == version_id
            )
        ).all()
    ]


def _findings_from_registry(
    session: Session, version_id: str, keys: tuple[str, ...], code: str
) -> tuple[ValidationFindingInput, ...]:
    """The campaign's fail-loud key mechanism (the multifamily duplication precedent — NOT
    shared machinery): each dossier finding KEY must match exactly one REGISTERED limitation
    row, whose text becomes the finding."""
    texts = _registered_limitations(session, version_id)
    findings: list[ValidationFindingInput] = []
    for key in keys:
        matches = [t for t in texts if key in t]
        if len(matches) != 1:
            raise DemoBt3PrereqError(
                f"dossier finding key {key!r} matched {len(matches)} registered limitation "
                f"row(s) of {code} — the dossier map and the registry have drifted; refusing"
            )
        findings.append(
            ValidationFindingInput(
                finding_text=matches[0], severity="MEDIUM", authored_by="Andrew Cox"
            )
        )
    return tuple(findings)


def _flagship_exposure_run(session: Session, *, portfolio_id: str) -> str:
    """The LATEST flagship factor-exposure run measuring the backtest portfolio — resolved from
    the flagship VAR_HISTORICAL rows (the stage-4 time-ordered selection, restricted to the
    portfolio the realized leg measures: the multifamily sleeve binds the SAME demo-mg1
    versions on a DIFFERENT portfolio, so the portfolio cross-check is load-bearing)."""
    from irp_shared.risk.models import FactorExposureResult

    rows = (
        session.execute(
            select(VarResult)
            .join(ModelVersion, ModelVersion.id == VarResult.model_version_id)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(
                VarResult.tenant_id == DEMO_TENANT_ID,
                VarResult.metric_type == METRIC_TYPE_VAR_HISTORICAL,
                Model.code == VAR_HS_MODEL_CODE,
                ModelVersion.code_version == "demo-mg1",
            )
            .order_by(
                VarResult.window_end.desc(),
                VarResult.system_from.desc(),
                VarResult.calculation_run_id.desc(),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        measured = {
            str(r[0])
            for r in session.execute(
                select(FactorExposureResult.portfolio_id)
                .where(
                    FactorExposureResult.calculation_run_id == str(row.exposure_run_id),
                    FactorExposureResult.tenant_id == DEMO_TENANT_ID,
                )
                .distinct()
            ).all()
        }
        if measured == {str(portfolio_id)}:
            return str(row.exposure_run_id)
    raise DemoBt3PrereqError(
        "no flagship HS exposure run measures the backtest portfolio — run the campaign first"
    )


def _campaign_return_run(session: Session) -> tuple[str, str]:
    """The campaign's PM-1 return run + its portfolio — the pair the BT-1/BT-2 backtests cite
    (re-read from their persisted rows, never guessed)."""
    from irp_shared.risk.models import VarBacktestResult

    rows = session.execute(
        select(VarBacktestResult.portfolio_return_run_id, VarBacktestResult.portfolio_id)
        .where(VarBacktestResult.tenant_id == DEMO_TENANT_ID)
        .distinct()
    ).all()
    if len(rows) != 1:
        raise DemoBt3PrereqError(
            f"expected ONE campaign backtest (return run, portfolio) pair (got {len(rows)}) — "
            f"run the campaign first"
        )
    return str(rows[0][0]), str(rows[0][1])


def run_demo_bt3_stage7(session: Session) -> Bt3Stage7Summary:
    """Execute stage 7 (register → the sibling series → both backtests → tier + file). The
    caller owns the ONE commit."""
    detach = persistent_tenant_context(session, DEMO_TENANT_ID)
    try:
        # --- Prereq + footprint probes (refuse-not-skip, BEFORE any write) ---
        return_run, backtest_portfolio = _campaign_return_run(session)
        fx_run = _flagship_exposure_run(session, portfolio_id=backtest_portfolio)
        existing = session.execute(
            select(CalculationRun.run_id).where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == RUN_TYPE_ES_BACKTEST,
            )
        ).first()
        if existing is not None:
            raise DemoBt3AlreadySeededError(
                "stage 7 footprint already present (an ES_BACKTEST run exists) — refusing to "
                "re-seed (refuse-not-skip)"
            )

        # --- Register the versions (idempotent registrars; conflicts refuse loudly) ---
        var_c975 = register_historical_var_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=_ACTOR_ID,
            code_version=_CODE_VERSION,
            confidence_level=_C975,
            window_observations=_WINDOW,
            version_label=_VERSION_LABEL_C975,
        )
        es_c975 = register_historical_var_es_model(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor_id=_ACTOR_ID,
            code_version=_CODE_VERSION,
            confidence_level=_C975,
            window_observations=_WINDOW,
            version_label=_VERSION_LABEL_C975,
        )
        es_bt_version = register_es_backtest_model(
            session, tenant_id=DEMO_TENANT_ID, actor_id=_ACTOR_ID, code_version=_CODE_VERSION
        )
        vb_v2 = register_var_backtest_christoffersen_model(
            session, tenant_id=DEMO_TENANT_ID, actor_id=_ACTOR_ID, code_version=_CODE_VERSION
        )

        # --- The sibling series: per as-of ONE snapshot feeds BOTH families ---
        var_runs: list[str] = []
        es_runs: list[str] = []
        for as_of in _AS_OFS:
            snapshot = build_var_hs_snapshot(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=SnapshotActor(actor_id=_ACTOR_ID),
                exposure_run_id=fx_run,
                window_observations=_WINDOW,
                as_of_valid_at=_dt(as_of),
            )
            v = run_var_historical(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=VarActor(actor_id=_ACTOR_ID),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=var_c975.id,
                snapshot_id=snapshot.id,
            )
            if v.status != "COMPLETED":
                raise DemoBt3PrereqError(f"VaR-HS c975 run @{as_of} did not complete")
            e = run_var_historical(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=VarActor(actor_id=_ACTOR_ID),
                code_version=_CODE_VERSION,
                environment_id=_ENVIRONMENT_ID,
                model_version_id=es_c975.id,
                snapshot_id=snapshot.id,
            )
            if e.status != "COMPLETED":
                raise DemoBt3PrereqError(f"ES-HS c975 run @{as_of} did not complete")
            var_runs.append(str(v.run.run_id))
            es_runs.append(str(e.run.run_id))

        # --- The ES backtest (the domain-gate honesty leg) ---
        es_bt = run_es_backtest(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=EsBacktestActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=es_bt_version.id,
            portfolio_return_run_id=return_run,
            var_run_ids=var_runs,
            es_run_ids=es_runs,
        )
        if es_bt.status != "COMPLETED":
            raise DemoBt3PrereqError(f"the ES backtest did not complete: {es_bt.failure_reason}")
        by_type = {
            r.metric_type: r for r in es_bt.rows if r.metric_type != "ES_EXCEPTION_INDICATOR"
        }
        z2_row = by_type[METRIC_TYPE_AS_Z2]
        count_row = by_type[METRIC_TYPE_ES_PAIR_COUNT]
        z1_row = by_type.get(METRIC_TYPE_AS_Z1)
        # The drift tripwires (refuse loudly, never re-derive silently): the designed drawdown
        # must remain a genuine exception, and the off-domain verdict must remain ABSENT.
        if count_row.n_exceptions < 1:
            raise DemoBt3PrereqError(
                "fixture drift: the 2026-05-22→23 drawdown no longer breaches the 0.9750 VaR — "
                "the seeded arithmetic moved; refusing"
            )
        if z2_row.test_decision is not None:
            raise DemoBt3PrereqError(
                "the off-domain verdict fired at T=3 — the domain gate is broken; refusing"
            )

        # --- The Christoffersen v2 over the SAME VaR series ---
        vb = run_var_backtest(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=VarBacktestActor(actor_id=_ACTOR_ID),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=vb_v2.id,
            portfolio_return_run_id=return_run,
            var_run_ids=var_runs,
        )
        if vb.status != "COMPLETED":
            raise DemoBt3PrereqError(
                f"the Christoffersen run did not complete: {vb.failure_reason}"
            )
        vb_by_type = {r.metric_type: r for r in vb.rows}
        if METRIC_TYPE_LR_IND not in vb_by_type or METRIC_TYPE_LR_CC not in vb_by_type:
            raise DemoBt3PrereqError(
                "the Markov rows are absent — the exception pattern degenerated; refusing"
            )

        # --- Tier + the FOUR INITIALs (NO TRIGGERED — the recorded honesty) ---
        validator_id = _resolve_principal(session, "risk_manager_2l", "2L validator")
        assign_model_tier(
            session,
            acting_tenant=DEMO_TENANT_ID,
            model_id=str(es_bt_version.model_id),
            materiality_rating=BT3_ES_BACKTEST_TIER.materiality_rating,
            complexity_rating=BT3_ES_BACKTEST_TIER.complexity_rating,
            rationale=BT3_ES_BACKTEST_TIER.rationale,
            actor_id=validator_id,
        )
        v_actor = ModelValidationActor(actor_id=validator_id)
        today = date(2026, 7, 19)
        initials = 0
        for version_obj, dossier, run_id, code in (
            (es_bt_version, BT3_ES_BACKTEST_INITIAL, str(es_bt.run.run_id), ES_BACKTEST_MODEL_CODE),
            (vb_v2, BT3_VB_V2_INITIAL, str(vb.run.run_id), "risk.var_backtest"),
            (var_c975, BT3_VARHS_C975_INITIAL, var_runs[0], VAR_HS_MODEL_CODE),
            (es_c975, BT3_ESHS_C975_INITIAL, es_runs[0], ES_HS_MODEL_CODE),
        ):
            findings: tuple[ValidationFindingInput, ...] = tuple(
                _findings_from_registry(session, str(version_obj.id), dossier.finding_keys, code)
            )
            record_validation(
                session,
                acting_tenant=DEMO_TENANT_ID,
                actor=v_actor,
                request=RecordValidationRequest(
                    model_version_id=version_obj.id,
                    validation_type=VALIDATION_TYPE_INITIAL,
                    outcome=dossier.outcome,
                    scope_summary=dossier.scope_note,
                    conditions=dossier.conditions,
                    report_ref=_REPORT_REF,
                    next_review_due=today + timedelta(days=365),
                    findings=findings,
                    evidence=(
                        ValidationEvidenceInput(evidence_type="CALCULATION_RUN", run_id=run_id),
                    ),
                ),
            )
            initials += 1

        return Bt3Stage7Summary(
            es_backtest_run_id=str(es_bt.run.run_id),
            christoffersen_run_id=str(vb.run.run_id),
            var_hs_run_ids=tuple(var_runs),
            es_hs_run_ids=tuple(es_runs),
            n_pairs=count_row.n_pairs,
            n_exceptions=count_row.n_exceptions,
            z2_value=z2_row.metric_value,
            z2_decision=z2_row.test_decision,
            z1_value=None if z1_row is None else z1_row.metric_value,
            lr_ind_decision=str(vb_by_type[METRIC_TYPE_LR_IND].test_decision),
            lr_cc_decision=str(vb_by_type[METRIC_TYPE_LR_CC].test_decision),
            initials_filed=initials,
        )
    finally:
        detach()
