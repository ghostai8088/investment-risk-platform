"""LIM-2: the family registry and its censuses — the gates that replace a comment with a check.

Before LIM-2, ``_resolve_latest`` branched ``if VAR ... else <active risk>`` and the ``else``
asserted "the only other admitted family" in a COMMENT, while ``_METRIC_MAP`` — edited in a
different place — is what actually admits families. Registering a third family's metrics without
touching the dispatch would have routed it into the active-risk resolver, which accepts
``benchmark_id=None`` happily and matches no rows: a SILENT false ``NEVER_EVALUABLE``, not a crash.

That is the same shape as ``_SYN_MODULES`` and ``SNAPSHOT_COMPONENT_KINDS`` — two lists that must
be edited together, with nothing forcing it. P7's measured hierarchy puts an EXACT SET-EQUALITY
census at zero recorded recurrences and enumerating matchers at five, so the census is the primary
gate here and the fail-closed ``else: raise`` is defence in depth.
"""

from __future__ import annotations

import pytest

from irp_shared.concentration.events import RUN_TYPE_CONCENTRATION
from irp_shared.concentration.models import CONCENTRATION_METRIC_TYPES, METRIC_TYPE_SHARE
from irp_shared.limit.events import THRESHOLD_UNIT_FRACTION
from irp_shared.limit.service import (
    _METRIC_MAP,
    LIMIT_FAMILY_REGISTRY,
    LIMITABLE_RUN_TYPES,
    LimitError,
    _resolve_latest,
)
from irp_shared.risk.events import RUN_TYPE_ACTIVE_RISK, RUN_TYPE_VAR

#: The ten concentration metrics LIM-2 deliberately registered, pinned LITERALLY. The map itself is
#: DERIVED from ``CONCENTRATION_METRIC_TYPES`` so it cannot drift from CON-1 — which means adding a
#: metric there would silently make it limit-bindable. This literal is what turns that into a
#: failing test and a decision.
_EXPECTED_CONCENTRATION_METRICS = {
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


def test_every_metric_map_family_has_a_resolver() -> None:
    """**The census this slice exists to add.** Set equality in BOTH directions: a registered metric
    with no resolver would dispatch into another family's, and a registered resolver with no metric
    is dead code nobody will notice is dead."""
    from_metrics = {run_type for (run_type, _) in _METRIC_MAP}
    from_registry = set(LIMIT_FAMILY_REGISTRY)
    assert from_metrics == from_registry, (
        f"_METRIC_MAP and LIMIT_FAMILY_REGISTRY disagree.\n"
        f"metrics with no resolver: {sorted(from_metrics - from_registry)}\n"
        f"resolvers with no metric: {sorted(from_registry - from_metrics)}"
    )
    assert from_registry == {RUN_TYPE_VAR, RUN_TYPE_ACTIVE_RISK, RUN_TYPE_CONCENTRATION}


def test_LIMITABLE_RUN_TYPES_is_derived_not_hand_maintained() -> None:
    """The SCH-2 pattern: a derived set, never a second list someone must remember to update."""
    assert LIMITABLE_RUN_TYPES == frozenset(LIMIT_FAMILY_REGISTRY)


def test_metric_map_concentration_census_is_exact() -> None:
    """Adding a metric to CON-1 must FAIL here rather than silently become limit-bindable."""
    registered = {m for (rt, m) in _METRIC_MAP if rt == RUN_TYPE_CONCENTRATION}
    assert registered == _EXPECTED_CONCENTRATION_METRICS
    # ...and the map is derived from CON-1's own tuple, so the two can never disagree.
    assert registered == set(CONCENTRATION_METRIC_TYPES)


def test_every_concentration_metric_is_a_FRACTION_with_no_benchmark() -> None:
    """The unit landmine stays disarmed with the SHIPPED vocabulary: every concentration metric is
    a dimensionless ratio, so no threshold unit was minted and none needs to be."""
    for (run_type, metric), spec in _METRIC_MAP.items():
        if run_type != RUN_TYPE_CONCENTRATION:
            continue
        assert spec.unit == THRESHOLD_UNIT_FRACTION, metric
        assert not spec.requires_benchmark, metric
        expected = "share_invested_long" if metric == METRIC_TYPE_SHARE else "metric_value"
        assert spec.result_attr == expected, metric


def test_the_registry_declares_only_what_has_a_consumer() -> None:
    """SCH-2 removed ``produces_run_on_failure`` on the finding that *a false declaration with no
    consumer is worse than no declaration*. ``requires_benchmark`` deliberately stays on
    ``MetricSpec``, where it is a per-METRIC property — duplicating it onto the family would be
    exactly that failure."""
    fields = set(LIMIT_FAMILY_REGISTRY[RUN_TYPE_VAR].__dataclass_fields__)
    assert fields == {"target_run_type", "resolve", "requires_dimension", "requires_basis"}


def test_only_concentration_is_dimensional_and_basis_bearing() -> None:
    for run_type, family in LIMIT_FAMILY_REGISTRY.items():
        dimensional = run_type == RUN_TYPE_CONCENTRATION
        assert family.requires_dimension is dimensional, run_type
        assert family.requires_basis is dimensional, run_type
        assert family.target_run_type == run_type, "the registry key must match its declaration"


def test_an_unregistered_family_is_REFUSED_not_silently_misrouted() -> None:
    """The fail-closed ``else`` that replaced the comment. Defence in depth behind the census: if
    both were ever wrong at once, refusing beats adjudicating a governed threshold through some
    other family's resolver."""

    class _Fake:
        target_run_type = "NOT_A_FAMILY"
        metric_type = "WHATEVER"
        threshold_unit = THRESHOLD_UNIT_FRACTION

    with pytest.raises(LimitError, match="not a schedulable v1 metric"):
        _resolve_latest(None, _Fake())  # type: ignore[arg-type]


def test_a_registered_metric_with_no_resolver_is_REFUSED(monkeypatch) -> None:  # noqa: ANN001
    """The exact divergence the census forbids, forced into existence to prove the dispatch refuses
    it rather than falling through — the negative control for the census itself (P7)."""
    from irp_shared.limit import service as limit_service
    from irp_shared.limit.service import MetricSpec

    monkeypatch.setitem(
        limit_service._METRIC_MAP,
        ("GHOST_FAMILY", "GHOST_METRIC"),
        MetricSpec("metric_value", THRESHOLD_UNIT_FRACTION, False),
    )

    class _Ghost:
        target_run_type = "GHOST_FAMILY"
        metric_type = "GHOST_METRIC"
        threshold_unit = THRESHOLD_UNIT_FRACTION

    with pytest.raises(LimitError, match="no resolver is registered"):
        _resolve_latest(None, _Ghost())  # type: ignore[arg-type]

    # ...and with the ghost metric present, the census itself must fail — proving the census is
    # load-bearing rather than a tautology that would pass whatever the map contained.
    from_metrics = {run_type for (run_type, _) in limit_service._METRIC_MAP}
    assert from_metrics != set(LIMIT_FAMILY_REGISTRY)
