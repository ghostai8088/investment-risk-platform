# DATA-1 — the first genuinely external dataset (decision record)

**Status: RATIFIED 2026-08-02 — OQ-DATA-1-1…12 ALL as recommended ("Proceed" on the briefed
gate).** Wave-14 slice 3.5 (INSERTED 2026-07-30, user-ratified). Planning branch
`data-1-planning` off `e3253a9` (the CAL-1b closeout merge). Grounding recon: six independent
lanes at pinned HEAD `e3253a9`, 193 facts; the curated fact base is Part 0. The four-lane
refute-by-default verifier ran BEFORE ratification (the ES-1 standing lesson); its 28 findings
(1 BLOCKING / 5 HIGH / 10 MED / 10 LOW) are ALL folded — Part 5 is the fold record; Part 6 is the
ratification record.

The ratified slice text (`delivery_roadmap.md:269`, quoted in full at G1) commits: **ONE
authoritative public dataset — candidate: a U.S. Treasury bill monthly yield series (source +
licensing verified at the slice gate) — ingested through the governed capture rails as the real
risk-free series**, with **CTRL-034 executed against it as an auditable artifact**, and **NO live
adapter** (the REQ-INT-002/003 vendor-contract trigger unchanged). By ratified re-deferral
(OQ-CAL-1-10, G20): **`RULE_TYPE_COMPLETENESS`** and **the P3-8 trading-calendar wiring** land
here, and this record **inherits P3-8's OQ by name** (Part 2, OQ-5).

---

## Part 0 — grounding facts (curated from the six-lane recon at `e3253a9`)

Every fact carries a verbatim quote (whitespace/wrapping normalized; the verifier fold added the
note that dash/arrow punctuation inside quotes is rendered normalized — where exactness matters
the ASCII original is preserved). Lane digests (all 193 facts) are preserved in the session
scratchpad; this part curates the load-bearing subset the OQs cite. **The independent citation
lane re-verified every quote; its corrections are folded in place and recorded in Part 5.**

### The ratified scope and its chain

- **G1.** The full DATA-1 row: "ONE authoritative public dataset — candidate: a U.S. Treasury bill
  monthly yield series (source + licensing verified at the slice gate) — ingested through the
  governed capture rails as the real risk-free series, with the vendor-onboarding diligence
  checklist (the CAL-1 control) EXECUTED against it as an auditable artifact. This converts the
  wave's \"real data\" claim from taxonomy seed rows into genuinely external market data on the
  governed rails; NO live adapter rides (the vendor-contract trigger for REQ-INT-002/003 stands
  unchanged). Sequenced after CAL-1 so the diligence control it reuses exists."
  (`10_delivery_backlog/delivery_roadmap.md:269`)
- **G2.** The wave-level real-data rule: "real data = authoritative external datasets through
  governed capture, NO live adapters (trigger: a real vendor contract)"
  (`10_delivery_backlog/delivery_roadmap.md:260`)
- **G3.** REQ-INT-002/003 are Draft at phase P9 in both requirement registers; the DATA-1 row's own
  text says their trigger "stands unchanged" — they stay byte-untouched.
  (`02_requirements/requirements_backbone.md:280-281`, `requirements_traceability_matrix.md:102`)
- **G4.** OQ-CAL-1-10 (ratified): "`RULE_TYPE_COMPLETENESS` and the P3-8 trading-calendar wiring
  both re-defer to **DATA-1**, whose genuinely external vendor series is the honest firing of
  REF-1's trigger (G6) and whose record inherits P3-8's OQ by name. Wiring P3-8 here would change a
  SHIPPED governed number's input acceptance (G41) inside a slice already carrying a Tier-3
  convention move — scope discipline." (`10_delivery_backlog/cal_1_decision_record.md:501-505`)
- **G5.** The CAL-1b close row's forward pointer: "NEXT = DATA-1 (the first genuinely external
  dataset — CTRL-034 re-executes; `RULE_TYPE_COMPLETENESS` + the P3-8 trading-calendar wiring land
  by ratified re-deferral)" (`10_delivery_backlog/delivery_roadmap.md:380`)
- **G6.** REF-1's ratified mint trigger: "Minting `RULE_TYPE_COMPLETENESS` (so the persisted rule
  can say *what* was expected) is deferred, trigger: *the first vendor dataset whose acceptance is
  expressed as an expected key set in the rule itself*."
  (`10_delivery_backlog/ref_1_decision_record.md:240-242`)
- **G7.** Namespace check (P7): `DATA-1` appears only in eight documentation/session-log files,
  every hit meaning this slice; zero matches for `DATA-1`/`DATA_1`/`DATA1` under `packages/`,
  `apps/`, `migrations/`, `scripts/`. One near-collision: the Wave-1 table also has a ROW numbered
  3.5 (TD-1) — row numbers are per-wave-table; references must use the slice id.
  (grep at `e3253a9`; `delivery_roadmap.md:35`)
- **G8.** The id/head baseline: migration head `0059_business_month_end`; next free canonical id
  **ENT-070** (ENT-032 the sole reservation); demo counts **26/43/139** (FINAL-POSITION, 12-z
  suite); hybrid set N = 7. (`docs/project_memory/current_state.md:8-12`)

### The risk-free series as it exists today (the consumer DATA-1 feeds)

- **G9.** The rf series rides ENT-052 `benchmark_return` — FR bitemporal captured input under the
  `benchmark` EV header; grain `(tenant_id, benchmark_id, return_date, return_type, return_basis)`
  current-head partial-unique; value "a canonical DECIMAL fraction (``0.01`` = 1%, NOT percent/bps
  — the ENT-025 convention), ``PreciseDecimal(20, 12)``".
  (`packages/shared-python/src/irp_shared/marketdata/models.py:808-827`)
- **G10.** The twice-ratified content constraint: "**Captured vendor-published values ONLY — NEVER
  computed from levels** (OQ-P2-6-9; a level-derived return is a methodology choice needing a
  registered ``model_version``, DEFERRED)." (`marketdata/models.py:797-798`)
- **G11.** REQ-PRF-004 fixes the doctrine at requirements level: "The risk-free leg is a CAPTURE
  (vendor-published RETURNS only — never derived from levels), joined by MONTH KEY with
  binder-enforced completeness and uniqueness; a missing month REFUSES pre-create rather than
  computing 'the windows we can'." (`02_requirements/requirements_traceability_matrix.md:60`)
- **G12.** SR-1's registered assumption (v1 AND the CAL-1b v2 texts): "RISK-FREE LEG: a CAPTURED
  vendor-published monthly return series carried as an ordinary benchmark head (ENT-052), joined
  to the portfolio months by MONTH KEY (year, month) — never by date".
  (`packages/shared-python/src/irp_shared/perf/bootstrap.py:952`)
- **G13.** SR-1's registered limitation prices the yield path: "A yield curve (ENT-021) would
  additionally need a registered yield -> period-return model; recorded, costed, and not taken in
  v1." (`perf/bootstrap.py:988-990`; the same limitation, differently worded, in
  `snapshot/service.py:2016-2019` — *cite + wording corrected at the verifier fold*)
- **G14.** The declared rf dating convention, on the join primitive itself: "the rf ``return_date``
  must fall INSIDE the month its return is for" — and "a first-of-following-month series joins one
  month LATE, every row, with matching row counts, and nothing in the data can distinguish it from
  a correctly-dated series"; "enforcement is the declaration plus vendor-onboarding diligence, the
  Wave-14 carry". (`perf/sharpe_kernel.py:87-93`)
- **G15.** The Sharpe binder's rf refusal arms: exactly one pinned rf series; uniform
  SIMPLE/return_basis; every pinned row consumed (no out-of-window months); at most one rf return
  per measured month; a missing measured month refuses pre-create naming the month — "there is no
  imputation and no carry-forward". (`perf/sharpe_service.py:256-308`)
- **G16.** The only rf data in the platform is demo-authored: "the only rf data in the platform is
  the demo-captured 18-row series (`demo/sr1_stage17.py`), authored in-repo — items 2/3/5/6/7 have
  no external vendor to interrogate yet." Demo identity: `USD-CASH-1M` under `DEMO_VENDOR`,
  18 monthly fraction rows 2024-01..2025-06, dated on the CALENDAR month end, captured per-row via
  `capture_benchmark_return` with `return_basis=TOTAL`.
  (`vendor_onboarding_diligence_checklist.md:51-53`; `demo/sr1_stage17.py:105-108,239,289-294`)
- **G17.** The rf capture rail accepts ANY `return_date` today (no month-alignment refusal — the
  SR-1 overclaim was corrected at the Wave-13 close); the binder catches a partial shift, never a
  uniform one. (`10_delivery_backlog/wave_14_planning.md:81-84`)

### The capture rails (what riding vs minting costs)

- **G18.** The ENT-052 rail is complete and reusable: race-safe DQ resolve-or-register (P3-C2
  savepoint pattern), binder finiteness guard (NaN/±Inf pre-write; the min-only `> -1` RANGE cannot
  catch +Inf), per-op audit grain (capture=1 CREATE; supersede=2; correct=2) under
  `MARKET.BENCHMARK_RETURN_*`, one ORIGIN lineage edge per physical version row rooted at the
  shared `VENDOR_BENCHMARK` `data_source`, `marketdata.view`/`.ingest` permission reuse, and an
  HTTP capture endpoint gated by `marketdata.ingest`.
  (`marketdata/benchmark_series.py:9-29,153-190,305-307`; `apps/backend/.../marketdata.py:145-146`)
- **G19.** Audit payloads are DC-2 metadata only — "NEVER the captured value payload — the
  ``factor_return`` precedent keeps vendor-licensed values out of the audit trail"; the MARKET
  family chains per-tenant, "Per-tenant chain (PROPRIETARY, no SYSTEM chain)".
  (`marketdata/benchmark_series.py:355-357`; `04_data_model/audit_event_taxonomy.md:79`)
- **G20.** Tenancy posture of the whole benchmark family: "PROPRIETARY/symmetric; NEVER hybrid;
  **NOT append-only**" (benchmark_return), and the header: "PROPRIETARY/symmetric; NEVER hybrid
  (per-tenant vendor-licensed; a shared-global benchmark *definition* would be an AD-013-R2 event,
  OD-P2-G)." (`marketdata/models.py:800,502-503`)
- **G21.** The closed hybrid set is N=7 with a membership rule that excludes series data: "a
  *standard, curated, globally shared* vocabulary is hybrid; anything PROPRIETARY (issuer,
  legal_entity, counterparty, instrument, and REF-1's own ``classification_assignment``) is
  symmetric and NEVER hybrid." Extension is a user-ratified invariant amendment (the AD-013-R2
  precedent). (`reference/models.py:63-79`; `11_decision_log/architecture_decision_log.md:29`)
- **G22.** The temporal-class doctrine: FR bitemporal for risk-driving inputs, IA for outputs, EV
  for reference/config (AD-005); "Governed derived numbers bind `dataset_snapshot` +
  `calculation_run` + a registered `model_version` ... captured inputs bind none of those. Pick the
  pattern correctly." (`11_decision_log/architecture_decision_log.md:12`; `CLAUDE.md:41-42`)
- **G23.** AD-004-R1 homes market-data series in PostgreSQL behind the market-data repository
  interface, "reusing the proven FORCE-RLS / audit / lineage / DQ rails".
  (`11_decision_log/architecture_decision_log.md:26`)

### The DQ machinery and the completeness chain

- **G24.** The DQ rule-type vocabulary is exactly three constants — `NOT_NULL`, `ALLOWED_VALUES`,
  `RANGE` — with a REGISTRY census pin by exact set equality
  (`tests/test_data_quality.py:366`) that a mint must move. New generic kinds "register by value +
  a function, never a schema migration"; the DB `rule_type` column is an unconstrained String(50)
  (migration 0006). (`dq/rules.py:4-5,21-23,124-129`; `migrations/versions/0006_...py:51`)
- **G25.** Evaluators are PURE — "Pluggable DQ evaluator interface + registry (pure logic, no DB)";
  `Dataset = Sequence[Mapping[str, Any]]`; `evaluate_rule` raises `UnknownRuleTypeError` on an
  unregistered type. Any calendar resolution must happen caller-side. (`dq/rules.py:1,25,132-137`)
- **G26.** `run_quality_check` persists an immutable `data_quality_result` and audits
  `DATA.VALIDATE` co-transactionally; ERROR-severity failure raises `DataQualityError` (the
  no-silent-failure policy); it already carries an `ingestion_batch_id` linkage populated on both
  PASS and raise paths. (`dq/service.py:193-198,271-274`)
- **G27.** The existing "completeness" machinery (`dq/gates.py`) is a derived presence gate: "a
  per-tenant resolve-or-register **NOT_NULL** rule over ``{'column': 'present'}``, then a governed
  ``run_quality_check`` over a derived dataset of one ``{'present': None}`` row per GAP"
  (`dq/gates.py:5-7`). CAL-1's recon put it plainly: "gap detection stays caller-computed"
  (`cal_1_decision_record.md:46-47`), and REF-1's trigger exists precisely "so the persisted rule
  can say *what* was expected" (`ref_1_decision_record.md:240`) — which the presence gate cannot.
  Per the corrected REF-1 record, NO capture path invokes it. (`ref_1_decision_record.md:236-238`)
  *(The verifier fold replaced a composite paraphrase that had been presented as a single quote —
  the P7 class; every component fact held.)*
- **G28.** `assert_passed_quality_checks` is fail-closed when a target has NO recorded checks or
  ANY FAIL (`dq/service.py:285-286`) — and it has **one live ingestion caller**: the P1A-4
  `stage_upload` finalize gate (`ingestion/service.py:279`, reached from the HTTP endpoint
  `apps/backend/.../api/ingest.py:89`). *(Verifier fold: the draft claimed "zero ingestion
  callers", inherited from the STALE docstrings `dq/service.py:7` / `dq/__init__.py:6` which still
  say "a **future** P1A-4 ingestion calls (none here)" — fixing those two docstrings is an
  in-slice Tier-2 item, Part 3.)*
- **G29.** The original P3-8 deferral text: "Missing-day hazard recorded LOUD (a vendor gap inside
  a window silently understates the compounded benchmark return; trading-calendar completeness
  validation is deferred — the reference calendar tables exist but wiring them is its own scope)."
  Its ratified OQ-4: "the alternative (calendar-validated completeness) is real scope that belongs
  to a data-quality slice". (`10_delivery_backlog/p3_8_decision_record.md:16,47`)
- **G30.** Today's shipped benchmark-relative runtime check refuses only a ZERO-row sub-period
  window — a partial vendor gap still compounds silently.
  (`perf/benchmark_relative_service.py:322-325`)
- **G31.** CAL-1's G41 warning, verbatim: "Changing the acceptance is a governed convention change
  to a SHIPPED number's input path, not a quiet tightening."
  (`cal_1_decision_record.md:262-264`)
- **G32.** The CAL-1b calendar surface available caller-side: `resolve_calendar` (fail-closed
  own-OR-SYSTEM), `calmath` (pure; `NO_HOLIDAYS`, `last_weekday_of_month`,
  `last_business_day_of_month`, `is_month_end` — holiday set always passed in, never DB-read),
  `xnys_holidays` (118 literals 2024–2035; `XNYS_RULE_72_OPEN_FRIDAYS`;
  `XNYS_COMPLETE_THROUGH = 2035-12-31`), and the scheduler's declared-coverage refusal pattern
  ("a derived MAX cannot represent a gap"). (`reference/service.py:342`; `calmath.py:9-69`;
  `reference/xnys_holidays.py:35-176`; `scheduling/service.py:333-338`)
- **G33.** Wave-14 planning named the gap the dominant vendor-file failure mode: "no
  completeness/gap/reconciliation rule type exists, and that is the dominant vendor-file failure
  mode (a file missing a holiday or an issuer passes all three silently)."
  (`wave_14_planning.md:77-79`)
- **G34.** REQ-DQR-001 names the fork: "no completeness/gap/reconciliation rule type exists — the
  in-or-out fork is named at Wave-14 REF-1's gate". REQ-PRF-002 (backbone + RTM) carries
  "calendar validation RE-POINTED at DATA-1 per OQ-CAL-1-10, 2026-08-01 — the substrate now
  exists; the wiring rides the first genuinely external series". REQ-PRF-003's month-end
  limitation is "RESOLVED BY THE v2 MINT at CAL-1b" — DATA-1 owes it nothing.
  (`requirements_backbone.md:239,296-297`; `requirements_traceability_matrix.md:58`)

### CTRL-034 and the governance constraints

- **G35.** CTRL-034: minted at CAL-1a as an R-10 act with H-05 approval; "acceptance is a
  procedural act executed BEFORE governed use, recorded here per execution"; the control exists
  because "some dataset defects are **undetectable in-data by design** (the SR-1 finding)".
  Nine items; matrix row Preventive/Manual, BR-6 + BR-14, Status "Implemented (CAL-1a,
  2026-08-01)"; legend Planned/Designed/Implemented/Operational.
  (`vendor_onboarding_diligence_checklist.md:3-23`; `control_matrix_skeleton.md:36,75`)
- **G36.** Item 3's ratified conditional: "Open/public ⇒ SYSTEM rows; licensed ⇒ per-tenant
  captures (the ratified OQ-W14P-6(iii) conditional; the `fx_rate` precedent). The reasoning, not
  just the verdict." The conditional's ratified scope was stated for holiday sets: "holiday sets
  land as SYSTEM rows **conditional on an open/public source** ... a licensed vendor calendar
  product falls under the `fx_rate` per-tenant-licensed precedent".
  (`vendor_onboarding_diligence_checklist.md:17`; `wave_14_planning.md:218-221`)
- **G37.** The checklist obligates DATA-1 by name: "**The first REAL rf/benchmark vendor dataset
  (DATA-1) executes this checklist in full**, with item 4 asking the vendor's dating convention
  against the declared one and recording the re-dating rule if they differ."
  (`vendor_onboarding_diligence_checklist.md:53-55`)
- **G38.** Execution 1's granularity bar: item 1 named the dataset key AND the consuming read
  file:line; item 7 named the exact verb, idempotence semantics, audit event, executing context;
  item 8 recorded positive AND negative censuses with enforcing test names; item 9 a trigger +
  owner. (`vendor_onboarding_diligence_checklist.md:31-39`)
- **G39.** Governance rails: a control mint is an R-10 act with H-05 approver, "not Claude's to
  route autonomously"; BR-15 makes H-05 the approver for legal/compliance positions; standing
  prohibition on "minting audit codes/permissions/roles outside the governed process"; grep -i
  'licens' finds ZERO hits in `02_requirements/` — checklist item 3 + the roadmap's gate clause are
  the repo's only licensing requirements text, so the gate record IS the licensing control.
  (`cal_1_decision_record.md:493-494`; `build_rules.md:41`;
  `claude_operating_instructions.md:367`; lane-4 grep)
- **G40.** OQ-CAL-1-9 left "the capture-time convention-field option NOT taken (it stays the named
  split candidate; taking it adds a second migration and DATA-1 is its natural home)".
  (`cal_1_decision_record.md:488-490`)
- **G41.** BR-6 requires every risk result to trace to source data + validation checks + model
  version + assumptions + run id + timestamp + initiator; BR-14: "All limitations must be
  explicitly documented." (`build_rules.md:15-23,37`)

### The external dataset (web lane; ALL literals flagged for hand re-verification at the gate)

- **G42.** FRED TB3MS = "3-Month Treasury Bill Secondary Market Rate, Discount Basis" — monthly,
  percent, "Averages of Business Days, Discount Basis", source "Board of Governors of the Federal
  Reserve System (US) ... Release: H.15 Selected Interest Rates".
  (`https://fred.stlouisfed.org/series/TB3MS`)
- **G43.** H.15 footnotes: bill rates are "Annualized using a 360-day year or bank interest. ...
  On a discount basis." — the published percent is NOT an investment return without conversion.
  The archived release carries BOTH "averages of business days unless otherwise noted" AND "monthly
  figures include each calendar day in the month" — which footnote governs the bill series must be
  pinned at the gate. (`federalreserve.gov/releases/h15/`, archived `…/h15/20131015/`)
- **G44.** Basis is economically material: GS3M (investment basis) June 2026 = 3.81% vs TB3MS
  (discount basis) 3.66% — a 15bp gap. (`fred.stlouisfed.org/series/GS3M`)
- **G45.** Licensing case: U.S. government works are public domain at origin (17 U.S.C. §105); the
  Board's disclaimer: "Unless otherwise indicated, information on Board's website is in the public
  domain and may be copied and distributed without permission ... Please cite to the Board".
  FRED's ToU: internal commercial use with attribution permitted; "data mining, mirroring, robots,
  scraping" prohibited (bears on any future programmatic pull; hand-encoded literals sidestep it;
  the Board's own Data Download Program has no such prohibition).
  (`law.cornell.edu/uscode/text/17/105`; `federalreserve.gov/disclaimer.htm`;
  `fred.stlouisfed.org/legal/`; `federalreserve.gov/feeds/h15.html`)
- **G46.** The 30 TB3MS monthly literals 2024-01..2026-06 were retrieved (5.22 … 3.66, full list in
  the lane digest) **through a render proxy** (fred.stlouisfed.org 403s this environment's fetcher)
  with a second extraction pass agreeing on six sampled months + the final observation; 2026-07 was
  unpublished as of 2026-08-02. **Independent hand re-verification of all 30 literals is a gate
  precondition (P7 citation lane).** (`fred.stlouisfed.org/data/TB3MS`, via proxy; lane-6 RF-23/24/25)
- **G47.** The series is REVISABLE: the Board maintains a historical data-correction page covering
  the 3-month bill series (selected 2002–2005 dates, ~30 entries — verifier re-fetch) — rare
  corrections must be representable. FRED dates monthly observations on the FIRST of the
  observation month; the monthly value posts ~1 business day after month end.
  (`federalreserve.gov/releases/h15/historical-data-correction.htm`;
  `fred.stlouisfed.org/series/TB3MS`)
- **G48.** The dominant academic monthly-rf precedent (Fama/French) uses a ONE-month bill rate from
  Ibbotson (to 2024-05) then the ICE BofA US 1-Month Treasury Bill Index — commercial index
  products, not public-domain publications.
  (`mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html`)
- **G49.** Cross-check: the late-July 2026 H.15 dailies (3.69–3.82) sit 3–16bp ABOVE the retrieved
  June monthly average 3.66 — same neighborhood, consistent with a modest July uptick; plausibility
  support only, re-run during the gate's hand re-verification. *(Verifier fold: the draft said
  "brackets", which was arithmetically false — 3.66 lies below the whole daily range.)*
  (`federalreserve.gov/releases/h15/`, re-fetched 2026-08-02 by the verifier)

---

## Part 1 — the central collision, stated before any decision

Three lanes independently converged on the same contradiction, and the record states it before
recommending anything:

**The ratified candidate is "a U.S. Treasury bill monthly YIELD series" (G1). The platform's
risk-free leg admits vendor-published RETURNS only.** ENT-052's twice-ratified constraint (G10),
REQ-PRF-004's doctrine (G11), and SR-1's registered assumption (G12) all fix the same line — and
SR-1's registered limitation already PRICED the yield path: "a registered yield → period-return
model; recorded, costed, and not taken in v1" (G13). A yield is an annualized percent on a 360-day
discount basis, averaged over the month's business days (G42/G43); a monthly return is a decimal
fraction realized over one month. Re-scaling one into the other (/12, geometric, or
discount-honoring de-annualization) is a **methodology choice** — three treatments that give
different numbers forever after — not a units conversion. Capturing a re-scaled yield into
`benchmark_return` would make a capture-only rail launder a computed number, exactly what the
never-derive constraint exists to prevent.

No authoritative public-domain publisher publishes a monthly T-bill *return* series: published
return series are commercial index products (G48), which the no-vendor-contract rule excludes
(G2). So the slice CANNOT deliver "the real risk-free series" all the way into the Sharpe binder
without either registering the conversion model (a governed model + a Sharpe re-source — new
version labels under the no-amend rule) or violating doctrine. The honest shape is therefore a
**capture-first slice**: land the real yield series verbatim as a new captured entity with full
diligence and completeness machinery, and take the conversion model + Sharpe re-binding as an
explicitly named, triggered carry — OR ratify the larger scope now. That is OQ-1, and it is the
gate's sharpest decision.

---

## Part 2 — the open questions (OQ-DATA-1-1…12), each with a recommendation

### OQ-DATA-1-1 — The dataset and the yield-vs-return fork (Tier-3, the sharpest)

Options:

- **(a) RECOMMENDED — capture-first.** Capture **TB3MS** (3-month bill, secondary market, discount
  basis, monthly average — G42) VERBATIM as a new captured entity (OQ-3), with the units
  re-expression percent→fraction (3.66 → 0.0366) as the ONLY transformation at capture (the
  ENT-025/ENT-052 canonical-fraction convention, G9 — a pure units change, declared in the
  checklist). The series does NOT feed Sharpe in this slice; the demo rf series stays. The
  **yield → period-return registered model + the Sharpe re-source (new version labels)** becomes a
  NAMED CARRY with trigger: *the first governed consumer that binds the real rf series* (priced by
  SR-1 at G13; the CAL-1b v2 mint is the executed precedent for the label move). "Ingested through
  the governed capture rails as the real risk-free series" is delivered as: the real risk-free
  DATASET, on the governed rails, diligence-executed — the roadmap row's conversion claim ("converts
  the wave's real-data claim … into genuinely external market data on the governed rails", G1) is
  the slice's substance and is fully delivered.
- **(b)** Take the full path now: the new captured entity + a registered `perf.riskfree` conversion
  model + a governed derived monthly-return series + Sharpe v3 labels re-sourced to it. Delivers
  the phrase completely; roughly doubles the slice (a governed number mint + a convention move in
  one slice — the exact shape OQ-CAL-1-10 called scope-indiscipline, G4).
- **(c)** Re-scale at capture into `benchmark_return` under a "declared capture convention" —
  REFUSED in-draft: it is the never-derive violation with paperwork (G10/G11).
- **(d)** Switch candidates to a published monthly RETURN series — REFUSED in-draft: the only such
  series are commercial index products (G48) barred by the no-contract rule (G2).

*Recommend (a).* The slice was inserted to make "real data" true on the rails (G1), not to remint
Sharpe; (b) is priced and available if the user wants the full chain now.

**Named dispositions folded at the verifier pass (the omission class):** two further Tier-3-shaped
alternatives the recon surfaced are disposed, not dropped. **Maturity** — TB3MS is the 3-MONTH
bill; the Fama/French monthly-rf precedent uses a ONE-month bill (G48) and the demo rf head is a
1-month cash series (G16). Recommendation stands on TB3MS: it is the H.15 headline bill series
with the longest authoritative public-domain history, and the ratified row says "Treasury bill"
without maturity (G1); the maturity that BINDS a governed number is expressly assigned to the
conversion-model carry (option (a)'s trigger), where the 1-month/FF-precedent alternative is
re-opened before any Sharpe re-source. **Observation form** — monthly AVERAGE (TB3MS) vs a
month-end observation drawn from the daily series: the average is what the Board itself publishes
at monthly grain (G42/G43); a month-end-sampled series would be a derivation from dailies (an
item-6 trap, exactly what this slice refuses to smuggle); `observation_convention` on the row
(OQ-3) carries the choice explicitly so a future month-end series is a NEW convention value, not a
silent re-reading.

### OQ-DATA-1-2 — Tenancy of a public dataset (Tier-3)

Item 3's conditional says open/public ⇒ SYSTEM rows (G36), but: the hybrid set is CLOSED at 7 with
a membership rule for *vocabularies*, not time series (G21); the whole marketdata family is
"PROPRIETARY/symmetric; NEVER hybrid" (G20); the MARKET audit family has NO SYSTEM chain (G19);
and the ratified conditional's own scope was holiday SETS (G36). *Recommend:* **per-tenant
capture** (the `fx_rate` precedent named by item 3 itself), with Execution 2's item 3 recording
the divergence REASONING: the public⇒SYSTEM arm presumes a hybrid-capable reference table; a
market-data series is not a curated shared vocabulary; landing it per-tenant keeps AD-013-R2's
closed set, the CLAUDE.md invariant, and the MARKET chain posture all byte-unchanged. NO
AD-013-R3. (The battery captures it in the demo tenant; a real tenant captures its own copy — the
public-domain license makes duplication costless, G45.)

**Folded (verifier MED):** leaving item 3's literal "Open/public ⇒ SYSTEM rows" arm standing
unamended would make every future open/public market-data onboarding re-litigate this divergence —
an unstated recurrence acceptance. The ratification ask therefore includes an **H-05-class
clarifying amendment to checklist item 3**: the SYSTEM arm applies where the landing table is
hybrid-capable (AD-013-R1/R2 reference vocabularies); a time SERIES lands per-tenant regardless of
license openness, with the license recorded. The control's own text then carries the refined
conditional. (Also folded, LOW: Execution 1's item-3 citation `delivery_roadmap.md:369` is stale
at this HEAD — Execution 2 re-points it to `wave_14_planning.md:216-221` with the correction
noted.)

### OQ-DATA-1-3 — The landing entity: ENT-070 `benchmark_rate` (Tier-3: entity mint)

A yield observation is neither a `benchmark_level` (positivity-gated index level) nor a
`benchmark_return` (realized fraction) — forcing it into either corrupts a declared vocabulary.
*Recommend:* mint **ENT-070 `benchmark_rate`** as the FOURTH FR bitemporal child of the existing
`benchmark` EV header — the THIRD series-observation table of the ENT-052 kind, after
`benchmark_constituent`/`benchmark_level`/`benchmark_return` (miscount corrected at the verifier
fold) — migration `0060`:

- Grain `(tenant_id, benchmark_id, rate_date, rate_type, quote_basis)` current-head
  partial-unique (the G9 pattern verbatim).
- `rate_value` `PreciseDecimal(20,12)` **decimal fraction** (0.0366 = 3.66% — the ENT-025 units
  convention, G9); binder finiteness guard + DQ RANGE `> -1` — *recorded honestly (verifier LOW):
  the `-1` floor is house-pattern inheritance from return semantics, deliberately loose for a
  rate; it admits negatives (negative rates are real) and rejects only the nonsensical, which is
  all a generic RANGE should do here.*
- `rate_type` controlled vocab v1 = `BILL_DISCOUNT_YIELD` (the H.15 discount-basis series, G43);
  `quote_basis` v1 = `DISCOUNT_360` (`INVESTMENT_365` reserved — the G44 gap is why the basis is
  IN the grain). The capture verb enforces a **`rate_type` → allowed-`quote_basis` map**
  (`BILL_DISCOUNT_YIELD` ⇒ `DISCOUNT_360` only), so an incoherent combination refuses at capture
  when the reserved basis activates (verifier LOW). Both vocabularies are the **capture-time
  convention surface** — this is how the slice pays OQ-CAL-1-9's named option (G40) WITHOUT
  retrofitting `benchmark_return` (OQ-10).
- `observation_convention` v1 = `MONTHLY_AVG_BUSINESS_DAYS` (G42/G43) — the dating/averaging
  convention carried ON the row, not only in prose.
- **Coverage grain (verifier MED, recorded as a v1 limitation + a structural refusal):**
  `rates_complete_through` lives on the `benchmark` HEAD while the rate grain is
  `(rate_type, quote_basis)`-scoped — one horizon cannot say WHICH series is complete once a
  second series shares the head. v1 therefore REFUSES capturing a second
  `(rate_type, quote_basis)` pair on a head whose horizon is set (fail-closed, negative-controlled);
  per-series coverage is the recorded follow-on if a second series ever lands.
- Symmetric FORCE RLS; FR (NOT append-only — supersede/correct per G47's revisability); ORIGIN
  lineage per version row off `VENDOR_BENCHMARK`; `marketdata.view`/`.ingest` REUSED (no R-07
  permission act); audit triple **`MARKET.BENCHMARK_RATE_CREATE/_UPDATE/_CORRECTION`** minted via
  the taxonomy-row-as-mint-record pattern — an explicit gate item (G39).

### OQ-DATA-1-4 — `RULE_TYPE_COMPLETENESS` (the fourth generic rule type)

*Recommend:* mint in `dq/rules.py` as value + pure evaluator + REGISTRY entry (no migration —
G24): params carry `{"key_column": ..., "expected": [sorted literal keys]}` and the evaluator
diffs the dataset's keys against `expected` both ways (missing ⇒ FAIL rows named; unexpected ⇒
FAIL — the census-both-directions lesson). The persisted rule then literally "says what was
expected" — REF-1's trigger wording satisfied verbatim (G6). The expected set is computed
CALLER-side (G25) from **two DECLARATIONS, never from data** (the G32 standard at BOTH
boundaries — verifier MED: a data-derived start makes a missing FIRST month unrepresentable):
`TB3MS_SERIES_START = 2024-01-01` (a module literal beside the horizon) through
`rates_complete_through`. **The persisted rule's params advance with the horizon** (verifier
LOW): the refresh verb calls `update_dq_rule` co-transactionally (its `DATA.DQ_RULE_DEFINE`-family
audit event in the verb's declared grain) so the rule row always says what was LAST expected; the
historical result→rule-version linkage is a recorded limitation (`data_quality_result` pins
neither params nor rule `record_version`). The registry census pin (G24) moves to the four-member
set. `dq/gates.py` stays as-is (sibling — its presence gate keeps its no-capture-path-caller state
honestly recorded, G27). Severity ERROR, co-transactional through `run_quality_check` (G26).

### OQ-DATA-1-5 — The P3-8 carry: what lands, what re-defers — an EXPLICIT gate decision

*(Rewritten in full at the verifier fold — the pass's BLOCKING, found independently by two
lanes.)* P3-8 deferred **"trading-calendar completeness validation"** as data-quality scope (G29). The
draft claimed the "calendar-derived expected-set machinery" lands here — refuted: this slice's
only completeness firing (OQ-6) computes a MONTHLY expected set by pure month arithmetic from two
declarations; **no DATA-1 deliverable consumes `resolve_calendar`/`calmath`/`xnys_holidays`**. A
monthly series has no trading-day grain to police; building a calendar-driven trading-day
expected-set builder here would ship untested dead surface with no consumer.

So the honest decomposition, put to the gate plainly rather than blended:

- **What LANDS:** the generic `RULE_TYPE_COMPLETENESS` (OQ-4 — REF-1's trigger honestly fired,
  G6) + its month-grain execution against the first genuinely external series (OQ-6).
- **What RE-DEFERS, in full and a third time:** the trading-calendar-SPECIFIC wiring — BOTH the
  calendar-derived trading-day expected sets AND `perf.benchmark_relative`'s runtime acceptance
  (today: zero-row-window refusal only, G30; per G31 changing it is a governed convention change
  to a SHIPPED number's input path ⇒ a NEW version label under the no-amend rule). **Named carry,
  trigger: the first captured DAILY benchmark series** — the grain the hazard actually fires on
  (today's only daily benchmark data is demo-authored; a monthly series cannot exercise it).
- **This diverges from the literal text of the roadmap's forward pointer** ("the P3-8
  trading-calendar wiring land[s] by ratified re-deferral", G5) and is therefore an **explicit
  ratification decision**, not a disposition the record takes for itself: ratifying OQ-5 ratifies
  the third deferral WITH its named trigger, and the close-time roadmap row + REQ-PRF-002 record
  **RE-POINTED (not discharged)** — the backbone's "the wiring rides the first genuinely external
  series" clause (G34) moves to the new trigger with this record cited.

The record still inherits P3-8's OQ by name, as OQ-CAL-1-10 requires (G4): this OQ IS that
inheritance, with the missing-day compounding hazard (G29/G30) restated and its control status
unchanged — loud limitation, zero-row refusal, no imputation.

### OQ-DATA-1-6 — Where completeness FIRES for this series

*Recommend:* at the REFRESH boundary (OQ-7's verb), not per-row, with the semantics made precise
at the verifier fold:

- **Firing condition (verifier MED):** the completeness rule runs only when the refresh is
  EFFECTIVE (additions > 0 OR the horizon advances); a true no-op returns BEFORE the DQ leg, so
  "idempotent no-op silent" stays true and PASS results do not accumulate as noise. Pinned by
  test.
- **FAIL-evidence semantics (verifier HIGH — the draft's whole-refresh rollback would have
  discarded its own FAIL evidence and made the gate's ANY-FAIL arm unreachable, the platform's
  named vacuous-guard class):** the verb wraps its DATA writes (rate rows + horizon advance) in a
  `begin_nested()` savepoint; on a completeness FAIL the savepoint rolls back the DATA while the
  FAIL `data_quality_result` + `DATA.VALIDATE` audit COMMIT (G26's "a failure ALWAYS persists a
  flagged result" honored through this path), and `DataQualityError` propagates. A negative
  control pins exactly this: failed refresh ⇒ zero rate rows, horizon unmoved, ONE persisted FAIL
  result.
- **Expected-set boundaries:** declared start → declared horizon (OQ-4). The in-progress-month
  exclusion is an operator CONVENTION whose violation degrades fail-closed (declaring an
  unpublished month ⇒ that month missing ⇒ completeness FAIL ⇒ refused refresh — verifier LOW,
  reworded from "structural"); additionally the verb REFUSES a `complete_through` beyond the month
  of the last supplied rate (cheap and structural).
- `assert_passed_quality_checks` (G28) gains its first CAPTURE-RAIL caller (its second overall —
  the live P1A-4 ingestion gate is the first): the battery asserts the captured series carries a
  passing completeness result.

### OQ-DATA-1-7 — The delivery path (NO live adapter)

*Recommend:* the CAL-1a pattern executed on the marketdata rail: a hand-encoded literal module
`marketdata/tb3ms_rates.py` (`TB3MS_SERIES_START = 2024-01-01`, 30 dated literals
2024-01..2026-06, `TB3MS_COMPLETE_THROUGH = 2026-06-30`, each value re-verified by hand at the
gate — G46), plus an add-only
`refresh_benchmark_rates(session, benchmark, *, actor, rates, complete_through=None)` verb:
intra-call dedupe first-spec-wins; FORWARD-ONLY `rates_complete_through` advance on the benchmark
head (the CAL-1a coverage pattern; a declared horizon because a derived MAX cannot represent a
gap, G32); per-row `MARKET.BENCHMARK_RATE_*` events (G18 grain) **plus one `REFERENCE.UPDATE` on
the `benchmark` head per effective refresh** (the head-advance write audited with its
`record_version` bump — the CAL-1a parent-update pattern; verifier MED: the draft left the head
write unaudited, a BR-5 gap) **plus the `update_dq_rule` params-advance event** (OQ-4); idempotent
no-op silent (the firing condition in OQ-6); NO removal path; supersede/correct stay per-row verbs
(G47 corrections are rare and row-scoped). FRED is the access channel (attribution recorded); the
checked-in module is hand-encoded from values READ via a proxy-rendered page view — a single
access, not mining/mirroring — and hand re-verified at the gate (wording aligned with G46 at the
verifier fold; the draft's "hand-transcribed" understated the provenance); any FUTURE programmatic
refresh targets the Board's DDP — recorded in the checklist, not built.

### OQ-DATA-1-8 — The licensing/source position (H-05-class per BR-15 — explicit gate item)

*Recommend recording in Execution 2:* authoritative ORIGIN = Board of Governors, H.15 release
(G42); licensing = U.S. public domain at origin (17 U.S.C. §105) + the Board's disclaimer, cite
the Board (G45); FRED = access/verification channel, attribution given, internal commercial use
permitted under its ToU (G45), with the TRUE acquisition path stated — proxy-rendered single-page
reads, hand re-verified, hand-encoded module (G46; verifier LOW) — not "hand-transcribed"; the
series is REVISABLE with documented historical corrections (G47) — represented by the FR
supersede/correct verbs. This is a legal/compliance position and is ratified at the gate, not
routed autonomously (G39).

### OQ-DATA-1-9 — CTRL-034 Execution 2 + the Status question

Execution 2 fills all nine items at Execution 1's granularity (G38), including: item 1 naming the
consuming reads as they EXIST in-slice — the completeness rule + the new rate read endpoint
(OQ-11) — with the FUTURE Sharpe month-key join (G14) named as the intended consumer behind the
OQ-1a carry; item 4 recording FRED's first-of-month dating (G47) against the declared
INSIDE-the-month convention (G14) — **conforming AT THE RATE-OBSERVATION grain** (an observation
dated inside the month it averages); *the return-month mapping (contemporaneous vs ex-ante — a
June-observed yield may be the rate FOR July) is expressly assigned to the conversion-model carry,
where a re-dating rule may yet be required* (verifier MED: the draft's unconditional "no re-dating
rule needed" pre-judged exactly the question the un-ratified conversion model must answer); item 4
also ENUMERATES the undetectable-in-data defects per the item's own text: uniform re-dating, a
basis mislabel (the 15bp discount-vs-investment gap, G44), and the H.15 averaging-footnote
ambiguity (G43 — pinned at the gate); item 5 labeling 2026-07 PENDING; item 6 naming the
derivation traps NOT taken (the three annualized→monthly treatments, the basis conversion);
item 8's positive census (30 rows, exact set-equality, endpoint anchors 5.22/3.66, the
declining-path shape) and negative pins (NO 2026-07 row; NO derived monthly-return row anywhere);
item 9: trigger = each `complete_through` advance re-runs the census, a source/convention change
re-executes the checklist in full, **owner R-10** (verifier MED: the draft omitted the owner
Execution 1's bar requires).
*Recommend* CTRL-034 Status moves **Implemented → Operational** at close (second execution, first
genuinely external dataset — the legend supports it, G35); the move is proposed at this gate, not
taken silently.

### OQ-DATA-1-10 — The OQ-CAL-1-9 convention-field option: disposition

*Recommend:* PAID-BY-DESIGN on the new entity — `quote_basis` + `observation_convention` +
`rate_type` ARE capture-time convention fields, born with the table (OQ-3, G40). Retrofitting
`benchmark_return` with a convention field stays UNTAKEN with the trigger re-recorded: *the first
real vendor RETURN series onboarding* (that vendor's dating convention interrogation will say
whether a column or the checklist carries it). Recorded here so the CAL-1 record's "natural home"
clause has an explicit disposition, not silence.

### OQ-DATA-1-11 — Demo/battery surface (Rule 7 + the count pin)

*Recommend:* demo stage 22 (`data1_stage22.py`, the 13-z FINAL-POSITION suite): capture the real
TB3MS series in the demo tenant through the verb (a NEW `US-TBILL-3M` benchmark head under source
`US-FRB-H15`; the DEMO_VENDOR rf series coexists — different `(code, source)`, G16); execute the
completeness rule (its first live PASS + a mutation-negative: drop one interior month ⇒ FAIL);
exercise supersede-as-correction once (G47). Zero new `calculation_run`s — the count pin stays
**26/43/139** with the FINAL-POSITION label relayed to the 13-z suite (the CAL-1b relay
precedent). Read surface (verifier HIGH, found by two lanes — the draft's "the EXISTING benchmark
read surface serves it" was FALSE: the marketdata router imports exactly
`list_benchmark_levels`/`list_benchmark_returns`/`list_benchmarks` and nothing can read a
`benchmark_rate` table): a minimal tenant-scoped read **IS in-scope** —
`GET /benchmarks/{benchmark_id}/rates` under the reused `marketdata.view`, the
`list_benchmark_returns` pattern verbatim — so the captured series is not a write-only field (the
SCH-2 disclosure lesson) and CTRL-034 item 1 has a real consuming read to cite.

### OQ-DATA-1-12 — Size, split, and the register footprint

*Recommend:* single slice, sized **M/L** with the comparison stated (verifier MED: the draft's
bare "M" understated against the platform's own comparables — CAL-1a was M with NO migration, NO
entity, NO rule mint, while this slice contains that whole shape PLUS migration `0060`, the
ENT-070 mint with a four-verb FR rail, the rule-type mint, and the read endpoint; the reuse
argument — `benchmark_series.py` copied verbatim — is what holds it under L). **Named split line
if it runs long: DATA-1a (entity + dataset + checklist + reads) / DATA-1b (the completeness mint +
wiring)** — ratified now so a mid-slice split needs no new gate. Registers touched at close:
ENT-070 row + next-free → ENT-071; `MARKET.BENCHMARK_RATE_*` taxonomy row (the mint record, R-07
at this gate); REQ-DQR-001 completeness clause advanced; **REQ-PRF-002 RE-POINTED (not
discharged) to the OQ-5 trigger** (verifier BLOCKING follow-through); REQ-PRF-004 unchanged (its
doctrine is what OQ-1a preserves); REQ-INT-002/003 byte-untouched (G3); CTRL-034 row evidence +
Status (OQ-9) + the item-3 amendment (OQ-2); **`current_state.md` CURRENT-TRUTH advance (head
0060, next-free ENT-071, the 13-z count-pin relay, NEXT pointer) and the roadmap close row
INCLUDING an explicit disposition of the ratified "as the real risk-free series" clause under
OQ-1a** (verifier MED: both were missing, and ledger 7 fails at close without the roadmap
disposition); NO new AD row (AD-020 stays free — the tenancy decision is an application of
AD-013-R2's closed set, not a new architecture decision); NO new permission, NO new role; the DQ
registry census pin moves (G24).

---

## Part 3 — deliverable inventory (the implementation contract, if ratified as recommended)

1. Migration `0060_benchmark_rate`: the ENT-070 table (grain/columns per OQ-3), symmetric FORCE
   RLS, current-head partial-unique, NO append-only trigger (FR), `rates_complete_through`
   (nullable Date) on `benchmark` — with a P4 executed non-vacuous up/down dry run.
2. `marketdata/models.py`: `BenchmarkRate` + vocabularies (`BENCHMARK_RATE_TYPES`,
   `BENCHMARK_RATE_QUOTE_BASES`, `OBSERVATION_CONVENTIONS`) + the `rate_type` → allowed-basis map
   (OQ-3).
3. `marketdata/benchmark_rates.py`: `capture_benchmark_rate` / `supersede` / `correct` /
   `reconstruct_benchmark_rate_as_of` + `refresh_benchmark_rates` (add-only; forward-only
   coverage; the OQ-6 semantics: effective-only firing, savepoint-preserved FAIL evidence,
   horizon-beyond-last-rate refusal; the OQ-3 second-series refusal; the OQ-4 `update_dq_rule`
   params advance), race-safe DQ resolve-or-register, finiteness guard, the
   `MARKET.BENCHMARK_RATE_*` triple + the head `REFERENCE.UPDATE` (OQ-7), ORIGIN lineage — the
   `benchmark_series.py` pattern verbatim.
4. `marketdata/tb3ms_rates.py`: `TB3MS_SERIES_START` + 30 hand-verified literals + horizon
   (OQ-7; G46 re-verification).
5. `dq/rules.py`: `RULE_TYPE_COMPLETENESS` + `evaluate_completeness` (pure, both-directions) +
   REGISTRY entry; the census pin update; negative controls (missing interior key ⇒ FAIL;
   missing FIRST key ⇒ FAIL — the declared-start boundary; unexpected key ⇒ FAIL; the evaluator
   mutation-tested).
6. `assert_passed_quality_checks`: first CAPTURE-RAIL caller (battery assertion per OQ-6 — the
   live P1A-4 ingestion gate is its first caller overall, G28) + the two STALE dq docstrings
   (`dq/service.py:7`, `dq/__init__.py:6`) corrected in-slice.
7. `GET /benchmarks/{benchmark_id}/rates` under `marketdata.view` (OQ-11 — the
   `list_benchmark_returns` pattern) with its permission-negative test.
8. CTRL-034 Execution 2 section (all nine items, OQ-9) + the item-3 clarifying amendment (OQ-2) +
   the Execution-1 stale-citation re-point + matrix row update.
9. Demo stage 22 + the 13-z suite + CI step + count-pin relay (OQ-11).
10. Registers per OQ-12; the two named carries recorded with triggers (OQ-1a, OQ-5).
11. Tests: dataset census (set-equality + anchors + negative pins), verb idempotence/forward-only/
    dedupe/refusal arms, completeness rule unit + PG, RLS/cross-tenant negatives for the new table
    (child WITH-CHECK asserted BY TABLE NAME — the CAL-1a lesson), audit-event grain incl. the
    head `REFERENCE.UPDATE`, reconstruct round-trip.

## Part 4 — what this slice deliberately does NOT do (recorded limitations, BR-14)

- Does NOT feed Sharpe with the real series (OQ-1a carry, triggered).
- Does NOT wire the trading calendar into completeness NOR change any shipped number's runtime
  acceptance — the P3-8 trading-calendar wiring re-defers IN FULL, a third time, as an explicit
  ratification decision (OQ-5 carry, triggered).
- Does NOT build any live adapter, scheduler hook, or programmatic fetch (G1/G2; FRED ToU G45).
- Does NOT extend the hybrid set or write SYSTEM rows (OQ-2).
- Does NOT mint a model, a permission, a role, or an AD row (OQ-12).
- The 2026-07 observation ships ABSENT (pending publication; the refresh verb is the paid path).
- Head-grain coverage: one `rates_complete_through` per benchmark head — a second
  `(rate_type, quote_basis)` series on the same head REFUSES in v1 (OQ-3).
- A historical `data_quality_result` does not pin the rule params/`record_version` it evaluated
  under — recoverable only via the DQ-rule audit trail (OQ-4).
- **The gate latch (review fold):** `assert_passed_quality_checks` blocks on ANY historical FAIL
  over the append-only results — a once-failed series stays gate-latched even after remediation
  (the operational read is the LATEST result per rule; a latest-scoped gate mode is the recorded
  follow-on, the LIM-1 recompute-from-source doctrine).
- **Duplicate-month blindness (review fold):** the month census is SET-based — a second
  observation inside an already-complete month passes "monthly completeness" (a MIS-dated row is
  still caught by the missing direction); an optional uniqueness param is the recorded follow-on.
- **FAIL-evidence caller contract (review fold):** the evidence survives only if the caller
  catches `DataQualityError` and COMMITS; a rollback-on-error caller discards it (the PG
  savepoint test is the executed pattern).

---

## Part 5 — the verifier fold (2026-08-02)

Four independent refute-by-default lanes over the full draft (citation / quant / governance /
scope), run as fresh-context workflow agents. Verdicts: citations SOUND-WITH-FINDINGS, quant
REFUTED-IN-PART, governance SOUND-WITH-FINDINGS, scope REFUTED-IN-PART. **28 findings — 1 unique
BLOCKING (found independently by two lanes), 5 unique HIGH, 10 MED, 10 LOW — ALL folded above in
place**, each marked *(verifier …)* at its fold site. Dispositions, most severe first:

- **BLOCKING (quant + scope, independently):** OQ-5 claimed the calendar-derived expected-set
  machinery lands while the design's expected set is pure month arithmetic — the ratified
  "trading-calendar wiring lands here" would in fact re-defer a third time with the record
  presenting half as delivered (the REF-1 "forward-looking prose read as delivery" class). FOLDED:
  OQ-5 rewritten in full — the third deferral is now stated plainly as an explicit ratification
  decision with its named trigger, and OQ-12 records REQ-PRF-002 as RE-POINTED, not discharged.
- **HIGH (citations):** G28's "zero ingestion callers" was FALSE — `assert_passed_quality_checks`
  has a live HTTP-reachable caller (`ingestion/service.py:279`); the draft had inherited stale
  docstrings instead of grepping callers. FOLDED: G28/OQ-6/Part 3 corrected ("first CAPTURE-RAIL
  caller"); the stale docstrings become an in-slice fix.
- **HIGH (citations):** G27 presented a composite paraphrase inside quotation marks with a false
  locator — the P7 fabricated-quotation class, inside a Part 0 promising verbatim quotes. FOLDED:
  replaced with true verbatim quotes and correct citations; every component fact held.
- **HIGH (quant):** OQ-6's "a FAIL rolls back the whole refresh" would have discarded the FAIL
  evidence run_quality_check persists co-transactionally, making the gate's ANY-FAIL arm
  structurally unreachable — the platform's named vacuous-guard class. FOLDED: savepoint
  semantics (data rolls back, FAIL evidence commits) with the pinning negative control specified.
- **HIGH (governance + scope, independently):** OQ-11's "the EXISTING benchmark read surface
  serves it" was FALSE — no endpoint can read the new table, and CTRL-034 item 1 would have had
  no consuming read to cite. FOLDED: `GET /benchmarks/{id}/rates` is in-scope (Part 3 item 7).
- **HIGH (scope):** OQ-1 dropped two recon-surfaced Tier-3 alternatives (1-month vs 3-month
  maturity; average vs month-end observation) without disposition — the omission class. FOLDED:
  both disposed in OQ-1 with the maturity choice expressly assigned to the conversion-model carry.
- **MED (10):** G49's "brackets" was arithmetically false (reworded to what the data shows); the
  head-advance write was unaudited (one `REFERENCE.UPDATE` per effective refresh named); checklist
  item 3's literal SYSTEM arm would be re-litigated forever (an H-05-class clarifying amendment
  added to the ask); Execution-2 sketch missed item-9's owner and item-4's defect enumeration
  (both added); item-4's "conforming, no re-dating rule needed" pre-judged the return-month
  mapping (scoped to the observation grain; the mapping assigned to the carry); OQ-12 omitted
  current_state + the roadmap-clause disposition (added — ledger 7 would have failed at close);
  sizing M understated vs the CAL-1a comparable (re-sized M/L with a ratified split line);
  `rates_complete_through`'s head-grain vs series-grain mismatch (v1 second-series refusal +
  recorded limitation); the expected set's start was data-derived (declared `TB3MS_SERIES_START`);
  "idempotent no-op silent" contradicted completeness-every-refresh (effective-only firing).
- **LOW (10):** G13 cite + "same text" wording; G15 range + the punctuation-normalization note;
  G47 2002–2005; G34 extended to carry the quoted backbone phrase; the FOURTH-child miscount; the
  `-1` floor recorded as loose inheritance + the rate_type→basis map; the in-progress-month
  exclusion reworded as convention-degrading-fail-closed + the horizon refusal; provenance wording
  aligned with G46 in OQ-7 AND OQ-8; Execution-1's stale `delivery_roadmap.md:369` citation
  re-pointed at Execution 2.

**What survived attack (the lanes' confirmations, abbreviated):** the Part-1 central collision
(all three doctrine anchors byte-exact; the no-public-domain-monthly-return claim survived a
counterexample hunt); the OQ-2 per-tenant tenancy reasoning (attacked with the strongest
counter-text and held structurally); the OQ-3 grain/scale against the real siblings; OQ-4's fit to
the actual DQ contracts and REF-1's trigger wording; OQ-11's count-pin neutrality (verified
against the 12-z suite's actual pin: Model.code / ModelValidation / COMPLETED runs — a capture+DQ
stage writes none); the 13-z sort order; the audit-mint pattern precedents; the licensing
origin/channel split; the item-4 observation-grain conformance; every governance routing (nothing
reserved routed autonomously); and the G7/G8 baselines re-executed clean.

---

## Part 6 — the ratification record (2026-08-02)

The user ratified **OQ-DATA-1-1…12 ALL as recommended** ("Proceed" on the plain-language gate
briefing, which named OQ-1 and OQ-5 as the decisions with the most real alternatives). The acts
this ratification executes, each of which was an explicit item in the ask:

- **OQ-1a — capture-first ratified.** TB3MS lands verbatim as a captured dataset; the
  yield→period-return registered model + the Sharpe re-source (new version labels) is a NAMED
  CARRY, trigger: *the first governed consumer that binds the real rf series*. The maturity
  (3-month vs 1-month) and observation-form dispositions stand as recorded.
- **OQ-2 — per-tenant tenancy ratified; the CTRL-034 item-3 clarifying amendment is
  H-05-APPROVED** (the SYSTEM arm applies where the landing table is hybrid-capable; a time
  series lands per-tenant regardless of license openness). No AD-013-R3; invariants byte-unchanged.
- **OQ-3 — the ENT-070 `benchmark_rate` mint APPROVED** (migration `0060`, the ratified grain,
  vocabularies, second-series refusal, v1 limitation).
- **The `MARKET.BENCHMARK_RATE_CREATE/_UPDATE/_CORRECTION` audit triple is R-07-APPROVED at this
  gate** — the taxonomy row written at implementation IS the mint record (the P2-7/SCH-1 pattern).
- **OQ-4/OQ-6 — `RULE_TYPE_COMPLETENESS` mint ratified** with the declared-boundaries expected
  set, params-advance mechanics, effective-only firing, and savepoint-preserved FAIL evidence.
- **OQ-5 — the THIRD deferral of the trading-calendar wiring is EXPLICITLY RATIFIED** with
  trigger: *the first captured DAILY benchmark series*; REQ-PRF-002 will be recorded RE-POINTED,
  not discharged; the divergence from the roadmap pointer's literal text is ratified with it.
- **OQ-7/OQ-8 — the delivery path and the licensing position are H-05-APPROVED as recorded**
  (Board/H.15 public-domain origin; FRED as attributed access channel; the true acquisition path
  stated; all 30 literals re-verified before implementation ships — *corrected at the review
  fold: the verification was a third full extraction pass via the SAME proxy channel, not an
  independent-channel hand pass; recorded honestly in Part 8*).
- **OQ-9 — CTRL-034 Execution 2 ratified; the Implemented→Operational status move is APPROVED,
  to be stamped at close.**
- **OQ-10 — the OQ-CAL-1-9 convention-field option is PAID-BY-DESIGN on the new entity;** the
  `benchmark_return` retrofit stays untaken with its re-recorded trigger.
- **OQ-11 — the read endpoint, demo stage 22, and the 13-z FINAL-POSITION relay ratified.**
- **OQ-12 — sized M/L; the DATA-1a/1b split line is PRE-RATIFIED** (usable mid-slice without a
  new gate); the register footprint as recorded.

---

## Part 7 — the implementation log (2026-08-02, branch `data-1` off `de20d4b`)

Implemented single-threaded in three commits (`567d2a4` core + tests; `12ae033` demo/PG/CI/FE;
batch 3 = the governance artifacts + this part). *(Part-8 correction: the draft of this part
claimed the FULL Part 3 inventory had shipped — the review refuted it: the endpoint's
permission-negative tests were missing, delivered at the fold.)* The decisions TAKEN
IN-IMPLEMENTATION, recorded per the gate-reversal discipline:

1. **The differing-value refresh refusal (new, fail-closed):** the ratified ADD-ONLY semantic
   left a hole — a refresh re-supplying a captured date with a DIFFERENT value would have
   silently no-opped, hiding a vendor revision (G47's real class). The verb REFUSES loudly,
   naming `correct_benchmark_rate`. First-spec-wins stays intra-call only.
2. **Additions beyond the horizon require the matching `complete_through` in the same call:**
   the both-directions census makes a captured month beyond the declared horizon an UNEXPECTED
   key ⇒ completeness FAIL ⇒ the refresh refuses — declare-what-you-have, structurally. Not a
   defect; recorded so nobody reads the refusal as a bug.
3. **The `_SeriesSpec` union widened** (`benchmark_series.py` now admits `BenchmarkRate`) — one
   generic FR core, three series tables, zero copied protocol code; `observation_convention`
   rides the spec's key tuple for row construction/queries while the DB unique index stays on
   the ratified four-key grain (stricter; a convention mismatch surfaces as a loud unique
   violation).
4. **The coherence map is tested NON-VACUOUSLY** via monkeypatch-minting the reserved
   `INVESTMENT_365` basis (with one rate_type × one basis in the live vocab the branch could
   never fire — the vacuous-guard class caught at authoring, not review).
5. **The third extraction pass:** the 30 literals were re-retrieved fresh at implementation
   (proxy-rendered FRED data page; all 30 values + both anchors + the update timestamp agree
   with the two recon passes). The Board's DDP CSV was attempted first and is not reachable
   anonymously from this environment — recorded; FRED-with-attribution stands as the access
   channel (Execution 2 item 3).
6. **Two guards fired during implementation, each on exactly the thing it guards:** the DQ
   registry set-equality pin (three suites — updated to the four-member set with the mint), and
   `test_ci_pg_coverage` (the new PG suite had no CI step; one added). The 21 head pins relayed
   `0059 → 0060`; the synthetic next-free glob relayed to `0061` with its NOTE.
7. **Savepoint semantics verified on BOTH engines:** the unit negative control (SQLite) and the
   PG twin (`test_completeness_fail_savepoint_semantics_on_real_pg`) both pin: gappy refresh ⇒
   `DataQualityError`, ZERO rate rows, horizon unmoved, ONE persisted FAIL result naming the
   missing month — and, folded from the review, the PG twin now ALSO pins the audit-row unwind
   (zero `MARKET.BENCHMARK_RATE_CREATE`, zero `REFERENCE.UPDATE`) on the authoritative engine
   *(the draft claimed the head-event pin on both engines while it existed only on SQLite)*.
8. **Registers written:** the ENT-070 row + next-free → ENT-071; the taxonomy
   `MARKET.BENCHMARK_RATE_*` activation sentence (the R-07 mint record); CTRL-034 Execution 2 +
   the item-3 amendment + the Execution-1 stale-citation re-point + Status → Operational;
   REQ-DQR-001 (four evaluators; the completeness half of its named gap closed) and
   REQ-PRF-002 RE-POINTED to the OQ-5 trigger in BOTH registers; current_state CURRENT TRUTH.

---

## Part 8 — the review fold (2026-08-02)

Four fresh-context adversarial lanes over the full diff (quant+mutation / security-RLS /
claims-vs-diff / demo-battery-integration). Verdicts: security SOUND-WITH-FINDINGS, the other
three REFUTED-IN-PART. **24 findings — 1 BLOCKING (procedural), 7 HIGH, 9 MED, 7 LOW — ALL
folded**, the load-bearing ones with executed negative controls:

- **BLOCKING (procedural, lane D):** the first full-PG battery ran while the quant lane was
  mutation-testing IN THE SHARED TREE (a live mutant was observed in `dq/rules.py` mid-run) —
  the P2 shared-tree class. Disposition: that battery is VOID as evidence; the tree was verified
  reverted (zero mutation markers in tree or diff), `__pycache__` purged, and the battery
  RE-RUN on the quiescent tree — the re-run below is the evidence of record. Standing lesson
  sharpened: never overlap a mutation lane with a gate battery on one tree.
- **HIGH (quant, proven by execution):** the `series_start`-precedes-horizon refusal fired AFTER
  `begin_nested()`, leaving the savepoint DANGLING — a catch-and-commit caller persisted the
  refused batch UNGATED (rate rows + horizon + head event, completeness never run), refuting the
  verb's own "fail-closed BEFORE any surviving write" contract. FOLDED: the expected set is
  computed pre-savepoint;
  `test_horizon_before_series_start_refuses_with_NOTHING_persisted` is the hostile-caller
  negative control (catch → COMMIT → zero rows, horizon None, zero events).
- **HIGH (three lanes independently):** the ratified endpoint permission-negative tests did not
  exist (Part 7 claimed full delivery). FOLDED: 403/404/happy-path serialization tests in
  `apps/backend/tests/test_benchmark_series_endpoints.py`; Part 7 corrected in place.
- **HIGH (security):** the PG savepoint twin never pinned the audit-row unwind (claimed on both
  engines, true on one). FOLDED: zero-CREATE + zero-REFERENCE.UPDATE pins added on PG.
- **HIGH (claims):** CTRL-034 was stamped Operational at implementation time against the
  ratified "stamps at close, after observed operation". FOLDED: reverted to Implemented with the
  approval noted; stamps at the observed close.
- **HIGH (claims):** three artifacts asserted battery execution as fact pre-observation. FOLDED:
  reworded; the close records the OBSERVED re-run (the P6 standard).
- **MED (quant, proven):** a WARNING-downgrade of the persisted rule made a failed refresh
  return a fabricated success dict over rolled-back data. FOLDED: the refusal raise is now
  severity-INDEPENDENT; `test_severity_downgrade_cannot_fabricate_success` executes the
  downgrade and proves the refusal + unwind.
- **MED (quant, proven):** the committed-FAIL-evidence design × the gate's ANY-FAIL-forever scan
  latch permanently. FOLDED as a recorded limitation (Part 4 + Execution 2 item 7) with the
  latest-scoped follow-on named.
- **MED (security):** the completeness rule was tenant-scoped while claiming series scope — a
  second rate-bearing head would clobber the expected-set params. FOLDED: the rule is
  HEAD-scoped (`completeness_rule_code_for`, the head id in the code).
- **MED (claims/provenance):** "THREE independent extraction passes" overstated — two full + one
  sampled, ALL via one proxy channel; the ratified independent hand re-verification remains
  UNDISCHARGED and moves to the close gate (the census gained four interior anchors; interior
  values otherwise rest on provenance, now stated everywhere honestly).
- **MED (claims):** stage 22 dropped the ratified supersede-as-correction exercise silently.
  FOLDED: the correction verb runs on the authoritative engine in the PG suite (a test tenant —
  fabricating a correction on the REAL series in the demo tenant would violate data realism);
  the narrowing recorded here.
- **MED (claims):** current_state lost its NEXT pointer and kept a stale header date. FOLDED
  (NEXT = LQ-1 after the DATA-1 close; 2026-08-02).
- **The LOWs:** the observation-convention mismatch silently absorbed by the refresh diff (now a
  loud refusal + test); the beyond-horizon-without-complete_through semantic pinned at the
  refresh level; the duplicate-month set-semantics limitation recorded; the FAIL-evidence caller
  contract stated in the docstring + item 7; the 12-z module docstring demoted (exactly one file
  carries FINAL-POSITION); the 13-z "runs last in the battery" scoped to the demo suites; the
  stage summary's horizon now taken from the verb's return, not the module constant.

**What survived attack (abbreviated):** all 30 fractions verified value-by-value against the
recon percent list (/100 exact); `evaluate_completeness` mutation-hardened (four mutants, all
killed); `_expected_months` boundary-correct; every OTHER pre-write refusal genuinely fires
pre-savepoint; the idempotent no-op truly silent; migration 0060 byte-parallel with 0029; the
forged-tenant test proves the CHILD's WITH CHECK; the grants fixture complete; DC-2 payloads
carry no rate value at any emit site; the frozen-file/mint invariants hold; count-pin neutrality
on every code path; the CAL-1b crash class does NOT recur (EV single-row probe; USD seeded
before the 13-z suite in both orderings); the quantize comparison exact; unit tier green from an
ISOLATED worktree.

---

## Part 9 — the close (2026-08-02)

**Merged: PR #165 = `0d5eb4a`** (the tenth autonomous merge). Pre-merge checks: all six contexts
green on both runs of the branch. Merged-main CI: **run 30757419834 — OBSERVED GREEN, all six jobs**
(Backend (Python), DB migration (Postgres), Frontend (TypeScript), API type drift, Documentation
check, Secret scan).

### The gates, as observed

| Gate | Observed |
|---|---|
| `make check` (lint + types + unit) | green |
| P4 migration dry run (up/down, throwaway workspace) | executed, non-vacuous |
| FE typecheck + tests | green, 207 tests |
| Full-PG battery, fresh schema, quiescent tree | **2,950 passed / 0 failed**, `PYTEST_EXIT=0` |
| PR checks | 6/6 green |
| Merged-main CI | **all six jobs success**, run 30757419834 |

The battery number is the **third** run. Run 1 was VOIDED under P2 (a mutation lane held the
shared tree). Run 2 was **RED** — and the failure was in a test the review fold had itself just
added: it committed and then read in the SAME session, but `set_tenant_context` is
TRANSACTION-LOCAL and auto-clears at COMMIT, so RLS correctly returned zero rows. That is the
MD-H1 annex-4 trap this repo already documents in `persistent_tenant_context`'s own docstring.
The fix (verify in a FRESH session) is strictly stronger than the original: it also proves the
correction is DURABLE rather than merely flushed.

### The P1 seven-ledger sweep + verify-on-main (run AFTER the merge, on `origin/main`)

| # | Ledger | Result |
|---|---|---|
| 1 | `canonical_data_model_standard.md` | ENT-070 row present; next-free pointer reads **ENT-071** |
| 2 | `audit_event_taxonomy.md` | `MARKET.BENCHMARK_RATE_*` activation row present (the R-07 record) |
| 3 | `control_matrix_skeleton.md` | CTRL-034 touched — Implemented → **Operational**, with the residual carried |
| 4 | `current_state.md` | CURRENT TRUTH block dated 2026-08-02; head `0060`; NEXT = LQ-1 |
| 5 | `02_requirements/` backbone + RTM | both halves carry the four-evaluator REQ-DQR-001 and the RE-POINTED REQ-PRF-002 |
| 6 | Counts | **26/43/139 MEASURED** on the fresh battery; the 13-z suite holds FINAL-POSITION, the 12-z demoted to POSITIONAL (exactly one file carries the label) |
| 7 | The record's own delivery claims | all eleven Part-3 deliverables traced to artifacts on the merged tree |

**Verify-on-main:** all five slice commits (`567d2a4`, `12ae033`, `4522908`, `ebdab88`,
`83b54dc`) confirmed ancestors of `origin/main`; the merged tree is **byte-identical**
(`65b43ca`) to the tree the 2,950-test battery validated. This is the clause that exists because
RM-1's sweep commit was authored and never merged — a sweep on the branch measures intent.

Ledger 7 is worth one note on method. The claim I expected to be soft — deliverable 6's
"`assert_passed_quality_checks`: first capture-rail caller" — turned out to be a real call at
`demo/data1_stage22.py:128`, not a docstring mention. The claim I nearly mis-reported as MISSING
was `ci.yml` plus the six register files: a `git diff --stat | tail -50` over a 57-line output
had silently cut the alphabetically-first rows. **A truncating pipe is not a census** — the same
family as the P2 `.pyc` lesson (an artifact of the measuring apparatus read as a fact about the
subject).

### What DATA-1 actually delivered, stated plainly

The platform now holds **genuinely external market data on the governed rails** — 30 monthly
TB3MS observations from the Federal Reserve H.15 series, captured verbatim, RLS-scoped,
audit-evented, DQ-gated, reconstructible on both time axes, and readable over the API. That
converts Wave 14's "real data" claim from taxonomy seed rows into an actual vendor dataset.

It deliberately feeds **no governed number**. That is the ratified capture-first position, and it
is the slice's most important decision: the rf leg admits vendor-published RETURNS only, and
converting an annualized yield to a period return is METHODOLOGY, not units. Deriving one
quietly would have put an unregistered model under a shipped Sharpe ratio.

### Open at the close

1. **UNDISCHARGED — the independent re-verification of the 30 TB3MS literals** (Execution 2
   item 6, ratified at the gate). Three extraction passes ran, but all three went through the
   SAME render-proxy channel (FRED and the Board's DDP CSV both refuse anonymous access from
   this environment), which is a recorded **common-mode residual**, not independent
   confirmation. The census pins both endpoints and four interior anchors; the remaining
   interior values rest on provenance. Discharging this needs an independent channel or a human
   pass. **This is a user-facing item, carried in the open in the control matrix.**
2. **Carry (OQ-DATA-1-1a):** the yield → period-return registered model + the Sharpe re-source.
   Trigger: *the first governed consumer that binds the real rf series.*
3. **Carry (OQ-DATA-1-5):** the P3-8 trading-calendar wiring, re-deferred IN FULL a third time
   as an explicit ratified decision. Trigger: *the first captured DAILY benchmark series.*
   REQ-PRF-002 is RE-POINTED, not discharged.
4. **Recorded limitations (Part 4):** the `assert_passed_quality_checks` gate latches on ANY
   historical FAIL; the month census is SET-based, so a duplicate observation inside an
   already-complete month passes.

### The lesson, as an act (P7)

Two of the three defects found in this slice were in **my own fail-closed path** — the half I had
already claimed was proven — and both were found by RUNNING the code, not by reading it. The
third was found by the battery, in a test the fold had just written. The mechanical form:
**every fold that touches a refusal path ships a hostile-caller negative control that executes
the refusal and asserts the absence of state** — not an assertion that the refusal was raised.
`test_horizon_before_series_start_refuses_with_NOTHING_persisted` (catch → COMMIT → zero rows,
horizon None, zero events) is the pattern to copy.

---

*Parts 10+ are appended if the slice reopens.*
