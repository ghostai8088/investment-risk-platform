"""Pluggable DQ evaluator interface + registry (pure logic, no DB).

A ``DQEvaluator`` is the ``DQRule.evaluate()`` interface: ``(params, dataset) -> DQEvaluation``. The
``REGISTRY`` maps a controlled-vocab ``rule_type`` string to an evaluator, so new GENERIC rule kinds
register by value + a function, never a schema migration (the genericity contract, MG-01 analog).
Exactly two generic evaluators are registered: ``not_null`` and ``allowed_values``. No domain rules.

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


#: The evaluator registry — exactly the two GENERIC rules (no domain-specific evaluators).
REGISTRY: dict[str, DQEvaluator] = {
    RULE_TYPE_NOT_NULL: evaluate_not_null,
    RULE_TYPE_ALLOWED_VALUES: evaluate_allowed_values,
}


def evaluate_rule(rule_type: str, params: Mapping[str, Any], dataset: Dataset) -> DQEvaluation:
    """Dispatch to the registered evaluator for ``rule_type`` (raises for an unknown type)."""
    evaluator = REGISTRY.get(rule_type)
    if evaluator is None:
        raise UnknownRuleTypeError(rule_type)
    return evaluator(params, dataset)
