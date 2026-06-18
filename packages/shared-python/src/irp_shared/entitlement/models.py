"""Entitlement ORM models (minimal RBAC foundation).

Permissions are global codes; grants are tenant-scoped through roles and effective-dated
user-role assignments. Users/roles/permissions are effective-dated reference/config (EV);
``user_role`` carries the active window used by deny-by-default checks.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from irp_shared.db.base import Base
from irp_shared.db.mixins import (
    EffectiveDatedMixin,
    PrimaryKeyMixin,
    TenantMixin,
    TimestampMixin,
)
from irp_shared.temporal import TemporalClass


class AppUser(PrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "app_user"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_subject", name="uq_app_user_tenant_id"),
    )

    # OIDC subject placeholder — real identity binding arrives with SSO (AD-007).
    external_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Role(PrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "role"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_role_tenant_id"),)

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Permission(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permission"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (UniqueConstraint("code", name="uq_permission_code"),)

    code: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RolePermission(PrimaryKeyMixin, Base):
    __tablename__ = "role_permission"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission_role_id"),
    )

    role_id: Mapped[str] = mapped_column(ForeignKey("role.id"), nullable=False, index=True)
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permission.id"), nullable=False, index=True
    )


class UserRole(PrimaryKeyMixin, TenantMixin, EffectiveDatedMixin, Base):
    __tablename__ = "user_role"
    __temporal_class__ = TemporalClass.EFFECTIVE_DATED

    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("role.id"), nullable=False, index=True)
