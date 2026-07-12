"""MD-H1 annex item 3: the audit-action vocabulary is CONSTANTS, never raw string literals.

The PA-0 incident: a proxy-mapping correction emitted ``action="update"`` where the sibling FR
binders emit ``"correct"`` — an ``action=="correct"`` restatement query would silently have missed
proxy restatements, and nothing but human review could catch the drift. This AST conformance test
makes the convention structural: any NEW ``action="..."`` raw literal in ``src/irp_shared`` fails
the build (use ``irp_shared.audit.actions``). The FROZEN ``audit/service.py`` takes ``action`` as an
opaque parameter and defines no literal itself.
"""

from __future__ import annotations

import ast
import pathlib

from irp_shared.audit import actions

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "irp_shared"


def test_vocabulary_values_are_the_taxonomy_strings() -> None:
    # pin the wire values — renaming a constant must not silently change the emitted string.
    assert actions.ACTION_CREATE == "create"
    assert actions.ACTION_UPDATE == "update"
    assert actions.ACTION_CORRECT == "correct"
    assert actions.ACTION_STATUS_CHANGE == "status_change"
    assert actions.ACTION_VALIDATE == "validate"
    assert actions.ACTION_REVERSE == "reverse"
    assert actions.ACTION_RECORD == "record"
    assert actions.ACTION_GRANT == "grant"


def test_no_raw_action_literals_in_source() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        if path.name == "actions.py":
            continue  # the canonical vocabulary definitions
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "action"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}={kw.value.value!r}")
    assert (
        not offenders
    ), f"raw action= string literals (use irp_shared.audit.actions constants): {offenders}"
