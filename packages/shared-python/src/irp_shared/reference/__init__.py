"""Reference-data vocabularies (P1B-1, REQ-SMR-005 + REQ-SMR-004 calendar partial).

The first Security Master & Reference Data slice and the first to exercise **AD-013-R1 hybrid
tenancy**: three EV reference vocabularies — ``currency`` (ENT-005), ``calendar`` (ENT-006) +
``calendar_holiday``, and ``rating_scale`` (ENT-007 taxonomy only) + ``rating_grade`` — via direct
governed CRUD (no ingestion). A global row carries ``tenant_id = SYSTEM_TENANT_ID`` and is read by
every tenant; a tenant override carries the tenant's own ``tenant_id``; the two coexist under
``UNIQUE(tenant_id, code)``. Hybrid visibility is the **asymmetric RLS policy** in migration 0008
(``USING`` own-or-SYSTEM / ``WITH CHECK`` own-only); "tenant override wins" is an application-layer
read dedup (``service.dedupe_tenant_wins``), never an RLS or schema concern.

Every write roots one MANUAL-``data_source`` ORIGIN lineage edge and emits ``REFERENCE.CREATE`` /
``REFERENCE.UPDATE`` (EVT-140/141) co-transactionally to the FROZEN ``audit.service.record_event``
(children fold into the parent event). This package imports only ``irp_shared`` rails
(``lineage`` / ``audit`` / ``db`` / ``temporal`` / ``entitlement``) one-way — never ``irp_backend``,
``irp_shared.models`` (plural aggregator), or ``irp_shared.ingestion`` — enforced by a test.

**Taxonomy / scope only:** NO rating ASSIGNMENTS (the FR half of ENT-007), NO ``issuer`` /
``counterparty`` / ``instrument`` / ``identifier_xref`` / ``corporate_action``, NO day-count/roll/
recurrence-expansion math.
"""
