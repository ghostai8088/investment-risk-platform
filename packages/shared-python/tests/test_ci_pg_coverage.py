"""CI-PARITY CONFORMANCE PIN: every PostgreSQL-gated suite must actually run in CI.

**The drift this exists to stop.** CI's PostgreSQL tier is a hand-enumerated per-file allowlist —
one `run: pytest <path>` step per suite, ~65 of them — while the local merge gate is a wildcard full
battery (`pytest` over `testpaths`). A new `*_pg.py` suite therefore joins the local gate
automatically and joins CI *only if someone remembers to add a step*. For four consecutive
Wave-11/12 slices nobody did, and the suites that fell out were not incidental: they were the RLS /
append-only / ops-no-grant enforcement layer of the scheduler, limits+breach, breach-lifecycle and
notification surfaces — i.e. the machine-checked proof that the newest governance code is actually
tenant-isolated and immutable. Two demo stages (PPF-2, PPF-3) had silently fallen out too.

Nothing was broken by that — those suites all pass, and the local full-PG battery is a merge
precondition, so the enforcement WAS being tested. But it was being tested by human discipline
rather than by machine, which is exactly the arrangement this platform refuses everywhere else. A
gate that depends on remembering is not a gate.

So: this test fails if any suite gated on ``IRP_TEST_DATABASE_URL`` is absent from the CI workflow.
It is deliberately a plain-text scan with no YAML dependency — the thing being pinned is "the file
mentions this path in a pytest step", which is precisely what a regex can assert and what a
mis-indented YAML edit cannot fake.

It runs at the UNIT tier (no database), so it guards CI from the cheapest possible gate.
"""

from __future__ import annotations

import re
from pathlib import Path

# Repo root: .../packages/shared-python/tests/this_file.py -> up 4.
_ROOT = Path(__file__).resolve().parents[3]
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_TEST_DIRS = (
    _ROOT / "packages" / "shared-python" / "tests",
    _ROOT / "apps" / "backend" / "tests",
    _ROOT / "apps" / "worker" / "tests",
)

#: A suite is PG-gated when it reads this env var to decide whether to skip.
_PG_GATE = "IRP_TEST_DATABASE_URL"

#: The real gating idiom. Anchoring on the MARKER (not the bare word) is what keeps this file
#: from matching itself: it names both the env var and the concept, but declares no marker.
_SKIP_MARKER = re.compile(r"pytest\.mark\.skipif")

#: Suites intentionally excluded from the CI allowlist, each with a reason. EMPTY on purpose: an
#: exemption is a governance decision, not a convenience — add one only with a written rationale
#: (the audit-allowlist discipline), since every entry re-opens the drift this pins shut.
_EXEMPT: dict[str, str] = {}


def _pg_gated_suites() -> list[Path]:
    """Every suite that SKIPS itself without PostgreSQL.

    Detection is "names the gate env var AND carries a skip marker". Both halves are load-bearing:

    * naming the var alone is too broad — it would match this very file (which necessarily mentions
      both the var and the concept), producing a false failure that invites a self-exemption;
    * requiring the var to be READ via ``os.environ`` here is too NARROW, and that mistake would be
      a fail-open in this guard: three real suites (``test_var_hs_pg``, ``test_es_hs_pg``,
      ``test_desmoothing_estimation_pg``) import ``URL`` from a sibling module and name the var only
      in their skip *reason*, so an ``environ``-anchored regex would silently drop three genuine
      enforcement suites out of the pin — precisely the class of hole being closed.
    """
    found: list[Path] = []
    for directory in _TEST_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("test_*.py")):
            text = path.read_text(encoding="utf8")
            if _PG_GATE in text and _SKIP_MARKER.search(text):
                found.append(path)
    return found


def _ci_pytest_paths() -> set[str]:
    """Every path appearing in a `run: pytest …` line of the workflow."""
    text = _CI.read_text(encoding="utf8")
    paths: set[str] = set()
    for match in re.finditer(r"run:\s*pytest\s+(?P<args>[^\n]+)", text):
        for token in match.group("args").split():
            if token.endswith(".py"):
                paths.add(token)
            elif "/tests" in token:  # a whole-directory invocation covers everything under it
                paths.add(token.rstrip("/") + "/")
    return paths


def _is_covered(suite: Path, ci_paths: set[str]) -> bool:
    rel = suite.relative_to(_ROOT).as_posix()
    if rel in ci_paths:
        return True
    # a directory-level pytest invocation covers the suite
    return any(p.endswith("/") and rel.startswith(p) for p in ci_paths)


def test_ci_workflow_exists() -> None:
    """A non-vacuous guard: if the workflow moved, every assertion below would pass trivially."""
    assert _CI.is_file(), f"CI workflow not found at {_CI}"
    assert "run: pytest" in _CI.read_text(encoding="utf8")


def test_pg_gated_suites_are_discoverable() -> None:
    """Non-vacuity: the scan must actually find the PG suites. If a refactor renamed the gate env
    var, this test would otherwise silently pass with an empty set and pin nothing."""
    suites = _pg_gated_suites()
    assert len(suites) >= 60, f"expected the PG tier to be large; found {len(suites)}"


def test_every_pg_gated_suite_runs_in_ci() -> None:
    """THE PIN. A PG suite absent from CI is enforcement that exists only by local discipline."""
    ci_paths = _ci_pytest_paths()
    missing = [
        s.relative_to(_ROOT).as_posix()
        for s in _pg_gated_suites()
        if not _is_covered(s, ci_paths) and s.name not in _EXEMPT
    ]
    assert not missing, (
        "these PostgreSQL-gated suites are NOT run by any CI step, so their enforcement holds only "
        "by local discipline — add a step to .github/workflows/ci.yml (mind the shared-database "
        "step ordering and the demo-stage alpha-sort convention), or record an explicit exemption "
        "with a rationale in _EXEMPT:\n  " + "\n  ".join(missing)
    )


def test_exemptions_carry_a_rationale() -> None:
    """An exemption must say why: an unexplained exemption is a silent hole."""
    for name, reason in _EXEMPT.items():
        assert reason.strip(), f"exemption for {name} has no rationale"
