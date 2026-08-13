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
#   4. (ONBOARD-1b) the tenant ADMINISTERS ITSELF: the admin creates a user, grants a role in
#      the bootstrap window (DIRECT), mints a second admin, and the next act is born PENDING —
#      approved by the second admin, refused as self-approval by the first. The granted user
#      then reads a surface their role permits <-> is 403'd on one it does not.
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

log "5. ONBOARD-1b: the tenant administers itself — four-eyes live over HTTP"
json_field() { $COMPOSE run --rm --entrypoint python migrate -c \
  "import json,sys; print(json.load(sys.stdin)[\"$1\"])"; }

# The role ids, read through the tenant admin's OWN typed surface (user.view).
roles=$(curl -sS "http://localhost:${BACKEND_PORT}/roles" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}")
ANALYST_ROLE=$(printf '%s' "$roles" | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(next(r["id"] for r in json.load(sys.stdin) if r["code"]=="risk_analyst_1l"))')
MANAGER_ROLE=$(printf '%s' "$roles" | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(next(r["id"] for r in json.load(sys.stdin) if r["code"]=="risk_manager_2l"))')
TA_ROLE=$(printf '%s' "$roles" | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(next(r["id"] for r in json.load(sys.stdin) if r["code"]=="tenant_admin"))')
[ -n "$ANALYST_ROLE" ] && [ -n "$MANAGER_ROLE" ] && [ -n "$TA_ROLE" ] || die "GET /roles did not return the cloned roles"

# 5a. create the analyst; grant their role in the BOOTSTRAP WINDOW (one admin -> DIRECT).
ANALYST_ID=$(curl -sS -X POST "http://localhost:${BACKEND_PORT}/users" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}" -H "Content-Type: application/json" \
  -d '{"external_subject":"analyst@ignition","display_name":"Analyst"}' | json_field id)
[ -n "$ANALYST_ID" ] || die "creating the analyst returned no id"
direct_status=$(curl -sS -X POST "http://localhost:${BACKEND_PORT}/users/${ANALYST_ID}/roles" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}" -H "Content-Type: application/json" \
  -d "{\"role_id\":\"${ANALYST_ROLE}\"}" | json_field status)
[ "$direct_status" = "DIRECT" ] || die "a lone admin's grant was ${direct_status}, expected DIRECT (the bootstrap window)"
echo "   lone admin's grant -> DIRECT (bootstrap window, stamped)"

# 5b. mint a SECOND admin (still DIRECT — the window closes only once this lands)...
ADMIN2_ID=$(curl -sS -X POST "http://localhost:${BACKEND_PORT}/users" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}" -H "Content-Type: application/json" \
  -d '{"external_subject":"second-admin@ignition","display_name":"Second Admin"}' | json_field id)
admin2_grant=$(curl -sS -X POST "http://localhost:${BACKEND_PORT}/users/${ADMIN2_ID}/roles" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}" -H "Content-Type: application/json" \
  -d "{\"role_id\":\"${TA_ROLE}\"}" | json_field status)
[ "$admin2_grant" = "DIRECT" ] || die "the second-admin mint was ${admin2_grant}, expected DIRECT"

# ...and the VERY NEXT act is born PENDING: four-eyes engages at two admins, not three (B3).
# The PENDING grant is risk_manager_2l, DELIBERATELY not tenant_admin: this arm's first draft
# granted tenant_admin here and then expected the target to lack user.manage in step 5e — refuted
# by its own execution (the analyst got 201 where the script demanded 403, because the script had
# made them an admin two steps earlier). The proof's refusal twin only discriminates if the
# granted role does NOT confer the verb the twin denies.
req=$(curl -sS -X POST "http://localhost:${BACKEND_PORT}/users/${ANALYST_ID}/roles" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}" -H "Content-Type: application/json" \
  -d "{\"role_id\":\"${MANAGER_ROLE}\",\"reason\":\"four-eyes proof\"}")
REQ_ID=$(printf '%s' "$req" | json_field id)
req_status=$(printf '%s' "$req" | json_field status)
[ "$req_status" = "PENDING" ] || die "with TWO admins the grant was ${req_status}, expected PENDING — SOD-04 did not engage at the threshold"
echo "   with a second admin -> PENDING (four-eyes engaged at two admins)"

# 5c. the refusal twin: the requester cannot approve their own request (SOD-04, person-level).
self_code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  "http://localhost:${BACKEND_PORT}/entitlement-requests/${REQ_ID}/approve" \
  -H "X-User-Id: ${ADMIN_ID}" -H "X-Tenant-Id: ${TENANT_ID}")
[ "$self_code" = "422" ] || die "self-approval got ${self_code}, expected 422 — four-eyes with one pair of eyes"
echo "   self-approval -> 422 (SOD-04, live)"

# 5d. the SECOND admin approves, and the act takes effect.
approve_status=$(curl -sS -X POST "http://localhost:${BACKEND_PORT}/entitlement-requests/${REQ_ID}/approve" \
  -H "X-User-Id: ${ADMIN2_ID}" -H "X-Tenant-Id: ${TENANT_ID}" | json_field status)
[ "$approve_status" = "APPROVED" ] || die "the second admin's approval returned ${approve_status}"
echo "   second admin approves -> APPROVED"

# 5e. the granted user resolves: permitted on what their role holds, refused on what it does not.
analyst_read=$(curl -sS -o /dev/null -w '%{http_code}' "http://localhost:${BACKEND_PORT}/portfolios" \
  -H "X-User-Id: ${ANALYST_ID}" -H "X-Tenant-Id: ${TENANT_ID}")
[ "$analyst_read" = "200" ] || die "the granted analyst got ${analyst_read} on /portfolios — the grant did not confer the role's reads"
analyst_write=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "http://localhost:${BACKEND_PORT}/users" \
  -H "X-User-Id: ${ANALYST_ID}" -H "X-Tenant-Id: ${TENANT_ID}" -H "Content-Type: application/json" \
  -d '{"external_subject":"x@x","display_name":"X"}')
[ "$analyst_write" = "403" ] || die "the analyst got ${analyst_write} creating a user — expected 403 (no user.manage)"
echo "   analyst -> /portfolios 200, POST /users 403 (the granted role's exact edge)"

log "6. TENANT ISOLATION, PROVEN AS THE DEPLOYED ROLE (DEPLOY-1 — the break-in test)"
# THE arm this slice exists for. Before DEPLOY-1 every service connected as ${POSTGRES_USER},
# which the postgres:16 image creates a SUPERUSER — so all 84 FORCE-RLS tables were bypassed in
# the only artifact anyone would deploy, and every proof in this file demonstrated its behaviour
# with tenant isolation switched OFF. Measured at the close: as the owner, two rows visible across
# two tenants with no tenant GUC armed; as irp_app, zero.
#
# The database-level proof is in test_app_role_pg.py. THIS is the one that matters, because the
# claim is about the deployed stack: a real principal, over HTTP, against a real second tenant.

# 6a. the role the BACKEND is actually connected as — asked of the running container, not inferred.
app_role=$($COMPOSE exec -T backend python -c \
  "import os,re;u=os.environ['DATABASE_URL'];print(re.match(r'.*://([^:]+):',u).group(1))" | tr -d '\r')
[ "$app_role" = "irp_app" ] || die "the backend is connected as '${app_role}', not irp_app — the whole fix is inert"
super_flags=$($COMPOSE exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT rolsuper::text||'/'||rolbypassrls::text FROM pg_roles WHERE rolname='irp_app'" | tr -d '\r')
[ "$super_flags" = "false/false" ] || die "irp_app reports rolsuper/rolbypassrls = ${super_flags} — expected false/false"
echo "   backend connects as irp_app; rolsuper=false rolbypassrls=false"

# 6b. a SECOND tenant, created over HTTP by the operator exactly as the first was.
create2=$(curl -sS -w '\n%{http_code}' -X POST "http://localhost:${BACKEND_PORT}/tenants" \
  -H "X-User-Id: ${OPERATOR_ID}" -H "X-Tenant-Id: ${SYSTEM_TENANT}" \
  -H "Content-Type: application/json" \
  -d '{"code":"neighbour","display_name":"Neighbour Tenant","admin_external_subject":"admin@neighbour","admin_display_name":"Neighbour Admin"}')
code2=$(printf '%s' "$create2" | tail -1)
[ "$code2" = "201" ] || die "second tenant creation returned ${code2}"
TENANT2_ID=$(printf '%s' "$create2" | sed '$d' | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(json.load(sys.stdin)["tenant_id"])')
ADMIN2_T2=$(printf '%s' "$create2" | sed '$d' | $COMPOSE run --rm --entrypoint python migrate -c \
  'import json,sys; print(json.load(sys.stdin)["admin_user_id"])')
echo "   second tenant=${TENANT2_ID}"

# 6c. THE POSITIVE HALF FIRST, and the ordering is deliberate. `/users` is a route this admin
#     genuinely holds (tenant_admin carries ONBOARD-1b's user verbs), so a 200 here is what makes
#     the refusal below mean something.
#
#     The first version of this arm used `/portfolios` — which tenant_admin cannot read on EITHER
#     tenant — so the break-in and the control both returned 403 and the test could not tell them
#     apart. Wrong answer and right answer coinciding is the REPRO-2 `cohort[0]` defect exactly.
own=$(curl -sS -o /dev/null -w '%{http_code}' "http://localhost:${BACKEND_PORT}/users" \
  -H "X-User-Id: ${ADMIN2_T2}" -H "X-Tenant-Id: ${TENANT2_ID}")
[ "$own" = "200" ] || die "tenant 2's admin got ${own} on its OWN /users — expected 200. Without this the refusal below proves nothing"
echo "   tenant-2 admin on its OWN /users -> 200 (the principal works)"

# 6d. THE BREAK-IN. The SAME principal, the SAME route, tenant 1's id.
#
#     Expect 403, not 401, and the reason is worth stating because the first draft of this arm
#     asserted 401 and failed: the dev-header shim takes (user, tenant) at face value and only
#     checks that the tenant is ADMITTED, so the principal is constructed and RLS does the real
#     work — under tenant 1's context this user has no rows, therefore no roles, therefore no
#     permissions. The isolation is enforced at the permission layer, and THAT is what the
#     constrained role makes true: as a SUPERUSER the same request would have found the rows.
breakin=$(curl -sS -w '\n%{http_code}' "http://localhost:${BACKEND_PORT}/users" \
  -H "X-User-Id: ${ADMIN2_T2}" -H "X-Tenant-Id: ${TENANT_ID}")
bcode=$(printf '%s' "$breakin" | tail -1)
bbody=$(printf '%s' "$breakin" | sed '$d')
[ "$bcode" = "403" ] || die "BREAK-IN: tenant 2's admin reading tenant 1's /users got ${bcode}, expected 403"
# Belt and braces: a refusal that still leaked a row would be the worst possible pass.
case "$bbody" in
  *"@ignition"*|*"First Admin"*) die "BREAK-IN LEAKED TENANT 1 DATA in the refusal body: ${bbody}" ;;
esac
echo "   SAME admin, SAME route, tenant-1's id -> 403, no tenant-1 identity in the body"

# 6e. and the negative twin for the ROLE itself: the constrained role must not be able to see
#     across tenants at the DATABASE either, which is the property the migration delivers.
rows=$($COMPOSE exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SET ROLE irp_app; SELECT count(*) FROM app_user;" | tr -d '\r' | tail -1)
[ "$rows" = "0" ] || die "irp_app with no tenant GUC armed sees ${rows} app_user rows — expected 0. RLS is not holding for the deployed role"
echo "   irp_app with no tenant context -> 0 app_user rows (RLS holds for the role the app uses)"


log "PASSED — the platform starts AND administers itself: tenant created over HTTP, four-eyes live, tenant isolation proven over HTTP as the constrained role, every refusal fired"
