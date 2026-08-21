"""Audit event types for the mapping lifecycle (W19-S3a, R-07 mint DS3a-2).

``DATA.MAPPING`` is a NEW DATA-category code, minted at this slice by the governed R-07 process;
the row in ``04_data_model/audit_event_taxonomy.md`` IS the mint record (the SCH-1 / LIM-1
precedent). ``audit/service.py`` stays FROZEN — this is a caller-side ``event_type`` string
constant, never a central enum.

**Why the mint moved here from S3b.** The wave plan filed the mapping codes with S3b's permission
mint. But S3a is where the PROPOSED → RATIFIED → SUPERSEDED lifecycle is born, and no existing code
covers it: ``DATA.INGEST`` is scoped to the ``ingestion_batch`` lifecycle and ``DATA.VALIDATE`` to
DQ runs. S3a as planned would have shipped a governed status lifecycle emitting NOTHING, which no
other lifecycle on this platform does. Surfaced as a scope change and ratified by the owner
(DS3a-2), not taken as a builder's call. The permission codes still land at S3b with the four-eyes
lifecycle.

**One code, two actions — the ``DATA.INGEST`` shape exactly**: ``action=create`` when a version is
proposed, ``action=status_change`` on every ratify and supersede transition. Minting three
verb-shaped codes would have been three mints where the platform's own precedent needs one.

*The first draft of this docstring said "ratify / supersede / withdraw". No verb transitions a
version to WITHDRAWN — the constant is reserved and the verb is S3b's — so the word described an
action the shipped code cannot produce. A reviewer caught it; a verifier then partly refuted the
finding on the grounds that the taxonomy row itself never echoed the word, which is true and is why
this is a docstring correction rather than a mint correction.*

``before`` / ``after`` are DC-2 metadata only: version identity, status, authorship, the operations
HASH and the operation KINDS — **never the operations themselves and never a staged cell**, because
a mapping's column names are client schema and the ingest path's redaction rule already pins that
audit payloads carry metadata and reason codes only.
"""

from __future__ import annotations

#: The minted code (R-07, W19-S3a). Its taxonomy row is the mint record.
MAPPING_EVENT = "DATA.MAPPING"

#: ``entity_type`` literal for audit + lineage (the table name).
ENTITY_MAPPING_VERSION = "ingestion_mapping_version"

#: ``source_module`` for every mapping audit event.
SOURCE_MODULE = "ingest_mapping"
