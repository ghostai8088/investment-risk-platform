"""THE migration-head pin — the one place the head literal lives (process fold, 2026-08-09).

Until this fold, twenty-one test files each asserted ``get_current_head() == "<head>"`` — the same
global fact hand-mirrored twenty-one times, which meant every migration bumped twenty-one files or
went red twenty-one ways (it did both: three stale-pin sweeps in the ONBOARD-1b build alone, and
the Wave-16 close's "22 stale pins in one fold" finding that made this a named decision). The
per-file CHAIN-POSITION assertions stay where they were — each slice's file still proves its own
revision's place in the walk, which IS local knowledge. Only the head equality moved here.

Moving the head is a CONSCIOUS act: a new migration edits exactly this line, and nothing else.
The single-head property (no forked heads) is asserted separately below because a fork would make
``get_current_head()`` raise — better to say so in words.
"""

from __future__ import annotations

from pathlib import Path

from alembic.script import ScriptDirectory

#: The platform's current migration head. A new migration updates THIS LINE ONLY.
EXPECTED_MIGRATION_HEAD = "0075_bind_batch_to_mapping"  # W19-S3a: the INGEST-1 mapping spine


def _script() -> ScriptDirectory:
    root = Path(__file__).resolve().parents[3]
    return ScriptDirectory(str(root / "migrations"))


def test_the_migration_chain_has_exactly_one_head() -> None:
    heads = _script().get_heads()
    assert len(heads) == 1, f"the migration chain FORKED: {heads}"


def test_the_head_is_the_declared_one() -> None:
    assert _script().get_current_head() == EXPECTED_MIGRATION_HEAD
