"""The report's family registry (RPT-1) — which governed numbers a report renders, and how to read
them back.

**A registry, not an if/else chain.** This platform has twice shipped a two-family conditional whose
``else`` was a comment (LIM-2's ``_METRIC_MAP``, killed by an exact set-equality census), so the
report's family set is declared data with a census over it. Adding a section to the report is a
registry entry plus a census edit — a deliberate act that shows up in review — not a branch someone
appends to a chain.

Each entry knows two things:

- **``read_values``** — given a COMPLETED run id, return the ordered ``(metric, value)`` pairs this
  family contributes. Used at BUILD time to pin, and at VERIFY time to re-resolve.
- **``methodology_ref`` / ``model_code``** — the provenance the rendered number carries, so a reader
  can follow the number to the method that produced it (and the RPT-1 census guarantees that
  reference resolves).

The ordering inside ``read_values`` is DETERMINISTIC by explicit ``ORDER BY``. That is not tidiness:
the report's content hash is taken over the rendered bytes, so an unordered read would make
regeneration non-deterministic and I2 unprovable — a hash mismatch caused by row order rather than
by any real change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.concentration.bootstrap import (
    CONCENTRATION_METHODOLOGY_REF,
    CONCENTRATION_MODEL_CODE,
)
from irp_shared.concentration.models import ConcentrationResult
from irp_shared.liquidity.bootstrap import LIQUIDITY_METHODOLOGY_REF, LIQUIDITY_MODEL_CODE
from irp_shared.liquidity.models import LiquidityResult
from irp_shared.perf.bootstrap import (
    ROLLING_RISK_METHODOLOGY_REF,
    ROLLING_RISK_MODEL_CODE,
)
from irp_shared.perf.models import RollingRiskResult


@dataclass(frozen=True)
class ReportFamily:
    """One governed family the report renders."""

    key: str
    section_title: str
    model_code: str
    methodology_ref: str
    #: (session, run_id, acting_tenant) -> ordered [(metric, value_as_str), ...]
    read_values: Callable[[Session, str, str], list[tuple[str, str]]]


def _read_concentration(session: Session, run_id: str, acting_tenant: str) -> list[tuple[str, str]]:
    rows = (
        session.execute(
            select(ConcentrationResult)
            .where(
                ConcentrationResult.calculation_run_id == run_id,
                ConcentrationResult.tenant_id == acting_tenant,
            )
            .order_by(ConcentrationResult.metric_type, ConcentrationResult.bucket_code)
        )
        .scalars()
        .all()
    )
    return [(f"{r.metric_type}:{r.bucket_code}", str(r.metric_value)) for r in rows]


def _read_liquidity(session: Session, run_id: str, acting_tenant: str) -> list[tuple[str, str]]:
    rows = (
        session.execute(
            select(LiquidityResult)
            .where(
                LiquidityResult.calculation_run_id == run_id,
                LiquidityResult.tenant_id == acting_tenant,
            )
            .order_by(LiquidityResult.metric_type, LiquidityResult.bucket_code)
        )
        .scalars()
        .all()
    )
    return [(f"{r.metric_type}:{r.bucket_code}", str(r.metric_value)) for r in rows]


def _read_rolling_risk(session: Session, run_id: str, acting_tenant: str) -> list[tuple[str, str]]:
    rows = (
        session.execute(
            select(RollingRiskResult)
            .where(
                RollingRiskResult.calculation_run_id == run_id,
                RollingRiskResult.tenant_id == acting_tenant,
            )
            .order_by(
                RollingRiskResult.metric_type,
                RollingRiskResult.window_months,
                RollingRiskResult.period_end,
            )
        )
        .scalars()
        .all()
    )
    return [
        (f"{r.metric_type}:{r.window_months}m:{r.period_end.isoformat()}", str(r.metric_value))
        for r in rows
    ]


#: The v1 report's families (ratified OQ-RPT-1-1 = the §2.1 spine).
#:
#: **VaR/ES is NOT in this v1 registry, and that is a recorded scope decision rather than an
#: oversight.** The ratified content list names it, but the VaR families write to a shared
#: ``var_result`` table across several run types (parametric / historical / unified / total), so
#: reading "the VaR for this report" requires a run-type filter whose omission is precisely the
#: defect PPF-2 shipped ("reusing a shipped result table activates any read omitting the run_type
#: filter"). Adding it is a registry entry plus that filter, and it lands in the same slice — but it
#: is written second, deliberately, so the identity machinery is proven on the three
#: single-run-type families first rather than debugged through a known trap.
REPORT_FAMILIES: tuple[ReportFamily, ...] = (
    ReportFamily(
        key="concentration",
        section_title="Concentration",
        model_code=CONCENTRATION_MODEL_CODE,
        methodology_ref=CONCENTRATION_METHODOLOGY_REF,
        read_values=_read_concentration,
    ),
    ReportFamily(
        key="liquidity",
        section_title="Liquidity",
        model_code=LIQUIDITY_MODEL_CODE,
        methodology_ref=LIQUIDITY_METHODOLOGY_REF,
        read_values=_read_liquidity,
    ),
    ReportFamily(
        key="rolling_risk",
        section_title="Rolling risk",
        model_code=ROLLING_RISK_MODEL_CODE,
        methodology_ref=ROLLING_RISK_METHODOLOGY_REF,
        read_values=_read_rolling_risk,
    ),
)

REPORT_FAMILIES_BY_KEY: dict[str, ReportFamily] = {f.key: f for f in REPORT_FAMILIES}


def family_for(key: str) -> ReportFamily:
    """Resolve a family by key, refusing an unknown one loudly.

    A ``dict.get`` returning ``None`` here would let an unknown family render as an EMPTY section —
    "no concentration data" is indistinguishable from "this family does not exist", which is the
    vacuous-read class this platform has now hit three times (a typo'd dimension_kind returning
    ``[]``, a fabricated zero for an unmatched selector, a silent skip for a missing blend).
    """
    try:
        return REPORT_FAMILIES_BY_KEY[key]
    except KeyError:
        raise ValueError(
            f"unknown report family {key!r} — known: {sorted(REPORT_FAMILIES_BY_KEY)}"
        ) from None


__all__ = [
    "REPORT_FAMILIES",
    "REPORT_FAMILIES_BY_KEY",
    "ReportFamily",
    "family_for",
]
