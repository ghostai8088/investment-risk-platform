"""BOOK-1a — the Northlight book's own fences, unit tier (no database).

What the PostgreSQL suite cannot cheaply say: that the book is deterministic, that its boundary
set has the thirteen month-ends the twelve-month rolling window needs (the remit's BLOCKING
finding, B-1), that its values sit inside the realism bands, that its names are not fixture names,
and that the package carries no clock and no future literal (the seed's own time-bomb fence,
Part 2.3 of the remit).
"""

from __future__ import annotations

import ast
import pathlib
import re
from datetime import date
from decimal import Decimal

from irp_shared.demo_tenant import book

_PKG = pathlib.Path(book.__file__).resolve().parent
_FIXTURE_NAMES = re.compile(r"\bINSTR-|\bCN-|\bDemo\b|\bdemo\b|\bTEST\b|\bFIXTURE\b")


def test_the_marked_year_opens_and_closes_on_a_month_end_with_thirteen_of_them() -> None:
    """A twelve-month rolling window needs thirteen month-end boundaries; the first draft of the
    remit had twelve and would have produced SUPPRESSED rows for every fund."""
    assert book.MONTH_ENDS[0] == book.YEAR_START == date(2025, 6, 30)
    assert book.MONTH_ENDS[-1] == book.YEAR_END == date(2026, 6, 30)
    assert len(book.MONTH_ENDS) == 13
    assert book.BOUNDARIES[0] == book.YEAR_START and book.BOUNDARIES[-1] == book.YEAR_END
    assert set(book.MONTH_ENDS) <= set(book.BOUNDARIES)
    assert 50 <= len(book.BOUNDARIES) <= 60
    assert all(book.is_business_day(d) for d in book.BOUNDARIES)


def test_the_book_is_deterministic() -> None:
    a, b = book.generate_paths(), book.generate_paths()
    assert a == b


def test_the_book_is_a_fund_not_a_fixture() -> None:
    assert 50 <= len(book.INSTRUMENTS) <= 80
    codes = [i.code for i in book.INSTRUMENTS]
    assert len(set(codes)) == len(codes)
    isins = [i.isin for i in book.INSTRUMENTS]
    assert len(set(isins)) == len(isins)
    assert all(
        re.fullmatch(r"ZZ\d{10}", isin) for isin in isins
    ), "ISIN-shaped, user-assigned prefix"
    issuers = {i.code for i in book.ISSUERS}
    for inst in book.INSTRUMENTS:
        assert inst.issuer in issuers
        assert not _FIXTURE_NAMES.search(inst.name), inst.name
        if "BOND" in inst.asset_class:
            assert inst.face_value is not None and inst.coupon_rate is not None
    accounts = {a.code for f in book.FUNDS for s in f.sleeves for a in s.accounts}
    assert all(i.account in accounts for i in book.INSTRUMENTS)
    for fund in book.FUNDS:
        assert fund.return_account in accounts
        weights = sum(Decimal(w) for _, w in book.BENCHMARK_CONSTITUENTS[fund.code])
        assert weights == Decimal("1")


def test_values_sit_inside_the_realism_bands() -> None:
    paths = book.generate_paths()
    for inst in book.INSTRUMENTS:
        series = [float(v) for v in paths.marks[inst.code].values()]
        assert len(series) == len(book.BOUNDARIES)
        assert all(1.0 <= v <= 10_000 for v in series), inst.code
        for a, b in zip(series, series[1:], strict=False):
            assert abs(b / a - 1) < 0.15, (inst.code, a, b)  # a boundary is a week
    for series in paths.fx.values():
        assert all(Decimal("0.5") <= v <= Decimal("200") for v in series.values())
    for code, series in paths.factor_returns.items():
        assert all(abs(v) < Decimal("0.05") for v in series.values()), code
        assert set(series) == set(book.RETURN_DAYS)
    assert all(book.is_business_day(d) for d in book.RETURN_DAYS)


def test_the_package_carries_no_clock_and_no_future_literal() -> None:
    """The seed's own time-bomb fence: no `now()`/`today()` anywhere, and no date literal later
    than the marked year's end. The XNYS 2035 coverage horizon is imported, not written here."""
    for path in _PKG.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            # A CALL to now()/today()/utcnow(), by name or attribute; a docstring may say the word.
            if isinstance(node, ast.Call):
                callee = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                assert callee not in {"now", "today", "utcnow"}, f"{path.name} reads the clock"
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"date", "datetime"}:
                args = [a.value for a in node.args if isinstance(a, ast.Constant)]
                if len(args) >= 3 and all(isinstance(a, int) for a in args[:3]):
                    assert date(*args[:3]) <= book.YEAR_END, f"{path.name}: {args[:3]}"
        # Quoted ISO dates are values; a bare date in a docstring is prose (a ratification date,
        # say) and is not a time bomb.
        for m in re.finditer(r"[\"'](20\d\d)-(\d\d)-(\d\d)[\"']", text):
            assert date(*map(int, m.groups())) <= book.YEAR_END, f"{path.name}: {m.group(0)}"
