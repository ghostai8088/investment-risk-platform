"""Data-quality skeleton (P1A-3, REQ-DQR-001 / DEP-DQF).

A generic, pluggable rule engine: ``data_quality_rule`` (config) + immutable ``data_quality_result``
(run output), a ``DQEvaluator`` interface with a small registry of **generic** evaluators
(``not_null``, ``allowed_values``), ``run_quality_check`` (evaluate + persist + audit), and
``assert_passed_quality_checks`` — the no-silent-failure gate a **future** P1A-4 ingestion calls.

No-silent-failure (CTRL-029 / QS-15/16/06 / BR-14): a failing check ALWAYS persists a flagged
result; ``severity=ERROR`` additionally raises; ``WARNING`` flags-only; an evaluator error always
propagates and is audited ``outcome='failure'`` — never silently passes.

This package imports only ``irp_shared.audit`` (+ db/temporal) — never ingestion, lineage, model, or
backend — so the single contract is callable by the web app and future workers without coupling.
"""
