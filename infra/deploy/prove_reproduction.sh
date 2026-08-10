#!/usr/bin/env bash
#
# REPRO-1 (Wave-16): CTRL-018's OBSERVED SCHEDULED GREEN, and the first time the deployed WORKER
# ever connects to a database and does governed work.
#
# WHY THIS AND NOT THE UNIT TESTS. `test_reproduction` proves the sweep in one process against one
# in-memory SQLite file. CTRL-018 claims something different in kind: that every night, on the real
# deployment, a machine re-derives the platform's governed numbers and says whether they came back
# the same. Everything in that sentence crosses a boundary the unit tier never touches — a
# container, a real PostgreSQL with FORCE RLS, the scheduler's due-tick arithmetic, and the worker
# process itself.
#
# AND THE WORKER'S DATABASE PATH HAS NEVER EXECUTED, ANYWHERE. `.env.example` ships
# IRP_TENANT_IDS empty, deploy.sh deliberately deploys it empty, and the supervisor fails closed on
# an empty list — so deploy.sh's worker step proves only that the REFUSAL fires. RPT-2 recorded
# that as a carry and named REPRO-1 as its host. This is where it is paid.
#
# BOTH ARMS RUN THROUGH THE WORKER. The negative arm is not an in-process shortcut: the seed
# creates TWO schedules precisely because a (schedule, tick) pair fires exactly once, so the
# divergence arm needs its own tick bucket. A proof whose failure path has never executed is an
# assumption wearing a proof's name.
#
# Usage: ./infra/deploy/prove_reproduction.sh

set -euo pipefail

PROJECT="irp-repro1"
# 55432 = deploy.sh, 55433 = prove_backup_restore.sh, 55435 = prove_report_identity.sh, 55436 here.
export POSTGRES_PUBLISH_PORT="${POSTGRES_PUBLISH_PORT:-55436}"
ENV_FILE="infra/deploy/.env.reproduction"
export IRP_ENV_FILE="$ENV_FILE"
COMPOSE="docker compose -p ${PROJECT} --env-file ${ENV_FILE}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# The tenant the seeded subject lives in — shared with prove_report_identity.sh's harness, because
# this proof reuses its seeded governed report as the reproduction subject. Re-declaring a
# different id here is precisely the bug the first deployed run produced.
PROOF_TENANT="9f000000-0000-4000-8000-000000000001"

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\n!!! FAILED: %s\n' "$*" >&2; exit 1; }

cleanup() {
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$ENV_FILE"
}
trap cleanup EXIT

# Generated from .env.example every run, never a developer's .env — the DEP-1 rule: a deployment
# proof that depends on an untracked file proves something about that machine.
cp .env.example "$ENV_FILE"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
PGUSER="${POSTGRES_USER:-irp}"
PGDB="${POSTGRES_DB:-irp}"

if docker ps --format '{{.Names}} {{.Ports}}' | grep -q ":${POSTGRES_PUBLISH_PORT}->"; then
  holder=$(docker ps --format '{{.Names}} {{.Ports}}' | grep ":${POSTGRES_PUBLISH_PORT}->" | head -1)
  die "host port ${POSTGRES_PUBLISH_PORT} is already published by: ${holder}
    Stop it, or re-run with POSTGRES_PUBLISH_PORT=<free port>."
fi

# Reads one KEY=VALUE out of a harness command's output. Deliberately not `grep | cut` on the whole
# blob: a value that happened to contain the key name would silently win.
field() { printf '%s\n' "$2" | sed -n "s/^$1=//p" | tail -1 | tr -d '[:space:]'; }

log "0. a migrated stack"
$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
# worker is built HERE, not lazily: compose reuses an existing project image, and a stale worker
# would smoke a build that no longer exists (the psycopg-less image prove_report_identity caught).
$COMPOSE build migrate worker >/dev/null
$COMPOSE up -d db >/dev/null
$COMPOSE up --exit-code-from migrate migrate >/dev/null
head_rev=$($COMPOSE exec -T db psql -U "$PGUSER" -d "$PGDB" -tAc "SELECT version_num FROM alembic_version" | tr -d '[:space:]')
echo "   alembic_version=${head_rev}"
# The expected head is DERIVED from the migrations the image actually carries, not hand-pinned.
# The pinned literal this replaces went RED the first time a migration landed after it (0066, at
# the Wave-16 close) — the same hand-mirrored-global-fact class as the 21 test-side head pins that
# went stale in the same fold, except this copy lived in infra where no unit tier could catch it.
# The check still asserts what it always asserted (migrate ran to head, exactly one head exists);
# it just asks alembic for the fact instead of a human remembering to update a string.
expected_heads=$($COMPOSE run --rm --entrypoint alembic migrate heads | awk '/head/{print $1}')
[ "$(printf '%s\n' "$expected_heads" | grep -c .)" = "1" ] || die "expected exactly ONE alembic head, got: ${expected_heads}"
[ "$head_rev" = "$expected_heads" ] || die "expected head ${expected_heads}, got ${head_rev}"

log "1. SEED a governed report and the nightly reproduction schedule"
seed_out=$($COMPOSE run --rm -e IRP_ALLOW_PROOF_SEED=1 --entrypoint python migrate \
  -m irp_shared.deploy.reproduction_proof seed) || die "the seed step failed"
echo "$seed_out"
SCHEDULE_A=$(field SCHEDULE_A "$seed_out")
[ -n "$SCHEDULE_A" ] || die "the seed did not emit a schedule id"
HEALTH_READER_ID=$(field HEALTH_READER_ID "$seed_out")
ALARM_RECIPIENT_ID=$(field ALARM_RECIPIENT_ID "$seed_out")

log "2. THE DEPLOYED WORKER TICKS — its database path, executed for the first time"
# The one-shot entrypoint (retained at CAD-1 for exactly this): one tenant, one tick, exit 0.
tick1=$($COMPOSE run --rm --entrypoint python worker \
  -m irp_worker.scheduler --tenant "$PROOF_TENANT") || die "the worker tick FAILED"
echo "   ${tick1}"
printf '%s' "$tick1" | grep -q "fired=" || die "the worker printed no tick summary"

log "3. WHAT THE TICK ACTUALLY DID"
after1=$($COMPOSE run --rm --entrypoint python migrate \
  -m irp_shared.deploy.reproduction_proof report) || die "the read-back failed"
echo "$after1"
sweeps=$(field SWEEP_RUN_COUNT "$after1")
outcomes=$(field OUTCOMES "$after1")
verdicts=$(field VERDICTS "$after1")
[ "$sweeps" = "1" ] || die "expected exactly 1 REPRODUCTION run after the first tick, got ${sweeps}"
printf '%s' "$outcomes" | grep -q "DISPATCHED" \
  || die "the scheduled run did not land as DISPATCHED: ${outcomes}"
printf '%s' "$verdicts" | grep -q "REPORT:MATCH" \
  || die "the report family did not reproduce on the deployed stack: ${verdicts}"
echo "   a scheduled sweep re-derived a governed report and it MATCHED"

log "4. NEGATIVE ARM (P9): plant a divergence and require the SAME machinery to say NO"
# Without this the whole script could be satisfied by a sweep that compares nothing. The plant is
# on the STORED side and needs the append-only trigger suspended — which is that control working,
# and is why this lives in a proof harness and not in an application path.
#
# The plant step ALSO creates the second schedule. Every schedule with interval_days=1 shares the
# same UTC-midnight grid, so seeding both up front made the FIRST tick fire both (fired=2) and
# consumed the negative arm's tick bucket before there was anything to catch — the arm would have
# run against an already-used bucket, found nothing to fire, and passed while proving nothing.
plant_out=$($COMPOSE run --rm -e IRP_ALLOW_PROOF_SEED=1 --entrypoint python migrate \
  -m irp_shared.deploy.reproduction_proof plant) || die "the plant step failed"
echo "$plant_out"
[ -n "$(field SCHEDULE_B "$plant_out")" ] || die "the plant step did not create the second schedule"

tick2=$($COMPOSE run --rm --entrypoint python worker \
  -m irp_worker.scheduler --tenant "$PROOF_TENANT") || die "the second worker tick FAILED"
echo "   ${tick2}"

after2=$($COMPOSE run --rm --entrypoint python migrate \
  -m irp_shared.deploy.reproduction_proof report) || die "the second read-back failed"
echo "$after2"
verdicts2=$(field VERDICTS "$after2")
alarms=$(field ALARM_EVENTS "$after2")
outcomes_alarm=$(field ALARM_OUTCOMES "$after2")
trigger=$(field TRIGGER_ENABLED "$after2")
printf '%s' "$verdicts2" | grep -q "REPORT:DIVERGED" \
  || die "A PLANTED DIVERGENCE WENT UNDETECTED — this control cannot fail, so it proves nothing.
    verdicts: ${verdicts2}"
[ "$alarms" -ge 1 ] 2>/dev/null \
  || die "the divergence was recorded but phase 5 raised NO alarm (ALARM_EVENTS=${alarms})"
# SENT, not merely "an event exists". The review's HIGH: with no `breach.review` holder the alarm
# short-circuits to SUPPRESSED before touching the sink, so the old ALARM_EVENTS>=1 assertion was
# satisfied by the no-recipient sentinel — the arm passed while the DELIVERY path never ran.
printf '%s' "$outcomes_alarm" | grep -q "SENT" \
  || die "the alarm was RECORDED but never DELIVERED — outcomes: ${outcomes_alarm}.
    A SUPPRESSED-only result means no recipient existed and the sink was never called."
# tgenabled='O', not "a pg_trigger row exists": a DISABLED trigger still has a catalog row, so the
# old count(*) could not fail for the condition it existed to detect.
[ "$trigger" = "1" ] || die "the append-only trigger is not ENABLED after the plant (tgenabled != 'O')"
echo "   the divergence was DETECTED, DELIVERED (${outcomes_alarm}), and the fence is back"

log "5. ALERT-1: the alarm channel's own HEALTH, read over HTTP on the deployed stack"
# The backend is not otherwise part of this proof — the arms above run through the worker — so it
# comes up here. Without it the health route could not be exercised at all, and an arm that cannot
# run is an arm that proves nothing (the C20 finding at the design's first verifier pass).
$COMPOSE up -d backend >/dev/null
BACKEND_PORT="${BACKEND_PORT:-8000}"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
[ "$ok" = "1" ] || die "the backend never became healthy"

[ -n "$HEALTH_READER_ID" ] || die "the seed emitted no HEALTH_READER_ID"
health=$(curl -sS -w '\n%{http_code}' "http://localhost:${BACKEND_PORT}/reproduction/alarm-health" \
  -H "X-User-Id: ${HEALTH_READER_ID}" -H "X-Tenant-Id: ${PROOF_TENANT}")
code=$(printf '%s' "$health" | tail -1)
body=$(printf '%s' "$health" | sed '$d')
[ "$code" = "200" ] || die "the schedule.view holder got ${code} on the health route: ${body}"
# The channel just delivered a real divergence through the real sink, so it must READ as working.
# A surface that cannot say "healthy" after a successful night cannot say "unhealthy" credibly.
printf '%s' "$body" | grep -q '"healthy":true' \
  || die "the alarm channel reads UNHEALTHY after a night it demonstrably worked: ${body}"
printf '%s' "$body" | grep -q '"sweep_overdue":false' \
  || die "a sweep that fired minutes ago reads as OVERDUE: ${body}"
# Counts-only: the payload must not carry verdict content (carry (n)'s boundary, live).
printf '%s' "$body" | grep -q 'first_divergence' \
  && die "the health payload leaked verdict CONTENT: ${body}"
echo "   schedule.view holder -> 200, healthy=true, counts-only"

# The refusal twins (P18). Being PAGED by the channel does not entitle you to audit it.
recipient_code=$(curl -sS -o /dev/null -w '%{http_code}' \
  "http://localhost:${BACKEND_PORT}/reproduction/alarm-health" \
  -H "X-User-Id: ${ALARM_RECIPIENT_ID}" -H "X-Tenant-Id: ${PROOF_TENANT}")
[ "$recipient_code" = "403" ] || die "the breach.review-only recipient got ${recipient_code} on the health route — expected 403"
bare_code=$(curl -sS -o /dev/null -w '%{http_code}' "http://localhost:${BACKEND_PORT}/reproduction/alarm-health")
[ "$bare_code" = "401" ] || die "an unauthenticated health read got ${bare_code}, not 401"
echo "   alarm recipient -> 403; bare -> 401 (the fence, live)"

log "REPRODUCTION PROVEN ON THE DEPLOYED STACK — a scheduled worker tick re-derived a governed
    artifact from its pinned inputs and reported MATCH; a planted divergence made the same
    machinery report DIVERGED and raise an alarm. The worker's database path executed for the
    first time (RPT-2 carry b). AND the channel's own health is now readable over HTTP, with its
    permission fence proven live (ALERT-1)."
