# Backend (FastAPI) image — scaffold. Aligns to AD-003 (Python 3.12+) and AD-010.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/shared-python ./packages/shared-python
COPY apps/backend ./apps/backend

# psycopg is EXPLICIT here (RPT-2): no pyproject declares it, the venv carries it via dev
# requirements, and this image shipped WITHOUT it from DEP-1 until the first HTTP smoke of
# a governed read 500'd with ModuleNotFoundError — the deployed service had never once
# reached its database, and nothing probed a DB-touching path until remit I6 did.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./packages/shared-python ./apps/backend "uvicorn[standard]>=0.30" "psycopg[binary]>=3.1"

EXPOSE 8000

# No secrets baked in; configuration comes from the environment (BR-10).
CMD ["uvicorn", "irp_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
