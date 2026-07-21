"""Direct contract tests for the shared governed-result read helper (API-1, calc/reads.py).

``list_governed_results`` is exercised end-to-end by the pacing suite (which now delegates to it —
the behavior-identical golden). Here we pin ``latest_run_rows`` (a pure function) directly: the
run-DESC input contract → keep ONLY the newest run's rows, empty on empty.
"""

from __future__ import annotations

from dataclasses import dataclass

from irp_shared.calc.reads import latest_run_rows


@dataclass
class _Row:
    calculation_run_id: str
    v: int


def test_latest_run_rows_empty() -> None:
    assert latest_run_rows([]) == []


def test_latest_run_rows_single_run() -> None:
    rows = [_Row("run-A", 1), _Row("run-A", 2)]
    assert latest_run_rows(rows) == rows  # one run → all its rows


def test_latest_run_rows_keeps_only_the_newest_run() -> None:
    # The helper trusts the caller's run-DESC ordering: rows[0]'s run is the newest, and ONLY that
    # run's rows survive (the CC-2 latest-resolver contract; cross-run mixing is a consumer error).
    rows = [
        _Row("run-new", 1),
        _Row("run-new", 2),
        _Row("run-old", 9),  # an older run's row, interleaved after the newest
    ]
    out = latest_run_rows(rows)
    assert [r.v for r in out] == [1, 2]
    assert all(r.calculation_run_id == "run-new" for r in out)
