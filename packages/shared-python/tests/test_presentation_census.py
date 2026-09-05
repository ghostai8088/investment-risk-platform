"""W19-S1: REQ-PRS-001's census — every family declares a contract or a categorical exclusion.

    "Every family in the run-type registry has a presentation contract, asserted by EXACT SET
    EQUALITY against the registry (not a subset — a subset relation is satisfied by an empty
    contract set, the RPT-3 defect); families outside the presentable set are named in a DECLARED
    EXCLUSION carrying a written reason, never given a stub contract to satisfy the census; a family
    added without a contract or an exclusion fails the census; each contract names at least one
    identity field so no rendered number is anonymous."

**The universe is the 22-member run-type VOCABULARY, discovered by walking the source.** Not
``REPRODUCIBLE_FAMILIES ∪ UNREPRODUCIBLE_FAMILIES``, which is 21: ``RUN_TYPE_REPRODUCTION`` is in
neither of those sets, so a census keyed on that union would leave it in NO set and nothing would
fail — silence exactly where the acceptance demands a declared exclusion. The first draft of the S1
remit made that mistake; a different-engine pass caught it.

**Two namespaces.** The vocabulary holds UPPERCASE run types; a pinned report section carries a
lowercase family key. That every report family key is currently its run type lowercased is a fact
about four rows, not a rule, so the bridge is declared and pinned rather than computed.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

from irp_shared.presentation.contracts import (
    EXCLUSION_CATEGORIES,
    FAMILY_KEY_TO_RUN_TYPE,
    MARK_TYPES,
    PRESENTATION_CONTRACTS,
    PRESENTATION_EXCLUSIONS,
    PresentationContractError,
    contract_for_family_key,
    contract_for_run_type,
)

#: P6 floors, MEASURED at this slice. A collapse means the census lost its subject.
_MIN_VOCABULARY = 20
_MIN_CONTRACTS = 4
_MIN_EXCLUSIONS = 15


def run_type_vocabulary(extra: dict[str, str] | None = None) -> set[str]:
    """Every ``RUN_TYPE_*`` string constant in the platform, walked from the source.

    The same walk the reproduction census uses (``test_reproduction.py``), reused rather than
    re-invented so the two censuses cannot disagree about what the platform's families are.

    ``extra`` injects synthetic run types into the SAME analysis, so a negative control can plant a
    family and watch the real census function catch it — rather than asserting against a
    re-implementation, which is the shape that let a mutant survive at W19-S3b.
    """
    import irp_shared

    found: set[str] = set()
    for info in pkgutil.walk_packages(irp_shared.__path__, prefix="irp_shared."):
        if not info.name.endswith((".events", ".models")):
            continue
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if name.startswith("RUN_TYPE_") and isinstance(value, str):
                found.add(value)
    found.update((extra or {}).values())
    return found


def census(extra: dict[str, str] | None = None) -> tuple[set[str], set[str], set[str]]:
    """(vocabulary, declared, unclassified) — the real function every control below drives."""
    vocabulary = run_type_vocabulary(extra)
    declared = set(PRESENTATION_CONTRACTS) | set(PRESENTATION_EXCLUSIONS)
    return vocabulary, declared, vocabulary - declared


def test_every_family_is_declared_EXACTLY_once() -> None:
    """THE requirement: exact set equality in BOTH directions, and disjointness.

    A subset check passes on an empty contract set — the RPT-3 defect. Both directions also catch
    the opposite failure: a contract for a family the platform no longer has, which is a declaration
    about nothing.
    """
    vocabulary, declared, unclassified = census()

    assert not unclassified, (
        f"families in the vocabulary with NEITHER a contract nor a declared exclusion: "
        f"{sorted(unclassified)}. The acceptance says such a family FAILS — silence is not an "
        f"exclusion."
    )
    assert not (
        declared - vocabulary
    ), f"declared for families the platform does not have: {sorted(declared - vocabulary)}"
    assert declared == vocabulary
    overlap = set(PRESENTATION_CONTRACTS) & set(PRESENTATION_EXCLUSIONS)
    assert (
        not overlap
    ), f"{sorted(overlap)} is both contracted and excluded — a contradiction, not a default"


def test_REPRODUCTION_is_declared_rather_than_silently_absent() -> None:
    """The family the 21-member union would have dropped.

    `RUN_TYPE_REPRODUCTION` is in neither `REPRODUCIBLE_FAMILIES` nor `UNREPRODUCIBLE_FAMILIES`, so
    a census keyed on that union leaves it unclassified and passes anyway. It is in the vocabulary,
    so it must be declared — and it is, as NOT_A_MEASURE: a sweep verdict records that something
    happened, it does not measure anything.
    """
    vocabulary, _, _ = census()
    assert "REPRODUCTION" in vocabulary
    assert PRESENTATION_EXCLUSIONS.get("REPRODUCTION") == "NOT_A_MEASURE"


def test_a_family_with_NEITHER_declaration_FAILS() -> None:
    """The negative control, driving the REAL census function rather than a re-implementation.

    A mutant that disabled the S3a census's fixed point survived a control asserting against the
    algorithm's parts. This plants a synthetic run type into the same walk the census performs and
    asserts the census reports it — so the control fails when the census stops working, not when a
    copy of it does.
    """
    clean_vocab, _, clean_unclassified = census()
    assert not clean_unclassified  # baseline

    vocabulary, _, unclassified = census(extra={"RUN_TYPE_ZZ_PLANTED": "ZZ_PLANTED"})
    assert "ZZ_PLANTED" in vocabulary
    assert unclassified == {"ZZ_PLANTED"}, (
        "a family with neither a contract nor an exclusion did NOT fail the census — a new "
        "governed family could ship with no declared presentation at all"
    )
    assert len(vocabulary) == len(clean_vocab) + 1


def test_every_contract_is_COMPLETE_and_uses_the_closed_mark_vocabulary() -> None:
    """Each contract names a mark from the acceptance's four, a unit, a precision, and ≥1 identity
    field — 'so no rendered number is anonymous'."""
    for run_type, contract in PRESENTATION_CONTRACTS.items():
        assert contract.get("mark") in MARK_TYPES, (
            f"{run_type} declares mark {contract.get('mark')!r}, which is not one of "
            f"{MARK_TYPES} — REQ-PRS-002 enumerates exactly these four"
        )
        assert isinstance(contract.get("precision"), int), f"{run_type} has no integer precision"
        assert contract.get("unit"), f"{run_type} declares no unit"
        identity = contract.get("identity") or ()
        assert len(identity) >= 1, f"{run_type} names no identity field — its numbers are anonymous"
        assert all(isinstance(f, str) and f for f in identity)


def test_every_exclusion_names_a_category_from_the_CLOSED_vocabulary() -> None:
    """DS1-1, owner-ratified: categorical rather than free text.

    A free-text reason per family would make the census a tautology — `A ∪ (vocabulary − A) ==
    vocabulary` — and reasons of exactly that kind have been FALSE in this repo before (four of
    REPRO-1's).

    **This asserts MEMBERSHIP, not TRUTH**, and saying so is the point: nothing here proves
    `COVARIANCE` really is an intermediate input. The vocabulary narrows what can be claimed so a
    wrong claim is visible on review. Claiming more would be the overclaim this project keeps
    finding.
    """
    for run_type, category in PRESENTATION_EXCLUSIONS.items():
        assert (
            category in EXCLUSION_CATEGORIES
        ), f"{run_type} is excluded as {category!r}, which is not one of {EXCLUSION_CATEGORIES}"
    # ...and the vocabulary is genuinely used — a single category for all 18 would be the
    # boilerplate this decision exists to avoid.
    assert len(set(PRESENTATION_EXCLUSIONS.values())) >= 2, (
        "every exclusion shares one category — the categorical vocabulary has collapsed back into "
        "the free-text tautology it replaced"
    )


def test_the_namespace_bridge_is_pinned_against_REPORT_FAMILIES() -> None:
    """The two key namespaces, bridged explicitly.

    Today every report family key is its run type lowercased. That is a fact about four rows, not a
    rule, and an implicit `.upper()` would break silently the first time it stops holding.
    """
    from irp_shared.report.families import REPORT_FAMILIES

    assert set(FAMILY_KEY_TO_RUN_TYPE) == {f.key for f in REPORT_FAMILIES}, (
        "the declared bridge and REPORT_FAMILIES disagree — a report family with no bridged run "
        "type cannot resolve a contract at render time"
    )
    # every bridged run type is CONTRACTED, never excluded: a family with a report section that is
    # also declared unpresentable is a contradiction the census above would not catch on its own.
    for family_key, run_type in FAMILY_KEY_TO_RUN_TYPE.items():
        assert run_type in PRESENTATION_CONTRACTS, f"{family_key} -> {run_type} has no contract"


def test_resolution_REFUSES_rather_than_defaulting() -> None:
    """P9: the 'a family whose contract no renderer can resolve FAILS' clause, FIRED.

    Both arms, because they fail for different reasons and a default in either would be the inert
    fallback this slice exists to remove.
    """
    with pytest.raises(PresentationContractError) as excluded:
        contract_for_run_type("COVARIANCE")  # declared, but excluded — not contracted
    assert "INTERMEDIATE_INPUT" in str(excluded.value)

    with pytest.raises(PresentationContractError) as unknown:
        contract_for_run_type("ZZ_NOT_A_FAMILY")
    assert "neither" in str(unknown.value)

    with pytest.raises(PresentationContractError):
        contract_for_family_key("not_a_family_key")

    # ...and the positive side, so the refusals above are not passing because everything raises.
    assert contract_for_family_key("rolling_risk")["mark"] == "path"


def test_the_rolling_risk_series_selector_names_ONE_real_series() -> None:
    """DS1-2, owner-ratified on the second asking, pinned so the correction cannot be undone.

    `rolling_risk` holds NINE series per run: four 7-point `:12m` series and five 1-point `:36m`
    rows, every one of those five SUPPRESSED and pinned as a non-numeric string. The first framing
    of this decision called the 33 rows "a genuine time series" and the owner ratified on it.

    The selector lives in the CONTRACT, not the renderer, so changing it changes the chart — which
    is what makes REQ-PRS-002's "produced FROM the pinned contract" clause bite rather than being
    satisfiable by a hard-coded renderer.
    """
    contract = PRESENTATION_CONTRACTS["ROLLING_RISK"]
    selector = contract.get("series_selector")
    assert selector == {"metric_type": "ROLLING_VOLATILITY", "window_months": 12}
    # the selector's keys must be identity fields, or it selects on something the contract does not
    # claim identifies a value
    assert set(selector) <= set(contract["identity"])


def test_the_populations_have_coverage_floors() -> None:
    """P6. A matcher covers the shapes someone thought of; a floor notices coverage FALLING."""
    vocabulary, declared, _ = census()
    assert len(vocabulary) >= _MIN_VOCABULARY, (
        f"the run-type vocabulary collapsed to {len(vocabulary)} (floor {_MIN_VOCABULARY}) — the "
        f"walk has stopped finding families and the census is passing over nothing"
    )
    assert len(PRESENTATION_CONTRACTS) >= _MIN_CONTRACTS
    assert len(PRESENTATION_EXCLUSIONS) >= _MIN_EXCLUSIONS
    assert len(declared) == len(vocabulary)


def test_the_walk_finds_the_families_we_know_exist() -> None:
    """The POSITIVE control. An empty-or-broken walk would make every assertion above vacuous:
    exact set equality against an empty universe is satisfied by an empty declaration."""
    vocabulary, _, _ = census()
    for known in ("VAR", "CONCENTRATION", "LIQUIDITY", "ROLLING_RISK", "REPORT", "REPRODUCTION"):
        assert known in vocabulary, f"the run-type walk no longer finds {known}"
