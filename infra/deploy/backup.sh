#!/usr/bin/env bash
#
# DEP-1 (Wave-15): take a PostgreSQL backup — and VERIFY the archive before calling it a backup.
#
# THE FORMAT IS THE CONTROL. This uses pg_dump's CUSTOM format (-Fc), not a plain .sql dump, and
# that is a correctness decision rather than a preference:
#
#   * A plain .sql dump is a stream of statements. `psql < dump.sql` on a TRUNCATED file applies
#     everything up to the truncation point and exits 0. You get a partially-restored database and
#     a success message — a recoverable outage silently converted into confident data loss.
#   * The custom format carries a table of contents and per-entry structure. `pg_restore` refuses a
#     damaged archive instead of half-applying it.
#
# A backup is also not a backup until something has read it back. This script therefore verifies the
# archive it just wrote (pg_restore --list) and records a checksum, so the restore side can detect
# corruption that happened in STORAGE rather than in writing.
#
# Usage: ./infra/deploy/backup.sh <output-archive-path> [compose-project]

set -euo pipefail

OUT="${1:?usage: backup.sh <output-archive-path> [compose-project]}"
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

mkdir -p "$(dirname "$OUT")"

log "dumping ${PGDB} (custom format — pg_restore can refuse a damaged archive; a .sql stream cannot)"
$COMPOSE exec -T db pg_dump -U "$PGUSER" -d "$PGDB" -Fc > "$OUT"

bytes=$(wc -c < "$OUT" | tr -d '[:space:]')
[ "$bytes" -gt 0 ] || { echo "FAILED: the archive is empty"; exit 1; }
log "archive written: ${OUT} (${bytes} bytes)"

# A written file is not a readable archive. Read it back before claiming a backup exists.
log "verifying the archive is readable (a backup nothing has read is not a backup)"
entries=$($COMPOSE exec -T -i db pg_restore --list < "$OUT" | grep -c ';' || true)
[ "${entries:-0}" -gt 0 ] || { echo "FAILED: pg_restore could not read the archive just written"; exit 1; }
echo "   table of contents readable — ${entries} entries"

# Checksum for the restore side: catches corruption in STORAGE, which archive-readability alone
# does not (a byte flipped inside a data block can still leave a readable TOC).
if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$OUT" | awk '{print $1}' > "${OUT}.sha256"
else
  sha256sum "$OUT" | awk '{print $1}' > "${OUT}.sha256"
fi
echo "   sha256 recorded: $(cat "${OUT}.sha256")"

log "BACKUP VERIFIED"
