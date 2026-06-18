# Backend (FastAPI) image — scaffold. Aligns to AD-003 (Python 3.12+) and AD-010.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/shared-python ./packages/shared-python
COPY apps/backend ./apps/backend

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./packages/shared-python ./apps/backend "uvicorn[standard]>=0.30"

EXPOSE 8000

# No secrets baked in; configuration comes from the environment (BR-10).
CMD ["uvicorn", "irp_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
