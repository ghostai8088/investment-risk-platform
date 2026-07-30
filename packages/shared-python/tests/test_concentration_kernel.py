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
