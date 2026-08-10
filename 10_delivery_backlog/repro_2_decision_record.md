# REPRO-2 decision record — the reproduction control becomes STARTABLE

**Status:** DRAFT v1 — pre-verifier

**Wave 17, slice 2** (the ratified Part 2.19 sequence). Branch `repro-2-planning`. Design
authority once ratified: THIS record.

## 1. What this slice is

CTRL-018 is real code no deployed tenant can run: the sweep exists, the alarm channel exists and
is now observable (ALERT-1), and yet a real tenant cannot START any of it — there is no schedule
write path, the worker ticks only hand-configured tenant ids, and the verdicts the control
produces are readable by nobody. REPRO-2 is the startability slice: the schedule WRITE path
(API + UI, discharging the SCH-1 `schedule.manage` forward-gate), the verdict READ surface
(where carry (n)'s redaction residual comes due), worker tenant discovery for tenants that
actually exist (the ONBOARD-1a carry, riding here by name), more families registered, and the
demo/deploy seeding carry (m).

Carries riding in, verbatim sources: ONBOARD-1a ("the worker still does not tick a created
tenant — `IRP_TENANT_IDS` stays deploy config; the carry rides to REPRO-2 by name");
REPRO-1 (m) ("no demo or deploy path creates a REPRODUCTION schedule — only the proof harness
does"); REPRO-1 (n) ("`first_divergence` can carry governed VALUES on the UNREPRODUCIBLE path …
before any read surface is added over ENT-073"); SCH-2's reserved question ("a create/pause API
is its own slice with its own maker-checker question").

## 2. Decisions (OQ-REP2-1…7)

### OQ-REP2-1 — Worker tenant discovery: SUPERSEDE OQ-SCH-1-2=A, registry-driven

SCH-1 ratified `IRP_TENANT_IDS` as "config, NOT a DB sweep" — and the circumstance that decision
was made under no longer holds: at SCH-1 there WAS no tenant registry, so "a DB sweep" meant an
app-side cross-tenant read with no legitimate home. ONBOARD-1a built ENT-074 as a deliberately
PLATFORM-GLOBAL table (no tenant_id, no RLS) read on every authenticated request — the worker can
read it with no BYPASSRLS and no RLS bypass of any kind.

**Recommendation:** the supervisor derives its tenant list from the registry — ACTIVE tenants
only (not SYSTEM, not SUSPENDED) — re-read each tick, so an onboarded tenant starts ticking
within one tick of creation and a suspended one stops. `IRP_TENANT_IDS` becomes an optional
RESTRICTION filter (if set, intersect with the registry — a deploy can still pin a subset;
it can no longer invent a tenant the registry does not know). **Zero ACTIVE tenants = idle and
re-poll**, not the SCH-1 refuse-to-start: under config, an empty list was evidence of
misconfiguration; under the registry it is the truthful state of a fresh platform, and a worker
that crash-loops until the first onboarding would make ONBOARD-1's ignition depend on restart
orchestration. The supersession is stated AT this gate (the REF-1/AD-013-R2 precedent for
amending a ratified decision with its circumstances).

### OQ-REP2-2 — The schedule WRITE path: `schedule.manage`, and the reserved maker-checker question answered NO

`POST /schedules`, `POST /schedules/{id}/pause`, `POST /schedules/{id}/resume` — guarded by the
ordinary `require_permission("schedule.manage")`, discharging the SCH-1 forward-gate (the
`UNROUTED_FORWARD_GATES` entry is DELETED; the census forces it). Validation is the EXISTING
`create_schedule` fail-closed rule set (cadence/family CHECKs, the CAD-1 FK guard) — the route
adds transport, not rules.

**The reserved question, answered: NO four-eyes on schedule writes.** SOD-04's class is authority
and limits — acts whose EFFECT is a change in who may do what or what the book may hold. A
schedule changes WHEN governed machinery runs; every act it triggers is itself fully governed
(run → snapshot → model gates → IA results), creating one grants nobody anything, and pause is
reversible. Putting cadence in the four-eyes queue would put "turn the nightly check on" behind a
second admin — friction on exactly the control this wave exists to start. Revisit trigger: the
first schedule family whose DISPATCH itself changes authority, money, or a limit.

### OQ-REP2-3 — The verdict READ surface: carry (n) comes due, and the recommendation is the STRICT discharge

`GET /reproduction/checks` (tenant-local list; filters family/verdict/since), gated on
`schedule.view` (the ALERT-1 audience — control-plane oversight, auditor included). Payload per
row: `id`, `family_key`, `verdict`, `rows_compared`, `rows_diverged`, `subject_run_id`,
`calculation_run_id`, `system_from`.

**`first_divergence` is the carry-(n) field** — on the DIVERGED path it names row KEY + FIELD
only (mutation-proven at REPRO-1); on the UNREPRODUCIBLE path it embeds a binder's redacted
exception text, and `_redact` bounds that text WITHOUT guaranteeing the absence of every
identifier. **Recommendation — the strict option:** the payload carries `first_divergence`
verbatim ONLY for DIVERGED rows; for UNREPRODUCIBLE rows it carries the exception CLASS NAME
alone (e.g. `OperationalError`) — never the message body. The bounded-but-unguaranteed text
stays in the database for DB-grade investigation; no read surface transports it, so the residual
carry (n) named is DISCHARGED BY EXCLUSION rather than accepted. **Alternative (rejected):
expose the redacted text to the five-role audience and accept the bounded residual — cheaper for
operators, but it converts a named residual into a standing acceptance on the platform's most
identifier-dense text channel.**

### OQ-REP2-4 — Families: register ALL SIXTEEN mechanically-adaptable families

`REPRODUCIBLE_FAMILIES` holds 3; the pinned-unregistered list holds 18, of which SIXTEEN are
"not yet adapted" for mechanical reasons (key/field declarations; binder resolution by model
code for the shared-table pairs; parameter read-back for the windowed families) and TWO are
structurally blocked in ways that are THEIR families' decisions, not this slice's:
CONCENTRATION (no snapshot consume path — pins current-head classifications) and LIQUIDITY (wall
clock inside a shipped governed refusal — a model-identity question).

**Recommendation:** register all sixteen. Each adapter is the same formula the first three
proved (declare the row key + compared fields; resolve the binder; the sweep machinery is
unchanged), each ships its own reproduce-green + planted-divergence test, and the coverage
census's exact-set assertion moves 3+18 → 19+2 with the two structural reasons preserved
verbatim. Sixteen adapters is the bulk of this slice's size (L) — a subset would be cheaper and
would leave "more families" as a permanently unfinished adjective; the roadmap sentence gets a
number instead.

### OQ-REP2-5 — Carry (m): the deploy path seeds the demo tenant's schedule; onboarding does NOT auto-create

`deploy.sh`'s demo seed gains one nightly REPRODUCTION schedule for the demo tenant (carry (m)
discharged — a deployed stack has a running control without hand-work). Tenant ONBOARDING does
NOT auto-create a schedule: a schedule is a governed act with an actor and a cadence choice, and
the platform does not manufacture governed acts nobody asked for. The UI (OQ-REP2-6) makes it
one click for a real tenant's admin-adjacent roles; `no_schedule` on the ALERT-1 panel already
points at the gap by name.

### OQ-REP2-6 — The UI: a "Reproduction" operations screen

One screen under the OPS conventions: the tenant's schedules (list + create + pause/resume — the
FE's write path via `writes.ts`, `schedule.manage` refusals rendered plainly) and the verdict
table (the OQ-REP2-3 payload; DIVERGED rows visually loud; UNREPRODUCIBLE rows carrying their
class name). The scheduled-runs ledger (`GET /schedules/runs`, shipped at SCH-2 with no
consumer) gets its first reader on the same screen. Nav: Operations group, between Alerting and
Reports.

### OQ-REP2-7 — Mint census and control disposition

NOTHING minted: no permission (`schedule.manage`/`schedule.view` reused — the forward-gate
discharge is the opposite of a mint), no entity, no event code (`SCHEDULE.CREATE`/`UPDATE` exist
from SCH-1 and fire from the service the routes call), no migration (fourth consecutive
no-migration... no: THIRD slice with none — state it plainly, not as a superlative). Route count
moves consciously (+4). **CTRL-018 stays Implemented** — this slice makes it STARTABLE, and the
row says so; Operational's trigger: the first observed scheduled green on a real (non-proof,
non-demo) tenant.

## 3. Proofs (the remit binds these; P18 throughout)

- The write path: create → the schedule fires on the next worker tick (end-to-end through the
  REAL supervisor loop, not a direct service call) ↔ a `schedule.view`-only principal is 403'd
  writing; pause → the tick skips it ↔ resume → it fires; the census forward-gate entry deletion
  is itself the routing proof.
- Discovery: an onboarded (registry-ACTIVE) tenant is ticked with NO config change ↔ a SUSPENDED
  tenant stops being ticked ↔ SYSTEM is never ticked; `IRP_TENANT_IDS` set → intersection
  honored; zero ACTIVE tenants → the worker idles and logs, does not exit; mutant: discovery
  reverts to config-only → the onboarded-tenant test reddens.
- The verdict read: DIVERGED rows carry field+key `first_divergence` ↔ an UNREPRODUCIBLE row's
  payload contains the class name and NOT the message body (a planted binder failure with a
  distinctive marker string in its message: the marker must NOT appear anywhere in the HTTP
  response — the carry-(n) discharge, asserted on the wire); permission parity (holder ↔ 403 ↔
  401); tenant-locality with a live second tenant.
- Sixteen adapters: per family, reproduce-green on an untouched subject ↔ a planted divergence
  detected (the REPRO-1 pattern); the coverage census exact-set 19+2.
- Deployed: `prove_reproduction.sh` extends — the schedule is created OVER HTTP by a seeded
  `schedule.manage` principal (replacing the harness-side create for one arm), and the verdict
  list is read over HTTP after the planted divergence, with the marker-absence assertion live.
- Mutation battery group `repro-2` (committed, `needs_pg` where PG-tier); both tiers + full-PG +
  CI-watch-to-green, exit codes quoted (P14).

## 4. Non-goals (each with its trigger, P19)

- **CONCENTRATION and LIQUIDITY registration** — their structural blockers are their families'
  decisions; triggers: CONCENTRATION's next consume-path slice; LIQUIDITY's next model-identity
  gate.
- **Schedule DELETE** — pause is the retirement verb (the SCH-1 IA posture); trigger: a real
  retention requirement.
- **Acknowledgement / re-fire (carry (j))**, unchanged from ALERT-1.
- **A push alerting leg**, unchanged from ALERT-1.
- **Backfill of missed ticks** — honest gaps stay honest (the SCH-1 no-backfill doctrine);
  trigger: a regulatory completeness requirement on a scheduled family.

## 5. Verifier ledger

Pass 1 (adversarial, five lanes): PENDING.
