"""Demo stage 26 (STRUCT-3, REQ-PPM-008/-001) — the three-level book, live.

The demo tenant's first real TREE: ``DEMO-STRUCTURE`` (FUND) → two STRATEGY sleeves → three
ACCOUNT leaves, positions on the leaves ONLY, one bond leaf off par so BOTH measures join the
rollup identity. Its own book (the stage-25 rule: a new holding in a shared demo book moves every
downstream golden; a new book moves none).

What the stage executes, through the REAL services:

1. A governed exposure run AT THE FUND — the rollup anchor (both measures, hand goldens).
2. A governed exposure run AT A STRATEGY — the clause-7 execution evidence: the SUBTREE family
   runs below the top of the tree, the node stamped on the run.
3. A factor-exposure run over the SLEEVE run — the SCOPE_INHERITED chain executing below the
   top, the sleeve scope copied forward (the campaign's registered allocation model + FX_USD).
4. The rollup identity asserted at every level from the composition read.
5. **The rename carry (P19, from the STRUCT-2 review)**: the FUND is renamed to a CONTRADICTORY
   label and the SAME three runs re-execute FRESH (new snapshots — the reproduction sweep is
   structurally blind to a rename); every computed value must be identical. The name census
   (STRUCT-2) is the half with teeth; this is the executed belt over the tree book. Families
   whose fresh inputs live on the flat demo books (returns/backtests/desmoothing/pacing chains)
   are covered by that census plus the SQLite two-family fresh guard — recorded, not implied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.demo.campaign import (
    _CODE_VERSION,
    _ENVIRONMENT_ID,
    _T0,
    DEMO_TENANT_ID,
)
from irp_shared.exposure import ExposureActor, ExposureRunResult, run_exposure
from irp_shared.exposure.service import rollup_exposure
from irp_shared.marketdata.factor import resolve_factor
from irp_shared.marketdata.models import Factor
from irp_shared.model.models import ModelVersion
from irp_shared.portfolio import (
    PortfolioActor,
    create_portfolio,
    resolve_portfolio,
    update_portfolio,
)
from irp_shared.portfolio.models import Portfolio
from irp_shared.position import create_position
from irp_shared.position.service import PositionActor
from irp_shared.reference.instrument import create_instrument
from irp_shared.reference.instrument_terms import create_instrument_terms
from irp_shared.reference.service import ReferenceActor
from irp_shared.risk.events import FactorExposureActor
from irp_shared.risk.factor_service import run_factor_exposure
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_FUND_CODE = "DEMO-STRUCTURE"
_AS_OF = datetime(2026, 5, 27, tzinfo=UTC)
_MARK_DATE = date(2026, 5, 27)
#: The second boundary for the leaf portfolio-return run (clause-7 executed breadth).
_AS_OF_2 = datetime(2026, 5, 28, tzinfo=UTC)
_MARK_DATE_2 = date(2026, 5, 28)


class DemoStruct3AlreadySeededError(RuntimeError):
    """The DEMO-STRUCTURE book already exists — refuse-not-skip, the campaign rule."""


class DemoStruct3Error(RuntimeError):
    """A stage-26 invariant did not hold."""


@dataclass(frozen=True)
class Struct3StageSummary:
    tenant_id: str
    fund_id: str
    strategy_ids: tuple[str, str]
    account_ids: tuple[str, ...]
    fund_run_id: str
    sleeve_run_id: str
    factor_run_id: str
    fund_market_value: Decimal
    fund_notional: Decimal


def _require(condition: bool, message: str) -> None:  # noqa: FBT001 - a demo invariant gate
    if not condition:
        raise DemoStruct3Error(message)


def run_demo_struct3_stage26(session: Session, *, actor_id: str) -> Struct3StageSummary:
    """Seed the tree, execute the fund/sleeve/chain runs, assert the identity, run the rename
    carry."""
    existing = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _FUND_CODE)
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoStruct3AlreadySeededError(
            f"portfolio {_FUND_CODE} already exists — re-seed from a clean database"
        )

    pf_actor = PortfolioActor(actor_id=actor_id)
    fund = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_FUND_CODE,
        name="Demo structured multi-sleeve fund",
        node_type="FUND",
        base_currency_code="USD",
        actor=pf_actor,
    ).id
    strat_eq = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-STRUCT-EQ",
        name="Demo equity sleeve",
        node_type="STRATEGY",
        actor=pf_actor,
        parent_portfolio_id=fund,
    ).id
    strat_fi = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-STRUCT-FI",
        name="Demo fixed-income sleeve",
        node_type="STRATEGY",
        actor=pf_actor,
        parent_portfolio_id=fund,
    ).id
    accounts: list[str] = []
    for code, parent in (
        ("DEMO-STRUCT-EQ-A", strat_eq),
        ("DEMO-STRUCT-EQ-B", strat_eq),
        ("DEMO-STRUCT-FI-A", strat_fi),
    ):
        accounts.append(
            create_portfolio(
                session,
                tenant_id=DEMO_TENANT_ID,
                code=code,
                name=code.lower().replace("-", " "),
                node_type="ACCOUNT",
                actor=pf_actor,
                parent_portfolio_id=parent,
            ).id
        )

    ref_actor = ReferenceActor(actor_id=actor_id)
    # (code, name, asset_class, account, qty, mark) — leaves only; hand goldens below.
    leaves = (
        ("ST-EQ-NORTH", "Northwind Logistics common stock", "EQUITY", accounts[0], "300", "42.00"),
        ("ST-EQ-CREST", "Crestline Foods common stock", "EQUITY", accounts[1], "150", "88.00"),
        ("ST-FI-UST31", "US Treasury 4.25% 2031", "BOND", accounts[2], "20", "985.40"),
    )
    for code, name, asset_class, account, qty, mark in leaves:
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class=asset_class,
            actor=ref_actor,
        ).id
        if asset_class == "BOND":
            create_instrument_terms(
                session,
                instrument_id=inst,
                acting_tenant=DEMO_TENANT_ID,
                actor=ref_actor,
                valid_from=_T0,
                face_value=Decimal("1000.0000"),
                denomination_currency="USD",
                coupon_rate=Decimal("0.0425"),
            )
        create_position(
            session,
            portfolio_id=account,
            instrument_id=inst,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=actor_id),
            quantity=Decimal(qty),
            valid_from=_T0,
        )
        create_valuation(
            session,
            portfolio_id=account,
            instrument_id=inst,
            valuation_date=_MARK_DATE,
            acting_tenant=DEMO_TENANT_ID,
            actor=ValuationActor(actor_id=actor_id),
            mark_value=Decimal(mark),
            currency_code="USD",
            valid_from=_T0,
        )
        if code == "ST-EQ-NORTH":
            # The next-day mark for the leaf's boundary pair (42.00 -> 42.84, +2%).
            create_valuation(
                session,
                portfolio_id=account,
                instrument_id=inst,
                valuation_date=_MARK_DATE_2,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=actor_id),
                mark_value=Decimal("42.84"),
                currency_code="USD",
                valid_from=_T0,
            )

    def _exposure_at(node: str) -> ExposureRunResult:
        result = run_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ExposureActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            portfolio_id=node,
            as_of_valid_at=_AS_OF,
            base_currency="USD",
        )
        _require(
            result.status == "COMPLETED",
            f"stage-26 exposure run at {node} is {result.status}: {result.failure_reason}",
        )
        return result

    fund_run = _exposure_at(fund)
    sleeve_run = _exposure_at(strat_fi)  # the SUBTREE family EXECUTED below the top
    _require(
        sleeve_run.run.scope_portfolio_id == str(strat_fi),
        "the sleeve run does not carry its node",
    )

    # The chain below the top: the campaign's registered allocation model + FX_USD factor.
    fe_model = _resolve_factor_exposure_model(session)
    fx_usd = session.execute(
        select(Factor.id).where(Factor.tenant_id == DEMO_TENANT_ID, Factor.factor_code == "FX_USD")
    ).scalar_one()
    factor_run = run_factor_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=FactorExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=fe_model,
        exposure_run_id=sleeve_run.run.run_id,
        factor_ids=[str(resolve_factor(session, fx_usd, acting_tenant=DEMO_TENANT_ID).id)],
    )
    _require(factor_run.status == "COMPLETED", "stage-26 factor run did not COMPLETE")
    _require(
        factor_run.run.scope_portfolio_id == str(strat_fi),
        "the factor run did not inherit the sleeve scope",
    )

    # --- clause-7 executed breadth (review fold): VAR below the top; the return chain at a
    #     LEAF (a non-root node — v1 portfolio-return is a single-portfolio book by ratified
    #     deferral, so the leaf is exactly where it can run) ---------------------------------
    from irp_shared.calc.models import CalculationRun
    from irp_shared.perf.events import PortfolioReturnActor
    from irp_shared.perf.return_service import run_portfolio_return
    from irp_shared.risk.events import VarActor
    from irp_shared.risk.var_service import run_var

    cov_run_id = str(
        session.execute(
            select(CalculationRun.run_id)
            .where(
                CalculationRun.tenant_id == DEMO_TENANT_ID,
                CalculationRun.run_type == "COVARIANCE",
                CalculationRun.status == "COMPLETED",
            )
            .order_by(CalculationRun.created_at.desc())
            .limit(1)
        ).scalar_one()
    )
    var_run = run_var(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=VarActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=_resolve_model(session, "risk.var.parametric"),
        exposure_run_id=factor_run.run.run_id,
        covariance_run_id=cov_run_id,
    )
    _require(var_run.status == "COMPLETED", "stage-26 VaR run did not COMPLETE")
    _require(
        var_run.run.scope_portfolio_id == str(strat_fi),
        "the VaR run did not inherit the sleeve scope — the chain broke below the top",
    )

    leaf = accounts[0]  # ST-EQ-NORTH's account: single-portfolio, two boundary marks
    boundary_1 = _exposure_at(leaf)
    b2 = run_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        portfolio_id=leaf,
        as_of_valid_at=_AS_OF_2,
        base_currency="USD",
    )
    _require(b2.status == "COMPLETED", "the second boundary run did not COMPLETE")
    pr = run_portfolio_return(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=PortfolioReturnActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=_resolve_model(session, "perf.return.twr"),
        exposure_run_ids=[boundary_1.run.run_id, b2.run.run_id],
    )
    _require(pr.status == "COMPLETED", "the leaf portfolio-return run did not COMPLETE")
    _require(
        pr.run.scope_portfolio_id == str(leaf),
        "the return run does not carry its LEAF node — the census stamp fold regressed",
    )

    # --- the rollup identity, from the composition read, per measure -----------------------
    def _totals(run_id: str, node: str) -> dict[str, Decimal]:
        return {
            r.exposure_type: r.total
            for r in rollup_exposure(
                session, acting_tenant=DEMO_TENANT_ID, run_id=run_id, node_id=node
            )
        }

    top = _totals(fund_run.run.run_id, fund)
    level1 = [_totals(fund_run.run.run_id, n) for n in (strat_eq, strat_fi)]
    level2 = [_totals(fund_run.run.run_id, n) for n in accounts]
    for measure, total in top.items():
        _require(
            total
            == sum((d.get(measure, Decimal(0)) for d in level1), Decimal(0))
            == sum((d.get(measure, Decimal(0)) for d in level2), Decimal(0)),
            f"rollup identity broken for {measure}",
        )
    # Hand goldens: MV = 300x42 + 150x88 + 20x985.40 = 12,600 + 13,200 + 19,708 = 45,508;
    # NOTIONAL = 20 x 1,000 = 20,000.
    _require(top["MARKET_VALUE"] == Decimal("45508.000000"), "fund market value moved")
    _require(top["NOTIONAL"] == Decimal("20000.000000"), "fund notional moved")

    # --- the rename carry: contradictory label, FRESH re-runs, values identical -------------
    def _values(result: ExposureRunResult) -> dict:
        return {
            (r.portfolio_id, r.instrument_id, r.exposure_type): (
                r.exposure_amount,
                r.signed_quantity,
                r.mark_value,
            )
            for r in result.rows
        }

    before = {
        "fund": _values(fund_run),
        "sleeve": _values(sleeve_run),
        "factor": {(r.instrument_id, r.factor_id): r.exposure_amount for r in factor_run.rows},
    }
    update_portfolio(
        session,
        resolve_portfolio(session, fund, acting_tenant=DEMO_TENANT_ID),
        actor=pf_actor,
        name="Distressed Sovereign Credit Special Situations",  # contradicts the book entirely
    )
    fund_rerun = _exposure_at(fund)
    sleeve_rerun = _exposure_at(strat_fi)
    factor_rerun = run_factor_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=FactorExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        model_version_id=fe_model,
        exposure_run_id=sleeve_rerun.run.run_id,
        factor_ids=[fx_usd],
    )
    _require(factor_rerun.status == "COMPLETED", "post-rename factor run did not COMPLETE")
    _require(_values(fund_rerun) == before["fund"], "the rename changed a fund exposure value")
    _require(
        _values(sleeve_rerun) == before["sleeve"], "the rename changed a sleeve exposure value"
    )
    _require(
        {(r.instrument_id, r.factor_id): r.exposure_amount for r in factor_rerun.rows}
        == before["factor"],
        "the rename changed a factor-exposure value",
    )
    _require(
        fund_rerun.run.input_snapshot_id != fund_run.run.input_snapshot_id,
        "the post-rename run is not FRESH",
    )

    return Struct3StageSummary(
        tenant_id=DEMO_TENANT_ID,
        fund_id=fund,
        strategy_ids=(strat_eq, strat_fi),
        account_ids=tuple(accounts),
        fund_run_id=fund_run.run.run_id,
        sleeve_run_id=sleeve_run.run.run_id,
        factor_run_id=factor_run.run.run_id,
        fund_market_value=top["MARKET_VALUE"],
        fund_notional=top["NOTIONAL"],
    )


def _resolve_model(session: Session, model_code: str) -> str:
    """A campaign-registered model version, resolved from the DB — the stage registers no model
    of its own."""
    from irp_shared.model.models import Model

    return str(
        session.execute(
            select(ModelVersion.id)
            .join(Model, ModelVersion.model_id == Model.id)
            .where(ModelVersion.tenant_id == DEMO_TENANT_ID, Model.code == model_code)
            .order_by(ModelVersion.version_label.desc())
            .limit(1)
        ).scalar_one()
    )


def _resolve_factor_exposure_model(session: Session) -> str:
    return _resolve_model(session, "risk.factor_exposure.allocation")
