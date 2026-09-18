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
#: Fixture vocabulary, case-insensitive: the reviewer's probes ("Test Holding", "Sample Holding",
#: "Fixture A", "Placeholder Corp", "Dummy plc", "Instrument 1") all passed the first version.
_FIXTURE_NAMES = re.compile(
    r"\bINSTR-|\bCN-|\bdemo\b|\btest\b|\bfixture\b|\bsample\b|\bplaceholder\b|\bdummy\b"
    r"|\bfoo\b|\bbar\b|\binstrument \d|\bholding \d|\bsecurity \d|\bacme\b",
    re.IGNORECASE,
)


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
    assert all(re.fullmatch(r"ZZ\d{10}", i) for i in isins), "ISIN-shaped, user-assigned prefix"
    assert all(book.isin(i[:11]) == i for i in isins), "every ISIN carries its check digit"
    assert book.isin("US037833100") == "US0378331005"  # the algorithm against a known real ISIN
    issuers = {i.code for i in book.ISSUERS}
    for inst in book.INSTRUMENTS:
        assert inst.issuer in issuers
        assert not _FIXTURE_NAMES.search(inst.name), inst.name
        if "BOND" in inst.asset_class:
            assert inst.face_value is not None and inst.coupon_rate is not None
    accounts = {a.code for f in book.FUNDS for s in f.sleeves for a in s.accounts}
    assert all(i.account in accounts for i in book.INSTRUMENTS)
    held_by_fund: dict[str, set[str]] = {}
    for fund in book.FUNDS:
        assert fund.return_account in accounts
        assert fund.scenario_account is None or fund.scenario_account in accounts
        weights = sum(Decimal(m.weight) for m in book.BENCHMARK_MEMBERS[fund.code])
        assert weights == Decimal("1")
        fund_accounts = {a.code for s in fund.sleeves for a in s.accounts}
        held_by_fund[fund.code] = {i.code for i in book.INSTRUMENTS if i.account in fund_accounts}
        assert len(held_by_fund[fund.code]) >= 3, fund.code
        # The benchmark is never a subset of the fund's own holdings.
        assert not ({m.code for m in book.BENCHMARK_MEMBERS[fund.code]} & held_by_fund[fund.code])
    # Three DIFFERENT funds: no two share a holding.
    codes = list(held_by_fund)
    for x in codes:
        for y in codes:
            if x < y:
                assert not (held_by_fund[x] & held_by_fund[y]), (x, y)
    prices = {i.start_price for i in book.INSTRUMENTS if i.asset_class == "EQUITY"}
    assert len(prices) >= 20, "equities priced individually, not at one round number"
    quantities = {i.quantity for i in book.INSTRUMENTS}
    assert len(quantities) >= 20, "positions sized individually"


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
    for inst in book.INSTRUMENTS:
        if inst.coupon_rate == Decimal("0") and inst.face_value is not None:
            # a zero-coupon bill never trades above par
            assert all(v <= inst.face_value for v in paths.marks[inst.code].values()), inst.code
    for fund in book.FUNDS:
        assert len(paths.benchmark_returns[fund.code]) == len(book.BOUNDARIES) - 1
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
