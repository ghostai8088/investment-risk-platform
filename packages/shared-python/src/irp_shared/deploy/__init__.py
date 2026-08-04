"""Deployment-time preparation (DEP-1, Wave-15).

The one-shot step a deployed stack runs BEFORE the backend and worker start: apply migrations, then
seed the SYSTEM reference slice. Both halves are idempotent, so re-running the step after a partial
failure is safe — which is the property a deploy script needs and the reason
``seed_system_reference`` was made idempotent at DEP-1 (OQ-W15P-4).
"""

from irp_shared.deploy.prepare import prepare_database

__all__ = ["prepare_database"]
