"""Data-source & lineage skeleton (P1A-1, REQ-LIN-001 / DEP-LIN).

The single ``record_lineage()`` capture contract (BX-LIN) every later governed write calls,
plus ``assert_has_lineage()`` for the no-bypass enforcement check (CTRL-013). Generic and
domain-agnostic: targets are referenced polymorphically by ``(entity_type, entity_id)`` with no
domain foreign key, so future Security Master / Portfolio / Risk / Private-Asset writes record
lineage without a schema change.
"""
