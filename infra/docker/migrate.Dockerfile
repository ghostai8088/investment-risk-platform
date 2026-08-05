# Deployment prepare image — migrate + seed (DEP-1, Wave-15).
#
# WHY A FOURTH IMAGE. The backend image deliberately carries neither `alembic` nor `migrations/`:
# a long-running API process has no business shipping the ability to rewrite its own schema, and
# the .dockerignore added at DEP-1 keeps migration and test material out of runtime images on
# purpose. But something has to apply migrations, and before DEP-1 *nothing in the stack could* —
# `docker compose up` produced a backend pointed at an empty database, and CI never ran the stack
# so nothing caught it (planning fact F1).
#
# This image exists for exactly one one-shot job and then exits. It is not a runtime service.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/shared-python ./packages/shared-python
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# `[deploy]` pulls alembic — the optional extra declared for exactly this path. psycopg is the
# driver the DATABASE_URL names (postgresql+psycopg://).
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir "./packages/shared-python[deploy]" "psycopg[binary]>=3.1"

# Migrate to head, then seed the SYSTEM reference slice. BOTH halves are idempotent, so this
# container can be re-run after a partial failure without manual recovery — the property that
# made `seed_system_reference` idempotent at DEP-1 (OQ-W15P-4) worth paying for.
CMD ["python", "-m", "irp_shared.deploy.prepare"]
