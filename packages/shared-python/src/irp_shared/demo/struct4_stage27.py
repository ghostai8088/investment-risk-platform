"""Demo stage 27 (STRUCT-4, REQ-PPM-010) — the three-currency book, live.

``DEMO-FX``: the requirement's own shape on real PG — THREE currencies (USD/EUR/GBP), the GBP
pair TRIANGULATED (no direct GBP/EUR rate is ever published), and SLEEVE-UK reporting in a
currency (USD) its holdings are NOT held in. Its own book (the stage-25 rule: a new holding in
a shared demo book moves every downstream golden; a new book moves none). Every golden below is
a HAND-DERIVED literal worked in ``08_testing_qa/struct4_fx_test_spec.md`` — never a replay of
the shipped formula (V-010-1).

What the stage executes, through the REAL services:

1. A governed exposure run AT THE FUND with NO explicit base — DP-11 live: the base RESOLVES to
   the root's declared EUR. The P18 positive control runs FIRST (translated-leg count > 0), then
   the GBP row's stated pivot (DP-12) and the fund golden.
2. The node-scoped consume AT SLEEVE-UK with NO explicit base — the governed read AT the
   foreign-reporting node: the base resolves to the NODE's declared USD and the total is the
   oracle (6,080.000000 USD).
3. The rollup translation at SLEEVE-UK from the FUND run — the read-time path lands on the SAME
   literal — and the identity pass-through at the inheriting SLEEVE-CORE.
4. **The rename-carry residual (P19, hosted here per the STRUCT-3 roadmap row): the RETURN
   chain fresh post-rename.** The fund is renamed to a contradictory label and the boundary
   exposure pair + the portfolio-return run at SLEEVE-CORE re-execute FRESH; every computed
   value must be identical. The remaining chains (backtest/desmoothing/pacing, whose input
   books are the SHARED flat demos) go to the Wave-18 close as a named P19 decision — recorded
   in the close record, not implied here.
"""

from __future__ import annotations

import json
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
from irp_shared.exposure.service import NodeRollup, rollup_exposure
from irp_shared.marketdata import FxRateActor, capture_fx_rate
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
from irp_shared.reference.models import Currency
from irp_shared.reference.service import ReferenceActor
from irp_shared.valuation import create_valuation
from irp_shared.valuation.service import ValuationActor

_FUND_CODE = "DEMO-FX"
_AS_OF = datetime(2026, 5, 27, tzinfo=UTC)
_MARK_DATE = date(2026, 5, 27)
#: The second boundary for the rename-carry return chain at SLEEVE-CORE.
_AS_OF_2 = datetime(2026, 5, 28, tzinfo=UTC)
_MARK_DATE_2 = date(2026, 5, 28)

#: The hand-derived literals (test-spec doc §2).
_SLEEVE_UK_USD_ORACLE = Decimal("6080.000000")
_SLEEVE_UK_EUR_TOTAL = Decimal("5629.629630")
_FUND_EUR_TOTAL = Decimal("6629.629630")


class DemoStruct4AlreadySeededError(RuntimeError):
    """The DEMO-FX book already exists — refuse-not-skip, the campaign rule."""


class DemoStruct4Error(RuntimeError):
    """A stage-27 invariant did not hold."""


@dataclass(frozen=True)
class Struct4StageSummary:
    tenant_id: str
    fund_id: str
    sleeve_uk_id: str
    sleeve_core_id: str
    fund_run_id: str
    node_run_id: str
    return_run_id: str
    sleeve_uk_usd_total: Decimal
    fund_eur_total: Decimal


def _require(condition: bool, message: str) -> None:  # noqa: FBT001 - a demo invariant gate
    if not condition:
        raise DemoStruct4Error(message)


def run_demo_struct4_stage27(session: Session, *, actor_id: str) -> Struct4StageSummary:
    """Seed the three-currency book, execute the foreign-node reads against the hand oracles,
    run the return-chain rename carry."""
    existing = session.execute(
        select(Portfolio).where(Portfolio.tenant_id == DEMO_TENANT_ID, Portfolio.code == _FUND_CODE)
    ).scalar_one_or_none()
    if existing is not None:
        raise DemoStruct4AlreadySeededError(
            f"portfolio {_FUND_CODE} already exists — re-seed from a clean database"
        )

    # GBP is this stage's third currency (the campaign seeds only USD/EUR).
    session.add(
        Currency(tenant_id=DEMO_TENANT_ID, code="GBP", name="Pound Sterling", valid_from=_T0)
    )
    session.flush()

    pf_actor = PortfolioActor(actor_id=actor_id)
    fund = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code=_FUND_CODE,
        name="Demo multi-currency fund",
        node_type="FUND",
        base_currency_code="EUR",  # the root DECLARES (DP-11)
        actor=pf_actor,
    ).id
    sleeve_uk = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-FX-UK",
        name="Demo UK sleeve reporting USD",
        node_type="STRATEGY",
        base_currency_code="USD",  # the FOREIGN-reporting node: holds GBP+EUR, reports USD
        actor=pf_actor,
        parent_portfolio_id=fund,
    ).id
    sleeve_core = create_portfolio(
        session,
        tenant_id=DEMO_TENANT_ID,
        code="DEMO-FX-CORE",
        name="Demo core sleeve",
        node_type="STRATEGY",
        actor=pf_actor,  # UNDECLARED — inherits the fund's EUR (DP-11)
        parent_portfolio_id=fund,
    ).id

    ref_actor = ReferenceActor(actor_id=actor_id)
    # (code, name, sleeve, qty, mark, ccy, second_mark) — test-spec doc §1.
    holdings = (
        ("FX-EQ-UK", "Thameside Utilities plc", sleeve_uk, "100", "40.00", "GBP", None),
        ("FX-EQ-EU", "Rheinland Chemie AG", sleeve_uk, "50", "20.00", "EUR", None),
        ("FX-EQ-US", "Blue Harbor Industrials", sleeve_core, "10", "108.00", "USD", "110.16"),
    )
    for code, name, sleeve, qty, mark, ccy, second in holdings:
        inst = create_instrument(
            session,
            tenant_id=DEMO_TENANT_ID,
            code=code,
            name=name,
            asset_class="EQUITY",
            actor=ref_actor,
        ).id
        create_position(
            session,
            portfolio_id=sleeve,
            instrument_id=inst,
            acting_tenant=DEMO_TENANT_ID,
            actor=PositionActor(actor_id=actor_id),
            quantity=Decimal(qty),
            valid_from=_T0,
        )
        for mark_date, value in ((_MARK_DATE, mark), (_MARK_DATE_2, second)):
            if value is None:
                continue
            create_valuation(
                session,
                portfolio_id=sleeve,
                instrument_id=inst,
                valuation_date=mark_date,
                acting_tenant=DEMO_TENANT_ID,
                actor=ValuationActor(actor_id=actor_id),
                mark_value=Decimal(value),
                currency_code=ccy,
                valid_from=_T0,
            )

    # EUR/USD + GBP/USD on BOTH boundary dates (exact-date pins); GBP/EUR is NEVER published —
    # the pair exists only triangulated through USD.
    for rate_date in (_MARK_DATE, _MARK_DATE_2):
        for base, quote, rate in (("EUR", "USD", "1.08"), ("GBP", "USD", "1.25")):
            capture_fx_rate(
                session,
                base_currency=base,
                quote_currency=quote,
                rate_date=rate_date,
                rate=Decimal(rate),
                acting_tenant=DEMO_TENANT_ID,
                actor=FxRateActor(actor_id=actor_id),
                valid_from=_T0,
            )

    def _build_at(node: str, as_of: datetime) -> ExposureRunResult:
        # NO explicit base_currency anywhere in this stage — DP-11's resolution is the subject.
        result = run_exposure(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=ExposureActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            portfolio_id=node,
            as_of_valid_at=as_of,
        )
        _require(
            result.status == "COMPLETED",
            f"stage-27 exposure run at {node} is {result.status}: {result.failure_reason}",
        )
        return result

    # 1. The fund run: base RESOLVES to the declared EUR; the GBP row triangulates.
    fund_run = _build_at(fund, _AS_OF)
    _require(
        {r.base_currency for r in fund_run.rows} == {"EUR"},
        "the fund run did not resolve the root's declared EUR",
    )
    translated_rows = [r for r in fund_run.rows if json.loads(r.fx_legs)]
    _require(len(translated_rows) > 0, "P18: the three-currency book translated NOTHING")
    tri = [json.loads(r.fx_legs) for r in fund_run.rows if len(json.loads(r.fx_legs)) == 2]
    _require(len(tri) == 1, "exactly the GBP row should triangulate")
    _require(
        [leg["pivot"] for leg in tri[0]] == ["USD", "USD"],
        "the triangulated row does not STATE its pivot (DP-12)",
    )

    # 2. The governed read AT the foreign-reporting node: base resolves to SLEEVE-UK's USD.
    node_run = run_exposure(
        session,
        acting_tenant=DEMO_TENANT_ID,
        actor=ExposureActor(actor_id=actor_id),
        code_version=_CODE_VERSION,
        environment_id=_ENVIRONMENT_ID,
        snapshot_id=fund_run.run.input_snapshot_id,
        scope_node_id=sleeve_uk,
    )
    _require(node_run.status == "COMPLETED", "the node-scoped run did not COMPLETE")
    _require(
        {r.base_currency for r in node_run.rows} == {"USD"},
        "the node run did not resolve the NODE's declared USD",
    )
    node_total = sum((r.exposure_amount for r in node_run.rows), Decimal(0))
    _require(
        node_total == _SLEEVE_UK_USD_ORACLE,
        f"the foreign-node total {node_total} != the hand oracle {_SLEEVE_UK_USD_ORACLE}",
    )

    # 3. The rollup translation lands on the SAME literal; the inheriting sleeve passes through.
    def _rollup(node: str) -> dict[str, NodeRollup]:
        rows = rollup_exposure(
            session, acting_tenant=DEMO_TENANT_ID, run_id=fund_run.run.run_id, node_id=node
        )
        return {r.exposure_type: r for r in rows}

    uk = _rollup(sleeve_uk)["MARKET_VALUE"]
    _require(uk.total == _SLEEVE_UK_EUR_TOTAL, "the sleeve EUR total moved")
    _require(
        (uk.reporting_currency, uk.translated_total) == ("USD", _SLEEVE_UK_USD_ORACLE),
        "the rollup translation does not match the hand oracle",
    )
    _require(uk.missing_fx is None, "the v3 pin should carry the translation leg")
    top = _rollup(fund)["MARKET_VALUE"]
    _require(top.total == _FUND_EUR_TOTAL, "the fund EUR total moved")
    core = _rollup(sleeve_core)["MARKET_VALUE"]
    _require(
        (core.reporting_currency, core.translated_total) == ("EUR", core.total),
        "the inheriting sleeve is not an exact identity pass-through",
    )

    # 4. The rename carry (P19 residual, the RETURN chain): fresh post-rename, values identical.
    from irp_shared.perf.events import PortfolioReturnActor
    from irp_shared.perf.return_service import run_portfolio_return

    def _return_chain() -> tuple[str, dict]:
        b1 = _build_at(sleeve_core, _AS_OF)
        b2 = _build_at(sleeve_core, _AS_OF_2)
        pr = run_portfolio_return(
            session,
            acting_tenant=DEMO_TENANT_ID,
            actor=PortfolioReturnActor(actor_id=actor_id),
            code_version=_CODE_VERSION,
            environment_id=_ENVIRONMENT_ID,
            model_version_id=_resolve_model(session, "perf.return.twr"),
            exposure_run_ids=[b1.run.run_id, b2.run.run_id],
        )
        _require(pr.status == "COMPLETED", "the sleeve return run did not COMPLETE")
        values = {
            (r.metric_type, str(r.period_start), str(r.period_end)): r.return_value for r in pr.rows
        }
        _require(len(values) == len(pr.rows), "the return-value key collapsed rows")
        return pr.run.run_id, values

    return_run_id, before_values = _return_chain()
    update_portfolio(
        session,
        resolve_portfolio(session, fund, acting_tenant=DEMO_TENANT_ID),
        actor=pf_actor,
        name="Emerging Markets Local Rates Overlay",  # contradicts the book entirely
    )
    rerun_id, after_values = _return_chain()
    _require(rerun_id != return_run_id, "the post-rename return chain is not FRESH")
    _require(
        after_values == before_values,
        "the rename changed a portfolio-return value — a name reached a computation",
    )

    return Struct4StageSummary(
        tenant_id=DEMO_TENANT_ID,
        fund_id=fund,
        sleeve_uk_id=sleeve_uk,
        sleeve_core_id=sleeve_core,
        fund_run_id=fund_run.run.run_id,
        node_run_id=node_run.run.run_id,
        return_run_id=return_run_id,
        sleeve_uk_usd_total=node_total,
        fund_eur_total=top.total,
    )


def _resolve_model(session: Session, model_code: str) -> str:
    """A campaign-registered model version, resolved from the DB — the stage registers no model
    of its own."""
    from irp_shared.model.models import Model, ModelVersion

    return str(
        session.execute(
            select(ModelVersion.id)
            .join(Model, ModelVersion.model_id == Model.id)
            .where(ModelVersion.tenant_id == DEMO_TENANT_ID, Model.code == model_code)
            .order_by(ModelVersion.version_label.desc())
            .limit(1)
        ).scalar_one()
    )
