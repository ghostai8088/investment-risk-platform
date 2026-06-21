"""Worker job entry points.

Tenant-scoped jobs run under tenant context (``app.current_tenant``, AD-016) so PostgreSQL RLS
admits only the job's tenant. Worker *business* paths never use the BYPASSRLS ops role — that is
reserved for controlled cross-tenant operational tasks (AD-015).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session, sessionmaker

from irp_shared.db.tenant import run_in_tenant

T = TypeVar("T")


def run_tenant_job(
    session_factory: sessionmaker[Session], tenant_id: str, work: Callable[[Session], T]
) -> T:
    """Run a unit of work for one tenant under tenant-scoped RLS context, then commit."""
    return run_in_tenant(session_factory, tenant_id, work)
