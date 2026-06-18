"""Every foundation model must declare a valid temporal class (BR-19)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from irp_shared.models import Base
from irp_shared.temporal import TemporalClass


def _mapped_classes() -> list[type]:
    return [mapper.class_ for mapper in Base.registry.mappers]


def test_every_model_declares_a_temporal_class() -> None:
    classes = _mapped_classes()
    assert classes, "expected at least one mapped model"
    for cls in classes:
        temporal_class = getattr(cls, "__temporal_class__", None)
        assert isinstance(
            temporal_class, TemporalClass
        ), f"{cls.__name__} missing __temporal_class__"


def test_tenant_scoped_models_have_tenant_id(session: Session) -> None:
    # Foundation invariant: tenant-scoped tables carry tenant_id (BR-17).
    for cls in _mapped_classes():
        if cls.__name__ in {
            "AuditEvent",
            "AuditCheckpoint",
            "CalculationRun",
            "AppUser",
            "Role",
            "UserRole",
        }:
            assert "tenant_id" in cls.__table__.columns, f"{cls.__name__} must have tenant_id"
