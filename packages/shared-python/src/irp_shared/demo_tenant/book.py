"""The Northlight book — every constant the BOOK-1a orchestrator seeds, and nothing that runs.

Ratified at the BOOK-1a planning gate (`10_delivery_backlog/w20_book1a_remit.md`, DS-B1a-1,
DS-B1a-2, DS-B1a-5). A CRO must recognise this as a manager's book, not a fixture, so the names are
those of plausible fictional issuers, the position counts are a fund's, and the totals sit where a
mid-sized manager's would (the realism rule's 2026-09-17 amendment,
`08_testing_qa/test_data_realism.md`).

**Fixed, not rolling.** The marked year is 2025-06-30 to 2026-06-30 and never moves: every mark,
FX mid, factor return, loading and benchmark row carries an explicit instant in the past, and this
module holds no call to ``now()`` or ``today()``. A rolling year would be a time bomb by
construction
and would move every hand-derived golden on every re-seed.

**Deterministic, not random.** Price paths and factor returns come from ``random.Random`` under a
fixed seed, so two seeds of the same commit produce the same bytes and the goldens in the slice
record stay true. The generator is plausibility, not a model: daily moves are a few tenths of a
percent with fatter tails on equities, bonds drift with their carry, cash does not move.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from irp_shared.reference.xnys_holidays import XNYS_HOLIDAYS

# --- identity ---------------------------------------------------------------------------------

#: The Northlight namespace, distinct from the base campaign's ``…00d1`` and the synthetic
#: ``…00c6``; ``…00e1`` for the second demo tenant. Same uuid5 discipline, different label.
_NS = uuid.UUID("00000000-0000-0000-0000-0000000000e1")


def northlight_id(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


TENANT_ID = northlight_id("tenant:northlight")
TENANT_CODE = "northlight"
TENANT_NAME = "Northlight Capital Partners"

CODE_VERSION = "demo-northlight-book1a"
ENVIRONMENT_ID = "demo"

#: Every capture's ``valid_from``: before the marked year, so as-of reads at any boundary resolve.
T0 = datetime(2025, 1, 1, tzinfo=UTC)

# --- the calendar and the boundary set ------------------------------------------------------------

YEAR_START = date(2025, 6, 30)  # a month-end, so the twelve-month rolling window has thirteen
YEAR_END = date(2026, 6, 30)
#: Factor returns begin here so the first month-end covariance (30 business days) and the first
#: historical-VaR snapshot (60 business days) both have their windows.
RETURNS_START = date(2025, 4, 1)

_HOLIDAYS = frozenset(d for d, _ in XNYS_HOLIDAYS)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _HOLIDAYS


def business_days(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        if is_business_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def month_ends(start: date, end: date) -> list[date]:
    """The last business day of every month touched by [start, end], inside the span."""
    out: list[date] = []
    d = start
    while d <= end:
        nxt = d + timedelta(days=1)
        if nxt.month != d.month and is_business_day(d):
            out.append(d)
        elif nxt.month != d.month:
            # the calendar month-end is not a business day: walk back to the last one
            back = d
            while not is_business_day(back):
                back -= timedelta(days=1)
            if start <= back <= end and back not in out:
                out.append(back)
        d = nxt
    return out


MONTH_ENDS: tuple[date, ...] = tuple(month_ends(YEAR_START, YEAR_END))
BOUNDARIES: tuple[date, ...] = tuple(
    sorted(
        set(d for d in business_days(YEAR_START, YEAR_END) if d.weekday() == 4) | set(MONTH_ENDS)
    )
)
RETURN_DAYS: tuple[date, ...] = tuple(business_days(RETURNS_START, YEAR_END))

# --- currencies and factors ---------------------------------------------------------------------

CURRENCIES: tuple[tuple[str, str], ...] = (
    ("USD", "US Dollar"),
    ("EUR", "Euro"),
    ("GBP", "Pound Sterling"),
)

#: FX mids at YEAR_START (quote per one unit of base), then a slow deterministic drift.
FX_START: dict[tuple[str, str], Decimal] = {
    ("EUR", "USD"): Decimal("1.0850"),
    ("GBP", "USD"): Decimal("1.2700"),
}


@dataclass(frozen=True)
class FactorSpec:
    code: str
    family: str
    currency: str | None
    daily_sigma: Decimal
    name: str


FACTOR_SOURCE = "NORTHLIGHT_RISK"
FACTORS: tuple[FactorSpec, ...] = (
    FactorSpec("FX_USD", "CURRENCY", "USD", Decimal("0.0000"), "USD numeraire"),
    FactorSpec("FX_EUR", "CURRENCY", "EUR", Decimal("0.0035"), "EUR vs USD"),
    FactorSpec("FX_GBP", "CURRENCY", "GBP", Decimal("0.0038"), "GBP vs USD"),
    FactorSpec("MKT_GLOBAL_EQ", "MARKET", None, Decimal("0.0090"), "Global equity market"),
    FactorSpec("RATES_USD_10Y", "RATES", "USD", Decimal("0.00045"), "USD 10-year yield change"),
    FactorSpec("RATES_EUR_10Y", "RATES", "EUR", Decimal("0.00040"), "EUR 10-year yield change"),
    FactorSpec(
        "CREDIT_IG", "CREDIT_SPREAD", None, Decimal("0.00015"), "Investment-grade spread change"
    ),
    FactorSpec("CREDIT_HY", "CREDIT_SPREAD", None, Decimal("0.00060"), "High-yield spread change"),
)
CURRENCY_FACTOR_CODES: tuple[str, ...] = ("FX_USD", "FX_EUR", "FX_GBP")

# --- the funds ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountSpec:
    code: str
    name: str


@dataclass(frozen=True)
class SleeveSpec:
    code: str
    name: str
    accounts: tuple[AccountSpec, ...]


@dataclass(frozen=True)
class FundSpec:
    code: str
    name: str
    base_currency: str
    sleeves: tuple[SleeveSpec, ...]
    return_account: str  # the ONE account whose return chain stands for the fund (DS-B1a-4)
    benchmark_code: str
    benchmark_name: str


FUNDS: tuple[FundSpec, ...] = (
    FundSpec(
        code="NL-GMA",
        name="Northlight Global Multi-Asset Fund",
        base_currency="USD",
        sleeves=(
            SleeveSpec(
                "NL-GMA-EQ",
                "Global Equity",
                (
                    AccountSpec("NL-GMA-EQ-US", "US Core"),
                    AccountSpec("NL-GMA-EQ-INTL", "International"),
                ),
            ),
            SleeveSpec(
                "NL-GMA-FI",
                "Fixed Income",
                (AccountSpec("NL-GMA-FI-GOV", "Government"), AccountSpec("NL-GMA-FI-CR", "Credit")),
            ),
            SleeveSpec("NL-GMA-CASH", "Cash", (AccountSpec("NL-GMA-CASH-1", "Cash"),)),
        ),
        return_account="NL-GMA-EQ-US",
        benchmark_code="NL-GMA-BM",
        benchmark_name="Northlight Global Multi-Asset Composite",
    ),
    FundSpec(
        code="NL-EFI",
        name="Northlight Euro Fixed Income Fund",
        base_currency="EUR",
        sleeves=(
            SleeveSpec(
                "NL-EFI-GOV", "Government", (AccountSpec("NL-EFI-GOV-CORE", "Core Govies"),)
            ),
            SleeveSpec(
                "NL-EFI-CR",
                "Credit",
                (
                    AccountSpec("NL-EFI-CR-IG", "IG Credit"),
                    AccountSpec("NL-EFI-CR-HY", "HY Credit"),
                ),
            ),
        ),
        return_account="NL-EFI-GOV-CORE",
        benchmark_code="NL-EFI-BM",
        benchmark_name="Northlight Euro Aggregate Composite",
    ),
    FundSpec(
        code="NL-PMF",
        name="Northlight Private Markets Fund of Funds",
        base_currency="USD",
        sleeves=(
            SleeveSpec(
                "NL-PMF-PE", "Private Equity", (AccountSpec("NL-PMF-PE-PRIM", "PE Primaries"),)
            ),
            SleeveSpec(
                "NL-PMF-PC", "Private Credit", (AccountSpec("NL-PMF-PC-DL", "Direct Lending"),)
            ),
            SleeveSpec(
                "NL-PMF-LIQ",
                "Liquidity Reserve",
                (AccountSpec("NL-PMF-LIQ-TSY", "Treasury Reserve"),),
            ),
        ),
        return_account="NL-PMF-LIQ-TSY",
        benchmark_code="NL-PMF-BM",
        benchmark_name="Northlight Private Markets Reference",
    ),
)

# --- issuers and instruments -------------------------------------------------------------------


@dataclass(frozen=True)
class IssuerSpec:
    code: str
    name: str
    country: str  # ISO 3166-1 alpha-2
    sector: str  # ISIC section (level 1)
    issuer_type: str  # CORPORATE | SOVEREIGN


@dataclass(frozen=True)
class InstrumentSpec:
    code: str  # ticker-style
    isin: str  # ISIN-shaped under the user-assigned ZZ prefix
    name: str
    asset_class: str
    currency: str
    issuer: str
    account: str
    quantity: Decimal
    start_price: Decimal
    daily_sigma: Decimal
    annual_drift: Decimal
    market_beta: Decimal  # MKT loading (equities)
    rate_loading: Decimal  # RATES loading (bonds; negative duration-like)
    credit_loading: Decimal  # CREDIT loading (corporates)
    credit_factor: str | None  # CREDIT_IG | CREDIT_HY | None
    liquidity_tier: str
    face_value: Decimal | None = None
    coupon_rate: Decimal | None = None


ISSUERS: tuple[IssuerSpec, ...] = (
    IssuerSpec("CASCADIA", "Cascadia Semiconductor Corp", "US", "C", "CORPORATE"),
    IssuerSpec("BRIGHTWATER", "Brightwater Health Systems Inc", "US", "Q", "CORPORATE"),
    IssuerSpec("ORRIN", "Orrin Software Group Inc", "US", "J", "CORPORATE"),
    IssuerSpec("GRANITE", "Granite Ridge Energy Corp", "US", "D", "CORPORATE"),
    IssuerSpec("HALCYON", "Halcyon Consumer Brands Inc", "US", "G", "CORPORATE"),
    IssuerSpec("MERIDIANU", "Meridian Utilities Holdings", "US", "D", "CORPORATE"),
    IssuerSpec("VANTAGE", "Vantage Freight Lines Inc", "US", "H", "CORPORATE"),
    IssuerSpec("SUMMITB", "Summit Bancorp", "US", "K", "CORPORATE"),
    IssuerSpec("LUMEN", "Lumen Bioscience Inc", "US", "M", "CORPORATE"),
    IssuerSpec("TIDEWATER", "Tidewater Retail Group Inc", "US", "G", "CORPORATE"),
    IssuerSpec("NORTHSTAR", "Northstar Aerospace Corp", "US", "C", "CORPORATE"),
    IssuerSpec("CEDAR", "Cedar Point Insurance Group", "US", "K", "CORPORATE"),
    IssuerSpec("RHEINWERK", "Rheinwerk Industrie AG", "DE", "C", "CORPORATE"),
    IssuerSpec("ALPENBANK", "Alpenbank AG", "DE", "K", "CORPORATE"),
    IssuerSpec("LOIRE", "Loire Luxe SA", "FR", "G", "CORPORATE"),
    IssuerSpec("GALLIC", "Gallic Energie SA", "FR", "D", "CORPORATE"),
    IssuerSpec("NOORD", "Noord Logistiek NV", "NL", "H", "CORPORATE"),
    IssuerSpec("TIBER", "Tiber Telecom SpA", "IT", "J", "CORPORATE"),
    IssuerSpec("IBERIA", "Iberia Renovables SA", "ES", "D", "CORPORATE"),
    IssuerSpec("HELVETIA", "Helvetia Pharma AG", "CH", "C", "CORPORATE"),
    IssuerSpec("THAMES", "Thames Utilities plc", "GB", "D", "CORPORATE"),
    IssuerSpec("ALBION", "Albion Mining plc", "GB", "B", "CORPORATE"),
    IssuerSpec("CALEDON", "Caledon Assurance plc", "GB", "K", "CORPORATE"),
    IssuerSpec("SEVERN", "Severn Grocers plc", "GB", "G", "CORPORATE"),
    IssuerSpec("UST", "United States Treasury", "US", "O", "SOVEREIGN"),
    IssuerSpec("BUND", "Bundesrepublik Deutschland", "DE", "O", "SOVEREIGN"),
    IssuerSpec("OAT", "Republique Francaise", "FR", "O", "SOVEREIGN"),
    IssuerSpec("BTP", "Repubblica Italiana", "IT", "O", "SOVEREIGN"),
    IssuerSpec("BONOS", "Reino de Espana", "ES", "O", "SOVEREIGN"),
    IssuerSpec("DSL", "Staat der Nederlanden", "NL", "O", "SOVEREIGN"),
    IssuerSpec("NLCASH", "Northlight cash custodian", "US", "K", "CORPORATE"),
)

SECTORS: tuple[tuple[str, str], ...] = (
    ("B", "Mining and quarrying"),
    ("C", "Manufacturing"),
    ("D", "Electricity, gas, steam and air conditioning supply"),
    ("G", "Wholesale and retail trade"),
    ("H", "Transportation and storage"),
    ("J", "Information and communication"),
    ("K", "Financial and insurance activities"),
    ("M", "Professional, scientific and technical activities"),
    ("O", "Public administration and defence"),
    ("Q", "Human health and social work activities"),
)
COUNTRIES: tuple[tuple[str, str], ...] = (
    ("US", "United States of America"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("GB", "United Kingdom"),
    ("NL", "Netherlands"),
    ("IT", "Italy"),
    ("ES", "Spain"),
    ("CH", "Switzerland"),
)

_D = Decimal


def _eq(code, isin, name, ccy, issuer, account, qty, px, sigma, beta, tier="HIGHLY_LIQUID"):
    # `sigma` is the idiosyncratic daily volatility; the market beta adds the systematic part.
    return InstrumentSpec(
        code,
        isin,
        name,
        "EQUITY",
        ccy,
        issuer,
        account,
        _D(qty),
        _D(px),
        _D(sigma) * _D("0.6"),
        _D("0.06"),
        _D(beta),
        _D("0"),
        _D("0"),
        None,
        tier,
    )


def _govt(code, isin, name, ccy, issuer, account, qty, px, dur, coupon, tier="HIGHLY_LIQUID"):
    return InstrumentSpec(
        code,
        isin,
        name,
        "GOVERNMENT_BOND",
        ccy,
        issuer,
        account,
        _D(qty),
        _D(px),
        _D("0.0004"),
        _D("0.03"),
        _D("0"),
        _D(dur) * _D("-1"),
        _D("0"),
        None,
        tier,
        _D("1000"),
        _D(coupon),
    )


def _corp(code, isin, name, ccy, issuer, account, qty, px, dur, spread, factor, coupon, tier):
    return InstrumentSpec(
        code,
        isin,
        name,
        "CORPORATE_BOND",
        ccy,
        issuer,
        account,
        _D(qty),
        _D(px),
        _D("0.0006"),
        _D("0.045"),
        _D("0"),
        _D(dur) * _D("-1"),
        _D(spread) * _D("-1"),
        factor,
        tier,
        _D("1000"),
        _D(coupon),
    )


INSTRUMENTS: tuple[InstrumentSpec, ...] = (
    # NL-GMA / US Core (12 US equities)
    _eq(
        "CSDA",
        "ZZ0000000011",
        "Cascadia Semiconductor Corp",
        "USD",
        "CASCADIA",
        "NL-GMA-EQ-US",
        "42000",
        "184.20",
        "0.018",
        "1.25",
    ),
    _eq(
        "BWHS",
        "ZZ0000000029",
        "Brightwater Health Systems Inc",
        "USD",
        "BRIGHTWATER",
        "NL-GMA-EQ-US",
        "38000",
        "96.75",
        "0.011",
        "0.80",
    ),
    _eq(
        "ORRN",
        "ZZ0000000037",
        "Orrin Software Group Inc",
        "USD",
        "ORRIN",
        "NL-GMA-EQ-US",
        "21000",
        "312.40",
        "0.016",
        "1.15",
    ),
    _eq(
        "GRNE",
        "ZZ0000000045",
        "Granite Ridge Energy Corp",
        "USD",
        "GRANITE",
        "NL-GMA-EQ-US",
        "55000",
        "58.10",
        "0.015",
        "0.95",
    ),
    _eq(
        "HLCB",
        "ZZ0000000052",
        "Halcyon Consumer Brands Inc",
        "USD",
        "HALCYON",
        "NL-GMA-EQ-US",
        "47000",
        "71.30",
        "0.010",
        "0.70",
    ),
    _eq(
        "MRDU",
        "ZZ0000000060",
        "Meridian Utilities Holdings",
        "USD",
        "MERIDIANU",
        "NL-GMA-EQ-US",
        "62000",
        "44.85",
        "0.008",
        "0.55",
    ),
    _eq(
        "VNTF",
        "ZZ0000000078",
        "Vantage Freight Lines Inc",
        "USD",
        "VANTAGE",
        "NL-GMA-EQ-US",
        "29000",
        "133.60",
        "0.014",
        "1.05",
    ),
    _eq(
        "SMBC",
        "ZZ0000000086",
        "Summit Bancorp",
        "USD",
        "SUMMITB",
        "NL-GMA-EQ-US",
        "51000",
        "67.90",
        "0.013",
        "1.10",
    ),
    _eq(
        "LMNB",
        "ZZ0000000094",
        "Lumen Bioscience Inc",
        "USD",
        "LUMEN",
        "NL-GMA-EQ-US",
        "18000",
        "221.75",
        "0.021",
        "1.30",
        "MODERATELY_LIQUID",
    ),
    _eq(
        "TDWR",
        "ZZ0000000102",
        "Tidewater Retail Group Inc",
        "USD",
        "TIDEWATER",
        "NL-GMA-EQ-US",
        "44000",
        "52.40",
        "0.012",
        "0.90",
    ),
    _eq(
        "NSAR",
        "ZZ0000000110",
        "Northstar Aerospace Corp",
        "USD",
        "NORTHSTAR",
        "NL-GMA-EQ-US",
        "26000",
        "158.90",
        "0.014",
        "1.00",
    ),
    _eq(
        "CDPI",
        "ZZ0000000128",
        "Cedar Point Insurance Group",
        "USD",
        "CEDAR",
        "NL-GMA-EQ-US",
        "35000",
        "88.15",
        "0.010",
        "0.85",
    ),
    # NL-GMA / International (8 EUR + 4 GBP equities)
    _eq(
        "RHWK",
        "ZZ0000000136",
        "Rheinwerk Industrie AG",
        "EUR",
        "RHEINWERK",
        "NL-GMA-EQ-INTL",
        "24000",
        "142.30",
        "0.014",
        "1.05",
    ),
    _eq(
        "ALPB",
        "ZZ0000000144",
        "Alpenbank AG",
        "EUR",
        "ALPENBANK",
        "NL-GMA-EQ-INTL",
        "61000",
        "38.20",
        "0.015",
        "1.15",
    ),
    _eq(
        "LOIR",
        "ZZ0000000151",
        "Loire Luxe SA",
        "EUR",
        "LOIRE",
        "NL-GMA-EQ-INTL",
        "9000",
        "486.50",
        "0.016",
        "1.10",
    ),
    _eq(
        "GALE",
        "ZZ0000000169",
        "Gallic Energie SA",
        "EUR",
        "GALLIC",
        "NL-GMA-EQ-INTL",
        "48000",
        "54.60",
        "0.012",
        "0.85",
    ),
    _eq(
        "NRDL",
        "ZZ0000000177",
        "Noord Logistiek NV",
        "EUR",
        "NOORD",
        "NL-GMA-EQ-INTL",
        "33000",
        "62.10",
        "0.013",
        "0.95",
    ),
    _eq(
        "TBRT",
        "ZZ0000000185",
        "Tiber Telecom SpA",
        "EUR",
        "TIBER",
        "NL-GMA-EQ-INTL",
        "210000",
        "3.86",
        "0.011",
        "0.75",
    ),
    _eq(
        "IBRN",
        "ZZ0000000193",
        "Iberia Renovables SA",
        "EUR",
        "IBERIA",
        "NL-GMA-EQ-INTL",
        "70000",
        "21.45",
        "0.017",
        "1.20",
    ),
    _eq(
        "HLVP",
        "ZZ0000000201",
        "Helvetia Pharma AG",
        "EUR",
        "HELVETIA",
        "NL-GMA-EQ-INTL",
        "12000",
        "268.00",
        "0.010",
        "0.65",
    ),
    _eq(
        "THMS",
        "ZZ0000000219",
        "Thames Utilities plc",
        "GBP",
        "THAMES",
        "NL-GMA-EQ-INTL",
        "90000",
        "9.42",
        "0.009",
        "0.60",
    ),
    _eq(
        "ALBM",
        "ZZ0000000227",
        "Albion Mining plc",
        "GBP",
        "ALBION",
        "NL-GMA-EQ-INTL",
        "54000",
        "18.70",
        "0.019",
        "1.25",
    ),
    _eq(
        "CLDN",
        "ZZ0000000235",
        "Caledon Assurance plc",
        "GBP",
        "CALEDON",
        "NL-GMA-EQ-INTL",
        "76000",
        "6.15",
        "0.012",
        "0.90",
    ),
    _eq(
        "SVRN",
        "ZZ0000000243",
        "Severn Grocers plc",
        "GBP",
        "SEVERN",
        "NL-GMA-EQ-INTL",
        "120000",
        "2.98",
        "0.011",
        "0.70",
    ),
    # NL-GMA / Government (4 US Treasuries; per-unit price on 1000 face)
    _govt(
        "UST-27",
        "ZZ0000000250",
        "US Treasury 4.125% 2027",
        "USD",
        "UST",
        "NL-GMA-FI-GOV",
        "14000",
        "994.10",
        "1.9",
        "0.04125",
    ),
    _govt(
        "UST-30",
        "ZZ0000000268",
        "US Treasury 4.000% 2030",
        "USD",
        "UST",
        "NL-GMA-FI-GOV",
        "11000",
        "981.60",
        "4.3",
        "0.04000",
    ),
    _govt(
        "UST-35",
        "ZZ0000000276",
        "US Treasury 4.250% 2035",
        "USD",
        "UST",
        "NL-GMA-FI-GOV",
        "9000",
        "972.30",
        "7.8",
        "0.04250",
    ),
    _govt(
        "UST-45",
        "ZZ0000000284",
        "US Treasury 4.500% 2045",
        "USD",
        "UST",
        "NL-GMA-FI-GOV",
        "5000",
        "951.80",
        "13.2",
        "0.04500",
    ),
    # NL-GMA / Credit (6 USD IG corporates)
    _corp(
        "CSDA-29",
        "ZZ0000000292",
        "Cascadia Semiconductor 4.60% 2029",
        "USD",
        "CASCADIA",
        "NL-GMA-FI-CR",
        "4000",
        "997.40",
        "3.6",
        "0.9",
        "CREDIT_IG",
        "0.0460",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "MRDU-31",
        "ZZ0000000300",
        "Meridian Utilities 4.85% 2031",
        "USD",
        "MERIDIANU",
        "NL-GMA-FI-CR",
        "3500",
        "1002.10",
        "5.1",
        "1.1",
        "CREDIT_IG",
        "0.0485",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "SMBC-28",
        "ZZ0000000318",
        "Summit Bancorp 5.10% 2028",
        "USD",
        "SUMMITB",
        "NL-GMA-FI-CR",
        "3000",
        "1008.60",
        "2.7",
        "1.3",
        "CREDIT_IG",
        "0.0510",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "VNTF-33",
        "ZZ0000000326",
        "Vantage Freight 5.35% 2033",
        "USD",
        "VANTAGE",
        "NL-GMA-FI-CR",
        "2500",
        "989.90",
        "6.4",
        "1.4",
        "CREDIT_IG",
        "0.0535",
        "LESS_LIQUID",
    ),
    _corp(
        "HLCB-30",
        "ZZ0000000334",
        "Halcyon Consumer 4.70% 2030",
        "USD",
        "HALCYON",
        "NL-GMA-FI-CR",
        "3000",
        "993.20",
        "4.4",
        "1.0",
        "CREDIT_IG",
        "0.0470",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "CDPI-34",
        "ZZ0000000342",
        "Cedar Point Insurance 5.20% 2034",
        "USD",
        "CEDAR",
        "NL-GMA-FI-CR",
        "2000",
        "984.70",
        "7.0",
        "1.2",
        "CREDIT_IG",
        "0.0520",
        "LESS_LIQUID",
    ),
    # NL-GMA / Cash
    InstrumentSpec(
        "NLUSD-CASH",
        "ZZ0000000359",
        "USD cash at custodian",
        "CASH",
        "USD",
        "NLCASH",
        "NL-GMA-CASH-1",
        _D("18500000"),
        _D("1.00"),
        _D("0"),
        _D("0"),
        _D("0"),
        _D("0"),
        _D("0"),
        None,
        "HIGHLY_LIQUID",
    ),
    # NL-EFI / Core Govies (5 EUR sovereigns)
    _govt(
        "BUND-30",
        "ZZ0000000367",
        "Bund 2.30% 2030",
        "EUR",
        "BUND",
        "NL-EFI-GOV-CORE",
        "16000",
        "998.70",
        "4.5",
        "0.0230",
    ),
    _govt(
        "BUND-35",
        "ZZ0000000375",
        "Bund 2.50% 2035",
        "EUR",
        "BUND",
        "NL-EFI-GOV-CORE",
        "10000",
        "987.40",
        "8.4",
        "0.0250",
    ),
    _govt(
        "OAT-33",
        "ZZ0000000383",
        "OAT 2.75% 2033",
        "EUR",
        "OAT",
        "NL-EFI-GOV-CORE",
        "12000",
        "991.20",
        "6.8",
        "0.0275",
    ),
    _govt(
        "BTP-31",
        "ZZ0000000391",
        "BTP 3.45% 2031",
        "EUR",
        "BTP",
        "NL-EFI-GOV-CORE",
        "13000",
        "1003.90",
        "5.0",
        "0.0345",
        "MODERATELY_LIQUID",
    ),
    _govt(
        "BONOS-32",
        "ZZ0000000409",
        "Bonos 3.10% 2032",
        "EUR",
        "BONOS",
        "NL-EFI-GOV-CORE",
        "9000",
        "996.50",
        "5.9",
        "0.0310",
    ),
    # NL-EFI / IG Credit (6 EUR IG corporates)
    _corp(
        "RHWK-30",
        "ZZ0000000417",
        "Rheinwerk Industrie 3.40% 2030",
        "EUR",
        "RHEINWERK",
        "NL-EFI-CR-IG",
        "4500",
        "1001.30",
        "4.4",
        "0.9",
        "CREDIT_IG",
        "0.0340",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "ALPB-29",
        "ZZ0000000425",
        "Alpenbank 3.65% 2029",
        "EUR",
        "ALPENBANK",
        "NL-EFI-CR-IG",
        "5000",
        "1004.80",
        "3.5",
        "1.2",
        "CREDIT_IG",
        "0.0365",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "GALE-32",
        "ZZ0000000433",
        "Gallic Energie 3.80% 2032",
        "EUR",
        "GALLIC",
        "NL-EFI-CR-IG",
        "4000",
        "995.60",
        "5.9",
        "1.0",
        "CREDIT_IG",
        "0.0380",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "NRDL-28",
        "ZZ0000000441",
        "Noord Logistiek 3.25% 2028",
        "EUR",
        "NOORD",
        "NL-EFI-CR-IG",
        "3500",
        "999.10",
        "2.6",
        "0.8",
        "CREDIT_IG",
        "0.0325",
        "MODERATELY_LIQUID",
    ),
    _corp(
        "HLVP-34",
        "ZZ0000000458",
        "Helvetia Pharma 3.55% 2034",
        "EUR",
        "HELVETIA",
        "NL-EFI-CR-IG",
        "3000",
        "990.40",
        "7.3",
        "0.7",
        "CREDIT_IG",
        "0.0355",
        "LESS_LIQUID",
    ),
    _corp(
        "DSL-31",
        "ZZ0000000466",
        "Staat der Nederlanden 2.60% 2031",
        "EUR",
        "DSL",
        "NL-EFI-CR-IG",
        "6000",
        "997.80",
        "5.2",
        "0.3",
        "CREDIT_IG",
        "0.0260",
        "HIGHLY_LIQUID",
    ),
    # NL-EFI / HY Credit (5 EUR HY corporates)
    _corp(
        "TBRT-29",
        "ZZ0000000474",
        "Tiber Telecom 6.40% 2029",
        "EUR",
        "TIBER",
        "NL-EFI-CR-HY",
        "3000",
        "986.20",
        "3.3",
        "2.4",
        "CREDIT_HY",
        "0.0640",
        "LESS_LIQUID",
    ),
    _corp(
        "IBRN-30",
        "ZZ0000000482",
        "Iberia Renovables 6.10% 2030",
        "EUR",
        "IBERIA",
        "NL-EFI-CR-HY",
        "2500",
        "991.70",
        "4.1",
        "2.2",
        "CREDIT_HY",
        "0.0610",
        "LESS_LIQUID",
    ),
    _corp(
        "LOIR-31",
        "ZZ0000000490",
        "Loire Luxe 5.75% 2031",
        "EUR",
        "LOIRE",
        "NL-EFI-CR-HY",
        "2000",
        "1010.30",
        "4.8",
        "1.9",
        "CREDIT_HY",
        "0.0575",
        "LESS_LIQUID",
    ),
    _corp(
        "ALBM-28",
        "ZZ0000000508",
        "Albion Mining 7.20% 2028",
        "EUR",
        "ALBION",
        "NL-EFI-CR-HY",
        "2500",
        "978.90",
        "2.5",
        "3.1",
        "CREDIT_HY",
        "0.0720",
        "ILLIQUID",
    ),
    _corp(
        "SVRN-30",
        "ZZ0000000516",
        "Severn Grocers 6.80% 2030",
        "EUR",
        "SEVERN",
        "NL-EFI-CR-HY",
        "2000",
        "983.50",
        "4.0",
        "2.7",
        "CREDIT_HY",
        "0.0680",
        "LESS_LIQUID",
    ),
    # NL-PMF / Treasury Reserve (2 T-bills + cash; the private sleeves are BOOK-1b's)
    _govt(
        "USTB-3M",
        "ZZ0000000524",
        "US Treasury Bill 3-month",
        "USD",
        "UST",
        "NL-PMF-LIQ-TSY",
        "22000",
        "988.90",
        "0.25",
        "0.0000",
    ),
    _govt(
        "USTB-6M",
        "ZZ0000000532",
        "US Treasury Bill 6-month",
        "USD",
        "UST",
        "NL-PMF-LIQ-TSY",
        "18000",
        "978.10",
        "0.50",
        "0.0000",
    ),
    InstrumentSpec(
        "NLUSD-CASH-PMF",
        "ZZ0000000540",
        "USD cash at custodian (PMF)",
        "CASH",
        "USD",
        "NLCASH",
        "NL-PMF-LIQ-TSY",
        _D("6200000"),
        _D("1.00"),
        _D("0"),
        _D("0"),
        _D("0"),
        _D("0"),
        _D("0"),
        None,
        "HIGHLY_LIQUID",
    ),
)

# --- benchmarks and the risk-free series ------------------------------------------------------

BENCHMARK_SOURCE = "NORTHLIGHT_INDEX"
#: One risk-free series per fund base currency; monthly TOTAL returns, one per measured month
#: (Jul 2025 .. Jun 2026), declining slowly.
RISK_FREE: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "USD": (
        "NL-USD-CASH-1M",
        "USD 1-month cash (risk-free proxy)",
        (
            "0.00365",
            "0.00360",
            "0.00352",
            "0.00345",
            "0.00338",
            "0.00331",
            "0.00324",
            "0.00318",
            "0.00312",
            "0.00306",
            "0.00300",
            "0.00295",
        ),
    ),
    "EUR": (
        "NL-EUR-CASH-1M",
        "EUR 1-month cash (risk-free proxy)",
        (
            "0.00180",
            "0.00178",
            "0.00175",
            "0.00172",
            "0.00170",
            "0.00168",
            "0.00166",
            "0.00164",
            "0.00162",
            "0.00160",
            "0.00158",
            "0.00156",
        ),
    ),
}

#: Benchmark constituents per fund: (instrument code, weight), currency taken from the instrument.
BENCHMARK_CONSTITUENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "NL-GMA": (
        ("CSDA", "0.12"),
        ("ORRN", "0.10"),
        ("BWHS", "0.08"),
        ("RHWK", "0.10"),
        ("LOIR", "0.08"),
        ("THMS", "0.07"),
        ("UST-30", "0.20"),
        ("UST-35", "0.15"),
        ("MRDU-31", "0.10"),
    ),
    "NL-EFI": (
        ("BUND-30", "0.30"),
        ("BUND-35", "0.20"),
        ("OAT-33", "0.20"),
        ("BTP-31", "0.15"),
        ("RHWK-30", "0.15"),
    ),
    "NL-PMF": (("USTB-3M", "0.60"), ("USTB-6M", "0.40")),
}

# --- scenario and curve -----------------------------------------------------------------------

SCENARIO_CODE = "NL-FX-STRESS"
SCENARIO_NAME = "Dollar strength: EUR -8%, GBP -6%"
SCENARIO_SHOCKS: tuple[tuple[str, str], ...] = (("FX_EUR", "-0.08"), ("FX_GBP", "-0.06"))

CURVE_SOURCE = "NORTHLIGHT_RATES"
CURVE_DATE = YEAR_END
CURVE_NODES: tuple[tuple[str, int, str], ...] = (
    ("1Y", 365, "0.0405"),
    ("2Y", 730, "0.0392"),
    ("5Y", 1825, "0.0388"),
    ("10Y", 3650, "0.0410"),
    ("30Y", 10950, "0.0445"),
)

# --- model parameters --------------------------------------------------------------------------

COVARIANCE_WINDOW = 30
VAR_CONFIDENCE = "0.99"
ES_CONFIDENCE = "0.975"
HS_CONFIDENCE = "0.95"
HS_WINDOW = 60
COVERAGE_FLOOR = Decimal("0.90")
#: The liquidity age gate reads the real clock; a fixed-year demo must not fail itself after a
#: month (DS-B1a-8). Ten years, and the reason recorded here and in the slice record.
LIQUIDITY_TIER_MAX_AGE_DAYS = 3660
ROLLING_WINDOWS: tuple[int, ...] = (12,)
SHARPE_WINDOWS: tuple[int, ...] = (12,)

# --- deterministic paths -----------------------------------------------------------------------

#: Chosen from a scan of forty seeds for a plausible year: market +9%, EUR flat, GBP +3%, 15 of
#: 24 equities up. Any seed is arbitrary; this one was picked and recorded rather than tuned.
SEED = 20260647
#: A modest equity premium so the marked year is not a bear market by accident of the seed.
MARKET_DAILY_DRIFT = 0.00045
_Q4 = Decimal("0.0001")
_Q6 = Decimal("0.000001")


def _q(x: Decimal, q: Decimal) -> Decimal:
    return x.quantize(q, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class Paths:
    """Every generated series, keyed for the seeder: factor returns per business day, FX mids per
    boundary, and marks per instrument per boundary."""

    factor_returns: dict[str, dict[date, Decimal]]
    fx: dict[tuple[str, str], dict[date, Decimal]]
    marks: dict[str, dict[date, Decimal]]
    benchmark_returns: dict[str, dict[date, Decimal]]


def generate_paths() -> Paths:
    rng = random.Random(SEED)
    days = RETURN_DAYS
    # 1. factor returns, business days only
    factor_returns: dict[str, dict[date, Decimal]] = {}
    for f in FACTORS:
        series: dict[date, Decimal] = {}
        sigma = float(f.daily_sigma)
        mean = MARKET_DAILY_DRIFT if f.family == "MARKET" else 0.0
        for d in days:
            r = rng.gauss(mean, sigma) if sigma > 0 else 0.0
            series[d] = _q(Decimal(repr(r)), _Q6)
        factor_returns[f.code] = series
    # 2. FX mids at every boundary from the cumulative currency-factor return
    fx: dict[tuple[str, str], dict[date, Decimal]] = {}
    for (base, quote), start in FX_START.items():
        code = f"FX_{base}"
        level = float(start)
        series = {}
        by_day = factor_returns[code]
        for d in days:
            level *= 1.0 + float(by_day[d])
            if d in BOUNDARIES:
                series[d] = _q(Decimal(repr(level)), _Q4)
        fx[(base, quote)] = series
    # 3. marks: each instrument's price follows its loadings on the factors plus its own noise
    marks: dict[str, dict[date, Decimal]] = {}
    for inst in INSTRUMENTS:
        price = float(inst.start_price)
        series = {}
        drift = float(inst.annual_drift) / 252.0
        idio = float(inst.daily_sigma)
        for d in days:
            if d < YEAR_START:
                continue
            rate_code = "RATES_USD_10Y" if inst.currency == "USD" else "RATES_EUR_10Y"
            credit = (
                0.0
                if inst.credit_factor is None
                else float(inst.credit_loading) * float(factor_returns[inst.credit_factor][d])
            )
            noise = rng.gauss(0.0, idio) if idio > 0 else 0.0
            # A plain expression, not an accumulation: the aggregation census reads every `+=`
            # in irp_shared, and a seed's arithmetic is not an aggregation site.
            r = (
                drift
                + float(inst.market_beta) * float(factor_returns["MKT_GLOBAL_EQ"][d])
                + float(inst.rate_loading) * float(factor_returns[rate_code][d])
                + credit
                + noise
            )
            if inst.asset_class != "CASH":
                price *= 1.0 + r
            if d in BOUNDARIES:
                series[d] = _q(Decimal(repr(price)), _Q4)
        marks[inst.code] = series
    # 4. benchmark returns per boundary: the weighted return of the constituents' marks
    benchmark_returns: dict[str, dict[date, Decimal]] = {}
    for fund in FUNDS:
        series = {}
        prev: date | None = None
        for d in BOUNDARIES:
            if prev is not None:
                total = Decimal("0")
                for code, w in BENCHMARK_CONSTITUENTS[fund.code]:
                    m0, m1 = marks[code][prev], marks[code][d]
                    total = total + Decimal(w) * (m1 / m0 - Decimal("1"))
                series[d] = _q(total, _Q6)
            prev = d
        benchmark_returns[fund.code] = series
    return Paths(
        factor_returns=factor_returns, fx=fx, marks=marks, benchmark_returns=benchmark_returns
    )
