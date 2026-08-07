"""The report's family registry (RPT-1) — which governed numbers a report renders, how to read them
back, and where their provenance comes from.

**A registry, not an if/else chain.** This platform has twice shipped a two-family conditional whose
``else`` was a comment (LIM-2's ``_METRIC_MAP``, killed by an exact set-equality census), so the
report's family set is declared data with a census over it. Adding a section to the report is a
registry entry plus a census edit — a deliberate act that shows up in review — not a branch someone
appends to a chain.

**Provenance is RESOLVED FROM THE BOUND RUN, not declared here.** The first draft declared one
``model_code`` + one ``methodology_ref`` per family, which is true for the three single-model
families and FALSE for VaR: seven registered models write into ``var_result`` under a single
``run_type`` (``VAR`` — ``events.py`` states outright that run_type must never equal metric_type),
and ``metric_type`` does not identify the model either, since ``risk.var.parametric_es`` and
``risk.var.parametric_es_total`` both write ``ES_PARAMETRIC``. A static pair would therefore have
rendered a FALSE methodology citation on a governed number for six of the seven. So each family
reads the ``model_version_id`` its result rows actually bind, and resolves the citation from that.

**And the resolved reference is checked against a DECLARED allowlist.** ``model_version
.methodology_ref`` is tenant-supplied — ``POST /models`` can stamp any string (the P3-4 lesson the
ES bootstrap quotes at length). Without the allowlist a tenant could make a board report cite a
methodology document of their own choosing. With it, a report can only ever cite a reference this
registry declares, and ``registered_methodologies`` is census-checked against what the bootstraps
actually register.

Each entry knows three things:

- **``read_values``** — given a COMPLETED run id, return the ordered ``(metric, value)`` pairs this
  family contributes. Used at BUILD time to pin, and at VERIFY time to re-resolve.
- **``read_provenance``** — the model code, methodology reference and model-version id the run's
  rows bind (I5: every rendered number carries its provenance, and the reference resolves).
- **``registered_methodologies``** — model code → the registered reference, the allowlist above.

The ordering inside ``read_values`` is DETERMINISTIC by explicit ``ORDER BY``. That is not tidiness:
the report's content hash is taken over the rendered bytes, so an unordered read would make
regeneration non-deterministic and I2 unprovable — a hash mismatch caused by row order rather than
by any real change.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_ as sa_and
from sqlalchemy import not_ as sa_not
from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.concentration.bootstrap import (
    CONCENTRATION_METHODOLOGY_REF,
    CONCENTRATION_MODEL_CODE,
)
from irp_shared.concentration.models import (
    DIMENSION_KIND_ISSUER,
    ROW_KIND_DETAIL,
    ConcentrationResult,
)
from irp_shared.liquidity.bootstrap import LIQUIDITY_METHODOLOGY_REF, LIQUIDITY_MODEL_CODE
from irp_shared.liquidity.models import LiquidityResult
from irp_shared.model.models import Model, ModelVersion
from irp_shared.perf.bootstrap import (
    ROLLING_RISK_METHODOLOGY_REF,
    ROLLING_RISK_MODEL_CODE,
)
from irp_shared.perf.models import RollingRiskResult
from irp_shared.risk.bootstrap import (
    ES_HS_METHODOLOGY_REF,
    ES_HS_MODEL_CODE,
    ES_METHODOLOGY_REF,
    ES_MODEL_CODE,
    ES_TOTAL_MODEL_CODE,
    VAR_HS_METHODOLOGY_REF,
    VAR_HS_MODEL_CODE,
    VAR_METHODOLOGY_REF,
    VAR_MODEL_CODE,
    VAR_TOTAL_METHODOLOGY_REF,
    VAR_TOTAL_MODEL_CODE,
    VAR_UNIFIED_METHODOLOGY_REF,
    VAR_UNIFIED_MODEL_CODE,
)
from irp_shared.risk.models import VarResult


class ReportProvenanceError(ValueError):
    """A bound run's provenance could not be resolved to a REGISTERED methodology.

    Its own class rather than a bare ``ValueError``: this refusal means "the report cannot honestly
    say where this number came from", which is a different failure from "the input was malformed"
    and deserves to be distinguishable at the call site and in the logs.
    """


@dataclass(frozen=True)
class FamilyProvenance:
    """What one family's bound run cites — resolved from the run, never assumed."""

    model_code: str
    methodology_ref: str
    model_version_id: str


@dataclass(frozen=True)
class ReportFamily:
    """One governed family the report renders."""

    key: str
    section_title: str
    #: model_code -> the REGISTERED methodology_ref. A report may cite NOTHING outside this map.
    registered_methodologies: dict[str, str]
    #: (session, run_id, acting_tenant) -> ordered [(metric, value_as_str), ...]
    read_values: Callable[[Session, str, str], list[tuple[str, str]]]
    #: (session, run_id, acting_tenant) -> the provenance the run's rows bind
    read_provenance: Callable[[Session, str, str], FamilyProvenance]


def _pair(row: object, detail_value: object) -> tuple[str, str]:
    """One (metric, value) pair, taking the value from the column the ROW KIND actually populates.

    **The bug this exists because of.** Both bucket-vector families split their value across two
    NULLABLE columns: DETAIL rows carry ``share_invested_long`` / ``tier_share`` and leave
    ``metric_value`` NULL; SUMMARY rows do the reverse. The first version of these readers took
    ``metric_value`` unconditionally, so every DETAIL row would have rendered the string "None" in
    a board-facing report — a governed number replaced by a placeholder, silently. It was found by
    building the end-to-end test, not by reading the code.

    A NULL from BOTH columns raises rather than rendering "None": a value the schema permits to be
    absent must never reach a reader as text.
    """
    kind = getattr(row, "row_kind", None)
    value = detail_value if kind == "DETAIL" else getattr(row, "metric_value", None)
    if value is None:
        raise ValueError(
            f"row {getattr(row, 'id', '?')} ({kind}, {getattr(row, 'metric_type', '?')}) carries "
            "no value in either column — refusing to render a placeholder for a governed number"
        )
    return (f"{getattr(row, 'metric_type', '?')}:{getattr(row, 'bucket_code', '?')}", str(value))


def _provenance_reader(
    result_cls: Any, registered: dict[str, str], family_key: str
) -> Callable[[Session, str, str], FamilyProvenance]:
    """Build the provenance reader for a family whose results carry ``model_version_id``.

    ONE implementation for every family, because four hand-written joins would be four chances to
    forget one of the four refusals below — and three of them are silent-wrong-answer failures
    rather than crashes.
    """

    def read(session: Session, run_id: str, acting_tenant: str) -> FamilyProvenance:
        rows = session.execute(
            select(Model.code, ModelVersion.methodology_ref, ModelVersion.id)
            .join(ModelVersion, ModelVersion.model_id == Model.id)
            .join(result_cls, result_cls.model_version_id == ModelVersion.id)
            .where(
                result_cls.calculation_run_id == run_id,
                result_cls.tenant_id == acting_tenant,
                # The MODEL's tenant, checked explicitly rather than left to RLS. Found by making
                # the refusal test use a REAL model version owned by ANOTHER TENANT instead of a
                # random UUID (the LIM-2 lesson): the reader resolved it happily, so a report could
                # have cited a model somebody else registered. PostgreSQL's row-level security
                # would have hidden it in production — which is precisely the argument for putting
                # the check here too, since a control that only works on one engine is a control
                # whose absence no unit test can see.
                ModelVersion.tenant_id == acting_tenant,
                Model.tenant_id == acting_tenant,
            )
            .distinct()
        ).all()
        if not rows:
            raise ReportProvenanceError(
                f"family {family_key!r} run {run_id} binds no resolvable model version — refusing "
                "to render a governed number with no provenance"
            )
        if len(rows) > 1:
            # One run binds ONE model version by construction; more than one means the result rows
            # disagree about what produced them, and picking either would be a guess.
            raise ReportProvenanceError(
                f"family {family_key!r} run {run_id} binds {len(rows)} distinct model versions — "
                "its rows disagree on their own provenance"
            )
        code, declared_ref, version_id = rows[0]
        expected = registered.get(str(code))
        if expected is None:
            raise ReportProvenanceError(
                f"family {family_key!r} run {run_id} binds UNREGISTERED model {code!r} — the "
                f"report may only cite {sorted(registered)}"
            )
        if declared_ref != expected:
            # methodology_ref is tenant-supplied at registration. A report citing whatever string a
            # tenant stamped would make the provenance line forgeable, which is the one thing it
            # exists to prevent.
            raise ReportProvenanceError(
                f"family {family_key!r} run {run_id}: model {code!r} declares methodology "
                f"{declared_ref!r}, but the registered reference is {expected!r} — refused"
            )
        return FamilyProvenance(
            model_code=str(code), methodology_ref=expected, model_version_id=str(version_id)
        )

    return read


def _read_concentration(session: Session, run_id: str, acting_tenant: str) -> list[tuple[str, str]]:
    """Concentration values for the report — **ISSUER-dimension DETAIL rows EXCLUDED at the query.**

    **The disclosure this closes (RPT-2 pre-merge audit, CONFIRMED by two independent lenses).**
    ``concentration.issuer.view`` exists solely to withhold issuer identity from ``auditor_3l``,
    which is the split three prior mints made (``reference.issuer.view`` / ``legal_entity.view`` /
    ``classification_assignment.view``) and the one REF-1 shipped a BLOCKING defect by collapsing.
    ``report.view`` IS held by ``auditor_3l`` — correctly, a rendered report is a governed output —
    so a reader that took every row of a concentration run would have handed the 3L auditor exactly
    the issuer-identity read those four mints refused, through a new door, with every per-code
    holder pin still passing.

    The exclusion is the SAME predicate ``list_concentration_results(include_issuer_detail=False)``
    applies (service.py) — deliberately identical, so the report can never render a payload class
    broader than the ``concentration.view`` code permits. Expressed at the QUERY, not by filtering
    afterwards, for the reason CON-1 recorded: a mis-scoped caller must not receive issuer identity
    by accident, and a post-filter is one refactor away from being dropped.

    A report over a run whose ONLY rows are issuer detail therefore yields zero values and is
    refused by the zero-values guard — the honest outcome: that run's content is not reportable
    under this permission.
    """
    rows = (
        session.execute(
            select(ConcentrationResult)
            .where(
                ConcentrationResult.calculation_run_id == run_id,
                ConcentrationResult.tenant_id == acting_tenant,
                # NOT (ISSUER and DETAIL) — the issuer-identity rows, and only those.
                sa_not(
                    sa_and(
                        ConcentrationResult.dimension_kind == DIMENSION_KIND_ISSUER,
                        ConcentrationResult.row_kind == ROW_KIND_DETAIL,
                    )
                ),
            )
            .order_by(ConcentrationResult.metric_type, ConcentrationResult.bucket_code)
        )
        .scalars()
        .all()
    )
    return [_pair(r, r.share_invested_long) for r in rows]


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
    return [_pair(r, r.tier_share) for r in rows]


def _read_rolling_risk(session: Session, run_id: str, acting_tenant: str) -> list[tuple[str, str]]:
    """Rolling risk, with the SUPPRESSED case rendered rather than stringified.

    **The third instance of the same defect, found by reading the schema after execution found the
    other two.** ``rolling_risk_result.metric_value`` is nullable and pairs with a ``suppressed``
    flag: a window with too few observations is suppressed BY DESIGN and carries NULL. The first
    version of this reader called ``str(metric_value)`` unconditionally, so those rows would have
    rendered "None" — indistinguishable, to a board reader, from a computation that failed.

    A suppressed row therefore renders its suppression EXPLICITLY, and a row that is NOT suppressed
    yet carries NULL raises: that combination is a data defect, and rendering anything at all for it
    would hide it.
    """
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
    out: list[tuple[str, str]] = []
    for r in rows:
        metric = f"{r.metric_type}:{r.window_months}m:{r.period_end.isoformat()}"
        if r.suppressed:
            out.append((metric, f"SUPPRESSED ({r.suppression_reason or 'unstated'})"))
            continue
        if r.metric_value is None:
            raise ValueError(
                f"rolling-risk row {r.id} is NOT suppressed yet carries no value — refusing to "
                "render a placeholder for a governed number"
            )
        out.append((metric, str(r.metric_value)))
    return out


def _read_var(session: Session, run_id: str, acting_tenant: str) -> list[tuple[str, str]]:
    """The VaR/ES family — one row per ``(run, metric_type)``.

    The metric key carries the metric_type AND the base currency. A board report that says
    "VaR: 12,345" without saying WHICH VaR, in what currency, is a disclosure defect rather than a
    formatting one: the same table holds parametric, total, unified, historical and both ES
    families, and ``var_value`` on an ES row holds an ES, not a VaR.
    """
    rows = (
        session.execute(
            select(VarResult)
            .where(
                VarResult.calculation_run_id == run_id,
                VarResult.tenant_id == acting_tenant,
            )
            .order_by(VarResult.metric_type)
        )
        .scalars()
        .all()
    )
    return [(f"{r.metric_type}:{r.base_currency}", str(r.var_value)) for r in rows]


#: Every model that writes into ``var_result``, mapped to the reference its bootstrap REGISTERS.
#: Read off the registration SITES rather than inferred from constant names — which matters, because
#: ``risk.var.parametric_es_total`` registers ``ES_METHODOLOGY_REF``, not a total-specific document,
#: and a name-based guess would have cited a file that does not exist.
VAR_REGISTERED_METHODOLOGIES: dict[str, str] = {
    VAR_MODEL_CODE: VAR_METHODOLOGY_REF,
    VAR_TOTAL_MODEL_CODE: VAR_TOTAL_METHODOLOGY_REF,
    VAR_UNIFIED_MODEL_CODE: VAR_UNIFIED_METHODOLOGY_REF,
    ES_MODEL_CODE: ES_METHODOLOGY_REF,
    ES_TOTAL_MODEL_CODE: ES_METHODOLOGY_REF,
    VAR_HS_MODEL_CODE: VAR_HS_METHODOLOGY_REF,
    ES_HS_MODEL_CODE: ES_HS_METHODOLOGY_REF,
}

_CONCENTRATION_METHODOLOGIES = {CONCENTRATION_MODEL_CODE: CONCENTRATION_METHODOLOGY_REF}
_LIQUIDITY_METHODOLOGIES = {LIQUIDITY_MODEL_CODE: LIQUIDITY_METHODOLOGY_REF}
_ROLLING_RISK_METHODOLOGIES = {ROLLING_RISK_MODEL_CODE: ROLLING_RISK_METHODOLOGY_REF}

#: The v1 report's families (ratified OQ-RPT-1-1 = the §2.1 spine). VaR/ES leads: it is the number
#: the §2.1 spine is built around, and a risk summary that opens with concentration buries it.
REPORT_FAMILIES: tuple[ReportFamily, ...] = (
    ReportFamily(
        key="var",
        section_title="Value at Risk / Expected Shortfall",
        registered_methodologies=VAR_REGISTERED_METHODOLOGIES,
        read_values=_read_var,
        read_provenance=_provenance_reader(VarResult, VAR_REGISTERED_METHODOLOGIES, "var"),
    ),
    ReportFamily(
        key="concentration",
        section_title="Concentration",
        registered_methodologies=_CONCENTRATION_METHODOLOGIES,
        read_values=_read_concentration,
        read_provenance=_provenance_reader(
            ConcentrationResult, _CONCENTRATION_METHODOLOGIES, "concentration"
        ),
    ),
    ReportFamily(
        key="liquidity",
        section_title="Liquidity",
        registered_methodologies=_LIQUIDITY_METHODOLOGIES,
        read_values=_read_liquidity,
        read_provenance=_provenance_reader(LiquidityResult, _LIQUIDITY_METHODOLOGIES, "liquidity"),
    ),
    ReportFamily(
        key="rolling_risk",
        section_title="Rolling risk",
        registered_methodologies=_ROLLING_RISK_METHODOLOGIES,
        read_values=_read_rolling_risk,
        read_provenance=_provenance_reader(
            RollingRiskResult, _ROLLING_RISK_METHODOLOGIES, "rolling_risk"
        ),
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
    "VAR_REGISTERED_METHODOLOGIES",
    "FamilyProvenance",
    "ReportFamily",
    "ReportProvenanceError",
    "family_for",
]
