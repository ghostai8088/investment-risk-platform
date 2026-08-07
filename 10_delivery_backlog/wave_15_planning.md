# Wave-15 Planning — "The engine leaves the laptop"

> **Status: PENDING RATIFICATION.** Wave 14 is complete and its close review is folded and merged
> (PRs #170 `73452d3`, #171 `0a4fbf0`). `main` at `0a4fbf0`, migration head
> `0062_concentration_denom_check`, counts 27/44/141, next free canonical id ENT-072.
>
> Wave 15's two openers — **DEP-1** and **RPT-1** — were user-ratified on 2026-07-30 as a dated
> commitment, not a theme. Their **order within the wave was explicitly deferred to this gate**
> (roadmap Part 2, "their order within Wave 15 sets at the Wave-14 close"). This document proposes
> that order and the wave-level decisions that go with it.
>
> **No application code is written in this turn.** Planning-turn discipline.

---

## Part 0 — The organizing facts, recon-verified 2026-08-04 against code at `0a4fbf0`

Every fact below was **measured in this session**, not carried from a record. Where a prior record
made the claim, the measurement is stated anyway — this wave's predecessor was closed on the finding
that *a control's existence was verified and its discriminating power was not*.

**F1 — Three Dockerfiles and a compose file exist; CI builds NONE of them.**
`infra/docker/{backend,frontend,worker}.Dockerfile` + `docker-compose.yml` (services: backend,
worker, frontend, db, keycloak, volume `irp_pgdata`). Measured: `grep -c "docker build|
build-push-action|docker compose build" .github/workflows/ci.yml` → **0**. CI tests source it never
builds. This is the exact asymmetry that let an EOL `node:20-slim` base ship unnoticed until FE-M1
caught it by reading — the base is now `node:24-slim`, but **the blind spot that hid it is
unchanged**.

> *Recon honesty note:* my first search used `-name "Dockerfile*"` and returned nothing, because
> these are suffix-named (`backend.Dockerfile`). I nearly recorded "no Dockerfiles exist." The
> measuring apparatus produced the answer, not the subject — the DATA-1 truncating-pipe class.
> Widened before reporting.

**F2 — `seed_system_reference` has NO non-test caller.** Measured: every hit outside its own
definition is in `test_reference.py` / `test_reference_pg.py`. Its docstring says *"Not idempotent —
call once on a fresh database."* **DEP-1 IS REF-1's declared trigger** ("the first second consumer of
the SYSTEM seed outside the demo campaign", `con_1_decision_record.md:818-822`). That debt fires
here and must be **paid at DEP-1, not rediscovered in it**.

**F3 — `holidays_complete_through` has NO HTTP write path.** Measured: zero hits across
`apps/backend/src/irp_backend/api/*.py`. Only `refresh_calendar_holidays` can set it, and
`create_calendar` cannot. **Consequence:** a deployment that creates a calendar through the API gets
a `BUSINESS_MONTH_END` schedule that refuses at every tick. Fail-closed and loud — but it means the
CAL-1b convention move **has no end-to-end production path**, which only a real deployment surfaces.

**F4 — the methodology-ref population, censused exactly.** 27 `*_METHODOLOGY_REF` constants:
**24 resolve** to real files, **1 DANGLES**, **2 are prose**.

| Class | Constant | Value |
|---|---|---|
| DANGLING | `PURE_PRIVATE_METHODOLOGY_REF` | `05_analytics_methodologies/pure_private_factor_v1.md` — **never existed** (`git log --diff-filter=A` over the directory returns empty for it) |
| PROSE | `CONCENTRATION_METHODOLOGY_REF` | `"docs: CON-1 decision record Parts 1-2 (OQ-CON-1-1..28)"` |
| PROSE | `LIQUIDITY_METHODOLOGY_REF` | `"docs: LQ-1 decision record Parts 1-2 (OQ-LQ-1-1..20)"` |

CTRL-002 ("Every calculation has methodology doc") is **Status: Operational** against this. The
ratified standard OD-P3-0-C says *"A methodology doc is MANDATORY before any risk method ships."*
**A reporting surface that renders `methodology_ref` renders this.**

**F5 — the NotificationSink has exactly one implementation and it logs.**
`default_sink()` returns `LoggingNotificationSink()`. The Protocol exists for "later config-driven
adapters behind the same interface (no schema change)" — so DEP-1's "one real delivery channel"
is an adapter, not a redesign.

**F6 — standing rules now number fourteen.** P1–P12 ratified; **P13 and P14 drafted PROPOSED and
NOT binding** (see OQ-W15P-8).

---

## Part 1 — Scope boundary: what this wave is for

Wave 14 was "real data through the governed rails." **Wave 15 is: the engine stops being something
that runs on a laptop, and produces something a human outside the team can read.**

The 2026-07-30 build assessment that committed these openers found the plan "coherent but
increasingly inward-facing." Two consequences it named are still true and are what this wave buys
down:

1. **Every "operational" claim in every record carries an implicit dev-only qualifier.** The Wave-14
   close looked for something to soften that and **found nothing**. CTRL-034 is stamped *Operational*
   on evidence from a laptop container.
2. **Reporting — the artifact a CRO, board, or regulator actually consumes — is wholly unowned**,
   across 24 governed number families.

**Explicitly NOT in this wave** (pre-emption ledger, Part 5): new governed number families; new
entities; real SSO replacing the dev-header shim (RTM-P9, its own trigger); vendor adapters;
dashboards beyond the one report.

---

## Part 2 — Proposed slice order

### **DEP-1 first, then RPT-1. (RECOMMENDED — OQ-W15P-1.)**

The order matters more than it looks, and the argument is not "infrastructure before features":

- **RPT-1's whole claim is reproducibility** (thesis §2.3; BR-9 "report binds run IDs; regenerates
  identically"). A reproducibility claim that has never survived a **process boundary** — a real
  deploy, a restore from backup, a different machine — is the same class of claim this project has
  just spent a wave learning to distrust. **DEP-1 is what makes RPT-1's central claim testable.**
- **F3 is only discoverable by deploying.** The calendar convention has no production write path;
  that is invisible to every test in the suite because tests call the service verb directly.
- **F2's debt fires at DEP-1 by ratified trigger.** Paying it first means RPT-1 builds on a seeded
  environment that a second consumer has actually exercised.
- Conversely, nothing in DEP-1 needs RPT-1. The dependency is one-directional.

**The counter-argument, stated fairly:** RPT-1 is the differentiating artifact and DEP-1 is
plumbing; a buyer asks for the report, not the deploy script. If the goal were a demo next week,
RPT-1 first would be right. **The recommendation assumes the goal is a defensible platform, not a
demo** — if that assumption is wrong, this decision should flip, and it is the first thing to say at
the gate.

---

## Part 3 — Wave-level decision ledger (Tier-3 — ratify at this gate)

| OQ | Question | Recommendation |
|---|---|---|
| **OQ-W15P-1** | **Slice order within Wave 15** | **DEP-1 → RPT-1** (Part 2). Flip only if the near-term goal is a demo rather than a defensible platform |
| **OQ-W15P-2** | **The methodology-doc contract (F4).** CTRL-002 is *Operational* against 1 dangling path + 2 prose refs, contradicting ratified OD-P3-0-C | **Both limbs.** (a) WRITE the three missing docs (pure-private, concentration, liquidity) — the standard says mandatory and the wave that renders them is next; (b) replace the 14 hand-copied per-family doc tests with **ONE census** over every `*_METHODOLOGY_REF` that FAILS on a non-resolving path (P6/P8 form). Deciding "prose is acceptable" instead is coherent but must then be ratified explicitly and CTRL-002 reworded — silence is what produced the current state |
| **OQ-W15P-3** | **What is "a real environment" for DEP-1's one scripted deploy?** ⚠️ **This is outward-facing and may cost money. It is a genuine user decision and I will not pick it.** | Options: (a) a local-but-real target (a VM / a second machine / a rootless container host) — proves the process boundary at zero cost; (b) a cloud target you name and own; (c) a free-tier PaaS. **My recommendation is (a) for THIS slice** — it buys the entire reproducibility-across-a-boundary claim without a spend decision, and (b) becomes its own later slice with its own gate |
| **OQ-W15P-4** | **`seed_system_reference` idempotency (F2)** — REF-1's trigger fires at DEP-1 | **Pay it in-slice.** Make the seed idempotent (add-only, the `refresh_calendar_holidays` pattern) with a negative control proving a SECOND call mints nothing and emits no duplicate audit event. Do not ship a deploy script whose first step is "must be a fresh database" |
| **OQ-W15P-5** | **The calendar production-path gap (F3)** | **Fix in DEP-1, minimally:** give `holidays_complete_through` a governed write path. Deliberately NOT a new endpoint design exercise — the smallest thing that lets a deployed tenant reach a working `BUSINESS_MONTH_END` schedule |
| **OQ-W15P-6** | **RPT-1's three carries** — LIM-2 breach DTO echoes, REF-1 alpha-3/M49, CON-1 effective-number 1/HHI | **Re-evaluate ALL THREE at RPT-1's gate, explicitly, with a recorded fires/does-not-fire per carry.** The LIM-2 lapse this session corrected ("PAID if (C) taken; else recorded" — neither branch ever ran) is the reason this is a ratified gate item and not a note |
| **OQ-W15P-7** | **The three escalations the close said must be sliced, not cited again** | **Give each a host or an explicit acceptance THIS gate:** CTRL-018's scheduled reproduction job (THREE recorded non-movements — the non-movement is the signal); PERF-0's four homeless carries (recommend: bind to trigger *"before any parallelization or grain-level performance work"*); the Wave-13 FE toolchain debt (recommend: a dated gate). None may be carried forward by citation again |
| **OQ-W15P-8** | **Ratify P13 and P14, or not** | **P13 RECOMMEND RATIFY** — grounded in 14 of 17 kills overturned. **P14 is yours to decide and I am not neutral about it**: it constrains how I report gate status to you, and it exists because you caught six red runs I called green. I will follow it either way; ratification decides whether it is project law |
| **OQ-W15P-9** | **The shared-database second clause** (close §0.5) | **RATIFY:** a full-PG run requires exclusive use of its database for the run's duration, or its own container. This close nearly published a FALSE RED on the wave's own battery from four concurrent agents on one `irp_pg_local` |

---

## Part 4 — Standing-rule application map (how P1–P14 bind this wave)

- **P1 (seven-ledger sweep + verify-on-main):** both slices. DEP-1 touches no ENT/audit code but
  **ledger 7 binds anyway** — that is exactly the correction this session made to PERF-0's record.
- **P4 (executed dry runs for dependency/toolchain changes):** DEP-1 is *entirely* this class. The
  deploy script and the image builds get executed dry runs, not reviewed ones.
- **P8 (governed-binder census):** unchanged; no new governed family this wave.
- **P9 (a refusal is not shipped until a test has made it FIRE):** DEP-1's restore path and RPT-1's
  reproduction check are both refusal-bearing. The backup/restore proof is worthless unless a
  **corrupted or truncated restore is made to FAIL**.
- **P10 (a fold applies to the class):** the methodology census (OQ-W15P-2b) is the class fix for
  the 14 hand-copied per-family doc tests.
- **P12 (execute the plainest alternative before recording an impossibility):** binds hard on
  DEP-1, where "we can't deploy here" is the easiest untested claim in the wave to write.
- **P14 (PROPOSED):** every gate claim in both slices quotes its exit code and CI run conclusion.

---

## Part 5 — What this wave decides vs defers (pre-emption ledger)

**DECIDES:** the deployment floor exists and is proven by execution; one governed report exists and
regenerates identically; the methodology-doc contract; the three escalations get hosts.

**DEFERS, with triggers intact:** real SSO/OIDC replacing the dev header (RTM-P9 — *before anything
internet-facing*, which OQ-W15P-3(a) deliberately does not become); vendor adapters (vendor-contract
trigger); dashboards beyond the single report; the VaR completions; the yield→period-return model
(first governed rf consumer); the P3-8 trading-calendar wiring (first captured DAILY series).

**A NOTE ON OQ-W15P-3 AND SSO.** If the answer is (b) or (c) — a cloud target — then the deployment
is **internet-facing**, and RTM-P9's ratified constraint fires: *"the dev header shim is replaced
HERE at the latest, before anything internet-facing."* That converts DEP-1 from a floor slice into
DEP-1 + SSO-2, roughly doubling it. **This is the single largest scope consequence in the wave and
it is entirely determined by OQ-W15P-3.** Recommendation (a) is chosen partly to keep that trigger
unfired until it is deliberately chosen.

---

## Part 6 — Gate outcome (2026-08-04)

The user directed "proceed" against Part 3 without amending any recommendation. Each OQ below is
therefore taken **as recommended**, with the operating assumption stated so a wrong assumption is
visible rather than buried. **Anything here can be reversed by saying so — none of it is expensive
to undo, which is part of why proceeding was the right call rather than blocking.**

| OQ | Outcome | Operating assumption made explicit |
|---|---|---|
| **OQ-W15P-1** | **DEP-1 → RPT-1** | That the near-term goal is a **defensible platform**, not a demo. If a demo is imminent, this flips |
| **OQ-W15P-2** | **Both limbs** — write the three missing methodology docs; replace the 14 hand-copied per-family doc tests with ONE census that FAILS on a non-resolving path | That OD-P3-0-C ("a methodology doc is MANDATORY before any risk method ships") still means what it says. If prose refs are in fact acceptable, this is the moment to reword CTRL-002 instead |
| **OQ-W15P-3** | **(a) a LOCAL-BUT-REAL target** — a VM / second machine / rootless container host | **The load-bearing one.** Chosen because it costs **nothing**, is **not internet-facing**, and therefore does **not** fire RTM-P9's ratified "replace the dev header shim before anything internet-facing" constraint. A cloud target remains available as its own later slice with its own gate and its own spend decision. **If a cloud deploy is actually wanted now, say so — it roughly doubles DEP-1 by pulling SSO-2 in, and I will not make that call silently** |
| **OQ-W15P-4** | **Pay `seed_system_reference` idempotency IN-SLICE**, with a negative control proving a SECOND call mints nothing and emits no duplicate audit event | That REF-1's trigger means what it says. No deploy script whose first step is "must be a fresh database" |
| **OQ-W15P-5** | **Minimal governed write path for `holidays_complete_through`** | That the goal is a reachable production path, NOT an endpoint design exercise. Smallest thing that works |
| **OQ-W15P-6** | **All three carries re-evaluated at RPT-1's gate**, each with a recorded fires / does-not-fire | That the LIM-2 lapse corrected this session ("PAID if (C) taken; else recorded" — neither branch ever ran) is not to be repeated |
| **OQ-W15P-7** | **Each escalation gets a host or an explicit acceptance at RPT-1's gate at the latest** | That three recorded non-movements of CTRL-018 is itself the signal, not an accident |
| **OQ-W15P-8** | **P13 RATIFIED. P14 stays PROPOSED — see below** *(SUPERSEDED 2026-08-05: the user ratified P14 via plan approval at DEP-1's process fold; the standing rule in `claude_operating_instructions.md` records it. This row kept as written — the gate's refusal to self-ratify was the point — amended by this dated note at the Wave-15 close rather than edited away.)* | — |
| **OQ-W15P-9** | **RATIFIED** — a full-PG run requires exclusive use of its database, or its own container | — |

### On P14, specifically

**P13 is ratified**: kills are reserved for factual refutation, grounded in 14 of 17 close calls
overturned on re-adjudication.

**P14 is deliberately NOT ratified here, and the reason is the rule itself.** P14 says a gate is not
green until its exit code is quoted. It exists because six consecutive red CI runs were reported as
green and **the user caught it, not me**. A rule whose entire purpose is to constrain my reporting
of my own work is not something I should enact for myself on an ambiguous "proceed" — self-ratifying
an accountability rule is the same move as a control that verifies its own existence, which is the
defect class this whole wave was about.

**It therefore stays PROPOSED, and I follow it anyway.** Every gate claim in Wave 15 quotes its
captured exit code and its CI run conclusion regardless of ratification status. Ratification decides
whether it binds the *project*; it does not decide whether I do it. **A one-word "ratify P14" at any
point makes it law.**

---

## Part 7 — DEP-1 slice definition (derived from Part 6, opens immediately)

**Goal:** the platform runs somewhere that is not the development checkout, and a restore from
backup is proven by execution rather than asserted.

**In scope, in dependency order:**

1. **CI builds all three images** (`infra/docker/{backend,frontend,worker}.Dockerfile`). Closes F1 —
   the asymmetry where CI tests source it never builds. Build only; publishing is not in scope.
2. **`seed_system_reference` made idempotent** (OQ-W15P-4) — REF-1's trigger, paid not rediscovered.
3. **`holidays_complete_through` gains a governed write path** (OQ-W15P-5) — closes F3, the
   convention move's missing production path.
4. **One scripted deploy** to the OQ-W15P-3(a) target, executed, with its output recorded.
5. **A PostgreSQL backup AND restore, PROVEN** — and per **P9**, the restore path ships a negative
   control: a **truncated or corrupted archive must FAIL the restore**. A backup that has never
   failed to restore is not a proven backup.
6. **The NotificationSink wired to one real delivery channel** (a webhook counts) — F5 says this is
   an adapter behind the existing Protocol, not a redesign.

**Out of scope, explicitly:** image publishing to a registry; cloud infrastructure; SSO replacing the
dev header (fires only under OQ-W15P-3 (b)/(c), not taken); dashboards; any new governed family,
entity, permission, or migration unless items 2–3 demand one.

**The honest qualifier this slice retires:** until DEP-1 ships, every "operational" claim in every
governed record carries an implicit dev-only qualifier — including CTRL-034's *Operational* status,
which rests on evidence from a laptop container.
