"""CON-1 kernel tests — the record's Part 2 literals, carried as LITERALS (never recomputed from
the fixtures: the expected value and the code must not share a point of failure)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from irp_shared.concentration.kernel import (
    GAP_ALL_UNCLASSIFIABLE,
    GAP_COVERAGE_BELOW_FLOOR,
    GAP_ZERO_INVESTED_LONG,
    Atom,
    compute_dimension,
)
from irp_shared.concentration.models import (
    BUCKET_SENTINELS,
    BUCKET_UNCLASSIFIABLE,
    BUCKET_UNCLASSIFIED,
    CONCENTRATION_METRIC_TYPES,
    SUMMARY_METRIC_TYPES,
)

FLOOR = Decimal("0.5")


def _d(v: str) -> Decimal:
    return Decimal(v)


class TestDemoGlobalBook:
    """The all-long flagship book (Part 2 table 1): issuer shares + HHI to six decimals."""

    ATOMS = [
        Atom(_d("60000.000000"), "ACME-CORP"),
        Atom(_d("30780.000000"), "EURX-AG"),
        Atom(_d("54000.000000"), "HARBOR-GP"),
    ]

    def test_shares_and_summary(self) -> None:
        r = compute_dimension(self.ATOMS, FLOOR)
        assert r.gaps == ()
        assert r.total_long == _d("144780.000000")
        shares = {b.bucket_code: b.share_invested_long for b in r.buckets}
        assert shares == {
            "ACME-CORP": _d("0.414422"),
            "HARBOR-GP": _d("0.372980"),
            "EURX-AG": _d("0.212598"),
        }
        assert r.hhi == _d("0.356057")
        assert r.max_share == _d("0.414422")
        assert r.coverage_ratio == _d("1.000000")
        assert r.coverage_classifiable == _d("1.000000")

    def test_hhi_tolerance_identity_over_classified(self) -> None:
        """abs(HHI − Σ_classified share²) ≤ N·10⁻⁶ (OQ-CON-1-3) — the quantize-order tolerance."""
        r = compute_dimension(self.ATOMS, FLOOR)
        recomputed = sum(
            (b.share_invested_long**2 for b in r.buckets if not b.is_residual), Decimal("0")
        )
        assert abs(r.hhi - recomputed) <= len(r.buckets) * Decimal("0.000001")


class TestDemoConcentrationBook:
    """Part 2's per-dimension book: the v6 re-derived literals (BETA-LLC is CLASSIFIED in the
    issuer dimension; the residual demonstration lives in sector/country)."""

    ISSUER_ATOMS = [
        Atom(_d("60000.000000"), "ALPHA-CORP"),
        Atom(_d("30000.000000"), "BETA-LLC"),
        Atom(_d("10000.000000"), None, BUCKET_UNCLASSIFIABLE),
    ]
    SECTOR_ATOMS = [
        Atom(_d("60000.000000"), "C"),
        Atom(_d("30000.000000"), None, BUCKET_UNCLASSIFIED),
        Atom(_d("10000.000000"), None, BUCKET_UNCLASSIFIABLE),
    ]

    def test_issuer_dimension(self) -> None:
        r = compute_dimension(self.ISSUER_ATOMS, FLOOR)
        assert r.gaps == ()
        shares = {b.bucket_code: b.share_invested_long for b in r.buckets}
        assert shares == {
            "ALPHA-CORP": _d("0.600000"),
            "BETA-LLC": _d("0.300000"),
            BUCKET_UNCLASSIFIABLE: _d("0.100000"),
        }
        assert r.coverage_ratio == _d("0.900000")
        assert r.coverage_classifiable == _d("1.000000")
        assert r.hhi == _d("0.450000")
        assert r.max_share == _d("0.600000")
        assert r.cr_n == _d("0.900000")

    def test_sector_dimension_with_residuals(self) -> None:
        r = compute_dimension(self.SECTOR_ATOMS, FLOOR)
        assert r.gaps == ()
        assert r.coverage_ratio == _d("0.600000")
        assert r.coverage_classifiable == _d("0.666667")
        assert r.hhi == _d("0.360000")
        assert r.max_share == _d("0.600000")
        assert r.cr_n == _d("0.600000")

    def test_residuals_stay_in_denominator_and_out_of_rankings(self) -> None:
        r = compute_dimension(self.SECTOR_ATOMS, FLOOR)
        assert sum((b.share_invested_long for b in r.buckets), Decimal("0")) == _d("1.000000")
        assert r.max_share < _d("0.700000"), "a 0.3 residual must never rank"


class TestShortBearingBook:
    """Part 2's distinguishing fixture: the ONLY case separating the invested-long denominator
    from the withdrawn gross one (1.000000 ≠ 0.892857)."""

    ATOMS = [
        Atom(_d("80000.000000"), "X-CORP"),
        Atom(_d("20000.000000"), "X-CORP"),
        Atom(_d("-25000.000000"), "X-CORP"),
        Atom(_d("-15000.000000"), "Y-CORP"),
    ]

    def test_shares_exclude_shorts_from_numerator_and_denominator(self) -> None:
        r = compute_dimension(self.ATOMS, FLOOR)
        assert r.total_long == _d("100000.000000")
        shares = {b.bucket_code: b.share_invested_long for b in r.buckets}
        assert shares["X-CORP"] == _d("1.000000")
        assert shares["Y-CORP"] == _d("0.000000")
        assert shares["X-CORP"] != _d("0.892857"), "the gross counterfactual must NOT reproduce"

    def test_evidence_totals(self) -> None:
        r = compute_dimension(self.ATOMS, FLOOR)
        x = next(b for b in r.buckets if b.bucket_code == "X-CORP")
        assert x.gross_amount == _d("125000.000000")
        assert x.long_amount == _d("100000.000000")
        assert x.short_amount == _d("-25000.000000")
        assert x.net_amount == _d("75000.000000")


class TestGaps:
    """The three structured gaps — each a POSITIVE control (P5: assert by evidence)."""

    def test_zero_invested_long_gap(self) -> None:
        r = compute_dimension([Atom(_d("-10000"), "X-CORP")], FLOOR)
        assert r.gaps == (GAP_ZERO_INVESTED_LONG,)

    def test_all_unclassifiable_gap(self) -> None:
        r = compute_dimension([Atom(_d("10000"), None, BUCKET_UNCLASSIFIABLE)], FLOOR)
        assert r.gaps == (GAP_ALL_UNCLASSIFIABLE,)
        assert r.coverage_classifiable == _d("0")

    def test_coverage_below_floor_gap(self) -> None:
        atoms = [
            Atom(_d("10000"), "A-CORP"),
            Atom(_d("90000"), None, BUCKET_UNCLASSIFIED),
        ]
        r = compute_dimension(atoms, FLOOR)
        assert r.gaps == (GAP_COVERAGE_BELOW_FLOOR,)

    def test_missing_residual_kind_refuses(self) -> None:
        with pytest.raises(ValueError):
            compute_dimension([Atom(_d("10000"), None, None)], FLOOR)


class TestUnitTierGrain:
    """The ratified BOTH-TIER duplicate refusal, unit tier (SQLite ``create_all``).

    The v4 pass added ``sqlite_where`` beside ``postgresql_where`` on both partial unique indexes
    precisely so the unit tier enforces the grain too — but no unit-tier test ever touched
    ``ConcentrationResult``, so the SQLite half of that repair shipped unexercised. PG remains the
    authoritative gate; this proves the declaration is real on the second dialect."""

    @staticmethod
    def _session():  # noqa: ANN205
        import uuid

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from irp_shared.models import Base

        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)(), str(uuid.uuid4())

    @staticmethod
    def _row(tenant: str, run_id: str, **overrides):  # noqa: ANN003, ANN205
        import uuid
        from datetime import UTC, datetime

        from irp_shared.concentration.models import ConcentrationResult

        base = dict(
            tenant_id=tenant,
            calculation_run_id=run_id,
            input_snapshot_id=str(uuid.uuid4()),
            model_version_id=str(uuid.uuid4()),
            portfolio_id=str(uuid.uuid4()),
            row_kind="DETAIL",
            dimension_kind="SECTOR_INDUSTRY",
            metric_type="SHARE",
            bucket_code="C",
            issuer_id=None,
            scheme_id=str(uuid.uuid4()),
            basis="NOT_APPLICABLE",
            denominator_basis="INVESTED_LONG",
            gross_amount=_d("1"),
            long_amount=_d("1"),
            short_amount=_d("0"),
            net_amount=_d("1"),
            share_invested_long=_d("1.000000"),
            metric_value=None,
            coverage_ratio=None,
            coverage_classifiable=None,
            system_from=datetime.now(UTC),
        )
        base.update(overrides)
        return ConcentrationResult(**base)

    def test_duplicate_DETAIL_bucket_refused(self) -> None:
        import uuid

        from sqlalchemy.exc import IntegrityError

        session, tenant = self._session()
        run_id = str(uuid.uuid4())
        session.add(self._row(tenant, run_id))
        session.flush()
        session.add(self._row(tenant, run_id))
        with pytest.raises(IntegrityError):
            session.flush()

    def test_duplicate_UNCLASSIFIED_residual_refused(self) -> None:
        """The specifically ratified control: the residual sentinel is a bucket_code like any
        other, so two of them in one (run, dimension) must be refused, not silently summed."""
        import uuid

        from sqlalchemy.exc import IntegrityError

        session, tenant = self._session()
        run_id = str(uuid.uuid4())
        session.add(self._row(tenant, run_id, bucket_code=BUCKET_UNCLASSIFIED))
        session.flush()
        session.add(self._row(tenant, run_id, bucket_code=BUCKET_UNCLASSIFIED))
        with pytest.raises(IntegrityError):
            session.flush()

    def test_duplicate_SUMMARY_metric_refused(self) -> None:
        import uuid

        from sqlalchemy.exc import IntegrityError

        from irp_shared.concentration.models import BUCKET_SUMMARY

        session, tenant = self._session()
        run_id = str(uuid.uuid4())
        summary = dict(
            row_kind="SUMMARY",
            metric_type="HHI_SECTOR_INDUSTRY",
            bucket_code=BUCKET_SUMMARY,
            share_invested_long=None,
            metric_value=_d("0.5"),
        )
        session.add(self._row(tenant, run_id, **summary))
        session.flush()
        session.add(self._row(tenant, run_id, **summary))
        with pytest.raises(IntegrityError):
            session.flush()

    def test_a_DIFFERENT_bucket_in_the_same_run_is_allowed(self) -> None:
        """The positive control — without it, an index that refused EVERYTHING would pass above."""
        import uuid

        session, tenant = self._session()
        run_id = str(uuid.uuid4())
        session.add(self._row(tenant, run_id, bucket_code="C"))
        session.add(self._row(tenant, run_id, bucket_code="D"))
        session.flush()


class TestSevenBucketCRN:
    """OQ-CON-1-21's labelled P5 mitigation: CR-N ships DEMONSTRATED-DEGENERATE in the demo, so
    its real coverage must live in the unit tier on a seven-bucket fixture.

    Every other shipped fixture has at most three classified buckets, where ``shares[:5]`` is the
    whole set and ``CR_5 == classified total`` identically — the top-5 truncation was never once
    executed. Here CR-5 is strictly less than the classified total, so a broken slice bound (``:4``,
    ``:6``, or no truncation at all) changes the answer.

    Hand-derived on long amounts summing to 1000: shares .30/.25/.15/.12/.08/.06/.04.
    CR-5 = .30+.25+.15+.12+.08 = 0.900000 (NOT 1.000000). HHI = .09+.0625+.0225+.0144+.0064
    +.0036+.0016 = 0.201000. MAX = 0.300000.
    """

    ATOMS = [
        Atom(_d("300.000000"), "B1"),
        Atom(_d("250.000000"), "B2"),
        Atom(_d("150.000000"), "B3"),
        Atom(_d("120.000000"), "B4"),
        Atom(_d("80.000000"), "B5"),
        Atom(_d("60.000000"), "B6"),
        Atom(_d("40.000000"), "B7"),
    ]

    def test_cr5_truncates_at_five_of_seven(self) -> None:
        r = compute_dimension(self.ATOMS, FLOOR)
        assert r.gaps == ()
        assert len([b for b in r.buckets if not b.is_residual]) == 7
        assert r.cr_n == _d("0.900000")
        assert r.cr_n < _d("1.000000"), "CR-5 equals the classified total — fixture is degenerate"
        assert r.hhi == _d("0.201000")
        assert r.max_share == _d("0.300000")


class TestVocabularyCensus:
    """The exact ten-name census (OQ-CON-1-13) — set equality, widths measured."""

    def test_metric_names_exact_and_within_width(self) -> None:
        assert set(CONCENTRATION_METRIC_TYPES) == {
            "SHARE",
            "MAX_SHARE_ISSUER",
            "MAX_SHARE_SECTOR_INDUSTRY",
            "MAX_SHARE_COUNTRY_OF_RISK",
            "HHI_ISSUER",
            "HHI_SECTOR_INDUSTRY",
            "HHI_COUNTRY_OF_RISK",
            "CR_5_ISSUER",
            "CR_5_SECTOR_INDUSTRY",
            "CR_5_COUNTRY_OF_RISK",
        }
        assert len(SUMMARY_METRIC_TYPES) == 9
        assert max(len(m) for m in CONCENTRATION_METRIC_TYPES) == 25 <= 30

    def test_bucket_sentinels_are_dunder(self) -> None:
        assert all(s.startswith("__") and s.endswith("__") for s in BUCKET_SENTINELS)

    def test_row_kind_census_is_exact_and_matches_the_DDL_check(self) -> None:
        """The third ratified P6 census, which shipped as a DDL CHECK with no test behind it.

        A third row kind added in Python without the migration would pass every ORM-tier test and
        then fail at the CHECK on the first PG write — the census makes the omission loud HERE."""
        from irp_shared.concentration.models import ROW_KINDS, ConcentrationResult

        assert set(ROW_KINDS) == {"DETAIL", "SUMMARY"}
        check = next(
            c
            for c in ConcentrationResult.__table__.constraints
            if getattr(c, "name", None) == "ck_concentration_result_row_kind"
        )
        rendered = str(check.sqltext)
        for kind in ROW_KINDS:
            assert (
                f"'{kind}'" in rendered
            ), f"{kind} is declared in Python but absent from the CHECK"


class TestGovernancePins:
    """The R-07 mint pinned BOTH directions per code (the REF-1 lesson: SoD pins are PER CODE),
    plus the CON-1-owned dimension split."""

    def test_holder_sets_exactly_as_ratified(self) -> None:
        from irp_shared.entitlement.bootstrap import ROLE_TEMPLATES

        def holders(code: str) -> set[str]:
            named = {r for r, cs in ROLE_TEMPLATES.items() if code in cs}
            return named | {"platform_admin"}  # ALL_CODES by construction

        assert holders("concentration.run") == {
            "platform_admin",
            "data_steward",
            "risk_analyst_1l",
        }
        assert holders("concentration.view") == {
            "platform_admin",
            "data_steward",
            "risk_analyst_1l",
            "risk_manager_2l",
            "auditor_3l",
        }
        assert holders("concentration.issuer.view") == {
            "platform_admin",
            "data_steward",
            "risk_analyst_1l",
            "risk_manager_2l",
        }, "auditor_3l must NEVER hold the issuer-identity read (the three-mint precedent)"

    def test_issuer_is_not_an_assignment_dimension(self) -> None:
        """ISSUER is CON-1-owned: no classification assignment may carry it (OQ-CON-1-23)."""
        from irp_shared.classification.models import DIMENSION_KINDS
        from irp_shared.concentration.models import (
            CONCENTRATION_DIMENSION_KINDS,
            DIMENSION_KIND_ISSUER,
        )

        assert DIMENSION_KIND_ISSUER not in DIMENSION_KINDS
        assert set(CONCENTRATION_DIMENSION_KINDS) == set(DIMENSION_KINDS) | {DIMENSION_KIND_ISSUER}
