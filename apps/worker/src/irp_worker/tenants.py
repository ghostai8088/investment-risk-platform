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
    """Parse a comma-separated ``IRP_TENANT_IDS`` value into canonical tenant ids — STRICTLY.

    **The skip-a-bad-entry behavior (CAD-1 OQ-3=A) is SUPERSEDED at REPRO-2, ratified 2026-08-10,
    and the reason is a consequence that only appeared once the list became a RESTRICTION rather
    than the tenant set itself.** Under config-as-the-set, dropping one fat-fingered id left the
    other tenants ticking and an all-bad list fell through to the caller's empty-list refusal — a
    bounded loss. Under registry discovery an empty parse means "no restriction", so a single
    typo would silently widen the filter to EVERY tenant: the looks-configured-but-isn't state
    CAD-1 FOLD-2 ratified against, inverted into over-ticking. A typo must be a refusal, never a
    widening.

    So: blank entries are ignored (a trailing comma is not a typo), and any NON-BLANK entry that
    is not a canonical UUID raises ``TenantIdError``. ``on_bad`` is still called first, so the
    offending entry is named in the log before the process refuses. Returns canonical ids in input
    order, de-duplicated (a repeated tenant would otherwise tick twice per cycle).

    An empty result now means exactly one thing — **the filter is UNSET** — which the caller reads
    as "no restriction", not as "fail closed".
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
            raise
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out
