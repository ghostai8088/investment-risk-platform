"""PRESENT-1 (REQ-PRS-001): how each governed family's numbers are ALLOWED to be shown.

A presentation contract says, for one run-type family: what MARK renders it, in what UNIT, to what
PRECISION, and which fields IDENTIFY a value so no rendered number is anonymous.

**Import-light on purpose**, the `aggregation/contracts.py` shape: string-literal keys, no service
imports, no model imports. A declaration that has to import the thing it describes cannot be read by
the thing it describes.

## Why exclusions are CATEGORICAL rather than free text (DS1-1, owner-ratified 2026-09-05)

Eighteen of the twenty-two families in the run-type vocabulary have no report section. If each
carried the reason "no report section binds this family", the census would reduce to asserting
``A ∪ (vocabulary − A) == vocabulary`` — a tautology dressed as a control — and the reasons would be
the boilerplate kind that has been FALSE here before: four of REPRO-1's free-text registry reasons
were later found factually wrong, discovered only when an adapter executed against them.

So each exclusion names a category from :data:`EXCLUSION_CATEGORIES`, and each category is a
falsifiable claim about the family rather than a restatement of its absence.

**The honest limit, stated because the alternative is an overclaim.** The census asserts a category
is IN the vocabulary. It does not assert the category is TRUE of the family — nothing mechanical
can, short of the report sections this row exists to plan. What the vocabulary buys is a narrow set
of things that can be said, so a wrong classification is visible to a reader rather than buried in a
sentence. That is a real improvement and it is not correctness.

## Two namespaces, bridged explicitly

The census universe is keyed by UPPERCASE run type (``VAR``) because that is what the vocabulary
holds. A pinned report section carries a lowercase family key (``var``). They are not the same
namespace and today's coincidence — that every report family key is its run type lowercased — is a
fact about four rows, not a rule. :data:`FAMILY_KEY_TO_RUN_TYPE` states the mapping, and the census
pins it against ``REPORT_FAMILIES`` by exact set equality, so a family key that stops being a
lowercased run type fails loudly instead of resolving to nothing.
"""

from __future__ import annotations

from typing import Any

#: The mark shapes REQ-PRS-002 admits. A contract naming anything else fails the census, and the
#: renderer refuses it — the acceptance text enumerates exactly these four, so the vocabulary is
#: closed at the requirement rather than at the author's convenience.
MARK_PATH = "path"
MARK_RECT = "rect"
MARK_LINE = "line"
MARK_CIRCLE = "circle"
MARK_TYPES: tuple[str, ...] = (MARK_PATH, MARK_RECT, MARK_LINE, MARK_CIRCLE)

#: Why a family has no presentation contract. A CLOSED vocabulary (DS1-1).
#:
#: - ``NOT_A_MEASURE``: the family's rows carry no presentable number at all. A report generation
#:   row and a reproduction sweep verdict are records THAT something happened, not measurements of
#:   anything — there is no quantity a contract could describe.
#: - ``INTERMEDIATE_INPUT``: the family produces numbers, and they are consumed by another governed
#:   family rather than shown. A covariance matrix and a factor loading are inputs to a headline,
#:   not headlines.
#: - ``NO_SECTION_YET``: the family would be presentable and nothing binds it to a report section.
#:   The only category that is a statement about the ROADMAP rather than about the family, and the
#:   only one that should shrink over time.
EXCLUSION_NOT_A_MEASURE = "NOT_A_MEASURE"
EXCLUSION_INTERMEDIATE_INPUT = "INTERMEDIATE_INPUT"
EXCLUSION_NO_SECTION_YET = "NO_SECTION_YET"
EXCLUSION_CATEGORIES: tuple[str, ...] = (
    EXCLUSION_NOT_A_MEASURE,
    EXCLUSION_INTERMEDIATE_INPUT,
    EXCLUSION_NO_SECTION_YET,
)

#: report family key -> run type. The bridge between the two namespaces, DECLARED.
FAMILY_KEY_TO_RUN_TYPE: dict[str, str] = {
    "var": "VAR",
    "concentration": "CONCENTRATION",
    "liquidity": "LIQUIDITY",
    "rolling_risk": "ROLLING_RISK",
}

#: run type -> contract, for every family a report section binds.
#:
#: ``identity`` names the fields that make a rendered number unambiguous. It is CONSUMED: the
#: renderer labels each value with them, so "no rendered number is anonymous" is a property of the
#: bytes rather than of a dict nobody reads.
#:
#: ``series_selector`` is present only where a family holds MORE THAN ONE series and the chart must
#: say which. `rolling_risk` holds nine — four seven-point 12-month series and five single-point
#: 36-month rows, all five of those SUPPRESSED — so charting "its values" would concatenate
#: drawdown, return and volatility into one meaningless line. The selector lives HERE rather than in
#: the renderer precisely so that changing it changes the chart, which is what makes REQ-PRS-002's
#: "produced FROM the pinned contract" bite.
PRESENTATION_CONTRACTS: dict[str, dict[str, Any]] = {
    "VAR": {
        "mark": MARK_RECT,
        "unit": "base_currency",
        "precision": 2,
        # metric_type discriminates seven models under one run type; base_currency says in what.
        # A board report saying "VaR: 12,345" without both is a disclosure defect.
        "identity": ("metric_type", "base_currency"),
    },
    "CONCENTRATION": {
        "mark": MARK_RECT,
        "unit": "fraction",
        "precision": 6,
        "identity": ("bucket_key",),
    },
    "LIQUIDITY": {
        "mark": MARK_RECT,
        "unit": "fraction",
        "precision": 6,
        "identity": ("tier",),
    },
    "ROLLING_RISK": {
        "mark": MARK_PATH,
        "unit": "fraction",
        "precision": 12,
        "identity": ("metric_type", "window_months"),
        # DS1-2 (owner-ratified 2026-09-05, on the second asking). ONE named series: seven points,
        # none suppressed. The first framing of that decision called this family's 33 rows "a
        # genuine time series" — they are nine — and the owner ratified on it before the error was
        # caught. Naming the series here is the fix.
        "series_selector": {"metric_type": "ROLLING_VOLATILITY", "window_months": 12},
    },
}

#: run type -> exclusion category, for every family NO report section binds.
PRESENTATION_EXCLUSIONS: dict[str, str] = {
    # Records that something happened, not measurements of anything.
    "REPORT": EXCLUSION_NOT_A_MEASURE,
    "REPRODUCTION": EXCLUSION_NOT_A_MEASURE,
    # Consumed by another governed family rather than shown.
    "COVARIANCE": EXCLUSION_INTERMEDIATE_INPUT,
    "COVARIANCE_PRIVATE": EXCLUSION_INTERMEDIATE_INPUT,
    "FACTOR_EXPOSURE": EXCLUSION_INTERMEDIATE_INPUT,
    "PURE_PRIVATE_FACTOR": EXCLUSION_INTERMEDIATE_INPUT,
    "PROXY_WEIGHT_ESTIMATE": EXCLUSION_INTERMEDIATE_INPUT,
    "DESMOOTHED_RETURN": EXCLUSION_INTERMEDIATE_INPUT,
    "SENSITIVITY": EXCLUSION_INTERMEDIATE_INPUT,
    # Presentable; nothing binds them to a report section yet.
    "ACTIVE_RISK": EXCLUSION_NO_SECTION_YET,
    "BENCHMARK_RELATIVE": EXCLUSION_NO_SECTION_YET,
    "ES_BACKTEST": EXCLUSION_NO_SECTION_YET,
    "EXPOSURE_AGGREGATE": EXCLUSION_NO_SECTION_YET,
    "PACING_PROJECTION": EXCLUSION_NO_SECTION_YET,
    "PORTFOLIO_RETURN": EXCLUSION_NO_SECTION_YET,
    "SCENARIO": EXCLUSION_NO_SECTION_YET,
    "SHARPE": EXCLUSION_NO_SECTION_YET,
    "VAR_BACKTEST": EXCLUSION_NO_SECTION_YET,
}


class PresentationContractError(Exception):
    """A family's presentation contract cannot be resolved, or a pinned one is unusable.

    Its own class rather than a bare ``KeyError`` because REQ-PRS-001 requires that a family whose
    contract no renderer can resolve FAILS, and a failure that surfaces as an opaque 500 (or worse,
    as a silent default) is not a refusal anyone can act on.
    """


def contract_for_run_type(run_type: str) -> dict[str, Any]:
    """The contract for a run type, or REFUSE. Never a default."""
    try:
        return PRESENTATION_CONTRACTS[run_type]
    except KeyError:
        raise PresentationContractError(
            f"no presentation contract for run type {run_type!r}; it is "
            + (
                f"declared excluded ({PRESENTATION_EXCLUSIONS[run_type]})"
                if run_type in PRESENTATION_EXCLUSIONS
                else "in neither the contract set nor the exclusion set"
            )
        ) from None


def contract_for_family_key(family_key: str) -> dict[str, Any]:
    """The contract for a REPORT family key (``var``), bridged to its run type. Never a default."""
    run_type = FAMILY_KEY_TO_RUN_TYPE.get(family_key)
    if run_type is None:
        raise PresentationContractError(
            f"report family key {family_key!r} has no declared run type — the two namespaces are "
            f"bridged by FAMILY_KEY_TO_RUN_TYPE, never by lowercasing"
        )
    return contract_for_run_type(run_type)


__all__ = [
    "EXCLUSION_CATEGORIES",
    "EXCLUSION_INTERMEDIATE_INPUT",
    "EXCLUSION_NOT_A_MEASURE",
    "EXCLUSION_NO_SECTION_YET",
    "FAMILY_KEY_TO_RUN_TYPE",
    "MARK_TYPES",
    "PRESENTATION_CONTRACTS",
    "PRESENTATION_EXCLUSIONS",
    "PresentationContractError",
    "contract_for_family_key",
    "contract_for_run_type",
]
