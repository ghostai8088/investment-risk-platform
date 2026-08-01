# CAL-1 Decision Record — ENT-006 holiday-calendar resolution (Wave-14 slice 3)

**Status: RATIFIED 2026-08-01 — OQ-CAL-1-1…12 ALL approved as recommended** (user: "proceed" on
the briefed gate). The ratification includes the **CTRL-034 mint approved at H-05** (OQ-9 — the
first control mint since P0.5, R-10-routed, approved at this gate) and the **CAL-1a/1b split**
(OQ-12) — CAL-1a is the operative next implementation. Grounding pinned at `main = 8637b67`
(2026-08-01). Method (the ratified per-slice discipline): six-lane recon fan-out against code at
the pin (185 facts) → single-threaded draft → a four-lane refute-by-default verifier pass with an
independent citation lane (2 BLOCKING, 6 HIGH, 5 MED, 8 LOW — ALL folded; Part 6 is the fold
ledger) → the Tier-3 gate. Nothing below is ratified until the gate.

The operative scope is the roadmap row (`delivery_roadmap.md:268`) and the wave plan's
enumerated workstreams (a)–(f) (`wave_14_planning.md:146`), plus the rf vendor-diligence
control moved here by REF-1's split trigger (b) (`wave_14_planning.md:342-345`).

---

## Part 0 — the facts that shape the slice (all cited at `8637b67`)

### 0.1 The substrate that exists — and what is genuinely absent

- **G1.** ENT-006 is **REALIZED (partial)**, not unbuilt: tables `calendar` + `calendar_holiday`
  have existed since migration `0008`, EV temporal class (mutable, `record_version`, no
  append-only trigger), members of the ORIGINAL five-table hybrid set (AD-013-R1) — so a SYSTEM
  holiday seed needs **no tenancy work**. (`04_data_model/canonical_data_model_standard.md:74`;
  `migrations/versions/0008_reference_data.py:80-108`; `reference/models.py:62-68`)
- **G2.** `calendar_holiday` is already the right shape for the job: `holiday_date` (Date) under
  `UNIQUE(tenant_id, calendar_id, holiday_date)`. The classification scheme/node machinery is the
  WRONG shape (hierarchy adjacency, no date column) — a holiday calendar cannot ride it.
  (`0008_reference_data.py:93-108`; `0056_classification.py:122-131`)
- **G3.** The only holiday DATA in the platform is a token SYSTEM seed: one XNYS calendar with
  exactly TWO 2026 holidays (Jan 1, Dec 25), written by a non-idempotent one-shot ("Not
  idempotent — call once on a fresh database"). (`reference/bootstrap.py:41-45,65-66`)
- **G4.** **No holiday-refresh write path exists.** Holiday children are written only at parent
  create; `update_calendar` patches head attributes only (name/mic/is_active — child patching
  scoped out at "§7"); the calendar API is POST/GET only. (`reference/calendar.py:26-27,100-104`)
- **G5.** **No business-day logic exists anywhere** — both month-end predicates say so in their
  docstrings, and the dependency tree cannot supply it: `shared-python` declares `sqlalchemy`
  only; numpy is pinned TEST-ONLY ("never an irp_shared runtime dep"); pandas and every calendar
  library (exchange_calendars, pandas_market_calendars, holidays) are absent from all manifests.
  A business-day helper is hand-rolled or a new-dependency decision. (`scheduling/service.py:110-111`;
  `rolling_kernel.py:72-74`; `requirements-dev.txt:16`)
- **G6.** The DQ rule-type vocabulary is exactly `NOT_NULL` / `ALLOWED_VALUES` / `RANGE`; there is
  no COMPLETENESS/gap rule type (the DB doesn't constrain `rule_type` — the vocabulary lives only
  in the code registry). The existing "completeness" machinery (`dq/gates.py`) is a derived
  presence gate built ON `NOT_NULL` over a synthetic one-row-per-gap dataset; gap detection stays
  caller-computed. REF-1 deferred `RULE_TYPE_COMPLETENESS` with the trigger "the first vendor
  dataset whose acceptance is expressed as an expected key set in the rule itself".
  (`dq/rules.py:21-23`; `dq/gates.py:5-8`; `0006_data_quality_skeleton.py:51`;
  `ref_1_decision_record.md:240-242`)
- **G7.** `synthetic/scale.py::perf_business_day` is NOT business-day logic despite its name — a
  fixed epoch offset, called by `scripts/perf_probe.py`. A grep-driven "business_day" refactor
  must not sweep it in. (`synthetic/scale.py:532-535`)

### 0.2 The three predicate sites, and the true shape of the trap

- **G8.** The month-end arithmetic exists in **THREE sites**: (i) the scheduler's
  `scheduling/service.py::_last_weekday_of_month` (weekend-only preceding roll); (ii) its
  **deliberate hand-mirror** `perf/rolling_kernel.py::last_weekday_of_month` (perf must not import
  scheduling — that module imports the entire risk+exposure compute stack; per the OQ-W12C-3b
  standing rule a hand-mirrored contract carries a CONFORMANCE PIN); (iii)
  `perf/rolling_kernel.py::is_month_end`, the **acceptance** predicate, which admits the calendar
  last day OR the last weekday. (`scheduling/service.py:107-116`; `rolling_kernel.py:65-70,76-79,91-93`;
  `claude_operating_instructions.md:68-72`)
- **G9.** The conformance pin is `packages/shared-python/tests/test_rolling_kernel.py:61-65`: it
  imports the scheduler's private rule and sweeps every month 2024–2035 asserting the two
  implementations identical. It pins only the mirrored PAIR; `is_month_end`'s acceptance set is
  not pinned to either.
- **G10.** `is_month_end`'s second clause is **load-bearing** (the RM-1 truncation lesson,
  recorded in the code itself at `rolling_kernel.py:87`): 2026-01-31 is a Saturday and 2026-05-31
  a Sunday — a firm valuing on the preceding Friday is fully GIPS-conforming, and a strict
  calendar-month-end gate would refuse a compliant book. Because it admits two dates, ONE month
  can hold two accepted grid points — a documented hazard `assert_month_aligned`'s five-condition
  criterion works around. Any CAL-1 change must **WIDEN acceptance (add the holiday-preceding
  business day), never substitute** — the verifier walked all five conditions against a widened
  third date class: none breaks under widening; substitution breaks (1)/(2)/(5) on shipped
  weekend-roll series. (`rolling_kernel.py:87-89,105-197`)
- **G11.** Every in-src consumer of `is_month_end` sits inside `assert_month_aligned` (four call
  sites, all REFUSALS — never a skip), which has exactly two production callers: the RM-1 binder
  and the SR-1 binder, both converting to governed input refusals PRE-create (zero
  run/result/run-audit rows minted on refusal). (`rolling_kernel.py:135-189`;
  `rolling_service.py:206-213,260`; `sharpe_service.py:210-217`)
- **G12.** **Verified in code (the record's own sharpening — the wave plan makes no claim either
  way):** no scheduler path reaches perf. `FAMILY_REGISTRY` — the declared single source of what
  is schedulable — contains exactly VAR and EXPOSURE_AGGREGATE; `run_rolling_risk` has exactly
  ONE non-test caller (the demo stage) and `run_sharpe_ratio` likewise. The trap therefore runs
  ONLY through data and dates (G13–G14), never through a dispatch link.
  (`scheduling/service.py:450-465`; `demo/rm1_stage16.py:339`; `demo/sr1_stage17.py:312`)
- **G13.** The mechanical trap arm: an EXPOSURE tick struck on a non-trading day has no marks and
  FAILS; `record_failed_dispatch` permanently occupies the `(schedule_id, scheduled_for)` bucket
  ("the NEXT grid tick is the retry, not this one") — at monthly cadence, "the difference between
  a retry next poll and a lost month". RM-1 then refuses a series missing an interior month-end,
  so ONE lost month poisons the downstream governed number. (`scheduling/events.py:41-47`;
  `scheduling/service.py:566-570`; `worker/scheduler.py:50-53`)
- **G14.** The atomicity constraint, confirmed against live code BY EXECUTION (verifier lane 1):
  `is_month_end(2027-05-28)` → **False**; `last_weekday_of_month(2027, 5)` → **2027-05-31**
  (Memorial Day). The true last business day before Memorial Day 2027 would be REFUSED by the
  shipped RM-1/SR-1 series the moment the scheduler learns holidays — exactly the wave plan's
  fact 6. The scheduler roll and the perf acceptance must move in the SAME slice.
  (`wave_14_planning.md:67-72`; `rolling_kernel.py:91-93`; executed)
- **G15.** The quantified residual this slice makes **RETIRABLE** (not "retires" — under the
  grandfathering in OQ-3/OQ-4, a live `CALENDAR_MONTH_END` schedule keeps the weekend-only grid
  until it is retired and recreated under the new kind; the transition path is a named
  deliverable, OQ-3): 4 of 144 months (2.8%) over 2024–2035 collide with holidays under the
  weekday rule — 2024-03-29, **2027-05-31 (Memorial Day — the forcing function, comfortably
  post-wave)**, 2029-03-30, 2032-05-31. Independently re-derived by the verifier via Easter
  computus + last-Monday arithmetic over the full 144-month sweep: exactly these four.
  (`scheduling/events.py:44-47`; `sch_2_decision_record.md:34`; executed)
- **G16.** The scheduler tick is an END-OF-DAY instant that becomes the EXPOSURE run's
  `as_of_valid_at` — a **bitemporal cutoff** reaching `Valuation.valid_from <= valid_at`, not a
  label. Moving the roll date moves the economic as-of of scheduled governed runs — and EXPOSURE
  is model-LESS (`requires_model_version=False`), so **the model_version mechanism cannot carry
  the scheduler-side convention change**. (`scheduling/service.py:119-135,450-461`)

### 0.3 The model-version machinery, and the only lawful convention move

- **G17.** `model_version` is immutable-append-only ("change = new version"): NO amend/supersede/
  deprecate path exists anywhere in the registry service (confirmed by a full 580-line read); ORM
  before_update/before_delete listeners raise `AppendOnlyViolation` on ModelVersion/
  ModelAssumption/ModelLimitation; a same-label re-register with different identity is refused
  with an instruction to mint a NEW `version_label`. (`model/models.py:182-184,300-316`;
  `model/service.py:489-499`)
- **G18.** The ratified precedent for a governed convention change to a shipped model, three
  times over (RS-1 `v2-ewma`/`v2-shrinkage-eb`; DS-2; MF-1 sibling labels): a NEW `version_label`
  on the SAME model code, the old label GRANDFATHERED. **The mechanism, precisely:** the new
  label is only the (tenant, model, label) IDENTITY; the convention itself is a registrar-stamped
  machine-readable ASSUMPTION literal (prefix pattern `estimator_convention=…`) parsed from the
  version's assumption texts by a `declared_*_parameters` gate — **ABSENT (zero rows) ⇒ the
  implicit grandfathered v1; AMBIGUOUS (>1) or a stray literal ⇒ refused fail-closed. Nothing is
  ever parsed from the label string.** The precedent parameterizes an estimator branch inside one
  binder; CAL-1 extends the pattern to a kernel predicate shared by two binders — a wider use,
  named as such. (`risk/bootstrap.py:2398-2448`; `perf/bootstrap.py:432-449,560-596`;
  `desmoothing_service.py:350-385`)
- **G19.** RM-1 = `perf.rolling_risk` `v1`. Its registered LIMITATION names this exact change as
  the future: "MONTH-END CONVENTION IS HOLIDAY-FREE in v1 … A full holiday-aware convention is a
  recorded v2." Its registered GRID assumption pins GIPS 2.A.23.a/b. (`perf/bootstrap.py:787-790,
  797-810,849-852`)
- **G20.** SR-1 = `perf.sharpe` `v1`. Its rf leg joins by MONTH KEY (year, month) — never by
  date — so it is numerically insulated from month-end DATE moves; but its grid is inherited from
  RM-1's, so its registered text is not. (`perf/bootstrap.py:907-910,952-955`; `sharpe_kernel.py:79-93`)
- **G21.** Editing a shipped assumptions tuple is the platform's named silent-divergence trap,
  refused in code in both registrars: `resolve_or_register_version` returns an existing version
  UNTOUCHED on a SELECT hit, so an edited tuple leaves earlier-registered tenants carrying
  different text under the same label. REF-1's OQ-22 was moved here on exactly this ground.
  (`perf/bootstrap.py:877-882,1004-1008`; `ref_1_decision_record.md:254-263`)
- **G22.** Disclosure owed at the gate: RM-1's v1 GRID assumption text was edited in place at the
  Wave-13 close (enumeration 3→5 conditions — the tuple itself says so), so **v1 registered text
  already diverges by registration date**; CAL-1's briefing must not claim v1 text is uniform.
  (`perf/bootstrap.py:807-810`)
- **G23.** Past readings are safe by construction ONLY through the result tables:
  `rolling_risk_result` / `sharpe_ratio_result` bind run + snapshot + model_version as NOT-NULL
  hard FKs under ORM guards AND the PG P0001 append-only trigger; old rows durably keep v1. The
  RUN row's `model_version_id` is a nullable GUID with NO DB FK — a soft stamp; never cite it as
  the enforcement point. (`perf/models.py:368-383,456-463,513-516`; `0054_rolling_risk_result.py:202-206`;
  `calc/models.py:49-51`)
- **G24.** Nothing retires v1 automatically: `assert_model_version_of` checks family membership
  only; after a v2 mint, v1 still binds new runs unless call sites repoint. Retiring v1
  fail-closed would itself be a governance act (a 2L REJECTED validation record, CTRL-022).
  (`model/service.py:520-571`)
- **G25.** Tier-3 mechanics (binding this slice's center of gravity): "Methodology/model choices,
  grains, entity mappings, scope narrowings" are explicit OQ sign-off ledger items requiring user
  sign-off BEFORE being encoded. (`claude_operating_instructions.md:135-136,146`)

### 0.4 The scheduler side: purity, buckets, and the live-grid hazard

- **G26.** `current_tick` is documented and implemented as a **pure function of (anchor, interval,
  cadence, now)** — it never reads the ledger, the DB, or a wall clock; that purity IS the
  poll-idempotency argument, and **the DB unique constraint `uq_scheduled_run_schedule_tick` on
  the exact instant is the declared "hard race backstop"** (the worker classifies exactly that
  constraint as benign SKIPPED_DUPLICATE). A holiday-aware tick that reads the DB breaks the
  purity contract — and, unless re-established at the DB grain, forfeits the backstop (OQ-5).
  (`scheduling/service.py:154-156,477-494`; `worker/scheduler.py:56-70,93-98`)
- **G27.** `INV-SCH-1`: `dispatch_one` and `record_failed_dispatch` both recompute the expected
  tick at the write boundary and refuse any other value — so the write-boundary recomputation must
  provably see the SAME holiday set the poll used. (`scheduling/service.py:226-228`)
- **G28.** The live-grid hazard, evidence-grounded in both directions: due-ness is "no
  `scheduled_run` row at exactly the recomputed tick instant". A convention/data change that
  RE-VALUES an already-fired period's tick creates a fresh bucket → **the same economic month
  fires a SECOND governed run** (the uq dedup keys on the exact timestamp). A never-fired old date
  that is no longer the recomputed tick becomes **structurally unfireable — silent skip, zero
  evidence** (the scheduler has NO cursor; missed grid points are "honest gaps" by doctrine).
  Burned buckets are PERMANENT (IA ledger + uq, no re-fire verb; ≤33-day out-of-band repair
  window). (`scheduling/service.py:236-247,290-297`; `wave_14_planning.md:64-66`)
- **G29.** Late dispatch of a still-current past tick is proven normal behavior (the SCH-2 demo
  polls 2026-06-01 and fires the 2026-05-29 end-of-day tick). (`demo/sch2_stage15.py:63-65`)
- **G30.** The cadence vocabulary: `INTERVAL` + `CALENDAR_MONTH_END` live; `"CALENDAR"` is
  **reserved-and-unused for a future GENERAL business-day cadence** (not month-end). The 0053
  CHECKs (`ck_schedule_cadence_kind_vocab`, `ck_schedule_interval_days_by_cadence`,
  `ck_schedule_model_version_by_family`) are TOTAL enumerations failing closed — any new cadence
  kind is un-insertable until a migration amends them; SQLite unit tiers carry none of these
  CHECKs, so the `_validate_config` service mirror must move in the same commit. The verifier's
  enumeration of every `cadence_kind` switch site confirms an unknown kind raises `ScheduleError`
  at `current_tick` and skip-and-reports at `select_active_due` — no site silently mishandles a
  new kind. `schedule.cadence_kind` is `String(20)` — a hard length ceiling on the new kind's
  name. (`scheduling/events.py:51-54`; `0053_schedule_cadence_family.py:88-119`;
  `scheduling/service.py:167-168,278-287,609-610`; `scheduling/models.py:94`)
- **G31.** The schedule row's grid is deliberately frozen for life: `_UPDATABLE = ("name",
  "status")` — a re-cadence is a NEW schedule, "this keeps the grid fixed for a schedule's life
  and sidesteps the re-cadence grid-shift seam (recorded v2)". And `update_schedule` performs NO
  `_validate_config` — making any grid-defining attribute updatable would ship with no validation
  rail on the update path. (`scheduling/service.py:69-72,730-734`)
- **G32.** Exception discipline on the poll path: `select_active_due` skip-and-reports a
  per-schedule `ScheduleError` (never raising into the worker's `for` header — a raise there
  aborts ALL FOUR tick phases for the tenant, the B3 lesson). Any holiday-resolution failure
  reaching the poll must surface as `ScheduleError`. (`scheduling/service.py:278-287`)
- **G33.** `schedule`/`scheduled_run` are symmetric FORCE RLS ("NEVER hybrid"); the schedule
  table at head is the 0049+0053 composite — 19 columns, **no calendar column, no calendar FK**.
  (`0049_scheduling.py:67-103,136-144`; `scheduling/models.py:18,69-108`)
- **G34.** FK-guard evidence for the calendar binding: the P3-5 guard pattern matches
  `tenant_id == acting_tenant` EXACTLY, which would REFUSE the SYSTEM-owned XNYS calendar; the
  hybrid RLS policy is asymmetric (USING own-OR-SYSTEM, WITH CHECK own-only) and **PG FK checks
  bypass RLS**. **The precedent pair already shipped at REF-1 in this same wave:** migration 0056
  gives `classification_assignment` (proprietary symmetric) a hard FK into hybrid
  `classification_scheme`, and OQ-REF-1-20 ratified a fail-closed own-OR-SYSTEM resolver
  (implemented at `reference/service.py:325-359` — "admit an own-tenant OR SYSTEM_TENANT row").
  `schedule → calendar` is the SECOND symmetric→hybrid FK, and its guard is a REUSE/extension of
  that shipped pattern, added to the existing `create_schedule` guard block ("gated on the
  registry DECLARATION, never on the value"). (`portfolio/guards.py:31-36`;
  `0008_reference_data.py:153-158`; `0056_classification.py:180-185`; `reference/service.py:325-359`;
  `ref_1_decision_record.md:244-247`; `scheduling/service.py:673-688`)
- **G35.** Tenant-default binding has no home: **no tenant registry table exists** ("the app has
  no tenant registry" — worker docstring; tenant_id is a bare UUID column everywhere) — that
  option requires NEW storage. SYSTEM-XNYS-implicit binding needs no DDL but hides the binding
  from the schedule row. (`worker/scheduler.py:218-219`; `reference/bootstrap.py:41-45`)
- **G36.** The demo grid CAL-1 extends: exactly ONE stage creates a schedule
  (`DEMO-MONTH-END-EXPOSURE`, CALENDAR_MONTH_END, boundary Friday 2026-05-29 — a WEEKEND roll;
  **no holiday boundary exists anywhere in the demo**). Executed check: Memorial Day 2026 =
  05-25, no 2026 XNYS holiday falls on any last-weekday month-end — the seeded boundary is
  retro-stable under real XNYS data; assert it in-test at CAL-1b.
  (`demo/sch2_stage15.py:56-57,192-203`; executed)
- **G37.** RM-1's demo stage builds its 19-boundary grid FROM `last_weekday_of_month`, and SR-1's
  demo deliberately dates rf rows on the CALENDAR month end so ~5/12 months differ from the
  book's last-weekday pins (exercising the month-key join) — a predicate change moves the demo's
  data-generation grid and could silently weaken what sr1_stage17 demonstrates (the OPS-1 "demo
  that cannot reach a control" lesson). (`demo/rm1_stage16.py:121`; `demo/sr1_stage17.py:247`)

### 0.5 The diligence control, the rf obligation, and P3-8

- **G38.** REF-1's split trigger (b) FIRED: the rf vendor-diligence control moved here, for three
  converging reasons — the draft's discharge home (editing `SHARPE_ASSUMPTIONS`) is forbidden
  (G21), the ratified deliverable is a PAIR ("checklist artifact + control-matrix row", an
  auditable artifact not prose), and **a CTRL mint is an R-10 act with H-05 as approver — not
  R-07 — and no slice has minted one since P0.5**. The capture-time convention-field option is a
  SECOND migration if taken — a named split candidate. (`ref_1_decision_record.md:254-263,414-415`;
  `wave_14_planning.md:143,278-279,337,342-345`)
- **G39.** The rf obligation's factual basis: `capture_benchmark_return` accepts ANY
  `return_date` (controlled-vocab + finiteness checks only); the Sharpe binder catches a PARTIAL
  shift, never a UNIFORM one — a uniformly one-month-late vendor series is undetectable in-data
  BY DESIGN, so no code gate can close it; enforcement is the declared convention + onboarding
  diligence. Claiming code-side enforcement would repeat SR-1's recorded overclaim class.
  (`marketdata/benchmark_series.py:800-817`; `sharpe_kernel.py:86-93`; `snapshot/service.py:1975-1979`;
  `sr_1_decision_record.md:204`)
- **G40.** Exhaustive rf consumers (the control's blast surface): sharpe_kernel (join +
  missing-month refusal), sharpe_service (adjudication + cross-tenant assert), perf/models
  (`risk_free_benchmark_id` NOT NULL), perf/bootstrap (registered texts), snapshot/service (window
  builder), demo/sr1_stage17, backend perf API. No other module consumes a risk-free rate.
  (`sharpe_service.py:222,306,402` et al.)
- **G41.** P3-8's completeness OQ, verbatim origin: the missing-day hazard is recorded LOUD and
  trading-calendar completeness validation deferred because wiring the calendar tables "is its
  own scope"; today the benchmark-side runtime check refuses only a ZERO-row window — a partial
  vendor gap still compounds silently. The wave plan carries it as a named CAL-1 slice-gate OQ
  because the prerequisite dissolves here; re-deferral is an allowed disposition. Changing the
  acceptance is a governed convention change to a SHIPPED number's input path, not a quiet
  tightening. (`p3_8_decision_record.md:16,47`; `wave_14_planning.md:127-130`;
  `benchmark_relative_service.py:324`)
- **G42.** No source library and no licensing-gate precedent exist: zero dependency hits for any
  calendar package; FE-M1/OPS-1's dependency gates were SECURITY-audit gates (the string "licens"
  appears in neither record — executed grep) — the closest precedents are OQ-W14P-3's
  taxonomy-licensing analysis and the fx_rate tenancy classification ("NEVER hybrid — `fx_rate`
  is per-tenant vendor-licensed" market data). The ratified conditional: **holiday sets land as
  SYSTEM rows conditional on an open/public source**; a licensed vendor calendar lands as tenant
  captures. (`wave_14_planning.md:218-221`; `p2_2_fx_rate_implementation_plan.md:122`;
  `fe_m1_decision_record.md:82`)
- **G43.** GIPS 2.A.23.b already lives in the repo verbatim (record + code): *"As of the calendar
  month end or the last business day of the month"* — the quote at `rm_1_decision_record.md:107`
  (exact) and `rolling_kernel.py:16-17` (lowercase "as of"), with the in-code truncation lesson
  at `rolling_kernel.py:87`. Rule 6a (strengthened 2026-07-30): every citation enters ONLY as a
  verbatim quoted passage with a locator, verified by an independent citation lane reading only
  the source. (`delivery_roadmap.md:329-335`)
- **G44.** DATA-1 is explicitly sequenced on CAL-1 delivering the diligence control — descoping
  it breaks the inserted slice's premise. (`delivery_roadmap.md:269`)

### 0.6 Registers, ledgers, ids, and expected deltas

- **G45.** REQ-SMR-004: the QS-11 holiday/business-day half is HOMED at CAL-1 in both register
  halves (backbone + RTM, Status In-Progress); QS-10 day-count stays trigger-based. QS-11's
  normative text requires the rolling convention be **declared** (following / modified following /
  preceding). Other calendar-touching REQs whose clauses dissolve or advance here, exhaustively:
  REQ-MKT-001 (trading-day counts open clause), REQ-MKT-005/006, REQ-PRF-002 ("calendar
  validation deferred" — the P3-8 clause), REQ-PRF-003 ("holiday-free month-end convention"),
  REQ-PRF-004. (`requirements_backbone.md:142,297`; `requirements_traceability_matrix.md:40,51,55-60`;
  `numerical_quant_standards.md:65-66`)
- **G46.** ENT-006's transition is **REALIZED (partial) → fully realized** (roll math delivered),
  recorded per the ENT-064 exemplar convention. Next-free ids at the pin (each attacked by the
  verifier and confirmed): **ENT-070**, **CTRL-034** (library ends CTRL-033; no diligence row
  exists), **AD-020** (newest entry AD-013-R2), **migration 0059** (head 0058). Whether CAL-1
  needs an AD row is now a function of OQ-6: the AD-014-conformant option needs none; an accepted
  deviation from AD-014 would be ADR-admissible (the AD-004-R1 honest-deviation precedent) and is
  decided at the gate. (`canonical_data_model_standard.md:74,97,119`; `control_matrix_skeleton.md:74`;
  `architecture_decision_log.md:22,27-29`)
- **G47.** Scheduling-adjacent control rows, exhaustively: CTRL-003 (family/model CHECK, changed
  at SCH-2), CTRL-018 (scheduled reproduction job, Planned — touched by OQ-6's reproducibility
  argument), CTRL-022 (validation-cadence ceiling), CTRL-031 (tick supervisor, OPERATING since
  CAD-1), OD-038. (`control_matrix_skeleton.md:44-74`)
- **G48.** The counts triple 26/41/136 = distinct registered `Model.code` for the demo tenant /
  `ModelValidation` rows / COMPLETED `CalculationRun` rows — a POSITIONAL pin in the CON-1 demo
  suite (earlier suites carry 25/40/133). A new-version_label move leaves 26 UNCHANGED (same
  codes); new validation records move 41; new demo COMPLETED runs move 136 — all MEASURED on a
  fresh battery, never derived. (`test_demo_stage9zzzzzzzzzz_con1_pg.py:256-279`)
- **G49.** The execution rules that bind this slice, by pointer: the P1 seven-ledger sweep incl.
  verify-on-main; both-tier-before-push; P7 lesson-forms (census > floor > matcher; no
  declarative prose); the pre-flight manifests for the "New migration" and "New demo stage"
  change classes — the ~21 head-pin assertions, HYBRID_TABLES parity, every DDL identifier
  ≤63 chars named explicitly in BOTH ORM and migration (`test_migration_identifiers.py`), the
  per-table CI RLS step, the downgrade smoke, the count-pin relay, superuser-bypasses-RLS
  scoping — plus, as a separate obligation, the CON-1 lesson that constraint-name parity is
  verified against the live `pg_constraint` catalog, not text.
  (`claude_operating_instructions.md:151-156,251-267,308-348`; `con_1` close, roadmap)

---

## Part 1 — what this record adds to or corrects in the wave plan's framing (drift-on-verify)

1. **The plan's fact 6 is CONFIRMED and REFINED (not corrected).** The ratified trap statement —
   the 2027-05-28 date "would be REFUSED by the governed rolling-risk series the moment the
   scheduler learns holidays" — is exactly what the code shows (G14, executed). This record ADDS
   the census that rules out any dispatch-mediated variant: no scheduler path reaches perf at
   all (G12), so the atomicity obligation runs through data, dates, and the FAILED-bucket arm
   (G13) only. *(The pre-verifier draft framed this as a correction against a quoted claim the
   plan never made — a fabricated quotation the verifier's citation lane caught; struck, and
   recorded in Part 6.)*
2. **"New/amended model_version" resolves to NEW ONLY (G17–G18, G21).** The roadmap row's
   "new/amended" disjunction (confirmed verbatim by the citation lane) is closed by code: there
   is no amend path — a new `version_label` on the same model code, v1 grandfathered. (The
   register/roadmap wording should be tightened at the close.)
3. **ENT-006 is not unbuilt (G1).** The wave plan's "(b) the holiday-refresh write path that does
   not exist today (children are create-once)" is confirmed verbatim; the register effect is
   partial→full realization, not a mint.
4. **The scheduler-side convention cannot ride model_version (G16).** EXPOSURE is model-less;
   a separate carrier is required (OQ-3). The wave plan does not name this fork.
5. **v2 is the platform's first DATA-dependent governed convention (G26–G28), and AD-014 binds
   it.** "No governed derived output without a bound, reproducible input snapshot"
   (`architecture_decision_log.md:22`); the wave plan's own fact 3 states "AD-014 requires the
   compute to read only pinned content", and LQ-1 in this same wave is mandated a snapshot
   COMPONENT_KIND on the same argument. The perf-side holiday input must be pinned or its
   non-pinning must be ratified as an explicit recorded deviation (OQ-6) — the pre-verifier
   draft recommended the deviation WITHOUT citing AD-014, the exact uncited-AD class ruled
   BLOCKING at Wave-14 planning; rebuilt in this revision.

---

## Part 2 — the decision ledger (Tier-3 OQs, with recommendations)

### OQ-CAL-1-1 — the atomic set, corrected. **Recommend as stated.**

The set that moves together is: the scheduler roll, its perf mirror, the `is_month_end`
acceptance (WIDENED, never substituted — G10), and the conformance pin (G8–G9) — plus the v2
registrations (OQ-2) and the scheduler-side carrier (OQ-3). Explicitly OUT: registering RM-1/SR-1
as schedulable families (no wave mandate; a separate slice concern), and any backfill/repair of
historical buckets (G28's permanence stands).

### OQ-CAL-1-2 — the perf-side carrier AND its data binding. **Recommend A — REBUILT after the verifier (one BLOCKING + one HIGH folded).**

A: `perf.rolling_risk` **v2** and `perf.sharpe` **v2** (SR-1 moves in lockstep — its grid text
inherits RM-1's even though its rf month-key join is numerically insulated, G20) as NEW version
labels on the SAME codes; v1 grandfathered byte-identical; no forced retirement (G24); no new
model code (26 count unchanged, G48). **The mechanism is the assumption-literal pattern, not
label parsing (G18):** the v2 registrar stamps machine-readable literals —
`month_end_convention=BUSINESS` and `holiday_calendar=<calendar code>` (default `XNYS`) — into
the v2 assumptions tuple; a `declared_month_end_parameters` gate parses them from the version's
assumption texts with the precedent's full discipline (absent ⇒ implicit weekend-only v1;
ambiguous or stray literal ⇒ fail-closed refusal). **The data binding (the verifier's BLOCKING
gap):** the binder resolves the declared calendar code under the tenant session via the shipped
own-OR-SYSTEM resolver pattern (G34 — own-tenant row wins, SYSTEM serves the default), and
refuses fail-closed pre-create when the calendar is unresolvable or its declared coverage (OQ-4)
does not span the series — a governed input refusal, zero rows minted (G11's pattern). The
resolved holiday set is then PINNED per OQ-6. Kernel consequence: `is_month_end` /
`last_business_day` take an optional holiday-set parameter defaulting to empty (v1 call sites
byte-identical — verified feasible: both binders resolve the model version BEFORE the alignment
gate; no breaking signature change at any call site).

### OQ-CAL-1-3 — the scheduler-side carrier: a NEW cadence kind, with the transition path named. **Recommend A.**

A: mint **`BUSINESS_MONTH_END`** (18 chars — inside the `String(20)` ceiling, G30; the name is
fixed here, not "at implementation") — the holiday-aware last-business-day tick — and leave
`CALENDAR_MONTH_END` untouched (grandfathered, the exact mirror of the v1/v2 label pattern).
Existing schedules' grids never move (G31's frozen-grid doctrine preserved). NOT the reserved
`"CALENDAR"` name — reserved for a general business-day cadence, a different concept (G30,
matching OD-SCH-2-C). **The transition path for live `CALENDAR_MONTH_END` schedules is a named
deliverable, not an implication (verifier HIGH):** retire-and-recreate under the new kind (the
frozen-grid doctrine's own remedy), documented as a runbook note in the record at CAL-1b and
demonstrated in the demo (the new-kind schedule is created alongside the legacy one); until an
operator performs it, a legacy schedule KEEPS the 2.8% collision residual — G15's "retirable".
Migration 0059 amends the two cadence CHECKs (total enumerations, G30) with the
`_validate_config` mirror in the same commit.

### OQ-CAL-1-4 — the calendar↔schedule binding: per-schedule FK, create-only, kind-gated, FAIL-CLOSED on resolution and coverage. **Recommend A.**

A: nullable `calendar_id` FK on `schedule` (migration 0059), with a CHECK completing the total
enumeration: `BUSINESS_MONTH_END → calendar_id NOT NULL`; legacy kinds → `calendar_id NULL`.
Create-only (NOT added to `_UPDATABLE` — G31). The FK guard reuses the shipped own-OR-SYSTEM
pattern (G34 — the SECOND symmetric→hybrid FK, after 0056's assignment→scheme). **Fail-closed
semantics (verifier HIGH — the empty/invisible-set fail-open):** (i) tick resolution for
`BUSINESS_MONTH_END` resolves the calendar HEAD under the session and raises `ScheduleError`
(skip-and-report, G32) when it is not visible; (ii) the calendar head gains a DECLARED
`holidays_complete_through` (Date, nullable, additive column in 0059) set explicitly by the
refresh verb — a tick whose month exceeds it refuses (`ScheduleError`), and the perf v2 binder
mirrors the refusal as a governed input refusal. Declared, never derived: a MAX over child rows
cannot represent a gap (the NOTIF-1 lesson) — an uncovered year must refuse, not silently
compute weekday-only answers indistinguishable from the legacy kind (the LIM-1 fail-open
standard). B (tenant default) requires storage that does not exist (G35); C (implicit SYSTEM
XNYS) hides the binding from the schedule row. No backfill: the existing demo schedule keeps its
legacy kind and NULL calendar.

### OQ-CAL-1-5 — grid idempotency under the new kind: a DB-GRAIN PERIOD KEY, not a service check. **Recommend A — REBUILT after the verifier (one HIGH, three lanes concurring).**

The pre-verifier draft claimed a due-select period check "closes structurally" — false under
concurrency: two polls straddling a holiday-refresh commit resolve different holiday sets,
compute DIFFERENT instants for the same economic month, each passes its own INV-SCH-1 recompute,
and the exact-instant uq never collides — two governed runs for one month, zero evidence. The
platform's idempotency is a DB guarantee (G26) and must stay one. A: `scheduled_run` gains a
stored `period_key` column (nullable; populated only for `BUSINESS_MONTH_END`, e.g. `2027-05`)
with a partial unique index `uq_scheduled_run_schedule_period` on `(schedule_id, period_key)
WHERE period_key IS NOT NULL` (migration 0059), and the worker's dedup classifier gains that
constraint's OWN name (the LIM-2 own-keys lesson) so a period collision classifies as
SKIPPED_DUPLICATE, not an error. The due-select period check rides as the polite first layer;
the DB key is the hard race backstop. The silent-skip arm resolves by late dispatch (G29) —
**bounded by the current-tick horizon**: a refresh landing after the next grid point supersedes
the re-valued month leaves it an honest gap per standing doctrine (recorded, not closed).
Legacy kinds keep instant-exact due-ness untouched; the holiday set is resolved ONCE per tick
cycle and threaded poll→write (G27).

### OQ-CAL-1-6 — reproducibility of a data-dependent convention: the AD-014 fork. **Recommend A (the conformant pin) — REBUILT after the verifier (BLOCKING: AD-014 was uncited).**

**The baseline:** AD-014 — "No governed derived output without a bound, reproducible input
snapshot" — and the wave plan's own fact 3 ("AD-014 requires the compute to read only pinned
content"); LQ-1 in this same wave is mandated a snapshot COMPONENT_KIND for pinned tier
assignments on the same argument. The v2 holiday set is a compute input to a governed number;
`calendar_holiday` is mutable EV with no history table.
**A (recommended, AD-014-CONFORMANT):** mint a new snapshot **COMPONENT_KIND `HOLIDAY_CALENDAR`**;
the v2 binders pin the resolved holiday set (calendar identity + the member dates over the
series span) into the run's input snapshot, and the kernel reads ONLY the pinned content —
bit-exact reproduction from the run's own bindings; CTRL-018's future reproduction job needs
nothing special. The scheduler side is NOT a governed derived output (the tick is operational;
the dispatched EXPOSURE run pins its own inputs at dispatch), so AD-014 does not bind it — there
the discipline is the ADD-ONLY refresh + one audited REFERENCE.UPDATE diff per refresh +
declared coverage (OQ-4, OQ-11), with the reasoning recorded here. No AD row needed under A.
**B (the pre-verifier draft's shape, now the recorded ALTERNATIVE):** no pin; add-only refresh +
audit-trail reconstruction as the reproducibility story — an explicit recorded DEVIATION from
AD-014, ADR-admissible per the AD-004-R1 honest-deviation precedent (an AD row at the gate's
discretion). Cheaper (no snapshot machinery), but a v2 reading would not be reproducible from
its bindings alone, and it contradicts the wave's own LQ-1 mandate. **The gate decides the fork;
A is recommended.**

### OQ-CAL-1-7 — the shared helper: a NEW pure leaf module; the mirror re-homed. **Recommend A.**

A: `irp_shared/calmath.py` (name at implementation): pure date arithmetic over a passed-in
`frozenset[date]` — zero irp_shared imports, no ORM, no session. Both scheduling and perf import
it; the hand-mirror and its reason (scheduling's heavy imports, G8) dissolve; the conformance pin
converts to v1/v2-parity tests on the ONE implementation. Attribution corrected per the
verifier: the standing rule is OQ-W12C-3b (Wave-12 close — pins are mandated ON mirrors that
exist; the mirror itself was an RM-1 implementation choice), and the wave plan's workstream (c)
pre-sanctions "re-home it" as an allowed disposition — so this is a sanctioned re-homing, not a
reversal. (The kernel docstring's "SCH-2 standing rule" misattribution is corrected in the same
slice.) B (extend the mirror to a second pair of hand-copies) doubles the divergence surface
CAL-1 exists to close.

### OQ-CAL-1-8 — the dataset and its licensing: hand-encoded XNYS from the published per-year source; SYSTEM rows; NEGATIVE censuses pinned. **Recommend A.**

A: a hand-encoded XNYS full-year holiday set covering at least 2024–2035 (the quantified
collision window, G15), source-cited to the NYSE's PUBLISHED per-year holiday calendar —
**never derived from an observance rule** (the verifier's executed trap: a naive "Saturday
holiday ⇒ preceding Friday observed" rule adds 2027-12-31 and 2032-12-31, both REAL trading days
under NYSE Rule 7.2's year-end exception and BOTH last-weekday December month-ends — silently
corrupting the collision census from 4 to 6). CAL-1a's tests pin the POSITIVE census (exact
set-equality per year + the four collision dates present) AND the NEGATIVE census (2027-12-31
and 2032-12-31 ABSENT). Verbatim source quotes + locators land in Part 5 at implementation; the
independent citation lane verifies against the source per rule 6a (G43). Holiday dates are
published public facts; the licensing reasoning (public source ⇒ SYSTEM rows per the ratified
conditional, G42) is recorded as a gate artifact. No new runtime dependency (G5). Delivered
through the new refresh path as its FIRST execution (idempotent against the seeded two-token
XNYS, G3). B (a calendar library) trades a hand-auditable ~130-row dataset for a dependency and
a licensing surface.

### OQ-CAL-1-9 — the diligence control: checklist-only; CTRL-034 minted R-10/H-05 AT THE GATE. **Recommend A.**

A: the ratified pair — a vendor-onboarding diligence checklist artifact (documentary home:
`09_compliance_controls/`, beside the matrix) + control-matrix row CTRL-034 — with the
capture-time convention-field option NOT taken (it stays the named split candidate; taking it
adds a second migration and DATA-1 is its natural home). The checklist is EXERCISED against the
holiday dataset being onboarded (its first execution) and includes the rf dating-convention
walk-through (G39 — the control stays procedural where the defect is undetectable in-data;
no code-enforcement overclaim). **The mint itself is an R-10 act with H-05 as approver (G38) —
not Claude's to route autonomously; it is an explicit item in the ratification ask.** Entry
status per the matrix vocabulary decided at mint (executed artifact ⇒ arguably Implemented).

### OQ-CAL-1-10 — P3-8 completeness + RULE_TYPE_COMPLETENESS: RE-DEFER both to DATA-1, named trigger. **Recommend A.**

A: the holiday set's acceptance is proven by exact set-equality censuses in tests against the
cited source (P7's strongest form, including OQ-8's negative pins) + the executed checklist — no
DQ rule mint needed for it. `RULE_TYPE_COMPLETENESS` and the P3-8 trading-calendar wiring both
re-defer to **DATA-1**, whose genuinely external vendor series is the honest firing of REF-1's
trigger (G6) and whose record inherits P3-8's OQ by name. Wiring P3-8 here would change a
SHIPPED governed number's input acceptance (G41) inside a slice already carrying a Tier-3
convention move — scope discipline. Re-deferral is a sanctioned disposition ("either ridden
there or re-deferred") and is recorded loud per OQ-4's own doctrine (G41).

### OQ-CAL-1-11 — the refresh write path's shape. **Recommend as stated.**

A new binder verb (`refresh_calendar_holidays`): add-only diff against the UNIQUE
(tenant, calendar, holiday_date) key (G2), one audited **REFERENCE.UPDATE (EVT-141, reused —
an audit EVENT, not a permission)** per refresh with the added-dates summary and the
`holidays_complete_through` advance (OQ-4); the entitlement gate, if an API verb ever ships, is
the EXISTING `reference.calendar.edit` permission — **no permission or audit-code mint** (the
verifier confirmed the create precedent folds children into one parent event with
`holiday_count`, so the diff shape fits EVT-141 as-is). SYSTEM-calendar refresh runs under the
SYSTEM tenant context via the bootstrap path (the hybrid WITH CHECK is own-only — G34; the
verifier confirmed SYSTEM-context writes exist only there today); idempotent re-run adds nothing
and emits no event. API exposure default OUT (the FE has no calendar surface today, G4).

### OQ-CAL-1-12 — sizing and the split: CAL-1 runs L → SPLIT at the wave plan's line. **Recommend A.**

Workstream count at this record's post-fold shape: migration 0059 (schedule FK + coverage column +
period key + partial unique + two CHECK amendments + vocab), the leaf helper + three predicate
sites + pin conversion, TWO v2 registrations with the declared-parameters gate, the
`HOLIDAY_CALENDAR` snapshot component, a new cadence kind end-to-end, the refresh verb, the
dataset + double census, the CTRL mint + checklist, a demo holiday boundary, six register
sweeps. That is larger than LIM-2 (M). A: split per the wave plan's ratified line — **CAL-1a:
dataset + refresh write path + the diligence control executed against it** (no migration, no
convention change; M) → **CAL-1b: the atomic convention move** (migration 0059, the new cadence
kind, the three predicates + helper, both v2 mints + the snapshot pin, the demo holiday
boundary; L). The atomicity constraint binds only CAL-1b's predicates to each other (the wave
plan says exactly this). DATA-1's premise (G44) is satisfied by CAL-1a alone.

---

## Part 3 — independently computed reference values

Recomputed for this record and INDEPENDENTLY RE-DERIVED BY EXECUTION in the verifier pass
(Easter computus + last-Monday arithmetic + the shipped predicates on sys.path):

- The four weekday-rule holiday collisions 2024–2035 (G15): 2024-03-29 (Good Friday, Easter
  2024-03-31), 2027-05-31 (Memorial Day), 2029-03-30 (Good Friday, Easter 2029-04-01),
  2032-05-31 (Memorial Day). Exhaustive 144-month sweep: exactly these four.
- 2027 May under v2: last weekday = Mon 2027-05-31 = Memorial Day → last BUSINESS day =
  **Fri 2027-05-28**; executed: `is_month_end(2027-05-28)` = **False** today — the widening target.
- **The Rule 7.2 negatives (verifier-found):** Jan 1 2028 and Jan 1 2033 are Saturdays; NYSE
  stays OPEN the preceding Fridays (2027-12-31, 2032-12-31 — the year-end exception; the
  Dec 31 2021 precedent). Both dates are last-weekday December month-ends: a naive observance
  encoding would wrongly add them as holidays and corrupt the collision census to 6. They are
  pinned ABSENT in CAL-1a's negative census (OQ-8).
- 2026 May (the seeded demo boundary): 2026-05-31 Sun, last weekday Fri 2026-05-29; Memorial Day
  2026 = Mon 2026-05-25 → the holiday-aware answer is UNCHANGED. Executed sweep: NO 2026 XNYS
  holiday falls on any last-weekday month-end — the demo boundary is retro-stable (G36); assert
  in-test at CAL-1b.
- Because no 2026 XNYS holiday moves a month-end, the demo's REAL holiday boundary (the ratified
  Part 4 wording: "CAL-1 exercises a real holiday boundary in the demo grid") **defaults to a
  2027-05 window** (the real Memorial Day collision). A synthetic demo-tenant holiday is the
  FALLBACK only, and taking it would be a deviation from the ratified wording requiring an
  explicit note at the gate (verifier MED — also in tension with the test-data-realism rule).

---

## Part 4 — implementation shape (sketch; hardened at ratification)

**CAL-1a (no migration):**

1. `refresh_calendar_holidays` binder verb per OQ-11 (+ negative controls: double-add refused by
   UNIQUE, removal refused, cross-tenant refused by RLS both tiers, `holidays_complete_through`
   advances only forward).
2. The XNYS dataset (2024–2035) as data in `reference/` (sibling data module), loaded through the
   refresh verb; the DOUBLE census per OQ-8 (positive set-equality + per-year counts + the four
   collision dates present; 2027-12-31/2032-12-31 ABSENT).
3. The diligence checklist artifact + CTRL-034 row (minted at the gate, R-10/H-05); the checklist
   executed against the XNYS dataset with the rf walk-through.
4. Register sweeps: REQ-SMR-004 progress note; ENT-006 note (data now real; math still CAL-1b);
   control matrix; current_state.

**CAL-1b (migration 0059):**

1. `irp_shared/calmath.py`: `last_business_day_of_month(year, month, holidays)`,
   `is_month_end` widening under the BUSINESS convention; property tests + the four collision
   dates pinned + the Rule 7.2 negatives.
2. The three predicate sites move onto the helper (re-homed per OQ-7); the conformance pin
   converts to v1/v2 parity sweeps (v1 path byte-identical 2024–2035 — the grandfather proof);
   the kernel docstring's rule misattribution corrected.
3. Migration 0059: `schedule.calendar_id` FK + `calendar.holidays_complete_through` +
   `scheduled_run.period_key` + partial unique `uq_scheduled_run_schedule_period` +
   `BUSINESS_MONTH_END` in both cadence CHECKs + the kind→calendar_id CHECK; `_validate_config` +
   the own-OR-SYSTEM FK guard (G34 precedent reuse) in the same commit.
4. **The P4 EXECUTED migration dry run on 0059** (up → rows staged → down → up) **under the
   non-superuser owner role** — the wave plan's Part 4 binds P4 to CAL-1 explicitly; named here
   as its own step (the LIM-2 lesson: an unexecuted or superuser-run dry run proves nothing).
5. The new cadence kind end-to-end: fail-closed head resolution + coverage refusal (OQ-4),
   holiday set resolved once per cycle and threaded poll→write (G27), period-key stamping + the
   worker dedup classifier's own key (OQ-5), ScheduleError discipline (G32).
6. `perf.rolling_risk` v2 + `perf.sharpe` v2 registrations: new assumption tuples carrying
   `month_end_convention=BUSINESS` + `holiday_calendar=XNYS` literals; the
   `declared_month_end_parameters` gate (absent ⇒ v1, ambiguous ⇒ fail-closed); the
   `HOLIDAY_CALENDAR` snapshot COMPONENT_KIND pin (OQ-6-A); the v1 tuples untouched (G21).
7. Demo: a `BUSINESS_MONTH_END` schedule bound to the SYSTEM XNYS calendar exercising the REAL
   2027-05 holiday boundary (Part 3's default), created ALONGSIDE the legacy schedule (the
   retire-and-recreate transition demonstrated); the runbook note for live-schedule transition;
   count-pin relay per the New-demo-stage manifest.
8. Register sweeps + the P1 seven-ledger close; REQ-PRF-003's "holiday-free" clause re-synced;
   REQ-PRF-002's deferral clause re-pointed at DATA-1 (OQ-10); CTRL-018 note (OQ-6-A keeps the
   future reproduction job trivial).

---

## Part 5 — cited external research (rule 6a) — POPULATED AT IMPLEMENTATION

The governing citation is already in-repo verbatim (G43): GIPS 2.A.23.b — *"As of the calendar
month end or the last business day of the month"* (`rm_1_decision_record.md:107`; in code at
`rolling_kernel.py:16-17` with the truncation lesson at `:87`). CAL-1b's v2 is the convention
that makes the platform actually honor the "last business day" arm on a holiday-aware basis.
The NYSE published-calendar citations for the dataset (verbatim + locators, per-year table —
never an observance rule, OQ-8) land in this Part at CAL-1a implementation and are verified by
the independent citation lane before the close. The NYSE Rule 7.2 year-end exception (the
2027-12-31/2032-12-31 negatives) is cited alongside.

---

## Part 6 — the verifier fold (2026-08-01, PRE-ratification)

Four refute-by-default lanes (code refutation with execution; independent citations; baseline
consistency; adversarial design) over the pre-verifier draft: **2 BLOCKING, 6 HIGH, 5 MED,
8 LOW — all folded into the revision above.** The full lane reports are preserved in the
planning workflow transcript. The folds, each in its P7 form:

- **B1 (baseline lane): OQ-6 recommended an unpinned mutable-EV input to a governed convention
  WITHOUT citing Accepted AD-014** — the exact uncited-AD class ruled BLOCKING at Wave-14
  planning. Fold: OQ-6 rebuilt around the AD-014 fork; the conformant snapshot pin
  (`HOLIDAY_CALENDAR` component) is now the recommendation; the deviation is the recorded
  alternative with its ADR-admissibility named. *(Form: the gate decides an explicitly-cited
  fork — procedural, bound to this ratification.)*
- **B2 (adversarial lane): OQ-2 decided the convention carrier but not WHICH CALENDAR governs a
  v2 perf run** — the kernel is no-DB, the binders had no calendar, the FK binds schedules only.
  Fold: the `holiday_calendar=` declared literal + own-OR-SYSTEM resolution + fail-closed
  refusal, written into OQ-2. *(Form: mechanical — the declared-parameters gate refuses
  absent/ambiguous states.)*
- **H1 (code + adversarial): "parsed from the version_label" was mechanically WRONG** — the
  precedent parses registrar-stamped assumption literals, never labels. Fold: G18/OQ-2 rewritten
  with the real mechanism and its fail-closed discipline. *(Form: mechanical at implementation —
  the gate's absent/ambiguous refusals are the enforcement.)*
- **H2 (three lanes concurring): OQ-5's "closes structurally" was FALSE under concurrency** —
  two polls straddling a refresh both insert distinct instants for one month; the uq never
  collides. Fold: the DB-grain `period_key` partial unique + the worker classifier's own key;
  the silent-skip current-tick horizon recorded. *(Form: mechanical — a DB constraint.)*
- **H3 (citations + baseline): the draft FABRICATED A QUOTATION** — "a dispatched RM-1 run that
  refuses" attributed in quote marks to a wave plan that contains neither the phrase nor the
  variant taxonomy, inside a record that itself cites the strengthened rule 6a. Fold: struck;
  Part 1 item 1 reframed as confirmation-plus-refinement. Recorded here without soft-pedaling:
  the drafter (Claude) manufactured a paraphrase-as-quotation while writing a record that
  invokes the rule against exactly that. *(Form: recurrence-accepted risk, mitigated by the
  standing independent citation lane — which is what caught it; no new rule minted.)*
- **H4 (baseline): "the residual this slice retires" overclaimed under the record's own
  grandfathering.** Fold: G15 → "makes RETIRABLE"; the retire-and-recreate transition path is a
  named CAL-1b deliverable (runbook + demo demonstration). *(Form: procedural, bound to CAL-1b's
  close checklist.)*
- **H5 (adversarial): the empty-or-RLS-invisible holiday set was silent FAIL-OPEN** (weekday-only
  answers indistinguishable from the legacy kind — reachable day one against the two-token
  seed). Fold: fail-closed head resolution + the DECLARED `holidays_complete_through` coverage
  refusal in OQ-4, mirrored in the perf v2 binder. *(Form: mechanical — refusals.)*
- **M1:** G34 now cites the shipped symmetric→hybrid FK precedent (0056 + OQ-REF-1-20) — reuse,
  not novelty. **M2:** REFERENCE.UPDATE correctly identified as an audit EVENT (EVT-141); the
  entitlement is the existing `reference.calendar.edit` (OQ-11 reworded). **M3:** the demo's
  real-boundary default is the 2027-05 window; synthetic = flagged deviation (Part 3). **M4:**
  the Rule 7.2 negative census (2027-12-31/2032-12-31 ABSENT) pinned into OQ-8/Part 3/Part 4.
  **M5:** the precedent-strength caveat written into G18 (estimator-branch → kernel-predicate is
  an extension, named as such).
- **LOW (8):** the OQ-5 horizon sentence; OQ-7's attribution to OQ-W12C-3b + the pre-sanctioned
  re-homing; the named P4 dry-run step (Part 4 CAL-1b.4); the G43 locators (`:16-17`, `:87`);
  the G49 manifest paraphrase split into its two distinct obligations; the G42 quote order;
  `BUSINESS_MONTH_END` fixed ≤20 chars (G30); the pin-test path stated in full.

**What the verifier CONFIRMED under attack (the load-bearing substrate):** the four collision
dates by independent computus over all 144 months; `is_month_end(2027-05-28)=False` by
execution; the no-dispatch-link census; the no-amend-path full read; the five alignment
conditions safe under WIDENING and broken by SUBSTITUTION; the seed/refresh gaps; the CHECK/RLS/
guard mechanics incl. the String(20) ceiling; every next-free id (ENT-070/CTRL-034/AD-020/0059);
the 26/41/136 pin semantics; ~30 doc citations verbatim including the roadmap row's
"new/amended" wording and the R-10/H-05 routing; the initial past-dated load's safety (no
runtime consumer of `CalendarHoliday` exists at the pin); and the 2026 demo boundary's
retro-stability.

---

## Part 7 — CAL-1a implementation corrections + the review fold (2026-08-01, STATED not slipped)

Four-lane refute-by-default review over the CAL-1a diff (dataset / verb semantics / test quality /
claims-vs-artifacts): **1 BLOCKING, 3 HIGH, 4 MED, 8 LOW — all folded.** The dataset itself
survived a fully independent derivation (118/118 exact agreement, dates and names) and every
boundary attack; the fold was in the guards and the record, per the platform's pattern.

**Sequencing corrections to the RATIFIED text (the LIM-2 3.5 discipline — stated, never silent):**

1. **OQ-CAL-1-11's `holidays_complete_through` advance ships at CAL-1b, not CAL-1a** (HIGH, two
   lanes). The column is migration-0059 DDL and CAL-1a is ratified no-migration — the OQ text
   bound a CAL-1a verb to a CAL-1b column. The correction: CAL-1a's verb emits the added-dates
   summary only; **the NAMED CAL-1b CARRY is the verb retrofit** (the explicit advance + its
   forward-only negative control), recorded in the verb docstring, the checklist item 7, and
   current_state — without it, OQ-4's coverage gate refuses every `BUSINESS_MONTH_END` tick.
2. **Part 4 CAL-1a step 1's "double-add refused by UNIQUE" control is superseded by design**
   (MED). The verb diffs additions against the existing set AND dedupes intra-call duplicates
   first-spec-wins (a review fold — the pre-fold verb crashed mid-flush on a duplicated input
   row), so the child UNIQUE is structurally unreachable through the verb. The operative add-only
   negatives are: subset-deletes-nothing (full remaining-set equality), never-mutates-an-existing
   child (now also pinning added==0/no event/no bump), and the dedupe contract test.
3. **"Cross-tenant refused by RLS both tiers" was never satisfiable as written** (MED): SQLite has
   no RLS and the verb (like `create_calendar`) has no application-layer tenant check — the
   refusal is PG-tier by nature, and is now pinned TWICE there (below).

**The fold's substantive findings:**

- **(BLOCKING, claims lane)** The checklist's Execution 1 claimed "verified: no runtime reader of
  `calendar_holiday` exists at `8637b67`" — **FALSE**: `GET /calendars/{calendar_id}` reads and
  serves the table, and will expose the 118 rows to every tenant's calendar-detail response the
  moment the seed lands. A false "verified:" claim inside a freshly-minted compliance artifact —
  the exact ledger-7 class. Corrected in place with the consuming read named; the original
  wording kept as history in the artifact.
- **(HIGH, test-quality lane)** The PG cross-tenant test proved a WEAKER refusal than it claimed:
  the verb's flush order puts the parent-head version-bump UPDATE before the child INSERT, so the
  own-only WITH CHECK fires on `calendar` and the child statement never runs — a server-stamping
  regression (the exact vulnerability the stamp defends) would have PASSED it. The LIM-2
  easy-input pattern, refound in a shipped security test. Fold: the test now asserts the refused
  TABLE by name, and a companion control isolates the child WITH CHECK (a SYSTEM-stamped child
  inserted directly under an intruder context must be refused naming `calendar_holiday`).
- **(MED, test-quality lane, EXECUTED)** The census alone missed 5 of 6 single-date mutations (the
  independent-derivation test caught all 6). Fold: nine observance anchors + the exact 9-member
  2028/2033 sets pinned; both overclaiming docstrings corrected to state the census/derivation
  division of labor.
- **(LOWs, all folded)** MLK styling matched to the NYSE rendering ("Martin Luther King, Jr.
  Day"); the in-test Rule 7.2 last-calendar-day simplification documented; the refresh verb's own
  audit-failure rollback pinned (previously inherited from the create path); empty-input,
  second-refresh event shape, and mixed rename+addition contracts pinned; the concurrency
  contract (no parent lock; raw IntegrityError on a concurrent overlap — bootstrap-only caller)
  documented in the docstring; current_state's self-stale "IN FLIGHT" wording fixed.

**Verified under attack and standing:** the 118 literals (independent derivation, zero
mismatches); the Dec-31-2021 Rule 7.2 precedent; the four collision dates re-derived exhaustively;
"first CTRL mint since P0.5" (row-count history 33→33→34); every checklist test-name citation;
the DC-2 adjudication of the event's added_from/added_through range summary (ratified by OQ-11's
own "added-dates summary" wording; boundary dates, not serialized child rows); the seed's every
existing consumer (grep + green runs); the import fences.
