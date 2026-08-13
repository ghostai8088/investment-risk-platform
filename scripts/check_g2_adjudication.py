#!/usr/bin/env python3
"""G2 — the adjudication ledger gate. **This checks PAPERWORK, never quality.**

Read that sentence again before citing this gate anywhere. It proves that a named human asked one
question about one exact piece of text. It has no opinion whatsoever about whether they answered it
well, and it must never be written up in a status document as a check on requirement quality.

**Why G2 is not a detector, which is the whole point.**

G2 was specified as an automated check: *does this acceptance criterion actually test the business
purpose beside it?* Six independent designs were built and scored against a labelled register with
three known-bad rows (2026-08-13 bake-off, 13 agents). All six caught all three. Every one of them
is nevertheless unusable, and for the same reason: underneath, each is checking WHICH WORDS APPEAR
in the acceptance sentence, and no word-based rule can tell a sentence that PROMISES something from
one that merely MENTIONS it. Measured on the best performer, by hand, on REQ-PPM-004:

    "Aggregates reproduce within tolerance and bind lineage"          -> FLAG   (correct)
    "Exposure rollup across the hierarchy is NOT implemented;
     the endpoint returns 501"                                        -> PASS   (!)
    the defect + six words: "; the hierarchy is recorded"             -> PASS   (!)
    the real 2026-08-12 repair, "removing the largest contributor
     moves total risk by that contributor's stated amount"            -> FLAG   (!)

The check passes the bug and blocks the patch, and six words of appended noise switch it off with
nothing built — not an attack someone must mount, an edit an author makes while tidying prose. The
model-judged variant understood the defects properly and failed differently: its verdict flips on
15 of 74 rows between runs. A verdict that changes between Tuesday and Wednesday cannot block a
merge.

The deeper reason, and the reason this file exists in the shape it does: G2 asks a question about
MEANING, about a document the person being checked can freely reword. Any word rule is one word
away from being switched off by the person it polices — which is exactly how the Wave 1-17 drift
happened. The criteria were written to be passable; a rule that reads those criteria would be
written around too.

So the gate is a person, and this file is the bookkeeping that makes the person's act unskippable
and makes it lapse when the text underneath it changes. Nothing more.

**What a human must do (Part A, which lives in the operating instructions, not here).**

Before a requirement row enters a slice's scope, a human who did not author it answers:

    "Describe an implementation that passes EVERY clause of this acceptance criterion and does NOT
     deliver the stated business purpose. Barred: 'they might compute it wrongly' — the
     implementation must be one a competent, lazy team would actually ship."

AMENDED (an exploit exists — rewrite the acceptance so it fails, and record the commit) or
REBUTTED (name the specific clause that blocks the obvious exploit, in a full sentence).

**One clause of the ratified design is deliberately NOT implemented**, and saying so here rather
than shipping it dead: the recommendation required *adjudicator != PR author*. On this project
every PR is authored by the sole human account, who is also the only valid adjudicator, so that
clause would either fail every run or be quietly deleted within a week. The substantive rule it
encodes — the adjudicator must not be the row's author — is enforced instead by ``MODEL:``
rejection plus roster membership: the register is authored by the model, so any human in the roster
satisfies it. If a second human ever joins the roster, revisit this.

Exit codes: 0 = clean · 1 = a scoped row is unadjudicated, stale or invalid · 2 = the gate could
not trust its own parse (structural), which is never reported as a pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BACKBONE = "02_requirements/requirements_backbone.md"
LEDGER = "02_requirements/g2_adjudication_ledger.jsonl"
ROSTER = "02_requirements/g2_adjudicators.json"
SCOPE = "02_requirements/g2_slice_scope.json"

#: A requirement row. The ``\**`` accommodates a bolded id — one of the six candidate designs was
#: demonstrated to go silently green when an id was bolded, because its pattern did not allow for
#: it. The ``[a-z]?`` accommodates an amendment row: the register carries REQ-MKT-002a and
#: REQ-MKT-004a, and FOUR of the six bake-off scripts silently dropped exactly those two — the
#: newest and least-reviewed rows in the file.
_ROW = re.compile(r"^\|\s*\**(REQ-[A-Z]{3}-\d{3}[a-z]?)\**\s*\|")
#: Anything that LOOKS like a requirement row. The count of these must equal the count parsed, or
#: the gate refuses to report at all. Four guards in this repository have shipped green while
#: matching nothing; this one asserts it matched the file's own row count before it says a word.
_ANY_ROW = re.compile(r"^\|\s*\**REQ-")
_HEADER = "| REQ | Title |"

_EMPHASIS = re.compile(r"[*_`]")

MIN_REASONING = 120
DISPOSITIONS = frozenset({"AMENDED", "REBUTTED"})

#: A floor on the parsed register, not merely "more than zero". The register has only ever grown
#: (74 rows at the re-baseline, 86 after part 1). A parse returning a handful is a broken parser
#: reporting a pass.
MIN_REGISTER_ROWS = 70
#: An empty scope must be a DECLARED emptiness, not a default one. See ``_scope_is_vacuous``.
MIN_NO_SCOPE_REASON = 60


class Structural(Exception):
    """The gate cannot trust its own reading of the inputs. Never a pass, never a plain failure."""


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        raise Structural(f"missing input {rel}")
    return p.read_text(encoding="utf-8")


def _normalise(cell: str) -> str:
    """Whitespace collapsed, markdown emphasis stripped. Nothing else.

    Deliberately minimal. Every additional normalisation is a way for a substantive edit to slip
    through as cosmetic, and the staleness check is the only thing standing between an adjudicated
    row and a rewritten one.
    """
    return " ".join(_EMPHASIS.sub("", cell).split())


def row_hash(purpose: str, acceptance: str) -> str:
    payload = _normalise(purpose) + "\x1f" + _normalise(acceptance)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _columns(text: str) -> tuple[int, int, int]:
    """(purpose, acceptance, width) column indices, read from the table header, not assumed."""
    headers = {
        tuple(c.strip() for c in line.strip().strip("|").split("|"))
        for line in text.splitlines()
        if line.startswith(_HEADER)
    }
    if len(headers) != 1:
        raise Structural(
            f"expected exactly one requirement-table header shape, found {len(headers)} — a column "
            f"reshuffle would make this gate hash the wrong cells"
        )
    cells = headers.pop()
    for name in ("Business purpose", "Acceptance"):
        if name not in cells:
            raise Structural(f"requirement table has no {name!r} column")
    return cells.index("Business purpose"), cells.index("Acceptance"), len(cells)


def parse_rows(text: str) -> dict[str, str]:
    """req_id -> hash of (business purpose, acceptance). Refuses on any parse mismatch."""
    i_purpose, i_acceptance, width = _columns(text)
    seen_any = 0
    out: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        if not _ANY_ROW.match(line):
            continue
        seen_any += 1
        m = _ROW.match(line)
        if not m:
            raise Structural(
                f"line {lineno} looks like a requirement row and did not parse: {line[:70]}"
            )
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != width:
            raise Structural(
                f"{m.group(1)} (line {lineno}) has {len(cells)} cells, the header declares {width}"
            )
        if m.group(1) in out:
            raise Structural(f"{m.group(1)} appears twice in the register")
        out[m.group(1)] = row_hash(cells[i_purpose], cells[i_acceptance])
    if seen_any != len(out):
        raise Structural(f"{seen_any} rows look like requirements, {len(out)} parsed")
    if len(out) < MIN_REGISTER_ROWS:
        # Not merely "> 0". A gate that matches nothing reports green forever, and the register has
        # only ever grown (74 -> 86). A parse that suddenly returns a handful of rows is a parser
        # failure wearing a pass, which is the exact shape of the four inert guards this repository
        # has already shipped.
        raise Structural(
            f"only {len(out)} requirement rows parsed, floor is {MIN_REGISTER_ROWS} — a gate that "
            f"matches (almost) nothing reports green"
        )
    return out


def load_ledger() -> list[dict]:
    """The append-only adjudication ledger, one JSON object per line."""
    entries: list[dict] = []
    for lineno, line in enumerate(_read(LEDGER).splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise Structural(f"{LEDGER} line {lineno} is not valid JSON: {exc}") from exc
    return entries


def validate_entries(
    entries: list[dict], roster: set[str]
) -> tuple[dict[tuple[str, str], dict], list[str]]:
    """Index the ledger by (req_id, hash), rejecting anything that would let a finding be erased."""
    index: dict[tuple[str, str], dict] = {}
    errors: list[str] = []
    for n, e in enumerate(entries, 1):
        req = e.get("req_id", "")
        key = (req, e.get("hash", ""))
        if key in index:
            # Rejected outright rather than last-line-wins: appending a line must never overwrite a
            # prior adjudication, or the ledger becomes editable history.
            errors.append(
                f"ledger entry {n}: duplicate key {key[0]} @ {key[1][:12]} — a second "
                f"adjudication of identical text would erase the first"
            )
            continue
        who = str(e.get("adjudicator", ""))
        if who.startswith("MODEL:"):
            errors.append(
                f"ledger entry {n} ({req}): adjudicator {who!r} is a model. G2 is the one "
                f"gate a model cannot answer for itself — that is why it exists"
            )
        elif who not in roster:
            errors.append(f"ledger entry {n} ({req}): adjudicator {who!r} is not in {ROSTER}")
        if e.get("disposition") not in DISPOSITIONS:
            errors.append(
                f"ledger entry {n} ({req}): disposition {e.get('disposition')!r} is not "
                f"one of {sorted(DISPOSITIONS)}"
            )
        reasoning = str(e.get("reasoning", ""))
        if len(reasoning) < MIN_REASONING:
            errors.append(
                f"ledger entry {n} ({req}): reasoning is {len(reasoning)} characters, "
                f"minimum {MIN_REASONING}. 'Looks fine' is not a disposition"
            )
        if e.get("disposition") == "AMENDED" and not str(e.get("amendment_commit", "")).strip():
            errors.append(
                f"ledger entry {n} ({req}): AMENDED with no amendment_commit — an exploit "
                f"was found and nothing records the repair"
            )
        index[key] = e
    return index, errors


def check_scope_declaration(scope_doc: dict) -> None:
    """An EMPTY scope must be a declared emptiness, never a default one.

    **This interlock exists because the first version of this gate did not have it, and a second,
    independent bake-off run found the hole within the hour.** With ``slice_scope: []`` the gate
    exited 0 having adjudicated nothing — the empty-population vacuity, sitting inside the very gate
    whose subject is checks that pass while checking nothing. This project has now shipped four
    guards that were green because they matched nothing; that this one nearly made five, in the fold
    written to prevent it, is the reason the rule below is a refusal rather than a warning.

    Two shapes are rejected:
      * a slice is DECLARED and its scope is empty — a slice that adjudicates nothing;
      * no slice is declared and no reason is given — the silent default that rots.

    What it does NOT do is decide whether a slice is really in flight. That would mean reading the
    roadmap, which has no machine-readable active-slice marker, and a fragile parse would fail open.
    So the emptiness is attributable rather than proven: someone must write down why. **Accepted
    residual, with its trigger:** at the first slice-planning gate that sets ``slice``, this becomes
    load-bearing on its own; until then it buys attribution, not detection.
    """
    slice_id = scope_doc.get("slice")
    scope = [r for r in scope_doc.get("slice_scope", []) if r]
    if slice_id and not scope:
        raise Structural(
            f"slice {slice_id!r} is declared with an EMPTY G2 scope. A slice that adjudicates "
            f"nothing is the empty-population vacuity this gate exists to refuse."
        )
    reason = str(scope_doc.get("no_scope_reason", "")).strip()
    if not slice_id and len(reason) < MIN_NO_SCOPE_REASON:
        raise Structural(
            f"no slice is declared and no_scope_reason is {len(reason)} characters (minimum "
            f"{MIN_NO_SCOPE_REASON}). An empty G2 scope must be someone's written decision, not "
            f"a file nobody has touched."
        )


def main() -> int:
    try:
        text = _read(BACKBONE)
        rows = parse_rows(text)
        roster = set(json.loads(_read(ROSTER))["adjudicators"])
        scope_doc = json.loads(_read(SCOPE))
        check_scope_declaration(scope_doc)
        entries = load_ledger()
    except (Structural, KeyError, json.JSONDecodeError) as exc:
        print(f"g2-adjudication STRUCTURAL FAILURE: {exc}", file=sys.stderr)
        return 2

    index, errors = validate_entries(entries, roster)
    adjudicated = {req for req, _ in index}
    current = {req for (req, h), _ in index.items() if rows.get(req) == h}

    scope = [r for r in scope_doc.get("slice_scope", []) if r]
    worklist = [r for r in scope_doc.get("worklist", []) if r]

    unknown = sorted(set(scope) - set(rows))
    for req in unknown:
        errors.append(f"{req} is in the slice scope and is not a row in the register")

    # A ledger entry pointing at a row that no longer exists. Harmless on its own, and a reliable
    # sign that either the register was renumbered without the ledger following, or the ledger is
    # accumulating adjudications of text nobody can read any more.
    for req in sorted({r for r, _ in index} - set(rows)):
        errors.append(
            f"the ledger adjudicates {req}, which is not a row in the register — a renumbering or "
            f"a deletion has left an adjudication pointing at text that no longer exists"
        )

    blocking: list[str] = []
    for req in scope:
        if req in unknown:
            continue
        if req not in adjudicated:
            blocking.append(
                f"{req} is entering a slice UNADJUDICATED. The G2 question has not been "
                f"asked about it by anyone."
            )
        elif req not in current:
            blocking.append(
                f"{req} was adjudicated, and its business purpose or acceptance text has "
                f"CHANGED since. The adjudication has lapsed — ask again."
            )

    print(f"requirement rows parsed    : {len(rows)}")
    print(f"  adjudicated (any version): {len(adjudicated)}")
    print(f"  adjudication CURRENT     : {len(current)}")
    print(f"slice scope                : {len(scope)}")
    print(f"  blocking                 : {len(blocking)}")
    print(f"worklist (advisory)        : {len(worklist)} — {', '.join(sorted(worklist)) or 'none'}")

    stale_worklist = sorted(set(worklist) & current)
    if stale_worklist:
        print(f"  now adjudicated, remove from the worklist: {', '.join(stale_worklist)}")

    if errors or blocking:
        print("\ng2-adjudication FAILED:")
        for e in errors + blocking:
            print(f"  - {e}")
        return 1

    print(
        "\ng2-adjudication passed. This proves the question was ASKED, "
        "not that it was answered well."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
