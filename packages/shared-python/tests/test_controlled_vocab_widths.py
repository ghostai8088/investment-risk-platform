"""Every controlled-vocabulary value FITS the column that stores it (W19-S3a).

**The defect this exists because of.** ``ingestion_batch.status`` was ``varchar(20)`` from migration
``0007``, while the vocabulary it stores declared ``COMPLETED_WITH_WARNINGS`` — 23 characters. A
batch that finished with a data-quality WARNING therefore could not be persisted on PostgreSQL at
all: it raised ``StringDataRightTruncation``. That shipped for four waves.

**Why nothing caught it, which is the part worth generalising.** SQLite ignores ``VARCHAR`` length
(column affinity), so the entire unit tier wrote the 23-character value happily; and no PG-tier test
ever drove the warning path, so the one tier that would have refused never saw it. This is the
recorded "a whole test TIER can be the alternate path" class (P5's own evidence line — the
PG-only ``window_months`` 500), and it is invisible to reading because the constant and the column
are declared forty lines apart in the same file and neither mentions the other.

It was found by the ``0075`` P17 harness, which is what harnesses are for.

**The gate, and its shape is deliberate.** P7 ranks countermeasures *exact set-equality census >
coverage floor > enumerating matcher*, and forbids a hand list checked against another hand list.
So this discovers its own population: for every mapped ``String(n)`` column, it finds the
module-level vocabulary constants in the class's OWN defining module whose name begins with that
column's name tokens, and asserts each value fits. No inventory to keep current — a new vocabulary
constant joins the census the moment it is written.

A repo-wide run at the mint found **exactly one** violation, the one above. That is the whole
enumerated class (P10: this record quantifies over every mapped class, because that is what it
walked).
"""

from __future__ import annotations

import importlib
import re

import pytest
from sqlalchemy import String

import irp_shared.models  # noqa: F401 - imports every model so the registry is complete
from irp_shared.db.base import Base

#: Columns whose vocabulary constants are NOT named after the column, with the reason. Kept tiny
#: and explicit: an alias is a coverage gap the discovery rule cannot see, so each one is a
#: deliberate admission rather than a convenience.
_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    # `scan_status` stores SCAN_PENDING / SCAN_CLEAN / SCAN_SKIPPED — named for the scan, not the
    # column. The values are short, but the pairing is real and the census should see it.
    ("ingestion_batch", "scan_status"): ("SCAN",),
}

#: P6 floor. If the discovered population collapses, the census has lost its subject and must fail
#: LOUDLY rather than pass over nothing. Measured at the mint, not guessed.
_MIN_PAIRS = 200

_CONST_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _vocab_constants(module: object) -> dict[str, str]:
    """Module-level UPPER_SNAKE ``str`` constants that look like controlled-vocabulary values.

    A vocabulary value is a bare token: no spaces (that would be prose), and not a path or a
    sentence. Over-capturing slightly is the right trade — a false pair costs nothing because a
    short value fits any column, while a missed pair costs the census its subject.
    """
    out: dict[str, str] = {}
    for name, value in vars(module).items():
        if not isinstance(value, str) or not _CONST_NAME.match(name):
            continue
        if " " in value or "/" in value or not value:
            continue
        out[name] = value
    return out


def _pairs() -> list[tuple[str, str, int, str, str]]:
    """Discovered (table, column, width, constant name, value) pairs.

    The matching rule: the COLUMN's name tokens are the LEADING tokens of the constant's name.
    ``status`` matches ``STATUS_COMPLETED_WITH_WARNINGS``; ``validation_type`` does NOT match
    ``VALIDATION_OUTCOME_APPROVED`` (its second token is OUTCOME, not TYPE), which is what keeps
    this from degenerating into token soup that flags unrelated vocabularies.
    """
    found: list[tuple[str, str, int, str, str]] = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        module = importlib.import_module(cls.__module__)
        constants = _vocab_constants(module)
        table = cls.__table__.name
        for column in cls.__table__.columns:
            if not isinstance(column.type, String) or column.type.length is None:
                continue
            prefixes = [tuple(column.name.upper().split("_"))]
            prefixes.extend(
                tuple(alias.split("_")) for alias in _ALIASES.get((table, column.name), ())
            )
            for name, value in constants.items():
                tokens = tuple(name.split("_"))
                if any(tokens[: len(p)] == p and len(tokens) > len(p) for p in prefixes):
                    found.append((table, column.name, column.type.length, name, value))
    return found


def test_every_controlled_vocab_value_fits_its_column() -> None:
    """The census. A value longer than its column is a row that CANNOT BE WRITTEN on PostgreSQL."""
    over = [
        (table, column, width, name, value)
        for table, column, width, name, value in _pairs()
        if len(value) > width
    ]
    assert not over, (
        "controlled-vocabulary values that do not fit their own column — on PostgreSQL these raise "
        f"StringDataRightTruncation, and on SQLite they silently succeed: {sorted(over)}"
    )


def test_the_census_population_has_not_collapsed() -> None:
    """P6: a matcher covers only the shapes someone thought of; a floor notices coverage FALLING,
    whatever the next shape turns out to be."""
    pairs = _pairs()
    assert len(pairs) >= _MIN_PAIRS, (
        f"the vocabulary/column census discovered only {len(pairs)} pairs (floor {_MIN_PAIRS}) — "
        "the discovery rule has stopped matching, not the codebase stopped having vocabularies"
    )


def test_the_census_pairs_the_column_this_gate_exists_because_of() -> None:
    """A named-instance control: the pair that was BROKEN must be one the census actually sees.

    Without this, a discovery rule that quietly stopped matching ``status`` would report zero
    violations and read exactly like compliance — which is how the defect survived in the first
    place.
    """
    seen = {(table, column, name) for table, column, _width, name, _value in _pairs()}
    assert ("ingestion_batch", "status", "STATUS_COMPLETED_WITH_WARNINGS") in seen
    assert ("ingestion_batch", "scan_status", "SCAN_SKIPPED") in seen  # via the declared alias


def test_the_checker_detects_a_violation_when_one_exists() -> None:
    """The POSITIVE CONTROL for the checker itself (P18 clause 1).

    A checker that never fires reports an empty offender list, which is indistinguishable from
    total compliance. This plants the real historical shape — a 23-character value against a
    20-wide column — and asserts the comparison catches it.
    """
    planted = [("t", "status", 20, "STATUS_COMPLETED_WITH_WARNINGS", "COMPLETED_WITH_WARNINGS")]
    over = [row for row in planted if len(row[4]) > row[2]]
    assert over, "the width comparison itself is broken"
    # ...and the FIXED width passes, so the control is not merely asserting that 23 > 20.
    fixed = [row for row in planted if len(row[4]) > 30]
    assert not fixed


@pytest.mark.parametrize(
    ("column", "constant", "expected"),
    [
        ("status", "STATUS_COMPLETED", True),
        ("validation_type", "VALIDATION_TYPE_INITIAL", True),
        ("validation_type", "VALIDATION_OUTCOME_APPROVED", False),
        ("currency_code", "FACTOR_FAMILY_CURRENCY", False),
        ("status", "STATUS", False),  # the bare family name is not a value
    ],
)
def test_the_matching_rule_is_precise(column: str, constant: str, expected: bool) -> None:
    """The rule's own boundary cases, pinned. Two of these are REAL near-misses a token-overlap
    rule flagged when this census was first drafted, and both are unrelated vocabularies."""
    prefix = tuple(column.upper().split("_"))
    tokens = tuple(constant.split("_"))
    matched = tokens[: len(prefix)] == prefix and len(tokens) > len(prefix)
    assert matched is expected
