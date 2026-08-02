"""Pluggable DQ evaluator interface + registry (pure logic, no DB).

A ``DQEvaluator`` is the ``DQRule.evaluate()`` interface: ``(params, dataset) -> DQEvaluation``. The
``REGISTRY`` maps a controlled-vocab ``rule_type`` string to an evaluator, so new GENERIC rule kinds
register by value + a function, never a schema migration (the genericity contract, MG-01 analog).
Exactly four generic evaluators are registered: ``not_null``, ``allowed_values``, ``range`` (P2-2,
strictly-positive FX rates), and ``completeness`` (DATA-1 — the REF-1-deferred rule kind whose
persisted params carry the EXPECTED KEY SET, so the rule itself says what was expected; the
dominant vendor-file failure mode — a file silently missing a key — finally fails loudly). No
domain rules.

``evaluate()` ALWAYS returns a structured ``DQEvaluation`` (never None) so a failure is structurally
un-swallowable; a malformed rule (unknown type / bad params) raises — the caller audits + reraises.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

#: Controlled-vocab rule_type values seeded now (new generic kinds add a value + a function).
RULE_TYPE_NOT_NULL = "NOT_NULL"
RULE_TYPE_ALLOWED_VALUES = "ALLOWED_VALUES"
RULE_TYPE_RANGE = "RANGE"  # P2-2: numeric bound check (e.g. strictly-positive FX rate)
#: DATA-1 (OQ-DATA-1-4; the REF-1 trigger fired): exact expected-key-set equality, BOTH directions.
RULE_TYPE_COMPLETENESS = "COMPLETENESS"

Dataset = Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class DQEvaluation:
    """The structured outcome of evaluating a rule over a dataset (a value object, not the ORM)."""

    passed: bool
    observed_value: str | None = None
    detail: str | None = None
    evaluated_count: int = 0
    failed_count: int = 0


class DQEvaluator(Protocol):
    """The pluggable ``DQRule.evaluate()`` interface."""

    def __call__(self, params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation: ...


class UnknownRuleTypeError(Exception):
    """Raised when a rule's ``rule_type`` has no registered evaluator (a rule-config error)."""

    def __init__(self, rule_type: str) -> None:
        super().__init__(f"no evaluator registered for rule_type {rule_type!r}")
        self.rule_type = rule_type


def _require_column(params: Mapping[str, Any]) -> str:
    column = params.get("column")
    if not isinstance(column, str) or not column:
        raise ValueError("rule params must include a non-empty string 'column'")
    return column


def evaluate_not_null(params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation:
    """Generic: every row's ``params['column']`` must be non-null."""
    column = _require_column(params)
    failed = sum(1 for row in dataset if row.get(column) is None)
    if failed == 0:
        return DQEvaluation(passed=True, evaluated_count=len(dataset))
    return DQEvaluation(
        passed=False,
        observed_value=None,
        detail=f"{failed} null value(s) in column {column!r}",
        evaluated_count=len(dataset),
        failed_count=failed,
    )


def evaluate_allowed_values(params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation:
    """Generic: every row's ``params['column']`` must be in ``params['allowed']``."""
    column = _require_column(params)
    allowed = params.get("allowed")
    if not isinstance(allowed, list | tuple | set):
        raise ValueError("allowed_values rule params must include an 'allowed' list")
    allowed_set = set(allowed)
    offenders = [row.get(column) for row in dataset if row.get(column) not in allowed_set]
    if not offenders:
        return DQEvaluation(passed=True, evaluated_count=len(dataset))
    return DQEvaluation(
        passed=False,
        observed_value=str(offenders[0])[:500],
        detail=f"{len(offenders)} value(s) in column {column!r} not in the allowed set",
        evaluated_count=len(dataset),
        failed_count=len(offenders),
    )


def evaluate_range(params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation:
    """Generic: every row's ``params['column']`` must lie within ``[min, max]``. ``min``/``max`` are
    optional bounds; ``min_inclusive``/``max_inclusive`` default True. A NULL value is an offender
    (use ``not_null`` for nullability). Strictly-positive ⇒ ``{min: 0, min_inclusive: False}``."""
    column = _require_column(params)
    lo = params.get("min")
    hi = params.get("max")
    lo_inc = bool(params.get("min_inclusive", True))
    hi_inc = bool(params.get("max_inclusive", True))
    offenders: list[Any] = []
    for row in dataset:
        value = row.get(column)
        if value is None:
            offenders.append(value)
            continue
        below = lo is not None and (value < lo if lo_inc else value <= lo)
        above = hi is not None and (value > hi if hi_inc else value >= hi)
        if below or above:
            offenders.append(value)
    if not offenders:
        return DQEvaluation(passed=True, evaluated_count=len(dataset))
    return DQEvaluation(
        passed=False,
        observed_value=str(offenders[0])[:500],
        detail=f"{len(offenders)} value(s) in column {column!r} outside the allowed range",
        evaluated_count=len(dataset),
        failed_count=len(offenders),
    )


def evaluate_completeness(params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation:
    """Generic: the dataset's ``params['key_column']`` values must equal ``params['expected']``
    EXACTLY — both directions (a missing expected key fails; an unexpected observed key fails —
    the census-both-directions standard). The persisted rule's params carry the expected key set
    LITERALLY, so the rule itself says what was expected (the REF-1 trigger wording). The caller
    computes the expected set from DECLARATIONS (never from the data being checked — a data-derived
    boundary cannot represent a missing edge) and advances the persisted params as the declared
    horizon moves."""
    key_column = params.get("key_column")
    if not isinstance(key_column, str) or not key_column:
        raise ValueError("completeness rule params must include a non-empty string 'key_column'")
    expected = params.get("expected")
    if not isinstance(expected, list | tuple):
        raise ValueError("completeness rule params must include an 'expected' key list")
    expected_set = set(expected)
    observed_set = {row.get(key_column) for row in dataset}
    missing = sorted(str(k) for k in expected_set - observed_set)
    unexpected = sorted(str(k) for k in observed_set - expected_set)
    if not missing and not unexpected:
        return DQEvaluation(passed=True, evaluated_count=len(dataset))
    parts: list[str] = []
    if missing:
        parts.append(f"{len(missing)} expected key(s) MISSING (first: {missing[0]})")
    if unexpected:
        parts.append(f"{len(unexpected)} UNEXPECTED key(s) (first: {unexpected[0]})")
    return DQEvaluation(
        passed=False,
        observed_value=(missing or unexpected)[0][:500],
        detail=f"key set mismatch in column {key_column!r}: " + "; ".join(parts),
        evaluated_count=len(dataset),
        failed_count=len(missing) + len(unexpected),
    )


#: The evaluator registry — exactly the four GENERIC rules (no domain-specific evaluators).
REGISTRY: dict[str, DQEvaluator] = {
    RULE_TYPE_NOT_NULL: evaluate_not_null,
    RULE_TYPE_ALLOWED_VALUES: evaluate_allowed_values,
    RULE_TYPE_RANGE: evaluate_range,
    RULE_TYPE_COMPLETENESS: evaluate_completeness,
}


def evaluate_rule(rule_type: str, params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation:
    """Dispatch to the registered evaluator for ``rule_type`` (raises for an unknown type)."""
    evaluator = REGISTRY.get(rule_type)
    if evaluator is None:
        raise UnknownRuleTypeError(rule_type)
    return evaluator(params, dataset)
