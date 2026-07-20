"""CC-2 snapshot content + purpose/kind registration tests (the serializer is duck-typed; no DB).

The three greenfield content functions' FROZEN key sets (a later additive column must NOT silently
join a content function — the 0038 false-drift landmine, applied from birth); the FR-flavor
exclusions/inclusions; the IA-flavor full immutable set; the purpose + kind allow-list membership
(NOT the PROXY_WEIGHT tuple-bypass).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from irp_shared.snapshot.models import (
    COMPONENT_KIND_CAPITAL_CALL,
    COMPONENT_KIND_COMMITMENT,
    COMPONENT_KIND_DISTRIBUTION,
    PURPOSE_PACING_INPUT,
    SNAPSHOT_COMPONENT_KINDS,
    SNAPSHOT_PURPOSES,
)
from irp_shared.snapshot.serialize import (
    capital_call_content,
    commitment_content,
    distribution_content,
)

_NOW = datetime(2026, 7, 20, tzinfo=UTC)


def _commitment_row() -> SimpleNamespace:
    return SimpleNamespace(
        id="a" * 32,
        tenant_id="b" * 32,
        portfolio_id="c" * 32,
        instrument_id="d" * 32,
        committed_amount=Decimal("25000000.000000"),
        currency_code="USD",
        commitment_date=date(2025, 6, 30),
        restatement_reason=None,
        supersedes_id=None,
        valid_from=_NOW,
        # The mutable close-out markers exist on the real row but must NOT appear in the pin.
        valid_to=_NOW,
        system_to=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
        system_from=_NOW,
        record_version=1,
    )


def _call_row(**kw) -> SimpleNamespace:  # noqa: ANN003
    base = dict(
        id="e" * 32,
        tenant_id="b" * 32,
        portfolio_id="c" * 32,
        instrument_id="d" * 32,
        commitment_version_id="a" * 32,
        event_date=date(2025, 8, 15),
        amount=Decimal("3000000.000000"),
        currency_code="USD",
        call_type="DRAWDOWN",
        external_ref="MERX-CALL-1",
        reverses_id=None,
        system_from=_NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _dist_row(**kw) -> SimpleNamespace:  # noqa: ANN003
    base = dict(
        id="f" * 32,
        tenant_id="b" * 32,
        portfolio_id="c" * 32,
        instrument_id="d" * 32,
        commitment_version_id="a" * 32,
        event_date=date(2026, 6, 30),
        amount=Decimal("1200000.000000"),
        currency_code="USD",
        distribution_type="RETURN_OF_CAPITAL",
        is_recallable=True,
        external_ref="MERX-DIST-2",
        reverses_id=None,
        system_from=_NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_commitment_content_frozen_key_set_fr_flavor() -> None:
    content = commitment_content(_commitment_row())
    assert set(content) == {
        "id",
        "tenant_id",
        "portfolio_id",
        "instrument_id",
        "committed_amount",
        "currency_code",
        "commitment_date",
        "restatement_reason",
        "supersedes_id",
        "valid_from",
        "system_from",
        "record_version",
    }
    # FR pin flavor: the mutable close-out markers are EXCLUDED (TR-09 byte-stability).
    for excluded in ("valid_to", "system_to", "created_at", "updated_at"):
        assert excluded not in content
    assert content["committed_amount"] == "25000000.000000"


def test_capital_call_content_frozen_key_set_ia_flavor() -> None:
    content = capital_call_content(_call_row())
    assert set(content) == {
        "id",
        "tenant_id",
        "portfolio_id",
        "instrument_id",
        "commitment_version_id",
        "event_date",
        "amount",
        "currency_code",
        "call_type",
        "external_ref",
        "reverses_id",
        "system_from",
    }
    # A reversal row's negated amount is pinned verbatim (signed).
    rev = capital_call_content(_call_row(amount=Decimal("-9000000.000000"), reverses_id="9" * 32))
    assert rev["amount"] == "-9000000.000000"
    assert rev["reverses_id"] == "9" * 32


def test_distribution_content_frozen_key_set_with_recallable() -> None:
    content = distribution_content(_dist_row())
    assert set(content) == {
        "id",
        "tenant_id",
        "portfolio_id",
        "instrument_id",
        "commitment_version_id",
        "event_date",
        "amount",
        "currency_code",
        "distribution_type",
        "is_recallable",
        "external_ref",
        "reverses_id",
        "system_from",
    }
    assert content["is_recallable"] is True
    assert distribution_content(_dist_row(is_recallable=False))["is_recallable"] is False


def test_pacing_purpose_and_kinds_in_allow_lists() -> None:
    # The purpose JOINS the enforced tuple (NOT the PROXY_WEIGHT/RESIDUAL_SHRINKAGE bypass).
    assert PURPOSE_PACING_INPUT in SNAPSHOT_PURPOSES
    for kind in (
        COMPONENT_KIND_COMMITMENT,
        COMPONENT_KIND_CAPITAL_CALL,
        COMPONENT_KIND_DISTRIBUTION,
    ):
        assert kind in SNAPSHOT_COMPONENT_KINDS
