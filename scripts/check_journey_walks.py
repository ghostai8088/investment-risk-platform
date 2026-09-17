#!/usr/bin/env python3
"""G5 — the journey-walk ledger gate. **This checks PAPERWORK, never quality.**

Read that sentence before citing this gate anywhere. It proves that a named human walked one
journey line on a deployed build and wrote down the decision the persona would take from it. It
has no opinion about whether that decision is sensible, whether the screen is good, or whether a
Chief Risk Officer would recognise the product. It must never be written up as a check on any of
those things.

**Why the product needs a gate that a script cannot answer.**

The 2026-08-12 re-baseline found the Wave 1-17 drift mechanism: acceptance criteria satisfiable
without delivering the stated purpose. It repaired the requirements register and built four gates
that read the register. The first presentation slice built under them shipped a chart nobody can
see on any screen, and the gate meant to catch that (G3) passed it, because a rendered artifact
asserted on by a test is "a rendered artifact". The register describes what a system does. It
cannot describe what a person experiences, and every gate that reads the register inherits that
limit. So the 2026-09-17 re-baseline (`02_requirements/product_rebaseline_2026-09-17.md`) puts a
person in the loop, on the G2 precedent: the act is human, the bookkeeping is mechanical.

**The act (Part A, which lives in the operating instructions, not here).**

At every slice close that declares journey lines, a person on the roster opens the DEPLOYED stack,
walks each declared line as the named persona, and answers:

    "Name the decision the persona would take from this screen today, and the value on the screen
     that drove it. If no decision follows from what is shown, the verdict is NOT WALKABLE."

The first draft of this gate asked the walker to describe what was on the screen. A different
engine broke it in one pass: five stacked tables of verbatim strings, a 120-character description,
WALKABLE. Describing a screen is not using it. Constructing a decision from it is. That is why the
ledger row carries `decision` and `driving_value`, and why a WALKABLE row without both is invalid.

**What the bookkeeping enforces, and nothing more.**

  * Every journey line the slice declared has a WALKABLE row: by a roster member, not a model;
    hashed against the line's CURRENT text (edit the line and every walk of it lapses); walked on
    a `deployed_head` that is an ancestor of the commit under check; and not STALE (no file under
    the declared source directories changed after that head).
  * An empty declaration is a DECLARED emptiness with a written reason (the vacuity a second G2
    bake-off found inside the G2 gate itself), never a default.
  * From Wave 20 on, a close review carries a `## Journey coverage (G5)` section naming the lines
    the wave made walkable, each backed by a WALKABLE ledger row, or says NO NEW JOURNEY COVERAGE
    with a reason.

Exit codes: 0 = clean · 1 = a declared line is unwalked, lapsed, stale or invalid · 2 = the gate
could not trust its own parse or its own git (structural), which is never reported as a pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JOURNEYS = "02_requirements/personas_and_user_journeys.md"
LEDGER = "02_requirements/journey_walk_ledger.jsonl"
ROSTER = "02_requirements/g2_adjudicators.json"
SCOPE = "02_requirements/journey_slice_scope.json"
CLOSE_REVIEW_DIR = "10_delivery_backlog"
CLOSE_REVIEW_GLOB = "wave_*_close_review.md"

#: A journey line is a table row whose first cell is its id: `| J-CRO-1 | ... |`. The id grammar
#: is deliberately narrow; a line that does not match it is not a journey line and is not hashed.
_LINE_ID = re.compile(r"^J-[A-Z]{2,4}-\d{1,2}$")
_LINE_ROW = re.compile(r"^\|\s*\**(J-[A-Z]{2,4}-\d{1,2})\**\s*\|(.*)\|\s*$")
#: Anything that LOOKS like a journey line. The count of these must equal the count parsed, or the
#: gate refuses to report: a parser that silently drops rows reports green over what it dropped.
_ANY_LINE_ROW = re.compile(r"^\|\s*\**J-[A-Z]{2,4}-\d")
_EMPHASIS = re.compile(r"[*_`]")
_WAVE_NUM = re.compile(r"wave_(\d+)_close_review\.md$")
_HEX = re.compile(r"^[0-9a-f]{7,40}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: The persona vocabulary of personas_and_user_journeys.md section 2. A J-CRO line walked "as" the
#: PM is not a walk of that line.
PERSONAS = frozenset(
    {"P-CRO", "P-RM", "P-RA", "P-PM", "P-MV", "P-DS", "P-CO", "P-IA", "P-ADM", "P-BRD", "P-OPS"}
)
#: Every declared source directory must sit under the front end: the STALE rule watches the
#: screen, and a directory elsewhere (or nowhere) is a way to declare a watch that sees nothing.
SOURCE_DIR_PREFIX = "apps/frontend/"

VERDICTS = frozenset({"WALKABLE", "NOT WALKABLE"})
MIN_REASONING = 120
#: Floors that a "." cannot pass. Paperwork, still: they prove a sentence was written, not that
#: it was a good one. The verifier's attack A1 (decision ".", driving_value "n/a", reasoning a
#: repeated character) passed the first version; these are its residue.
MIN_DECISION = 40
MIN_REASONING_DISTINCT_CHARS = 20
_HAS_DIGIT = re.compile(r"\d")
MIN_NO_SCOPE_REASON = 60
#: A floor on the parsed journey lines, not merely "more than zero". Twelve exist at birth.
MIN_JOURNEY_LINES = 10

G5_HEADING = "## Journey coverage (G5)"
G5_FROM_WAVE = 20
G5_NONE_MARK = "NO NEW JOURNEY COVERAGE"
G5_MIN_NONE_REASON = 60
#: Eighteen close reviews existed when this gate was written and nineteen when it shipped. A
#: discovery glob that finds fewer has gone blind, and a blind glob reports green.
G5_MIN_CLOSE_REVIEWS = 18
_G5_TABLE_LINE = re.compile(r"^\|\s*\**(J-[A-Z]{2,4}-\d{1,2})\**\s*\|", re.M)
#: The G5 section heading, LINE-ANCHORED. A substring search took a prose mention of the heading
#: earlier in the file as the section (verifier attack A7c) and read the remainder as its body.
_G5_HEADING_LINE = re.compile(r"^#{2,3} Journey coverage \(G5\)\s*$", re.M)


class Structural(Exception):
    """The gate cannot trust its own reading of the inputs. Never a pass, never a plain failure."""


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        raise Structural(f"missing input {rel}")
    return p.read_text(encoding="utf-8")


def _normalise(cell: str) -> str:
    """Whitespace collapsed, markdown emphasis stripped. Nothing else — every further normalisation
    is a way for a substantive edit to slip through as cosmetic."""
    return " ".join(_EMPHASIS.sub("", cell).split())


def line_hash(text: str) -> str:
    return hashlib.sha256(_normalise(text).encode("utf-8")).hexdigest()


def parse_lines(text: str) -> dict[str, str]:
    """journey line id -> hash of its text (every cell after the id). Refuses on any mismatch."""
    seen_any = 0
    out: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not _ANY_LINE_ROW.match(raw):
            continue
        seen_any += 1
        m = _LINE_ROW.match(raw.rstrip())
        if not m:
            raise Structural(
                f"line {lineno} looks like a journey line and did not parse: {raw[:70]}"
            )
        line_id, body = m.group(1), m.group(2)
        if line_id in out:
            raise Structural(f"{line_id} appears twice in {JOURNEYS}")
        out[line_id] = line_hash(body)
    if seen_any != len(out):
        raise Structural(f"{seen_any} rows look like journey lines, {len(out)} parsed")
    if len(out) < MIN_JOURNEY_LINES:
        raise Structural(
            f"only {len(out)} journey lines parsed, floor is {MIN_JOURNEY_LINES} — a gate that "
            f"matches (almost) nothing reports green"
        )
    return out


def load_ledger() -> list[dict]:
    entries: list[dict] = []
    for lineno, raw in enumerate(_read(LEDGER).splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("//"):
            continue
        try:
            entries.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise Structural(f"{LEDGER} line {lineno} is not valid JSON: {exc}") from exc
    return entries


def validate_entries(entries: list[dict], roster: set[str], lines: dict[str, str]) -> list[str]:
    """Every row must be well-formed on its own, whether or not any slice is asking about it."""
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for n, e in enumerate(entries, 1):
        line = str(e.get("line", ""))
        tag = f"ledger entry {n} ({line or '?'})"
        if not _LINE_ID.match(line):
            errors.append(f"{tag}: {line!r} is not a journey line id")
        elif line not in lines:
            errors.append(f"{tag}: no journey line with this id exists in {JOURNEYS}")
        key = (line, str(e.get("line_hash", "")), str(e.get("deployed_head", "")))
        if key in seen:
            errors.append(
                f"{tag}: duplicate (line, line_hash, deployed_head) — a walk cannot be re-recorded"
            )
        seen.add(key)
        who = str(e.get("walked_by", ""))
        if who.startswith("MODEL:"):
            errors.append(
                f"{tag}: walked_by {who!r} is a model. G5 is the gate a model cannot answer "
                f"for itself"
            )
        elif who not in roster:
            errors.append(f"{tag}: walked_by {who!r} is not in {ROSTER}")
        verdict = e.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{tag}: verdict {verdict!r} is not one of {sorted(VERDICTS)}")
        if not _HEX.match(str(e.get("deployed_head", ""))):
            errors.append(f"{tag}: deployed_head is not a commit hash")
        reasoning = str(e.get("reasoning", ""))
        if len(reasoning) < MIN_REASONING:
            errors.append(
                f"{tag}: reasoning is under {MIN_REASONING} characters. 'Looks fine' is not a walk"
            )
        elif len(set(reasoning)) < MIN_REASONING_DISTINCT_CHARS:
            errors.append(f"{tag}: reasoning is {len(reasoning)} characters of filler")
        if verdict == "WALKABLE":
            decision = str(e.get("decision", "")).strip()
            driving = str(e.get("driving_value", "")).strip()
            if not decision or not driving:
                errors.append(
                    f"{tag}: WALKABLE with no decision or no driving_value. Describing a screen is "
                    f"not using it; the walker names the decision the persona would take and the "
                    f"value that drove it, or the line is NOT WALKABLE"
                )
            else:
                if len(decision) < MIN_DECISION:
                    errors.append(
                        f"{tag}: decision is {len(decision)} characters (minimum {MIN_DECISION}). "
                        f"A decision is a sentence, not a mark"
                    )
                if not _HAS_DIGIT.search(driving):
                    errors.append(
                        f"{tag}: driving_value {driving!r} carries no number. The value that drove "
                        f"a risk decision is a number on the screen"
                    )
        if e.get("persona") not in PERSONAS:
            errors.append(f"{tag}: persona {e.get('persona')!r} is not one of {sorted(PERSONAS)}")
        elif line[:5] == "J-CRO" and e.get("persona") not in {"P-CRO", "P-RM"}:
            errors.append(f"{tag}: a J-CRO line walked as {e.get('persona')} is not a walk of it")
        elif line[:4] == "J-PM" and e.get("persona") != "P-PM":
            errors.append(f"{tag}: a J-PM line walked as {e.get('persona')} is not a walk of it")
        if not _ISO_DATE.match(str(e.get("walked_at", ""))):
            errors.append(f"{tag}: walked_at is not an ISO date")
        if not str(e.get("route", "")).strip().startswith("/"):
            errors.append(f"{tag}: no route recorded")
    return errors


def check_scope_declaration(scope_doc: dict) -> None:
    """An EMPTY scope must be a declared emptiness, never a default one (the G2 interlock)."""
    slice_id = scope_doc.get("slice")
    scope = [r for r in scope_doc.get("journey_lines", []) if r]
    if slice_id and not scope:
        raise Structural(
            f"slice {slice_id!r} is declared with an EMPTY G5 scope and no journey line. A "
            f"presentation slice that walks nothing is the empty-population vacuity this gate "
            f"refuses; "
            f"a slice with genuinely no journey line declares no slice and writes the reason."
        )
    dirs = [str(d).strip() for d in scope_doc.get("source_dirs", []) if str(d).strip()]
    if slice_id and not dirs:
        raise Structural(
            f"slice {slice_id!r} declares journey lines and no source_dirs — the STALE rule would "
            f"have nothing to watch, so a post-walk rewrite of the screen would merge on the "
            f"old walk."
        )
    for d in dirs:
        if not d.startswith(SOURCE_DIR_PREFIX) or ".." in d.split("/"):
            raise Structural(
                f"source_dirs entry {d!r} is not under {SOURCE_DIR_PREFIX}. The STALE rule watches "
                f"the screen; a directory anywhere else is a watch that sees nothing."
            )
    reason = str(scope_doc.get("no_scope_reason", "")).strip()
    if not slice_id and len(reason) < MIN_NO_SCOPE_REASON:
        raise Structural(
            f"no slice is declared and no_scope_reason is {len(reason)} characters (minimum "
            f"{MIN_NO_SCOPE_REASON}). An empty G5 scope must be someone's written decision."
        )


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )


def head_commit() -> str:
    r = _git("rev-parse", "HEAD")
    if r.returncode != 0:
        raise Structural(f"git rev-parse HEAD failed: {r.stderr.strip()}")
    return r.stdout.strip()


def is_ancestor(deployed_head: str, head: str) -> bool:
    r = _git("merge-base", "--is-ancestor", deployed_head, head)
    if r.returncode == 0:
        return True
    if r.returncode == 1:
        return False
    raise Structural(
        f"git cannot resolve {deployed_head[:12]}: {r.stderr.strip()} — a shallow checkout cannot "
        f"answer the ancestor question; fetch full history (fetch-depth: 0) before running "
        f"this gate"
    )


def changed_under(deployed_head: str, head: str, source_dirs: list[str]) -> list[str]:
    """Files under the declared directories that moved after the walked build.

    **A directory that does not exist at HEAD is a refusal, not an empty diff.** ``git diff --
    <path matching nothing>`` exits 0 with no output, so a scope file naming a directory that is
    not there (a typo, or the laziest edit a builder can make) would report the screen unchanged
    while it was rewritten — the verifier's attack A4. The check is made HERE and not at
    declaration time because the directories are declared at the planning gate, before the screen
    exists; they must exist by the time a walk is being credited.
    """
    for d in source_dirs:
        probe = _git("ls-tree", "-d", head, "--", d.rstrip("/"))
        if probe.returncode != 0 or not probe.stdout.strip():
            raise Structural(
                f"declared source directory {d!r} does not exist at {head[:12]} — the STALE rule "
                f"would be watching nothing"
            )
    r = _git("diff", "--name-only", deployed_head, head, "--", *source_dirs)
    if r.returncode != 0:
        raise Structural(f"git diff {deployed_head[:12]}..{head[:12]} failed: {r.stderr.strip()}")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def close_reviews() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for p in sorted((ROOT / CLOSE_REVIEW_DIR).glob(CLOSE_REVIEW_GLOB)):
        m = _WAVE_NUM.search(p.name)
        if m:
            found.append((int(m.group(1)), p))
    if len(found) < G5_MIN_CLOSE_REVIEWS:
        raise Structural(
            f"found {len(found)} close reviews, floor is {G5_MIN_CLOSE_REVIEWS} — the discovery "
            f"glob has gone blind and this gate would report green having checked nothing"
        )
    return sorted(found)


def g5_close_errors(walked_ok: set[str], lines: dict[str, str]) -> list[str]:
    """From Wave 20 on, a close review's journey-coverage section is a required output.

    A listed line must exist and must have at least one WALKABLE ledger row by a roster member on
    a build in this commit's lineage. The ledger is append-only, so this is monotone: a line once
    walked stays walked in the close that claimed it, and a later edit of the line lapses the
    SLICE gate (which asks for the current hash), not the historical close (which recorded an act
    that happened).

    **What this does NOT check, stated so nobody cites it as if it did:** a close that OMITS a
    declared-but-unwalked line from its table passes. The scope file is single-slice and
    overwritten, so the gate cannot know what a whole wave's slices declared. The wave close's
    verifier lane checks the table against the roadmap's Journey-lines column for that wave; this
    is a P7 clause-b act bound to the close review, recorded here rather than left implied.
    """
    errors: list[str] = []
    for wave, path in close_reviews():
        if wave < G5_FROM_WAVE:
            continue
        text = path.read_text(encoding="utf-8")
        heads = list(_G5_HEADING_LINE.finditer(text))
        if not heads:
            errors.append(
                f"{path.name} closes wave {wave} and has no '{G5_HEADING}' section. Which journey "
                f"lines a wave made walkable is a required OUTPUT of its close, not a good "
                f"intention."
            )
            continue
        if len(heads) > 1:
            raise Structural(f"{path.name} has {len(heads)} '{G5_HEADING}' headings")
        body = text[heads[0].end() :]
        body = re.split(r"^## ", body, maxsplit=1, flags=re.M)[0]
        listed = _G5_TABLE_LINE.findall(body)
        if not listed:
            if G5_NONE_MARK not in body:
                errors.append(
                    f"{path.name}: the G5 section lists no journey line and does not say "
                    f"'{G5_NONE_MARK}'. An empty table is not a measurement."
                )
            elif len(" ".join(body.split())) - len(G5_NONE_MARK) < G5_MIN_NONE_REASON:
                errors.append(f"{path.name}: '{G5_NONE_MARK}' with no reason.")
            continue
        seen: set[str] = set()
        for line in listed:
            if line in seen:
                errors.append(f"{path.name}: {line} is listed twice in the G5 table")
            seen.add(line)
            if line not in lines:
                errors.append(
                    f"{path.name}: the G5 table claims {line}, which is not a journey line"
                )
            elif line not in walked_ok:
                errors.append(
                    f"{path.name}: the G5 table claims wave {wave} made {line} walkable and the "
                    f"ledger holds NO valid WALKABLE row for it — a claim without its act"
                )
    return errors


def main() -> int:
    try:
        lines = parse_lines(_read(JOURNEYS))
        roster = set(json.loads(_read(ROSTER))["adjudicators"])
        scope_doc = json.loads(_read(SCOPE))
        check_scope_declaration(scope_doc)
        entries = load_ledger()
        errors = validate_entries(entries, roster, lines)
        scope = [r for r in scope_doc.get("journey_lines", []) if r]
        source_dirs = [d for d in scope_doc.get("source_dirs", []) if d]

        # A WALKABLE row is "valid" for a slice when it is well-formed, current, on an ancestor
        # of HEAD, and not stale. The git questions are asked only when a row exists to ask about.
        walked_any: set[str] = set()
        current: set[str] = set()
        blocking: list[str] = []
        head = head_commit() if entries else ""
        for e in entries:
            line = str(e.get("line", ""))
            if e.get("verdict") != "WALKABLE" or line not in lines:
                continue
            if str(e.get("walked_by", "")).startswith("MODEL:") or e.get("walked_by") not in roster:
                continue
            dh = str(e.get("deployed_head", ""))
            if not _HEX.match(dh) or not is_ancestor(dh, head):
                # A walk on a build outside this lineage is a walk of a different product; it
                # counts for nothing here, not even for a close review's claim.
                continue
            walked_any.add(line)
            if e.get("line_hash") != lines[line]:
                continue
            if line in scope and changed_under(dh, head, source_dirs):
                continue
            current.add(line)

        for line in scope:
            if line not in lines:
                blocking.append(
                    f"{line} is in the slice scope and is not a journey line in {JOURNEYS}"
                )
            elif line not in walked_any:
                blocking.append(
                    f"{line} was declared by slice {scope_doc.get('slice')!r} and NOBODY has "
                    f"walked "
                    f"it WALKABLE on a deployed build. The screen is not accepted until a person "
                    f"names the decision it supports."
                )
            elif line not in current:
                blocking.append(
                    f"{line} was walked WALKABLE, and either its text changed since (the walk "
                    f"lapsed), the deployed build is not an ancestor of this commit, or a file "
                    f"under {source_dirs} changed after that build (STALE) — walk it again."
                )

        errors.extend(g5_close_errors(walked_any, lines))
    except (Structural, KeyError, json.JSONDecodeError) as exc:
        print(f"journey-walks STRUCTURAL FAILURE: {exc}", file=sys.stderr)
        return 2

    print(f"journey lines parsed       : {len(lines)}")
    print(f"ledger rows                : {len(entries)}")
    print(f"  lines walked WALKABLE    : {len(walked_any)}")
    print(f"  current for this commit  : {len(current)}")
    print(
        f"slice scope                : {len(scope)} — "
        f"{scope_doc.get('slice') or 'no slice declared'}"
    )
    print(f"  blocking                 : {len(blocking)}")

    if errors or blocking:
        print("\njourney-walks FAILED:")
        for e in errors + blocking:
            print(f"  - {e}")
        return 1

    print(
        "\njourney-walks passed. This proves a person walked the declared lines and named a "
        "decision, not that the product is good."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
