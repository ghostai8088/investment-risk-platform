"""Tenant-id canonicalization for the worker boundary (the OQ-a fail-open fix).

The worker arms the RLS GUC (``app.current_tenant``) from an EXTERNAL string — a CLI ``--tenant``
arg or an ``IRP_TENANT_IDS`` env entry. The RLS policy compares ``tenant_id::text =
current_setting('app.current_tenant', true)``, and ``tenant_id`` renders as a lowercase-hyphenated
UUID. A non-canonical UUID (uppercase, braces, urn form) would therefore match NOTHING — the tick
would run RLS-armed against an id that hides every row and silently do no work (the **SSO-1 bug's
second instance**, a fail-*open*). So every tenant id is canonicalized to ``str(uuid.UUID(x))``
BEFORE it reaches ``persistent_tenant_context`` — mirroring the backend's ``deps.py`` boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable


class TenantIdError(ValueError):
    """A worker tenant id that is not a canonical UUID (fail closed — never arm RLS from it)."""


def canonical_tenant_id(raw: str) -> str:
    """Return the canonical lowercase-hyphenated UUID string for ``raw``; raise ``TenantIdError``
    if it is not a UUID. Arming RLS from a non-canonical string silently RLS-hides every row."""
    try:
        return str(uuid.UUID(str(raw).strip()))
    except (ValueError, AttributeError, TypeError) as exc:
        raise TenantIdError(f"not a canonical tenant UUID: {raw!r}") from exc


def parse_tenant_ids(
    raw_csv: str | None, *, on_bad: Callable[[str, TenantIdError], None] | None = None
) -> list[str]:
    """Parse a comma-separated ``IRP_TENANT_IDS`` value into canonical tenant ids.

    Blank entries are ignored. A malformed entry is **skipped** (OQ-3=A: one fat-fingered id must
    not take the whole engine down) and reported via ``on_bad`` if given — the loser is dropped, the
    valid tenants remain. Returns the canonical ids in input order, de-duplicated (a repeated tenant
    would otherwise tick twice per cycle). An EMPTY result is the caller's to treat as fail-closed.
    """
    out: list[str] = []
    seen: set[str] = set()
    for entry in (raw_csv or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            canonical = canonical_tenant_id(entry)
        except TenantIdError as exc:
            if on_bad is not None:
                on_bad(entry, exc)
            continue
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out
