#!/usr/bin/env bash
#
# ONBOARD-1a: THE IGNITION PROOF — a tenant is created OVER HTTP on the deployed stack, and its
# first administrator resolves against a governed read.
#
# WHY THIS AND NOT THE TEST SUITES. The PG tier proves the boundary check and the two-context
# transaction; the endpoint tier proves the route and the fence. What neither proves is the layers
# COMPOSED on the real deployment: the migrate image delivering 0067 to a real database, the
# prepare step seeding the operator from the deploy env, the backend resolving that operator
# through real RLS, and the onboarding transaction crossing two contexts on a connection pool that
# nothing in a test harness configured. Every one of those seams has produced a deployed-only
# defect this platform has already paid for (the psycopg-less images, the empty-database backend,
# the hand-pinned migration head).
#
# THE ARMS, each with its refusal twin (P18):
#   1. the operator creates a tenant over HTTP        <-> a tenant principal is 403'd doing it
#   2. the first admin RESOLVES on a governed read    <-> an unregistered tenant claim is 401'd
#   3. the SYSTEM fence: the operator is 401'd on the same governed read it just enabled
#
# Usage: ./infra/deploy/prove_onboarding.sh

set -euo pipefail

PROJECT="irp-onboard1a"
# 55432=deploy, 55433=backup/restore, 55435=report-identity, 55436=reproduction, 55437 here.
export POSTGRES_PUBLISH_PORT="${POSTGRES_PUBLISH_PORT:-55437}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
ENV_FILE="infra/deploy/.env.onboarding"
export IRP_ENV_FILE="$ENV_FILE"
COMPOSE="docker compose -p ${PROJECT} --env-file ${ENV_FILE}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OPERATOR_SUBJECT="proof-operator@platform"  # pipe-free: the env file is dot-sourced AND compose-parsed

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\n!!! FAILED: %s\n' "$*" >&2; exit 1; }

cleanup() {
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$ENV_FILE"
}
trap cleanup EXIT

# Generated from .env.example every run — the DEP-1 rule.
cp .env.example "$ENV_FILE"
# The operator subject rides the PREPARE step's env (ratified OQ-ONB-2 sub-fork (a)).
echo "IRP_PLATFORM_OPERATOR_SUBJECT=${OPERATOR_SUBJECT}" >> "$ENV_FILE"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
PGUSER="${POSTGRES_USER:-irp}"
PGDB="${POSTGRES_DB:-irp}"

log "0. a migrated, operator-seeded stack"
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
$COMPOSE build migrate backend >/dev/null
$COMPOSE up -d db >/dev/null
$COMPOSE up --exit-code-from migrate migrate > /tmp/onb_prepare.log 2>&1 \
  || { cat /tmp/onb_prepare.log; die "the prepare step failed"; }
grep -q "platform operator seeded" /tmp/onb_prepare.log \
  || die "the prepare step did not seed the operator — IRP_PLATFORM_OPERATOR_SUBJECT was set"

# The derived-head check (the class fix from the Wave-16 close, reused verbatim).
head_rev=$($COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc "SELECT version_num FROM alembic_version" | tr -d '[:space:]')
expected_heads=$($COMPOSE run --rm --entrypoint alembic migrate heads | awk '/head/{print $1}')
[ "$head_rev" = "$expected_heads" ] || die "expected head ${expected_heads}, got ${head_rev}"
echo "   alembic_version=${head_rev}"

$COMPOSE up -d backend >/dev/null
ok=0
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
[ "$ok" = "1" ] || die "the backend never became healthy"

SYSTEM_TENANT="00000000-0000-0000-0000-000000000001"
OPERATOR_ID=$($COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc \
  "SELECT id FROM app_user WHERE tenant_id = '${SYSTEM_TENANT}' AND external_subject = '${OPERATOR_SUBJECT}'" | tr -d '[:space:]')
[ -n "$OPERATOR_ID" ] || die "the seeded operator has no app_user row"
echo "   operator app_user.id=${OPERATOR_ID}"

log "1. THE IGNITION: the operator creates a tenant over HTTP"
create=$(curl -sS -w '\n%{http_code}' -X POST "http://localhost:${BACKEND_PORT}/tenants" \
  -H "X-User-Id: ${OPERATOR_ID}" -H "X-Tenant-Id: ${SYSTEM_TENANT}" \
  -H "Content-Type: application/json" \
  -d '{"code":"ignition","display_name":"Ignition Proof","admin_external_subject":"first-admin@ignition","admin_display_name":"First Admin"}')
code=$(printf '%s' "$create" | tail -1)
body=$(printf '%s' "$create" | sed '$d')
[ "$code" = "201" ] || die "tenant creation returned ${code}: ${body}"
TENANT_ID=$(printf '%s' "$body" | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(json.load(sys.stdin)["tenant_id"])')
ADMIN_ID=$(printf '%s' "$create" | sed '$d' | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(json.load(sys.stdin)["admin_user_id"])')
[ -n "$TENANT_ID" ] && [ -n "$ADMIN_ID" ] || die "the response carried no ids"
echo "   tenant=${TENANT_ID} admin=${ADMIN_ID}"

log "2. THE FIRST ADMIN RESOLVES on a governed read (the reason the slice exists)"
# tenant_admin holds no portfolio.view in 1a, so the RIGHT expectation is 403 — the principal
# RESOLVED (past the registry check, past RLS, past user lookup) and was refused by the
# PERMISSION gate. A 401 here would mean the boundary rejected the tenant this slice just made.
admin_code=$(curl -sS -o /dev/null -w '%{http_code}' "http://localhost:${BACKEND_PORT}/portfolios" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}")
[ "$admin_code" = "403" ] || die "the first admin got ${admin_code} on /portfolios — expected 403 (resolved, permission-refused). 401 means the created tenant FAILED its own boundary check"
echo "   admin -> /portfolios: 403 (resolved; permission-refused — tenant_admin has 1b's verbs)"

log "3. REFUSAL TWINS (P18)"
# (a) an unregistered tenant claim is 401'd — the boundary check, live on the deployed stack.
stranger_code=$(curl -sS -o /dev/null -w '%{http_code}' "http://localhost:${BACKEND_PORT}/portfolios" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: 99999999-9999-4999-8999-999999999999")
[ "$stranger_code" = "401" ] || die "an UNREGISTERED tenant claim got ${stranger_code}, not 401 — the boundary check is not running on the deployed stack"
echo "   unregistered tenant claim -> 401"
# (b) the SYSTEM fence: the operator is refused on the governed read it just enabled.
fence_code=$(curl -sS -o /dev/null -w '%{http_code}' "http://localhost:${BACKEND_PORT}/portfolios" \
  -H "X-User-Id: ${OPERATOR_ID}" -H "X-Tenant-Id: ${SYSTEM_TENANT}")
[ "$fence_code" = "401" ] || die "the SYSTEM operator got ${fence_code} on /portfolios — the fence is down and a SYSTEM principal reaches data routers"
echo "   SYSTEM operator on a data router -> 401 (the fence)"
# (c) the first admin CANNOT create tenants — the platform catalog stayed out of the clones.
escalate_code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "http://localhost:${BACKEND_PORT}/tenants" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"code":"escalated","display_name":"E","admin_external_subject":"e@e","admin_display_name":"E"}')
[ "$escalate_code" = "403" ] || die "a TENANT principal got ${escalate_code} creating a tenant — the escalation the catalog split exists to prevent"
echo "   tenant admin creating a tenant -> 403 (the catalog split, live)"

log "4. the clone landed in the DATABASE (not just the response)"
clone_count=$($COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc \
  "SELECT count(*) FROM role WHERE tenant_id = '${TENANT_ID}'" | tr -d '[:space:]')
[ "$clone_count" = "5" ] || die "expected 5 cloned roles (four business + tenant_admin), got ${clone_count}"
pa_count=$($COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc \
  "SELECT count(*) FROM role WHERE tenant_id = '${TENANT_ID}' AND code IN ('ops','platform_admin')" | tr -d '[:space:]')
[ "$pa_count" = "0" ] || die "ops/platform_admin were cloned into a customer tenant"
echo "   5 roles cloned; ops/platform_admin absent, as ratified"

log "PASSED — the platform starts: tenant created over HTTP, first admin resolves, every refusal fired"
