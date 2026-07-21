#!/usr/bin/env python3
"""Dump the FastAPI OpenAPI schema to a committed file (FE-2, OD-FE-2-A).

Offline — imports the app and calls ``app.openapi()``; NO running server needed. Deterministic
output (``sort_keys=True``, trailing newline) so the committed ``openapi.json`` diff is minimal and
the FE-2 drift-check (regenerate + ``git diff --exit-code``) is stable. The generated
``api-types.d.ts`` is produced FROM this file by ``openapi-typescript`` (see the frontend
``gen:api`` script); this Python step is the schema half of that pipeline.

Usage: ``python scripts/dump_openapi.py`` → writes ``apps/frontend/openapi.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from irp_backend.main import app

_OUT = Path(__file__).resolve().parent.parent / "apps" / "frontend" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    _OUT.write_text(json.dumps(schema, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {_OUT} ({len(schema.get('paths', {}))} paths, "
        f"{len(schema.get('components', {}).get('schemas', {}))} schemas)"
    )


if __name__ == "__main__":
    main()
