"""SCH-1 — the first scheduler: cadenced governed background execution (Wave-11 slice 1).

A governed CONTROL PLANE that re-executes already-shipped governed numbers on a cadence. It mints
NO new governed number — every fire re-invokes an existing family binder through the existing
governed-run scaffold.

**SCH-2 (Wave-13 slice 0)** discharged the SCH-1 family-2 deferral: a second cadence
(``CALENDAR_MONTH_END``, the last WEEKDAY of the month at END of day) and a second family
(``EXPOSURE_AGGREGATE``, the model-less rollup), both driven from ``service.FAMILY_REGISTRY``, plus
the read-only operator surface in ``queries.py``. See
``10_delivery_backlog/sch_1_decision_record.md`` and ``sch_2_decision_record.md``.
"""

from __future__ import annotations
