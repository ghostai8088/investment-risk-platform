"""The ONE governed-write error dispatcher, shared across API router modules.

Hoisted from ``api/marketdata.py`` at CC-1 (the sanctioned mechanical fence exception,
OD-CC-1 scope note): the helper was module-private there while the non-marketdata capture
routers re-implemented the MD-H1 pattern inline; the clean-code standing bar takes ONE
shared implementation over a third copy. ``marketdata.py`` redirects by import — behavior
byte-identical (its endpoint suites are the golden).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from irp_shared.db.integrity import is_unique_violation


def raise_mapped_write(
    db: Session, exc: Exception, errors: dict[type[Exception], tuple[int, str]]
) -> None:
    """Roll the whole unit back (CTRL-032), then map the exception to its family
    (status, detail).

    An ``IntegrityError`` maps to the family's 409 duplicate detail ONLY when it is a real
    unique-constraint collision (the MD-H1 review fold): any OTHER integrity failure inside
    the governed unit — FK / NOT NULL / RLS ``WITH CHECK`` — is RE-RAISED (fail-loud 500),
    never mislabeled "already exists".
    """
    db.rollback()  # whole-unit rollback (CTRL-032) before mapping
    if isinstance(exc, IntegrityError) and not is_unique_violation(exc):
        raise exc  # NOT the duplicate class — a real data-integrity bug must stay a loud 500
    code, detail = errors[type(exc)]
    raise HTTPException(status_code=code, detail=detail) from None
