# Worker image — scaffold. Aligns to AD-003 / AD-006 / AD-010.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/shared-python ./packages/shared-python
COPY apps/worker ./apps/worker

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./packages/shared-python ./apps/worker

# No calculations yet; this is a heartbeat entrypoint.
CMD ["python", "-m", "irp_worker.main"]
