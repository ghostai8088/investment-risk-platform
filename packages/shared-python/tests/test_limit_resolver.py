"""LIM-2: the concentration RESOLVER, executed — the coverage the slice shipped without.

The adversarial review's D6: nothing in the repository executed ``_resolve_concentration`` past its
first early return. Not the basis refusal, not the zero-bucket rule, not the summary path — while
``service.py`` stated as FACT that "its test forces the mismatch by writing a row with a different
basis directly" and the decision record ratified that this refusal ships with an executed negative
control. Both claims were false. This module is the artifact those claims should have cited.

It is a Python-tier module using hand-built row stubs rather than a seeded database, deliberately:
the subject is the resolver's DECISION LOGIC over a set of result rows, and a stub set makes the
adversarial cases — a foreign scheme's code, a sentinel, a basis that no shipped writer can produce
— constructible at all. The end-to-end proof that these rows are the ones the platform really
writes lives in the PG tier and the demo stage.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from irp_shared.concentration.models import (
    BUCKET_UNCLASSIFIED,
    DIMENSION_KIND_ISSUER,
    METRIC_TYPE_SHARE,
    ROW_KIND_DETAIL,
    ROW_KIND_SUMMARY,
)
from irp_shared.limit.events import BREACH_ABOVE, BREACH_BELOW, THRESHOLD_UNIT_FRACTION
from irp_shared.limit.service import (
    _resolve_concentration,
    _spec_for,
)

_RUN = "run-1"
_SCHEME = str(uuid.uuid4())
_TENANT = str(uuid.uuid4())


def _row(**kw):  # noqa: ANN003, ANN201
    """One ``concentration_result``-shaped row."""
    base = {
        "calculation_run_id": _RUN,
        "dimension_kind": "SECTOR_INDUSTRY",
        "row_kind": ROW_KIND_DETAIL,
        "metric_type": METRIC_TYPE_SHARE,
        "bucket_code": "C",
        "scheme_id": _SCHEME,
        "issuer_id": None,
        "denominator_basis": "INVESTED_LONG",
        "share_invested_long": Decimal("0.31"),
        "metric_value": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _limit(**kw):  # noqa: ANN003, ANN201
    base = {
        "tenant_id": _TENANT,
        "scope_portfolio_id": "pf-1",
        "target_run_type": "CONCENTRATION",
        "metric_type": METRIC_TYPE_SHARE,
        "threshold_unit": THRESHOLD_UNIT_FRACTION,
        "threshold_value": Decimal("0.20"),
        "breach_direction": BREACH_ABOVE,
        "dimension_kind": "SECTOR_INDUSTRY",
        "bucket_code": "C",
        "issuer_id": None,
        "scheme_family": "ISIC",
        "authored_scheme_id": _SCHEME,
        "denominator_basis": "INVESTED_LONG",
    }
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture()
def rows_of(monkeypatch):  # noqa: ANN001, ANN201
    """Point the resolver at a chosen row set; return a knob for whether a code is a real node."""
    state = {"rows": [], "known_codes": {"C", "K"}}

    def _fake_latest(session, **kw):  # noqa: ANN001, ANN003, ARG001
        return state["rows"]

    import irp_shared.concentration.service as conc_service

    monkeypatch.setattr(conc_service, "latest_concentration", _fake_latest)

    # The taxonomy lookup the resolver uses to tell a real-but-empty bucket from a bogus one.
    import irp_shared.classification.service as cls_service

    def _fake_resolve_node(session, *, scheme_id, code, acting_tenant):  # noqa: ANN001, ARG001
        if code not in state["known_codes"]:
            raise cls_service.ClassificationNotVisible(f"no node {code!r}")
        return SimpleNamespace(code=code)

    monkeypatch.setattr(cls_service, "resolve_node", _fake_resolve_node)
    return state


def _resolve(limit, state):  # noqa: ANN001, ANN202
    return _resolve_concentration(None, limit, _spec_for(limit))


class TestTheBasisDiscipline:
    """The EVALUATION-TIME half of OQ-LIM-2-4 — the refusal the record singled out and never
    tested. With one value in the shipped vocabulary this is unreachable through any production
    write path, which is exactly why it must be forced here: otherwise the day a second basis
    lands is the day this guard executes for the first time, in anger."""

    def test_a_mismatched_basis_is_REFUSED_not_thresholded(self, rows_of) -> None:  # noqa: ANN001
        rows_of["rows"] = [_row(denominator_basis="NAV")]
        out = _resolve(_limit(), rows_of)
        assert out.refusal is not None
        assert "basis mismatch" in out.refusal
        assert not out.is_resolved
        assert out.observed is None, "a refused resolution must carry no comparable value"

    def test_the_POSITIVE_CONTROL_a_matching_basis_resolves(self, rows_of) -> None:  # noqa: ANN001
        """Without this, the refusal above would pass just as well if the resolver refused
        everything."""
        rows_of["rows"] = [_row()]
        out = _resolve(_limit(), rows_of)
        assert out.refusal is None
        assert out.is_resolved
        assert out.observed == Decimal("0.31")
        assert out.resolved_scheme_id == _SCHEME

    def test_the_basis_is_checked_on_the_SUMMARY_path_too(self, rows_of) -> None:  # noqa: ANN001
        """Both return paths call the same guard — a regression that dropped it from one would
        otherwise be invisible."""
        rows_of["rows"] = [
            _row(
                row_kind=ROW_KIND_SUMMARY,
                metric_type="HHI_SECTOR_INDUSTRY",
                bucket_code="__SUMMARY__",
                metric_value=Decimal("0.4"),
                share_invested_long=None,
                denominator_basis="NAV",
            )
        ]
        out = _resolve(_limit(metric_type="HHI_SECTOR_INDUSTRY", bucket_code=None), rows_of)
        assert out.refusal is not None and "basis mismatch" in out.refusal


class TestTheFabricatedZero:
    """**Finding D1.** The resolver used to return a fully-resolved ``observed=0`` whenever the
    named bucket matched no row — conflating "the book holds none of it" with "your selector named
    something this run never evaluated"."""

    def test_a_bucket_code_that_names_no_node_is_REFUSED(self, rows_of) -> None:  # noqa: ANN001
        """The slice's headline limit, mistyped: ISIC codes sections as letters, so a limit written
        as 'TECH' matched nothing and read IN_APPETITE forever on a 31%-concentrated book."""
        rows_of["rows"] = [_row()]
        out = _resolve(_limit(bucket_code="TECH"), rows_of)
        assert out.refusal is not None
        assert "never evaluated" in out.refusal
        assert not out.is_resolved

    def test_a_REAL_node_with_no_row_resolves_to_an_honest_ZERO(self, rows_of) -> None:  # noqa: ANN001
        """The case the refusal must NOT swallow: 'K' is a genuine node of the run's scheme that
        emitted no row, so the book truly holds none of it. Refusing here would fail OPEN on a
        floor limit and cry wolf on a ceiling."""
        rows_of["rows"] = [_row()]
        out = _resolve(_limit(bucket_code="K"), rows_of)
        assert out.refusal is None
        assert out.is_resolved
        assert out.observed == Decimal(0)

    def test_a_BELOW_floor_writes_NO_false_breach_on_an_unknown_bucket(self, rows_of) -> None:  # noqa: ANN001
        """The severe direction. A floor limit ('at least 5% in tech') over a bogus code used to
        resolve observed=0, satisfy `_breaches(0, 0.05, BELOW)`, and write a breach into the
        APPEND-ONLY, non-withdrawable lifecycle — the exact harm the CON-1 descope exists to
        prevent, and unretractable once written."""
        rows_of["rows"] = [_row()]
        out = _resolve(
            _limit(
                bucket_code="TECH", breach_direction=BREACH_BELOW, threshold_value=Decimal("0.05")
            ),
            rows_of,
        )
        assert not out.is_resolved, "an unverifiable selector must not produce a comparable value"

    def test_a_BELOW_floor_STILL_breaches_on_a_real_empty_bucket(self, rows_of) -> None:  # noqa: ANN001
        """The counter-control: the fix must not turn a genuine floor violation into a refusal.
        'K' is real and empty, so zero is a measurement and the floor is genuinely breached."""
        rows_of["rows"] = [_row()]
        out = _resolve(
            _limit(bucket_code="K", breach_direction=BREACH_BELOW, threshold_value=Decimal("0.05")),
            rows_of,
        )
        assert out.is_resolved and out.observed == Decimal(0)

    def test_a_sentinel_bucket_is_REFUSED_at_resolution(self, rows_of) -> None:  # noqa: ANN001
        """0057's `detail_shape` CHECK forbids __SUMMARY__ on a DETAIL row, so a limit naming one
        can never match — an unfireable control that would read green forever."""
        rows_of["rows"] = [_row()]
        out = _resolve(_limit(bucket_code=BUCKET_UNCLASSIFIED), rows_of)
        assert out.refusal is not None and not out.is_resolved

    def test_an_ISSUER_bucket_needs_no_taxonomy_lookup(self, rows_of) -> None:  # noqa: ANN001
        """ISSUER carries no scheme, and `create_limit` proves the issuer exists tenant-filtered
        before the write — so absence from the run IS zero exposure, with no node to consult."""
        issuer = str(uuid.uuid4())
        rows_of["rows"] = [
            _row(dimension_kind=DIMENSION_KIND_ISSUER, scheme_id=None, bucket_code="other")
        ]
        out = _resolve(
            _limit(
                dimension_kind=DIMENSION_KIND_ISSUER,
                bucket_code=issuer,
                issuer_id=issuer,
                scheme_family=None,
                authored_scheme_id=None,
            ),
            rows_of,
        )
        assert out.refusal is None and out.observed == Decimal(0)


class TestNothingToEvaluate:
    def test_a_run_that_never_covered_the_dimension_resolves_NOTHING(self, rows_of) -> None:  # noqa: ANN001
        """Distinct from both a refusal and a zero: no COMPLETED run covered this dimension, so the
        metric is genuinely cold and `limit_health` must say NEVER_EVALUABLE."""
        rows_of["rows"] = [_row(dimension_kind="COUNTRY_OF_RISK")]
        out = _resolve(_limit(), rows_of)
        assert out.refusal is None and not out.is_resolved and out.run_id is None


class TestStalenessIsAnchoredOnTheRESOLVEDRun:
    """**Review D5.** The first version asked an independent question — "is the NEWEST run of this
    (tenant, run_type, scope) FAILED?" — while the resolvers key more narrowly (VaR adds
    ``metric_type``, active risk adds ``benchmark_id``) and ``calculation_run`` carries no metric
    discriminator. So a COMPLETED sibling-metric run landing after a failure CLEARED the flag while
    the verdict was still read off the pre-failure book, and a FAILED sibling RAISED it on a limit
    whose own number was minutes old. Anchoring on the resolved run makes the answer monotone.
    """

    def _rows(self, monkeypatch, resolved_at, failures):  # noqa: ANN001, ANN202
        """Stub the two run lookups: the resolved run's system_from, then any newer FAILED run."""
        import irp_shared.limit.service as svc

        calls = {"n": 0}

        class _Result:
            def __init__(self, value):
                self._value = value

            def scalar_one_or_none(self):  # noqa: ANN201
                return self._value

        class _Session:
            def execute(self, *_a, **_k):  # noqa: ANN002, ANN003, ANN201
                calls["n"] += 1
                return _Result(resolved_at if calls["n"] == 1 else failures)

        return svc._superseded_by_a_failed_run(_Session(), _limit(), "resolved-run")

    def test_a_FAILED_run_newer_than_the_verdict_raises_staleness(self, monkeypatch) -> None:  # noqa: ANN001
        assert self._rows(monkeypatch, resolved_at=1, failures="a-newer-failed-run") is True

    def test_no_newer_failure_leaves_it_clear(self, monkeypatch) -> None:  # noqa: ANN001
        """The positive control: without it, a check that always returned True would pass above."""
        assert self._rows(monkeypatch, resolved_at=1, failures=None) is False

    def test_a_missing_resolved_run_is_not_reported_stale(self, monkeypatch) -> None:  # noqa: ANN001
        """Defensive: the resolver just read it, so None means something is deeply wrong — but
        asserting staleness on a run we cannot date would be a fabricated signal."""
        assert self._rows(monkeypatch, resolved_at=None, failures="anything") is False
