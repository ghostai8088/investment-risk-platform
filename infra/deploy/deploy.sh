#!/usr/bin/env bash
#
# DEP-1 (Wave-15, OQ-W15P-3=a): ONE scripted deploy to a local-but-real target.
#
# "Local-but-real" is the ratified target and it is chosen deliberately: it costs nothing, it is
# NOT internet-facing, and so it does NOT fire RTM-P9's constraint that the dev-header shim be
# replaced before anything internet-facing. What it must still buy is the thing the whole slice is
# for — a genuine PROCESS BOUNDARY. So this script:
#
#   * builds the images from source (never reuses a local tag),
#   * brings up a stack on its OWN project name and OWN volume — it never touches `irp_pg_local`,
#     the development container, so the deploy cannot accidentally succeed on preexisting state,
#   * starts from an EMPTY database and migrates + seeds through the governed prepare step,
#   * and VERIFIES BY REACHING THE RUNNING API — not by this script exiting 0.
#
# That last point is the one that matters. A deploy script that reports success because its last
# command returned 0 is the same class of claim this project spent Wave 14 learning to distrust:
# it asserts the deployment happened rather than demonstrating the deployment works.
#
# Usage:  ./infra/deploy/deploy.sh [--keep]
#         --keep   leave the stack running afterwards (default: tear down, including volumes)

set -euo pipefail

PROJECT="irp-dep1"
COMPOSE="docker compose -p ${PROJECT}"

# Publish the deployed database on a DISTINCT host port. The first execution of this script
# failed with "Bind for 0.0.0.0:5432 failed: port is already allocated" — the development
# container `irp_pg_local` holds 5432. A deploy that demands you stop your dev database is not
# a deploy, and this collision is invisible until something actually starts the stack.
export POSTGRES_PUBLISH_PORT="${POSTGRES_PUBLISH_PORT:-55432}"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

log() { printf '\n=== %s\n' "$*"; }

cleanup() {
  if [ "$KEEP" -eq 0 ]; then
    log "tearing down (volumes included — a deploy that leaves state behind cannot be re-proven)"
    $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  else
    log "stack left running (--keep). Tear down with: ${COMPOSE} down -v"
  fi
}
trap cleanup EXIT

# A DEPLOY MUST NOT INHERIT A DEVELOPER'S LOCAL STATE. The second execution of this script failed
# exactly there: the repo's `.env` predates `.env.example`'s AUTH_MODE line, `auth_mode` defaults to
# 'oidc', and the backend correctly fail-closed with "auth_mode='oidc' requires OIDC_ISSUER". The
# original version of this script only copied the example when .env was ABSENT, so a stale developer
# env produced a silently broken deploy — the deployment equivalent of testing against a dirty
# database.
#
# So the deploy generates its OWN env file from the checked-in example, every run, and never reads
# `.env`. That is what makes the run reproducible on a machine that has never developed here.
DEPLOY_ENV="infra/deploy/.env.deploy"
log "generating a fresh deploy env from .env.example (never reusing a developer .env)"
cp .env.example "$DEPLOY_ENV"
export IRP_ENV_FILE="$DEPLOY_ENV"
COMPOSE="docker compose -p ${PROJECT} --env-file ${DEPLOY_ENV}"

log "0. starting from a clean slate (no reuse of prior deploy state)"
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true

log "1. building images from source"
$COMPOSE build migrate backend worker frontend

log "2. bringing up the database"
$COMPOSE up -d db

log "3. prepare step: alembic upgrade head + the idempotent SYSTEM seed"
$COMPOSE up --exit-code-from migrate migrate

log "4. re-running the prepare step — it MUST be idempotent"
# Not decoration. The whole reason `seed_system_reference` was made idempotent at DEP-1 is so a
# deploy can be re-run after a partial failure. If that only works in a unit test, it is not a
# deployment property. This proves it against the real stack.
$COMPOSE up --exit-code-from migrate migrate

log "5. starting the application services"
$COMPOSE up -d backend frontend

log "6. VERIFYING THE RUNNING DEPLOYMENT (not the exit code of step 5)"
ok=0
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 2
done
if [ "$ok" -ne 1 ]; then
  log "FAILED: the backend never became reachable on :8000"
  $COMPOSE logs --tail 40 backend
  exit 1
fi
echo "   backend /health reachable"

curl -fsS "http://localhost:8000/version" | tee /dev/stderr >/dev/null
echo "   backend /version reachable (app config loaded)"

# A health endpoint proves a PROCESS IS LISTENING. It does not prove the database was migrated or
# seeded — which is precisely the failure this stack shipped with, and precisely the failure a
# green `docker compose up` would still show. So assert the DATABASE STATE the prepare step was
# supposed to produce, read back from the deployed database itself.
#
# (Deliberately not asserted through a governed API read: every governed read requires an
# entitled principal, and the SYSTEM reference seed does not create app users. Inventing a user
# to satisfy a probe would be manufacturing the evidence.)
log "7. asserting the DEPLOYED DATABASE actually holds migrated + seeded state"
head_rev=$($COMPOSE exec -T db psql -U "${POSTGRES_USER:-irp}" -d "${POSTGRES_DB:-irp}" -tAc \
  "SELECT version_num FROM alembic_version")
echo "   alembic_version = ${head_rev}"
[ -n "$head_rev" ] || { log "FAILED: alembic_version is empty — the database was never migrated"; exit 1; }

n_cur=$($COMPOSE exec -T db psql -U "${POSTGRES_USER:-irp}" -d "${POSTGRES_DB:-irp}" -tAc \
  "SELECT count(*) FROM currency")
echo "   seeded currencies = ${n_cur}"
[ "${n_cur//[[:space:]]/}" = "4" ] || { log "FAILED: expected 4 seeded currencies, found ${n_cur} — the seed did not run, or ran twice"; exit 1; }

if curl -fsS "http://localhost:5173/" >/dev/null 2>&1; then
  echo "   frontend serving on :5173"
else
  log "FAILED: the frontend never became reachable on :5173"
  exit 1
fi

log "DEPLOY VERIFIED — images built from source, empty database migrated and seeded through the
    governed prepare step (twice, proving idempotency), API and frontend both reachable."
