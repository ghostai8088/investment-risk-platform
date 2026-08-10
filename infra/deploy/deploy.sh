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

# Wave-15 process-fold audit finding 1: the original deploy started backend+frontend and said
# "DEPLOY VERIFIED" — while the WORKER, the engine's tick loop, never ran at all. The claim
# quantified over more than it exercised (the P10 class). The deploy env deliberately ships
# IRP_TENANT_IDS empty (no tenant exists yet), and the worker's RATIFIED behaviour on that input
# is to FAIL CLOSED at startup rather than idle silently (CAD-1 FOLD-2). So that is what gets
# proven: the worker must start, refuse LOUDLY with the documented message, and exit non-zero.
# A worker that comes up green here would be the defect.
log "8. the worker on an EMPTY platform: it must start, IDLE LOUDLY, and keep polling"
# **This assertion INVERTED at REPRO-2 (ratified 2026-08-10), and the inversion is the point.**
# It used to require the worker to REFUSE (exit 2, "no valid tenants") on an unconfigured tenant
# list, because under CAD-1 the tenant list WAS deploy config and an empty one could only be a
# misconfiguration. Under registry-driven discovery the same input means something different and
# TRUE: a freshly deployed platform has no tenants yet. Refusing there would make the platform's
# ignition depend on restart orchestration — the worker would crash-loop until somebody onboarded
# a tenant.
#
# What did NOT change is the property CAD-1 was protecting: a silently-idle engine. The worker
# must SAY it is idle, every cycle. So this step now bounds the run (IRP_MAX_CYCLES — the seam
# added for exactly this proof, since a polling supervisor otherwise never exits) and asserts the
# announcement rather than the exit code.
#
# The fail-closed arms did not disappear either; they moved to the states that are genuinely
# wrong, and step 8b below proves one of them live.
set +e
wout=$($COMPOSE run --rm --no-deps -e IRP_MAX_CYCLES=2 -e IRP_TICK_INTERVAL_SECONDS=1 worker 2>&1)
wrc=$?
set -e
if [ "$wrc" -ne 0 ]; then
  log "FAILED: the worker did not complete its bounded run on an empty platform (exit ${wrc})"
  printf '%s\n' "$wout" | tail -15
  exit 1
fi
if ! printf '%s' "$wout" | grep -q "no ACTIVE tenants in the registry"; then
  log "FAILED: the worker was idle and did NOT SAY SO — a silently-idle engine is the exact failure CAD-1 refused, and registry discovery does not get to reintroduce it"
  printf '%s\n' "$wout" | tail -15
  exit 1
fi
echo "   worker idled LOUDLY on an empty registry and polled again (exit 0, announcement present)"

log "8b. the worker with a MISCONFIGURED restriction: it must still FAIL CLOSED"
# The retained half of CAD-1 FOLD-2. A filter naming a tenant the registry does not know is a
# definite misconfiguration — ticking the remainder silently would be the looks-configured-but-
# isn't state — so this refuses, and the deploy proves it rather than trusting the unit tier.
set +e
bout=$($COMPOSE run --rm --no-deps -e IRP_TENANT_IDS=99999999-9999-4999-8999-999999999999 worker 2>&1)
brc=$?
set -e
if [ "$brc" -eq 0 ]; then
  log "FAILED: the worker STARTED with a restriction naming an unknown tenant — the filter silently shrank to nothing"
  exit 1
fi
if ! printf '%s' "$bout" | grep -q "the registry does not know"; then
  log "FAILED: the worker exited (${brc}) but not via the documented unknown-tenant refusal"
  printf '%s\n' "$bout" | tail -15
  exit 1
fi
echo "   worker refused a restriction naming an unknown tenant (exit ${brc})"

log "DEPLOY VERIFIED — images built from source, empty database migrated and seeded through the
    governed prepare step (twice, proving idempotency), API and frontend both reachable, and the
    worker PROVEN to idle LOUDLY on an empty registry while still failing closed on a restriction
    that names a tenant the registry does not know (REPRO-2's discovery supersession, both arms)."
