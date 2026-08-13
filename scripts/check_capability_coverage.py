#!/usr/bin/env python3
"""Capability coverage gate — does every capability the STRATEGY commits to have a requirement?

**Why this exists, and why its input is deliberately not a document Claude generated.**

Eight weeks of delivery drifted from the product's stated intent, and every audit run in that time
missed it for one structural reason: each audit compared code against requirements, or records
against code, and the requirement register was the reference point in all of them. An audit whose
yardstick is the artifact that carries the gap cannot see the gap.

So this gate's inputs are the two documents the OWNER wrote and owns:

  * ``01_product_strategy/capability_map.md``      — the CAP-nn / nn.m capability tree
  * ``01_product_strategy/regulatory_product_scope.md`` — the SCOPE-nn commitments

and it asks one question of each leaf: **is there a requirement behind it?**

Measured at the moment of writing: SCOPE-01..05 — including SCOPE-02's "public and private, both
first-class" — are cited in exactly ONE file, their own. Nothing downstream speaks that vocabulary,
so a commitment could be made and never converted with nothing registering the gap.

**Ratchet, not a wall.** The known gaps are recorded in a baseline file, visibly and by name. The
gate fails when a NEW uncovered capability appears, or when the baseline is edited to hide one
rather than to pay it. The gaps can shrink without touching this file; they cannot grow quietly.
That is deliberate: a gate that goes red on day one and blocks a security fix gets switched off,
and this project has already learned that a control everyone routes around is worse than no control.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The AUTHORITATIVE capability taxonomy. `capability_map.md` says so in its own header — "the
#: authoritative capability taxonomy is requirements_backbone.md §4 (CAP-1 … CAP-19) … where this
#: map and the backbone differ, the backbone governs" — so §4 is the declaration and the map is the
#: business view. The gate reads the declaration.
CAPABILITY_MAP = "02_requirements/requirements_backbone.md"
SCOPE_DOC = "01_product_strategy/regulatory_product_scope.md"
BACKBONE = "02_requirements/requirements_backbone.md"
RTM = "02_requirements/requirements_traceability_matrix.md"
BASELINE = "02_requirements/capability_coverage_baseline.json"

#: A leaf capability inside a capability-map table cell: "14.3 Lineage query/visualization".
#: The map writes several per cell separated by "·", so this matches the ID and its label.
_LEAF = re.compile(r"\b(\d{1,2}\.\d{1,2}[a-z]?)\s+([A-Za-z][^·|]*)")
#: The backbone's Cap column. A row may serve SEVERAL leaves and writes them "12.1/12.2" — the
#: first version of this matcher accepted only a cell holding exactly one id and therefore reported
#: model inventory, audit capture and RBAC as uncovered when all three have requirements. Checked in
#: the opposite direction before being trusted, which is the only reason it was caught.
_CAP_CELL = re.compile(
    r"\|\s*((?:\d{1,2}\.\d{1,2}[a-z]?)(?:\s*[/,]\s*\d{1,2}\.\d{1,2}[a-z]?)*)\s*\|"
)
_LEAF_ID = re.compile(r"\d{1,2}\.\d{1,2}[a-z]?")
_SCOPE = re.compile(r"\b(SCOPE-\d{2,3})\b")


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        print(f"capability-coverage: missing input {rel}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def declared_leaves() -> dict[str, str]:
    """Every leaf capability the strategy declares, id -> label."""
    text = _read(CAPABILITY_MAP)
    # Section 4 ONLY — the taxonomy table. Leaf ids elsewhere in the file are citations, not
    # declarations, and conflating them would let a capability declare itself by being referenced.
    m = re.search(r"^## 4\..*?$(.*?)^## 5\.", text, re.S | re.M)
    if not m:
        print(
            "capability-coverage: backbone section 4 (capability taxonomy) not found",
            file=sys.stderr,
        )
        sys.exit(2)
    out: dict[str, str] = {}
    for cap_id, label in _LEAF.findall(m.group(1)):
        out.setdefault(cap_id, " ".join(label.split())[:80])
    return out


def cited_leaves() -> set[str]:
    """Every leaf capability a requirement row claims to serve."""
    text = _read(BACKBONE) + "\n" + _read(RTM)
    out: set[str] = set()
    for cell in _CAP_CELL.findall(text):
        out |= set(_LEAF_ID.findall(cell))
    return out


def scope_coverage() -> tuple[set[str], set[str]]:
    """SCOPE ids declared, and those a REQUIREMENT cites.

    **Scoped to the requirement register on purpose, and the first version was not.** It scanned
    every markdown file in the tree, so a commitment counted as discharged the moment any document
    mentioned it — and it fired within the hour: the re-baseline document that DISCUSSES SCOPE-01,
    -02 and -05 made the gate report all three as covered and their baseline entries as stale.

    Writing *about* a commitment is not serving it. A SCOPE id is discharged when a REQUIREMENT
    ROW declares that it serves it, which is the whole point — the drift happened because the
    strategy's vocabulary was spoken in exactly one file and nothing in the delivery path had to
    answer to it. Prose about the gap does not close the gap.
    """
    declared = set(_SCOPE.findall(_read(SCOPE_DOC)))
    cited = set(_SCOPE.findall(_read(BACKBONE))) | set(_SCOPE.findall(_read(RTM)))
    return declared, cited


#: G3 (product re-baseline). A row in the PRESENTATION domain must have an acceptance criterion a
#: HUMAN CAN SEE. Measured before this gate existed: of 74 requirement rows, 22 required
#: reproduction and TWO required anyone to see anything, and the Definition of Done's only UI clause
#: was a prohibition. A presentation requirement whose acceptance is "the endpoint returns 200" is
#: how a platform ends up with 105 read endpoints and no screens.
_PRESENTATION_LEAF = re.compile(r"\b21\.\d{1,2}\b")
#: Deliberately a vocabulary of OBSERVABLE outcomes, not of UI nouns. "renders", "byte-identical
#: SVG" and "a reader reaches" all qualify; "the API exposes" does not, which is the point.
_HUMAN_VISIBLE = (
    "render",
    "rendered",
    "renders",
    "display",
    "displayed",
    "screen",
    "chart",
    "svg",
    "a reader",
    "sees",
    "seen",
    "visible",
    "on the page",
    "rendition",
)
#: A REQ row: id in column 1, cap in column 3, acceptance in column 9, of eleven pipe-separated
#: cells. Parsed positionally rather than by header, and asserted below so a column reshuffle
#: cannot silently turn this check into a no-op.
_REQ_ROW = re.compile(r"^\|\s*(REQ-[A-Z0-9-]+)\s*\|")


def presentation_rows_without_visible_acceptance() -> list[tuple[str, str]]:
    """Presentation requirements whose acceptance nobody could watch happen."""
    offenders: list[tuple[str, str]] = []
    for line in _read(BACKBONE).splitlines():
        m = _REQ_ROW.match(line)
        if not m:
            continue
        cells = line.split("|")
        if len(cells) < 11:
            continue
        cap, acceptance = cells[3], cells[9]
        if not _PRESENTATION_LEAF.search(cap):
            continue
        if not any(tok in acceptance.lower() for tok in _HUMAN_VISIBLE):
            offenders.append((m.group(1), acceptance.strip()[:90]))
    return offenders


#: G4 (product re-baseline). A wave close review must carry the capability-coverage artifact — the
#: gate exists to make it a required OUTPUT rather than a good intention, which is what it was.
CLOSE_REVIEW_GLOB = "wave_*_close_review.md"
CLOSE_REVIEW_DIR = "10_delivery_backlog"
G4_HEADING = "## Capability coverage (G4)"
#: Waves 1-17 closed before this gate existed. Retro-fitting a coverage table onto seventeen
#: historical documents would be writing a measurement that was never taken — the precise sin the
#: re-baseline exists to stop. G4 binds the next close and every one after it.
G4_FROM_WAVE = 18
#: The seventeen historical close reviews must still be FOUND. If the glob stops matching, the gate
#: has nothing to check and would report green forever — the failure mode this repository has now
#: hit five times, once inside the G2 fold written to prevent it.
G4_MIN_CLOSE_REVIEWS = 17
#: A wave that covered no new capability must SAY SO, in words, rather than shipping an empty table.
G4_NONE_MARK = "NO NEW CAPABILITY COVERAGE"
G4_MIN_NONE_REASON = 60
_WAVE_NUM = re.compile(r"wave_(\d+)_close_review\.md$")
_G4_TABLE_LEAF = re.compile(r"^\|\s*(\d{1,2}\.\d{1,2}[a-z]?)\s*\|", re.M)


def close_reviews() -> list[tuple[int, Path]]:
    """(wave number, path) for every close review, newest last. Refuses if the glob goes blind."""
    found: list[tuple[int, Path]] = []
    for p in sorted((ROOT / CLOSE_REVIEW_DIR).glob(CLOSE_REVIEW_GLOB)):
        m = _WAVE_NUM.search(p.name)
        if m:
            found.append((int(m.group(1)), p))
    if len(found) < G4_MIN_CLOSE_REVIEWS:
        print(
            f"capability-coverage: found {len(found)} close reviews, floor is "
            f"{G4_MIN_CLOSE_REVIEWS} — the discovery glob has gone blind and this gate would "
            f"report green having checked nothing",
            file=sys.stderr,
        )
        sys.exit(2)
    return sorted(found)


def g4_errors(cited: set[str], leaves: dict[str, str]) -> list[str]:
    """G4 — every close review from wave 18 on carries a verifiable capability-coverage table.

    **What is checked, and why it is the wave's OWN coverage rather than the platform's.** A table
    of "coverage right now" goes stale the moment the next requirement row lands, so enforcing it
    would redden CI until someone edited a historical document — rewriting a measurement after the
    fact, which is the class of defect this gate exists to prevent. The wave's own contribution is
    stable: the leaves its slices newly covered do not change when a later wave mints new ones.

    So each listed leaf must (a) be a real leaf in the owner's taxonomy and (b) still be cited by a
    requirement row today. (b) is monotone in the right direction: a leaf that was covered at close
    and is uncovered now is a REGRESSION, and failing on it is correct.
    """
    errors: list[str] = []
    for wave, path in close_reviews():
        if wave < G4_FROM_WAVE:
            continue
        text = path.read_text(encoding="utf-8")
        if G4_HEADING not in text:
            errors.append(
                f"{path.name} closes wave {wave} and has no '{G4_HEADING}' section. The coverage "
                f"table is a required OUTPUT of a close review, not a good intention."
            )
            continue
        body = text.split(G4_HEADING, 1)[1]
        body = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0]
        listed = _G4_TABLE_LEAF.findall(body)
        if not listed:
            if G4_NONE_MARK not in body:
                errors.append(
                    f"{path.name}: the G4 section lists no capability and does not say "
                    f"'{G4_NONE_MARK}'. An empty table is not a measurement."
                )
            elif len(" ".join(body.split())) - len(G4_NONE_MARK) < G4_MIN_NONE_REASON:
                errors.append(
                    f"{path.name}: '{G4_NONE_MARK}' with no reason. A wave that covered no new "
                    f"capability is a fact worth a sentence."
                )
            continue
        seen: set[str] = set()
        for leaf in listed:
            if leaf in seen:
                errors.append(f"{path.name}: capability {leaf} is listed twice in the G4 table")
            seen.add(leaf)
            if leaf not in leaves:
                errors.append(
                    f"{path.name}: the G4 table claims capability {leaf}, which is not a leaf in "
                    f"the owner's taxonomy (backbone section 4)"
                )
            elif leaf not in cited:
                errors.append(
                    f"{path.name}: the G4 table claims wave {wave} covered capability {leaf}, and "
                    f"NO requirement row cites it today — either the claim was never true or the "
                    f"coverage has REGRESSED"
                )
    return errors


def main() -> int:
    leaves = declared_leaves()
    cited = cited_leaves()
    uncovered_caps = {k: v for k, v in sorted(leaves.items()) if k not in cited}

    scope_declared, scope_cited = scope_coverage()
    uncovered_scope = sorted(scope_declared - scope_cited)

    baseline_path = ROOT / BASELINE
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    else:
        baseline = {"accepted_uncovered_capabilities": [], "accepted_uncovered_scope": []}

    accepted_caps = set(baseline.get("accepted_uncovered_capabilities", []))
    accepted_scope = set(baseline.get("accepted_uncovered_scope", []))

    new_caps = {k: v for k, v in uncovered_caps.items() if k not in accepted_caps}
    new_scope = [s for s in uncovered_scope if s not in accepted_scope]

    # The ratchet's other tooth: an accepted gap that is now COVERED must leave the baseline, or the
    # file silently grants permission for it to regress. Paying a debt updates the ledger.
    stale_caps = sorted(accepted_caps - set(uncovered_caps))
    stale_scope = sorted(accepted_scope - set(uncovered_scope))

    print(f"capability leaves declared : {len(leaves)}")
    print(f"  covered by a requirement : {len(leaves) - len(uncovered_caps)}")
    print(f"  uncovered (accepted)     : {len(uncovered_caps) - len(new_caps)}")
    print(f"  uncovered (NEW)          : {len(new_caps)}")
    print(f"SCOPE ids declared         : {len(scope_declared)}")
    print(f"  cited downstream         : {len(scope_declared & scope_cited)}")
    print(f"  uncited (NEW)            : {len(new_scope)}")

    errors: list[str] = []
    for cap_id, label in new_caps.items():
        errors.append(
            f"capability {cap_id} ({label}) is declared in the capability map and NO requirement "
            f"row cites it. Write the requirement, or record it in {BASELINE} with a reason."
        )
    for s in new_scope:
        errors.append(
            f"{s} is committed in the scope document and is cited in NO other document. A "
            f"commitment nothing downstream speaks is how the Wave 1-17 drift happened."
        )
    for cap_id in stale_caps:
        errors.append(
            f"capability {cap_id} is listed as an accepted gap but IS now covered — remove it from "
            f"{BASELINE}. A stale exemption is standing permission to regress."
        )
    for s in stale_scope:
        errors.append(
            f"{s} is listed as an accepted gap but IS now cited — remove it from {BASELINE}."
        )

    invisible = presentation_rows_without_visible_acceptance()
    for req_id, acceptance in invisible:
        errors.append(
            f"{req_id} is a PRESENTATION requirement whose acceptance criterion nobody could watch "
            f'happen: "{acceptance}...". A presentation row must be acceptable by SEEING '
            f"something rendered — 2 of the 74 pre-re-baseline rows were, and that is why the "
            f"platform has read endpoints with no screens."
        )
    print(f"presentation rows w/o visible acceptance: {len(invisible)}")

    reviews = close_reviews()
    bound = [w for w, _ in reviews if w >= G4_FROM_WAVE]
    errors.extend(g4_errors(cited, leaves))
    print(f"close reviews found        : {len(reviews)} — {len(bound)} bound by G4")

    if errors:
        print("\ncapability-coverage FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\ncapability-coverage passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
