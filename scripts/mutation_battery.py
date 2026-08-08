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


def _pytest(root: Path, targets: list[str]) -> int:
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
    # The unit tier only: a mutation battery that needed a live PostgreSQL would not be runnable
    # at the moment a fold needs it, and every control declared here is unit-tier by construction.
    env.pop("IRP_TEST_DATABASE_URL", None)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--tb=no", "-q", *targets],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default=None, help="run only this group")
    parser.add_argument("--list", action="store_true", help="list mutants and exit")
    args = parser.parse_args()

    mutants = _load(args.group)
    if args.list:
        for m in mutants:
            print(f"{m.id:<12} [{m.group}] {m.why}")
        return 0
    if not mutants:
        print(f"no mutants selected (group={args.group!r})")
        return 1

    root = _clone()
    print(f"clone: {root}")

    targets = sorted({t for m in mutants for t in m.tests})
    baseline = _pytest(root, targets)
    print(f"BASELINE (unmutated): exit {baseline}")
    if baseline != 0:
        print("baseline is RED — every kill below would be unattributable. Stopping.")
        return 1

    killed, survived = [], []
    for m in mutants:
        pristine = (root / m.file).read_text()
        applied, message = m.apply(root)
        if not applied:
            survived.append((m.id, message))
            print(f"{m.id:<12} **SURVIVOR** ({message})")
            continue
        exit_code = _pytest(root, m.tests)
        # Restore EXACTLY the bytes displaced — the FK-1 rule, and the reason this reads from
        # memory rather than from git.
        (root / m.file).write_text(pristine)
        if exit_code != 0:
            killed.append(m.id)
            print(f"{m.id:<12} KILLED (exit {exit_code})  — {m.why}")
        else:
            survived.append((m.id, "tests still passed"))
            print(f"{m.id:<12} **SURVIVOR** (exit 0)  — {m.why}")

    after = _pytest(root, targets)
    print(f"\nPOST-BATTERY baseline: exit {after}")
    print(f"RESULT: {len(killed)}/{len(mutants)} killed")
    if survived:
        for mid, why in survived:
            print(f"  SURVIVOR {mid}: {why}")
    return 0 if not survived and after == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
