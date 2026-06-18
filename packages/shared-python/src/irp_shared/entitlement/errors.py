"""Entitlement errors."""

from __future__ import annotations


class PermissionDenied(Exception):
    """Raised when a principal lacks a required permission or violates tenant isolation."""

    def __init__(self, permission_code: str, tenant_id: str) -> None:
        super().__init__(f"permission denied: {permission_code} (tenant {tenant_id})")
        self.permission_code = permission_code
        self.tenant_id = tenant_id
