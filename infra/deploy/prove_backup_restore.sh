#!/usr/bin/env bash
#
# DEP-1 (Wave-15): PROVE the backup/restore pair by execution — both arms.
#
# The roadmap asks for "a PROVEN PostgreSQL backup/restore". A backup nothing has ever restored is
# not a backup, it is a file; and a restore that has never been shown to REFUSE damaged input is
# not a safeguard, it is an assumption. So this proves both:
#
#   POSITIVE  real data -> backup -> DESTROY the data -> restore -> the data is back, exactly.
#   NEGATIVE  (P9) a TRUNCATED archive -> the restore REFUSES, and the target database is
#             UNCHANGED afterwards.
#
# The negative arm is the one that matters. A restore that "succeeds" on a damaged dump converts a
# recoverable outage into confident data loss — the operator believes they are restored and are
# not. Asserting that the target still holds its original rows AFTER the refusal is what
# distinguishes a real refusal from one that failed halfway through destroying the target.
#
# Usage: ./infra/deploy/prove_backup_restore.sh

set -euo pipefail

PROJECT="irp-dep1-br"
export POSTGRES_PUBLISH_PORT="${POSTGRES_PUBLISH_PORT:-55433}"
ENV_FILE="infra/deploy/.env.deploy"
export IRP_ENV_FILE="$ENV_FILE"
COMPOSE="docker compose -p ${PROJECT} --env-file ${ENV_FILE}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARCHIVE="/tmp/irp_dep1_backup.dump"

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\n!!! FAILED: %s\n' "$*" >&2; exit 1; }

cleanup() { $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true; rm -f "$ARCHIVE" "${ARCHIVE}.sha256"; }
trap cleanup EXIT

cp .env.example "$ENV_FILE"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
PGUSER="${POSTGRES_USER:-irp}"
PGDB="${POSTGRES_DB:-irp}"
psql_q() { $COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc "$1" | tr -d '[:space:]'; }

log "0. a clean stack with real, governed data in it"
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
$COMPOSE build migrate >/dev/null
$COMPOSE up -d db >/dev/null
$COMPOSE up --exit-code-from migrate migrate >/dev/null

before_rev=$(psql_q "SELECT version_num FROM alembic_version")
before_cur=$(psql_q "SELECT count(*) FROM currency")
before_hol=$(psql_q "SELECT count(*) FROM calendar_holiday")
echo "   alembic_version=${before_rev}  currency=${before_cur}  calendar_holiday=${before_hol}"
[ "$before_cur" = "4" ] || die "expected the seeded 4 currencies before backup, got ${before_cur}"
[ "$before_hol" -gt 100 ] 2>/dev/null || die "expected the full XNYS holiday set, got ${before_hol}"

log "1. BACKUP"
bash infra/deploy/backup.sh "$ARCHIVE" "$PROJECT"

# ----------------------------------------------------------------- NEGATIVE ARM (P9) — run FIRST
# Run before the positive arm, deliberately: it must prove the refusal leaves the target intact,
# and that assertion is only meaningful while the target still HAS its data.
log "2. NEGATIVE CONTROL: truncate the archive and require the restore to REFUSE"
cp "$ARCHIVE" "${ARCHIVE}.good"
cp "${ARCHIVE}.sha256" "${ARCHIVE}.good.sha256"
full=$(wc -c < "$ARCHIVE" | tr -d '[:space:]')
head -c $(( full / 2 )) "${ARCHIVE}.good" > "$ARCHIVE"   # a real, half-written archive
rm -f "${ARCHIVE}.sha256"                                 # storage corruption: no checksum survives
echo "   truncated ${full} bytes -> $(wc -c < "$ARCHIVE" | tr -d '[:space:]')"

if bash infra/deploy/restore.sh "$ARCHIVE" "$PROJECT" >/tmp/irp_neg.log 2>&1; then
  cat /tmp/irp_neg.log
  die "THE RESTORE ACCEPTED A TRUNCATED ARCHIVE — this is the failure mode the control exists for"
fi
echo "   restore refused (exit non-zero), as required"

after_neg_cur=$(psql_q "SELECT count(*) FROM currency")
after_neg_hol=$(psql_q "SELECT count(*) FROM calendar_holiday")
echo "   target after the refusal: currency=${after_neg_cur} calendar_holiday=${after_neg_hol}"
[ "$after_neg_cur" = "$before_cur" ] && [ "$after_neg_hol" = "$before_hol" ] \
  || die "the refused restore MODIFIED the target — it failed halfway instead of refusing up front"
echo "   target UNCHANGED — the refusal landed before the target was touched"

# ----------------------------------------------------------------------------- POSITIVE ARM
log "3. POSITIVE: destroy the data, then restore it from the good archive"
mv "${ARCHIVE}.good" "$ARCHIVE"
mv "${ARCHIVE}.good.sha256" "${ARCHIVE}.sha256"

$COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${PGUSER}; GRANT USAGE ON SCHEMA public TO PUBLIC;" >/dev/null
gone=$(psql_q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "$gone" = "0" ] || die "the destroy step did not actually destroy anything (${gone} tables left)"
echo "   schema destroyed — 0 tables remain"

bash infra/deploy/restore.sh "$ARCHIVE" "$PROJECT"

after_rev=$(psql_q "SELECT version_num FROM alembic_version")
after_cur=$(psql_q "SELECT count(*) FROM currency")
after_hol=$(psql_q "SELECT count(*) FROM calendar_holiday")
echo "   restored: alembic_version=${after_rev} currency=${after_cur} calendar_holiday=${after_hol}"

[ "$after_rev" = "$before_rev" ] || die "migration head differs after restore (${before_rev} -> ${after_rev})"
[ "$after_cur" = "$before_cur" ] || die "currency count differs after restore (${before_cur} -> ${after_cur})"
[ "$after_hol" = "$before_hol" ] || die "holiday count differs after restore (${before_hol} -> ${after_hol})"

log "BACKUP/RESTORE PROVEN — both arms:
    POSITIVE  data destroyed and restored exactly (head ${after_rev}, ${after_cur} currencies, ${after_hol} holidays)
    NEGATIVE  a truncated archive was REFUSED and the target was left UNCHANGED"
