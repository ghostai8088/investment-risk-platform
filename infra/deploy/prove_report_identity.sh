#!/usr/bin/env bash
#
# RPT-1 (Wave-15): I2's RESTORE-CYCLE arm — a governed report regenerates byte-identically after
# the database it lives in has been destroyed and restored from a backup.
#
# WHY THIS AND NOT THE UNIT TEST. `test_report_generation` proves generate -> regenerate is
# byte-identical inside one process, one session, one SQLite file. That is BR-9's literal claim and
# it is NOT what an auditor relies on. They rely on: the report shown in March can be reproduced
# from the archive in September, after a restore, in a process that did not generate it. Every part
# of that crosses a boundary the unit tier never touches — a pg_dump serialization round-trip, a
# rebuilt schema, a fresh interpreter, a new connection.
#
# DEP-1 is why this exists: ten of its eleven defects were pre-existing and invisible to a
# 2,980-test suite, because tests exercise code paths without ever starting the system.
#
# THE HASH THAT MATTERS IS CARRIED OUT OF BAND. `regenerate_report` compares against the hash stored
# on the report row — but that hash went through the backup too, so a dump that faithfully preserved
# a WRONG value would satisfy it. The hash captured here, in this shell, before the archive existed,
# is the one that can actually fail.
#
# Usage: ./infra/deploy/prove_report_identity.sh

set -euo pipefail

PROJECT="irp-rpt1-id"
# 55432 = deploy.sh, 55433 = prove_backup_restore.sh, 55435 = here. The pre-flight below exists
# because the first local run collided with an unrelated container on the port this originally
# used, and docker's error ("Bind for 0.0.0.0:55434 failed") names neither the script nor the
# holder — a minute of confusion for a condition the script can state in one line.
export POSTGRES_PUBLISH_PORT="${POSTGRES_PUBLISH_PORT:-55435}"
ENV_FILE="infra/deploy/.env.report_identity"
export IRP_ENV_FILE="$ENV_FILE"
COMPOSE="docker compose -p ${PROJECT} --env-file ${ENV_FILE}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARCHIVE="/tmp/irp_rpt1_identity.dump"

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\n!!! FAILED: %s\n' "$*" >&2; exit 1; }

cleanup() {
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$ARCHIVE" "${ARCHIVE}.sha256" "$ENV_FILE"
}
trap cleanup EXIT

# Generated from .env.example every run, never read from a developer's .env — the DEP-1 rule: a
# deployment proof that depends on an untracked file proves something about that machine.
cp .env.example "$ENV_FILE"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
PGUSER="${POSTGRES_USER:-irp}"
PGDB="${POSTGRES_DB:-irp}"
psql_q() { $COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc "$1" | tr -d '[:space:]'; }

if docker ps --format '{{.Names}} {{.Ports}}' | grep -q ":${POSTGRES_PUBLISH_PORT}->"; then
  holder=$(docker ps --format '{{.Names}} {{.Ports}}' | grep ":${POSTGRES_PUBLISH_PORT}->" | head -1)
  die "host port ${POSTGRES_PUBLISH_PORT} is already published by: ${holder}
    Stop it, or re-run with POSTGRES_PUBLISH_PORT=<free port>."
fi

log "0. a migrated stack"
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
# backend is built HERE, not lazily at `up`: compose reuses an existing project image, and a
# stale backend (the exact psycopg-less image this proof's first run caught) would smoke a build
# that no longer exists.
$COMPOSE build migrate backend >/dev/null
$COMPOSE up -d db >/dev/null
$COMPOSE up --exit-code-from migrate migrate >/dev/null
echo "   alembic_version=$(psql_q 'SELECT version_num FROM alembic_version')"

log "1. GENERATE a governed report on the deployed stack"
# IRP_ALLOW_PROOF_SEED is the harness's arming switch: the module refuses to write governed rows
# into whatever database DATABASE_URL happens to name unless a caller sets it deliberately.
seed_out=$($COMPOSE run --rm -e IRP_ALLOW_PROOF_SEED=1 --entrypoint python migrate \
  -m irp_shared.deploy.report_identity_proof seed) || die "the seed/generate step failed"
echo "$seed_out"
REPORT_ID=$(printf '%s\n' "$seed_out" | sed -n 's/^REPORT_ID=//p' | tr -d '[:space:]')
CONTENT_HASH=$(printf '%s\n' "$seed_out" | sed -n 's/^CONTENT_HASH=//p' | tr -d '[:space:]')
MAKER_ID=$(printf '%s\n' "$seed_out" | sed -n 's/^MAKER_ID=//p' | tr -d '[:space:]')
VIEWER_ID=$(printf '%s\n' "$seed_out" | sed -n 's/^VIEWER_ID=//p' | tr -d '[:space:]')
NOBODY_ID=$(printf '%s\n' "$seed_out" | sed -n 's/^NOBODY_ID=//p' | tr -d '[:space:]')
RUN_ID=$(printf '%s\n' "$seed_out" | sed -n 's/^RUN_ID=//p' | tr -d '[:space:]')
PORTFOLIO_ID=$(printf '%s\n' "$seed_out" | sed -n 's/^PORTFOLIO_ID=//p' | tr -d '[:space:]')
for v in MAKER_ID VIEWER_ID NOBODY_ID RUN_ID PORTFOLIO_ID; do
  [ -n "$(eval "printf '%s' \"\$$v\"")" ] || die "seed did not emit $v"
done
[ -n "$REPORT_ID" ] || die "no REPORT_ID captured"
[ ${#CONTENT_HASH} -eq 64 ] || die "CONTENT_HASH is not a sha256 (${#CONTENT_HASH} chars)"

rows_before=$(psql_q "SELECT count(*) FROM report_generation")
[ "$rows_before" = "1" ] || die "expected exactly 1 report_generation row, got ${rows_before}"

log "2. BACKUP, then DESTROY the database"
bash infra/deploy/backup.sh "$ARCHIVE" "$PROJECT"
$COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${PGUSER}; GRANT USAGE ON SCHEMA public TO PUBLIC;" >/dev/null
gone=$(psql_q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "$gone" = "0" ] || die "the destroy step left ${gone} tables — the restore would prove nothing"
echo "   schema destroyed — 0 tables remain"

log "3. RESTORE"
bash infra/deploy/restore.sh "$ARCHIVE" "$PROJECT"
rows_after=$(psql_q "SELECT count(*) FROM report_generation")
[ "$rows_after" = "1" ] || die "the report row did not survive the restore (${rows_after} rows)"

log "4. REGENERATE in a FRESH PROCESS and compare against the OUT-OF-BAND hash"
verify_out=$($COMPOSE run --rm --entrypoint python migrate \
  -m irp_shared.deploy.report_identity_proof verify "$REPORT_ID" "$CONTENT_HASH") \
  || die "REGENERATION AFTER RESTORE DID NOT REPRODUCE THE REPORT"
echo "$verify_out"
printf '%s\n' "$verify_out" | grep -q "RESTORE_CYCLE_IDENTITY_OK=${CONTENT_HASH}" \
  || die "the verify step did not report the expected hash"

log "5. NEGATIVE CONTROL (P9): the same regeneration against a WRONG out-of-band hash must FAIL"
# Without this arm the whole script could be satisfied by a `verify` that compares nothing. It is
# the same lesson prove_backup_restore.sh carries: a proof that has only ever passed is an
# assumption. The hash is mutated in its FIRST character, so it stays a well-formed sha256 and the
# only thing that can reject it is the comparison itself.
wrong_first=$([ "${CONTENT_HASH:0:1}" = "a" ] && echo "b" || echo "a")
WRONG_HASH="${wrong_first}${CONTENT_HASH:1}"
[ "$WRONG_HASH" != "$CONTENT_HASH" ] || die "the mutated hash equals the real one — no control here"
if neg_out=$($COMPOSE run --rm --entrypoint python migrate \
      -m irp_shared.deploy.report_identity_proof verify "$REPORT_ID" "$WRONG_HASH" 2>&1); then
  printf '%s\n' "$neg_out"
  die "THE IDENTITY CHECK ACCEPTED A WRONG HASH — this proof cannot detect a failed restore"
fi
printf '%s\n' "$neg_out" | grep -q "RESTORE-CYCLE IDENTITY FAILED" \
  || die "the refusal fired for the wrong reason: ${neg_out}"
echo "   a one-character hash change was REFUSED, naming the mismatch"

log "6. THE HTTP SURFACE ON THE RESTORED STACK (RPT-2, remit I6 / P15)"
# The backend publishes host port 8000 UNCONDITIONALLY (docker-compose.yml, unlike the parametrised
# POSTGRES_PUBLISH_PORT). A local dev backend on 8000 makes `up -d backend` fail, and every probe
# below would then hit the DEV backend and could pass against the wrong stack. Say so up front.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  holder=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1" (pid "$2")"}')
  die "host port 8000 is already listening: ${holder}. The HTTP arm would probe THAT process, not
    this proof's stack. Stop it and re-run."
fi
# The unit tier proves the endpoints against SQLite in-process; THIS arm proves them where none of
# those assumptions hold — a restored PostgreSQL, the real entitlement join, dev-header identity
# over the wire, nginx-adjacent port publishing. The proof tenant's principals were seeded by the
# ARMED harness (see seed_principals' docstring for why that honors deploy.sh's no-invented-users
# rule rather than superseding it).
$COMPOSE up -d backend >/tmp/irp_backend_up.log 2>&1 || {
  cat /tmp/irp_backend_up.log >&2
  die 'backend failed to start — output above (previously suppressed by 2>&1 to /dev/null)'
}
for i in $(seq 1 30); do
  curl -fsS http://localhost:8000/health >/dev/null 2>&1 && break
  [ "$i" = 30 ] && die "backend did not come up for the HTTP arm"
  sleep 2
done
PT="9f000000-0000-4000-8000-000000000001"
hdr_v=(-H "X-User-Id: ${VIEWER_ID}" -H "X-Tenant-Id: ${PT}")
hdr_m=(-H "X-User-Id: ${MAKER_ID}" -H "X-Tenant-Id: ${PT}")
hdr_n=(-H "X-User-Id: ${NOBODY_ID}" -H "X-Tenant-Id: ${PT}")

code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8000/reports")
[ "$code" = "401" ] || die "unauthenticated list was $code, expected 401"
echo "   401 without a principal"

code=$(curl -s -o /dev/null -w '%{http_code}' "${hdr_n[@]}" "http://localhost:8000/reports")
[ "$code" = "403" ] || die "unentitled list was $code, expected 403"
echo "   403 for a principal with no report code"

curl -fsS "${hdr_v[@]}" "http://localhost:8000/reports" | grep -q "$REPORT_ID" \
  || die "the viewer's list does not contain the restored report"
echo "   the restored report is listed for the viewer"

served=$(curl -fsS "${hdr_v[@]}" "http://localhost:8000/reports/${REPORT_ID}/html" | shasum -a 256 | cut -d' ' -f1)
[ "$served" = "$CONTENT_HASH" ] \
  || die "HTTP-served bytes hash ${served} != recorded ${CONTENT_HASH} — I1 fails OVER THE WIRE"
echo "   GET /html bytes hash to the recorded identity ACROSS the restore: ${served}"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${hdr_v[@]}" -H 'Content-Type: application/json' \
  -d "{\"portfolio_id\":\"${PORTFOLIO_ID}\",\"as_of_date\":\"2026-06-30\",\"family_runs\":{\"concentration\":\"${RUN_ID}\"}}" \
  "http://localhost:8000/reports")
[ "$code" = "403" ] || die "the VIEW code reached the generate verb over HTTP ($code) — the split failed live"
echo "   403: view cannot generate, on the deployed stack"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${hdr_m[@]}" -H 'Content-Type: application/json' \
  -d "{\"portfolio_id\":\"${PORTFOLIO_ID}\",\"as_of_date\":\"2026-06-30\",\"family_runs\":{\"concentration\":\"${RUN_ID}\"},\"generated_at\":\"1999-01-01T00:00:00Z\"}" \
  "http://localhost:8000/reports")
[ "$code" = "422" ] || die "a caller-supplied generated_at was $code, expected a 422 refusal (remit I2)"
echo "   422: the wire cannot assert evidence time"

gen=$(curl -fsS -X POST "${hdr_m[@]}" -H 'Content-Type: application/json' \
  -d "{\"portfolio_id\":\"${PORTFOLIO_ID}\",\"as_of_date\":\"2026-06-30\",\"family_runs\":{\"concentration\":\"${RUN_ID}\"}}" \
  "http://localhost:8000/reports") || die "the maker's generate failed over HTTP"
NEW_ID=$(printf '%s' "$gen" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
NEW_HASH=$(printf '%s' "$gen" | sed -n 's/.*"content_hash":"\([^"]*\)".*/\1/p')
[ ${#NEW_HASH} -eq 64 ] || die "generate returned no sha256"
served2=$(curl -fsS "${hdr_m[@]}" "http://localhost:8000/reports/${NEW_ID}/html" | shasum -a 256 | cut -d' ' -f1)
[ "$served2" = "$NEW_HASH" ] || die "the HTTP-generated report does not re-serve byte-identically"
echo "   generate-over-HTTP then re-read: byte-identical (${served2})"

# CROSS-GENERATION IDENTITY, now ASSERTED rather than merely observed. The RPT-2 review caught the
# commit message claiming this property while the script only compared each report to itself. Two
# INDEPENDENT generations over the same pinned inputs — one before the backup, one over HTTP after
# the restore — must produce the same bytes, or "reproducible" means only "self-consistent".
[ "$served2" = "$CONTENT_HASH" ] || die "two independent generations over the SAME pinned inputs
    differ: pre-backup ${CONTENT_HASH} vs post-restore-over-HTTP ${served2}"
echo "   cross-generation identity: two independent generations agree (${served2})"

log "RESTORE-CYCLE IDENTITY PROVEN (I2)
    report ${REPORT_ID}
    POSITIVE  generated, backed up, database DESTROYED, restored, and regenerated
              byte-identically in a different process: ${CONTENT_HASH}
    NEGATIVE  a one-character change to the out-of-band hash was REFUSED"
