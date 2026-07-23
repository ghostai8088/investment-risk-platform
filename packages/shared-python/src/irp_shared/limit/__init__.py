"""LIM-1 — the governed LIMIT + BREACH workflow (Wave-11 slice 2, "operationalize").

The platform's first governed WRITE-SIDE workflow: a governed LIMIT DEFINITION (ENT-031, EV) is
evaluated on the per-tenant operational tick against the latest COMPLETED governed result for its
scope + metric; a breach appends an IA `breach` record (ENT-033). NOT a governed number — a breach
references an already-governed `calculation_run`, binding no new snapshot/model. See
``10_delivery_backlog/lim_1_decision_record.md``.
"""

from __future__ import annotations
