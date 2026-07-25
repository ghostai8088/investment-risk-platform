# Worker image — scaffold. Aligns to AD-003 / AD-006 / AD-010.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/shared-python ./packages/shared-python
COPY apps/worker ./apps/worker

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./packages/shared-python ./apps/worker

# CAD-1: the supervisor drives the per-tenant operational tick on a cadence (IRP_TENANT_IDS /
# IRP_TICK_INTERVAL_SECONDS). An external scheduler can invoke `python -m irp_worker.scheduler
# --tenant <id>` once per tenant instead (OQ-1=A keeps both).
CMD ["python", "-m", "irp_worker.supervisor"]
