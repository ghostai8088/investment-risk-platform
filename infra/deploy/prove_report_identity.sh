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
$COMPOSE build migrate >/dev/null
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

log "RESTORE-CYCLE IDENTITY PROVEN (I2)
    report ${REPORT_ID}
    POSITIVE  generated, backed up, database DESTROYED, restored, and regenerated
              byte-identically in a different process: ${CONTENT_HASH}
    NEGATIVE  a one-character change to the out-of-band hash was REFUSED"
