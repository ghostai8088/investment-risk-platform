"""Generic ingestion staging (P1A-4, REQ-INT-001) — the first composing slice.

A domain-agnostic upload→validate→stage→DQ→lineage→audit capability: ``ingestion_batch`` (the
status-mutable run record) + immutable ``ingestion_staged_record`` (raw parsed rows, generic JSON),
an anti-corruption layer (CSV-only, size cap, filename sanitization, encoding validation, CSV
formula neutralization, a no-op AV seam) + ``stage_upload`` — which COMPOSES the shipped
rails: P1A-1 ``record_lineage`` (one ``data_source → ingestion_batch`` ORIGIN edge) and P1A-3
``run_quality_check`` / ``assert_passed_quality_checks`` (generic rules only). It maps NOTHING into
canonical domain tables (deferred to P1B/P1C) and reuses ``DATA.INGEST`` + ``DATA.VALIDATE`` (no new
audit code) and the ``data.upload`` permission (no new permission).

Durable evidence / no-silent-failure (CTRL-029 / CTRL-032): on an anti-corruption rejection or a DQ
ERROR the batch is driven to ``REJECTED`` and committed together with the staged rows, the flagged
``data_quality_result`` + ``DATA.INGEST``/``DATA.VALIDATE`` audit — never silently dropped.

This package imports only ``irp_shared.lineage`` + ``irp_shared.dq`` + ``irp_shared.audit`` (+ db) —
never ``irp_backend`` or ``irp_shared.model`` — and nothing imports it back (one-way dependency).
"""
