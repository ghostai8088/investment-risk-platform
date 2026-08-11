"""The mutation battery, as a committed artifact rather than a claim in a commit message.

A control is not a control until the change that would break it has been executed against it (P9),
and every slice since LQ-1 has cited a battery in its records. Until now those batteries were
ad-hoc shell written into a scratchpad and thrown away, so the citation had **no artifact** — the
Wave-16 close review recorded that as a finding: four cited proofs nobody could re-run. This is the
harness, and the mutants are declared in ``mutants.toml`` beside it, so re-running a past slice's
proof is one command.

**It never mutates the working tree.** The tree is copied to a scratch clone and every mutant is
applied there. That is not tidiness — FK-1's worst defect was its own battery restoring a file with
``git checkout``, which restores the COMMITTED state and silently destroyed an uncommitted fix,
after which the battery reported 4/4 KILLED over the tree it had just corrupted. A battery that
cannot touch the source it is validating cannot repeat that.

**An unmatched anchor is a SURVIVOR, never a pass.** A mutant whose ``find`` string is absent did
not weaken anything, so a green test proves nothing about it; reporting that as a kill is how a
battery inflates its own score after a refactor moves the code it was aiming at.

Usage::

    python scripts/mutation_battery.py                  # every mutant in the manifest
    python scripts/mutation_battery.py --group w16-close # one group
    python scripts/mutation_battery.py --list

Exit code 0 iff every selected mutant was KILLED and the unmutated baseline was green.

**The baseline is SCOPED to the mutants' target suites, and that is not the gate.** Running the
whole tree per mutant would make the battery too slow to use during a fold, so it runs only the
suites a mutant claims to be killed by. The consequence is worth stating because it bit on this
harness's first outing: it returned 12/12 with a green baseline over a tree whose full unit suite
had **21 failures** in files no mutant targeted. A green battery says the declared controls fire.
It says nothing at all about the rest of the suite, and `make check-all` remains the gate (P14).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).resolve().parent / "mutants.toml"
#: Copied, never mutated in place. Regenerated per run so a stale clone cannot be measured.
CLONE = Path(os.environ.get("IRP_MUTATION_CLONE", "/tmp/irp-mutation-clone"))
_EXCLUDE = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


@dataclass(frozen=True)
class Mutant:
    id: str
    group: str
    why: str
    file: str
    tests: list[str]
    find: str | None = None
    replace: str | None = None
    #: Delete everything from ``find`` up to (excluding) ``until`` — for removing a whole block.
    until: str | None = None
    #: True when the killing tests need a live PostgreSQL (``IRP_TEST_DATABASE_URL``).
    #:
    #: The harness strips that variable by default so a battery is runnable mid-fold without a
    #: database. The consequence bit on this harness's second outing: three PG-tier mutants
    #: reported KILLED-looking greens because their suites SKIPPED entirely — pytest exits 0 for a
    #: fully-skipped run, and "exit 0" was the kill signal. Opting in is the fix; the
    #: zero-tests-ran floor below is the backstop that would have caught it anyway.
    needs_pg: bool = False

    def apply(self, root: Path) -> tuple[bool, str]:
        """Return ``(applied, message)``. A missing anchor is a refusal, not a silent no-op."""
        path = root / self.file
        if not path.exists():
            return False, f"file absent: {self.file}"
        source = path.read_text()
        if self.find is None:
            return False, "mutant declares no `find` anchor"
        if self.find not in source:
            return False, "ANCHOR NOT MATCHED"
        if self.until is not None:
            start = source.index(self.find)
            if self.until not in source[start:]:
                return False, "`until` anchor not matched after `find`"
            end = start + source[start:].index(self.until)
            mutated = source[:start] + source[end:]
        else:
            mutated = source.replace(self.find, self.replace or "", 1)
        if mutated == source:
            return False, "mutation was a no-op"
        path.write_text(mutated)
        return True, "applied"


def _load(group: str | None) -> list[Mutant]:
    data = tomllib.loads(MANIFEST.read_text())
    mutants = [Mutant(**m) for m in data["mutant"]]
    return [m for m in mutants if group is None or m.group == group]


def _clone() -> Path:
    if CLONE.exists():
        shutil.rmtree(CLONE)
    shutil.copytree(
        REPO, CLONE, ignore=shutil.ignore_patterns(*_EXCLUDE), symlinks=True, dirs_exist_ok=False
    )
    return CLONE


def _pytest(root: Path, targets: list[str], *, needs_pg: bool = False) -> tuple[int, int]:
    """Run pytest. Returns ``(exit_code, tests_that_actually_ran)``.

    The second value is not decoration. pytest exits 0 for a run in which every test SKIPPED, so
    an exit code alone cannot distinguish "the mutant was killed by nothing because the suite is
    fine" from "the suite never executed". This harness reported three such phantom greens on its
    second outing (PG-tier mutants whose database URL it had stripped), which is the same
    false-green class it was built to prevent — so the count is now part of the verdict.
    """
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            str(root / p)
            for p in (
                "packages/shared-python/src",
                "apps/backend/src",
                "apps/worker/src",
            )
        ),
    }
    if not needs_pg:
        # Unit tier by default: a battery that always needed a live PostgreSQL would not be
        # runnable at the moment a fold needs it. PG-tier mutants opt in via `needs_pg`.
        env.pop("IRP_TEST_DATABASE_URL", None)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        # NO explicit ``-q``: pyproject's ``addopts`` already supplies one, and a second makes it
        # ``-qq`` — which suppresses the summary line ENTIRELY. That is the root cause of the
        # "pytest's final summary line is missing from the full-PG logs" anomaly carried open
        # across RPT-1, REPRO-1 and the Wave-16 close, where gate counts had to be recovered by
        # counting progress characters by hand. Diagnosed here because this harness needs the
        # count to tell a kill from a skip.
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--tb=no", *targets],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, _ran(proc.stdout)


_SUMMARY = re.compile(r"(\d+) (passed|failed|error)")


def _ran(stdout: str) -> int:
    """Tests that actually executed — passed + failed + errored, skips deliberately excluded."""
    return sum(int(n) for n, _ in _SUMMARY.findall(stdout))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default=None, help="run only this group")
    parser.add_argument("--list", action="store_true", help="list mutants and exit")
    parser.add_argument(
        "--check-anchors",
        action="store_true",
        help="verify every mutant's `find` still matches its target file, and exit. Seconds, not "
        "minutes — this is the half that runs inside `make check`.",
    )
    args = parser.parse_args()

    mutants = _load(args.group)
    if args.list:
        for m in mutants:
            print(f"{m.id:<12} [{m.group}] {m.why}")
        return 0
    if args.check_anchors:
        # Ratified at the Wave-17 close gate (2026-08-11, D5 — "the cheap anchor check in
        # `make check`"). The full battery clones the tree and runs pytest per mutant, which is too
        # slow to sit in every local gate; but the failure it had just suffered needed none of
        # that. Four `w16-close` mutants stopped matching their target file when ALERT-1 moved
        # bytes in a module it did not own the mutants for, and because NO gate ran the battery,
        # four Wave-16 alarm controls sat with no executable proof for a day — one of them the
        # infinite-paging bug a different review engine had caught. An unmatched anchor is a
        # SURVIVOR, so the battery was RED at HEAD the whole time and nothing asked.
        stale = [m for m in mutants if m.find not in (REPO / m.file).read_text(encoding="utf-8")]
        for m in stale:
            print(f"{m.id:<12} STALE ANCHOR in {m.file} — {m.why}")
        print(f"anchors: {len(mutants) - len(stale)}/{len(mutants)} match")
        if stale:
            print(
                "\nA stale anchor is a SURVIVOR, never a pass: the control it targets has NO "
                "executable proof. Re-anchor it against the current bytes — do not delete it."
            )
            return 1
        return 0
    if not mutants:
        print(f"no mutants selected (group={args.group!r})")
        return 1

    root = _clone()
    print(f"clone: {root}")

    targets = sorted({t for m in mutants for t in m.tests})
    any_pg = any(m.needs_pg for m in mutants)
    baseline, baseline_ran = _pytest(root, targets, needs_pg=any_pg)
    print(f"BASELINE (unmutated): exit {baseline}, {baseline_ran} tests ran")
    if baseline != 0:
        print("baseline is RED — every kill below would be unattributable. Stopping.")
        return 1
    if baseline_ran == 0:
        print("baseline ran ZERO tests — the battery would report phantom kills. Stopping.")
        return 1

    killed, survived = [], []
    for m in mutants:
        pristine = (root / m.file).read_text()
        applied, message = m.apply(root)
        if not applied:
            survived.append((m.id, message))
            print(f"{m.id:<12} **SURVIVOR** ({message})")
            continue
        exit_code, ran = _pytest(root, m.tests, needs_pg=m.needs_pg)
        # Restore EXACTLY the bytes displaced — the FK-1 rule, and the reason this reads from
        # memory rather than from git.
        (root / m.file).write_text(pristine)
        if ran == 0:
            # A suite that never executed cannot have killed anything. Reported as a SURVIVOR for
            # the same reason an unmatched anchor is: a mutation that did not run is not a
            # mutation that was killed.
            survived.append((m.id, "target suite ran ZERO tests (skipped?) — nothing was proven"))
            print(f"{m.id:<12} **SURVIVOR** (0 tests ran)  — {m.why}")
        elif exit_code != 0:
            killed.append(m.id)
            print(f"{m.id:<12} KILLED (exit {exit_code}, {ran} ran)  — {m.why}")
        else:
            survived.append((m.id, f"tests still passed ({ran} ran)"))
            print(f"{m.id:<12} **SURVIVOR** (exit 0)  — {m.why}")

    after, after_ran = _pytest(root, targets, needs_pg=any_pg)
    print(f"\nPOST-BATTERY baseline: exit {after}, {after_ran} tests ran")
    print(f"RESULT: {len(killed)}/{len(mutants)} killed")
    if survived:
        for mid, why in survived:
            print(f"  SURVIVOR {mid}: {why}")
    return 0 if not survived and after == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
