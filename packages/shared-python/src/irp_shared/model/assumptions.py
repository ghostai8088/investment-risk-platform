"""Shared model-assumption parse-back primitives (RD-2 dedup, 2026-07-13).

Every governed model that carries a DECLARED identity parameter (the Geltner alpha, the VaR
z-scores/confidence, the covariance window, the Kupiec alpha) parsed it back from the version's
``model_assumption`` rows with the SAME skeleton: load every assumption for the version, extract the
SOLE well-formed value for a prefix, refuse fail-closed — never a bare parse crash (the P3-4 lesson
that a generically-minted version can stamp anything under the same permission). That skeleton had
accumulated to five ``declared_*`` functions sharing five identical ``select(ModelAssumption)``
loads, two byte-identical ``_single`` helpers, and three inline sole-value extractions, meeting the
P3-4-R0 3rd-consumer tipping rule. This module owns the load + the sole-value extraction; each
family keeps its OWN type conversion, domain check, and cross-field validation.
"""

from __future__ import annotations

from collections.abc import Callable
from re import Pattern

from sqlalchemy import select
from sqlalchemy.orm import Session

from irp_shared.model.models import ModelAssumption, ModelVersion


def load_assumption_texts(session: Session, version: ModelVersion) -> list[str]:
    """Load every ``assumption_text`` declared for ``version`` — the one shared
    ``select(ModelAssumption)`` load the parse-backs used to each carry verbatim."""
    rows = (
        session.execute(
            select(ModelAssumption).where(ModelAssumption.model_version_id == version.id)
        )
        .scalars()
        .all()
    )
    return [r.assumption_text for r in rows]


def sole_declared(texts: list[str], prefix: str) -> str | None:
    """Return the SOLE value declared under ``prefix`` (the prefix stripped), or ``None`` when it is
    absent or ambiguous (zero or more than one match). Composite parse-backs cross-validate several
    before refusing, so this returns ``None`` rather than raising (the former ``_single``)."""
    found = [t[len(prefix) :] for t in texts if t.startswith(prefix)]
    return found[0] if len(found) == 1 else None


def require_declared(
    texts: list[str],
    prefix: str,
    *,
    pattern: Pattern[str],
    on_invalid: Callable[[], Exception],
) -> str:
    """Return the sole ``prefix`` value when EXACTLY one exists AND it matches ``pattern``; else
    raise ``on_invalid()``. Single-parameter parse-backs use this to fail closed (422) rather than a
    bare parse crash. ``on_invalid`` is the injectable error factory — the RD-1 ``not_visible=`` /
    ``error=`` precedent (``assert_portfolio_in_tenant(error=…)``)."""
    value = sole_declared(texts, prefix)
    if value is None or not pattern.fullmatch(value):
        raise on_invalid()
    return value
