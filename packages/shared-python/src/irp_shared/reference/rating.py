"""Rating-scale reference binder (ENT-007 **taxonomy only**, EV). Head + grade children.

Grades are written through the parent ``create_rating_scale`` and fold into its single
``REFERENCE.CREATE`` event. **Taxonomy only** — there are NO rating ASSIGNMENTS here (the FR half of
ENT-007: rating-to-instrument/issuer linkage, as-of, outlook, watch), and no ``reference.rating.*``
permission. ``rank`` is enforced unique per scale so the scale is deterministically orderable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from irp_shared.reference.models import RatingGrade, RatingScale
from irp_shared.reference.service import (
    ENTITY_RATING_SCALE,
    ReferenceActor,
    record_reference_create,
    record_reference_update,
)

#: Mutable head attributes ``update_rating_scale`` will diff/apply.
_UPDATABLE = ("name", "agency", "is_active")


@dataclass(frozen=True)
class GradeSpec:
    """One grade of a rating scale (``rank`` is the ordinal; lower = stronger by convention)."""

    code: str
    rank: int
    description: str | None = None


def create_rating_scale(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    actor: ReferenceActor,
    agency: str | None = None,
    is_active: bool = True,
    grades: Sequence[GradeSpec] = (),
) -> RatingScale:
    """Create a ``rating_scale`` head + its ``rating_grade`` children (governed: one MANUAL-source
    origin edge + one ``REFERENCE.CREATE``; children fold in). Taxonomy only — no assignments."""
    scale = RatingScale(
        tenant_id=str(tenant_id),
        code=code,
        name=name,
        agency=agency,
        is_active=is_active,
        record_version=1,
    )
    session.add(scale)
    session.flush()

    for spec in grades:
        session.add(
            RatingGrade(
                tenant_id=scale.tenant_id,  # server-stamped from the resolved parent
                rating_scale_id=scale.id,
                code=spec.code,
                rank=spec.rank,
                description=spec.description,
                record_version=1,
            )
        )
    if grades:
        session.flush()

    record_reference_create(
        session,
        entity=scale,
        entity_type=ENTITY_RATING_SCALE,
        after_value={
            "code": code,
            "name": name,
            "is_active": is_active,
            "agency": agency,
            "grade_count": len(grades),
        },
        actor=actor,
    )
    return scale


def update_rating_scale(
    session: Session,
    scale: RatingScale,
    *,
    actor: ReferenceActor,
    **changes: Any,
) -> RatingScale:
    """Apply mutable head changes (effective-dated supersede), bump ``record_version``, emit
    ``REFERENCE.UPDATE``. Head attributes only — grade children are not patched here (§7)."""
    unknown = set(changes) - set(_UPDATABLE)
    if unknown:
        raise ValueError(f"non-updatable rating_scale attributes: {sorted(unknown)}")

    before = {key: getattr(scale, key) for key in changes}
    for key, value in changes.items():
        setattr(scale, key, value)
    scale.record_version += 1
    session.flush()
    record_reference_update(
        session,
        entity=scale,
        entity_type=ENTITY_RATING_SCALE,
        before_value=before,
        after_value={key: getattr(scale, key) for key in changes},
        actor=actor,
    )
    return scale
