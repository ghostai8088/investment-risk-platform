"""MD-H1 guardrail (annex item 6): the shared no-RUNNING-orphan invariant assertion.

Every governed-run failure path — a pre-create refusal (422) or a post-create FAILED (a magnitude/DQ
gate) — must leave NO ``calculation_run`` stranded in ``RUNNING``: it is either absent (refused
pre-write) or terminal ``FAILED``. The BT-1 HIGH (a hand-minted NaN VaR detonating as a raw 500)
left exactly such a RUNNING orphan. This one helper lets any failure-path test assert the invariant
uniformly instead of re-deriving a bespoke count each time.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from irp_shared.calc.models import CalculationRun, RunStatus


def assert_no_running_orphan(session: Session, *, run_type: str | None = None) -> None:
    """Assert no ``calculation_run`` is stranded in ``RUNNING`` (optionally scoped to ``run_type``).

    Call after any refused/failed governed operation: a correct failure path leaves the run absent
    or terminal-FAILED, never RUNNING (the BT-1 orphan class).
    """
    q = (
        select(func.count())
        .select_from(CalculationRun)
        .where(CalculationRun.status == RunStatus.RUNNING.value)
    )
    if run_type is not None:
        q = q.where(CalculationRun.run_type == run_type)
    orphans = session.execute(q).scalar()
    assert orphans == 0, (
        f"a refused/failed run left {orphans} calculation_run row(s) in RUNNING "
        f"(run_type={run_type or 'ANY'}) — the BT-1 orphan class"
    )
