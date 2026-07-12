"""MD-H1 guardrail (annex item 1): a REPO-WIDE PostgreSQL identifier-length sweep.

PostgreSQL truncates any identifier (table / index / constraint / FK name) to 63 bytes, silently
merging two names that share a 63-char prefix — a class that only fails on real Postgres, never on
SQLite (the P3-8 68-char FK incident, caught by local PG, not the SQLite suite). Per-migration
``_IDENTIFIERS`` asserts guard one file at a time and are easy to forget on the next migration; this
one test sweeps EVERY migration's AST for over-long snake_case identifier literals, so the guarantee
is structural, not per-file discipline.

The filter (a pure ``[a-z_][a-z0-9_]*`` string) matches table/index/constraint/FK names and excludes
docstrings (spaces), methodology paths (``/``/``.``), and vocab labels (uppercase) — the things that
are legitimately long but are NOT database identifiers.
"""

from __future__ import annotations

import ast
import pathlib
import re

_PG_IDENTIFIER_LIMIT = 63
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_MIGRATIONS = pathlib.Path(__file__).resolve().parents[3] / "migrations" / "versions"


#: Runtime-built identifier prefixes the repo actually uses (review fold: the sweep's Constant-only
#: walk is blind to f-strings, and every RLS migration builds f"tenant_isolation_{table}" policy
#: names). For each declared table name, every prefix+table must ALSO fit the PG limit.
_BUILT_IDENTIFIER_PREFIXES = ("tenant_isolation_",)


def test_no_migration_identifier_exceeds_postgres_limit() -> None:
    offenders: list[tuple[str, str]] = []
    for path in sorted(_MIGRATIONS.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and len(node.value) > _PG_IDENTIFIER_LIMIT
                and _IDENTIFIER.match(node.value)
            ):
                offenders.append((path.name, node.value))
    assert not offenders, (
        "migration identifiers exceeding PostgreSQL's 63-char limit (silently truncate/collide "
        f"on real Postgres): {offenders}"
    )


def test_built_policy_names_fit_postgres_limit() -> None:
    """Review fold (finder 3): f-string-BUILT identifiers are invisible to the Constant sweep.

    The RLS migrations mint ``tenant_isolation_<table>`` policy names at runtime; a table name of
    47+ chars silently truncates its policy name on PG. Check every ``op.create_table`` name
    against every known built-identifier prefix.
    """
    offenders: list[tuple[str, str, int]] = []
    for path in sorted(_MIGRATIONS.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                table = node.args[0].value
                for prefix in _BUILT_IDENTIFIER_PREFIXES:
                    built = prefix + table
                    if len(built) > _PG_IDENTIFIER_LIMIT:
                        offenders.append((path.name, built, len(built)))
    assert not offenders, f"runtime-built identifiers exceeding the PG 63-char limit: {offenders}"


def test_migrations_directory_is_discovered() -> None:
    # Guard the guard: a wrong parents[] depth would make the sweep vacuously pass on zero files.
    assert _MIGRATIONS.is_dir()
    assert any(_MIGRATIONS.glob("*.py")), "no migration files found — the sweep would be vacuous"
