#!/usr/bin/env bash
#
# DEP-1 (Wave-15): restore a PostgreSQL backup — REFUSING a damaged archive BEFORE touching the
# target database.
#
# THE ORDER OF OPERATIONS IS THE CONTROL. Every integrity check runs against the ARCHIVE first, and
# the target is only touched once the archive has proven readable. That ordering is the whole point:
#
#   "the restore failed" is NOT good enough. A restore that fails HALFWAY has already dropped the
#   objects it was going to replace, so the operator is left with neither the old database nor the
#   new one — strictly worse than never having started. The refusal must land while the target is
#   still intact.
#
# P9: this refusal ships with a test that makes it FIRE — see infra/deploy/prove_backup_restore.sh,
# which truncates a real archive and asserts both that the restore refuses AND that the target
# database still holds its original rows.
#
# Usage: ./infra/deploy/restore.sh <archive-path> [compose-project]

set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <archive-path> [compose-project]}"
PROJECT="${2:-irp-dep1}"
ENV_FILE="${IRP_ENV_FILE:-infra/deploy/.env.deploy}"
COMPOSE="docker compose -p ${PROJECT} --env-file ${ENV_FILE}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
PGUSER="${POSTGRES_USER:-irp}"
PGDB="${POSTGRES_DB:-irp}"

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\n!!! REFUSED: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- archive-side checks (no target)

[ -f "$ARCHIVE" ] || die "no such archive: ${ARCHIVE}"

bytes=$(wc -c < "$ARCHIVE" | tr -d '[:space:]')
[ "$bytes" -gt 0 ] || die "the archive is empty (${ARCHIVE})"

if [ -f "${ARCHIVE}.sha256" ]; then
  expected=$(cat "${ARCHIVE}.sha256")
  if command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')
  else
    actual=$(sha256sum "$ARCHIVE" | awk '{print $1}')
  fi
  [ "$expected" = "$actual" ] || die "checksum mismatch — the archive changed after it was written.
    expected ${expected}
    actual   ${actual}
  The target database has NOT been touched."
  log "checksum matches the one recorded at backup time"
else
  log "WARNING: no .sha256 beside the archive — storage corruption cannot be detected here"
fi

log "reading the archive's table of contents BEFORE touching ${PGDB}"
if ! $COMPOSE exec -T -i db pg_restore --list < "$ARCHIVE" > /dev/null 2>&1; then
  die "pg_restore cannot read this archive — it is truncated or corrupt.
  The target database has NOT been touched, which is the point: a half-applied restore leaves
  neither the old database nor the new one."
fi
log "archive is readable"

# ---------------------------------------------------------------- target-side (archive proven ok)

log "restoring into ${PGDB} (--clean --if-exists: replace objects, single transaction)"
$COMPOSE exec -T -i db pg_restore -U "$PGUSER" -d "$PGDB" --clean --if-exists --single-transaction \
  < "$ARCHIVE"

log "RESTORE COMPLETE"
