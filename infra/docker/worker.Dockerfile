# Worker image — scaffold. Aligns to AD-003 / AD-006 / AD-010.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/shared-python ./packages/shared-python
COPY apps/worker ./apps/worker

# psycopg is EXPLICIT here (RPT-2): no pyproject declares it, the venv carries it via dev
# requirements, and this image shipped WITHOUT it from DEP-1 until the first HTTP smoke of
# a governed read 500'd with ModuleNotFoundError — the deployed service had never once
# reached its database, and nothing probed a DB-touching path until remit I6 did.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./packages/shared-python ./apps/worker "psycopg[binary]>=3.1"

# CAD-1: the supervisor drives the per-tenant operational tick on a cadence (IRP_TENANT_IDS /
# IRP_TICK_INTERVAL_SECONDS). An external scheduler can invoke `python -m irp_worker.scheduler
# --tenant <id>` once per tenant instead (OQ-1=A keeps both).
CMD ["python", "-m", "irp_worker.supervisor"]
