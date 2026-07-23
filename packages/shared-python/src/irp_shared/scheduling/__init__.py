"""SCH-1 — the first scheduler: cadenced governed background execution (Wave-11 slice 1).

A governed CONTROL PLANE that re-executes already-shipped governed numbers on a cadence. It mints
NO new governed number — every fire re-invokes an existing family binder (v1: ``run_var``) through
the existing governed-run scaffold. See ``10_delivery_backlog/sch_1_decision_record.md``.
"""

from __future__ import annotations
