# Wave-19 planning record — SHOW IT: real data in, governed charts out, deployed and demonstrable

| | |
|---|---|
| Status | **RATIFIED by the owner 2026-08-20 ("proceed") — all 12 decision points as recommended, plus two sub-questions decided by Claude and flagged for reversal (Part 3). Landed as PR #231.** |
| Authored | 2026-08-19, revised 2026-08-20 after the different-engine verification. Against main `d886fb8` (tree clean, CI green on all nine checks at that head, migration head `0073_declare_root_currency`, next free canonical id ENT-077, next free control id CTRL-038) |
| Method | Ultracode planning workflow `wf_bae159d8-6d5` (Fable): 5 subsystem readers → 3 independent drafts → 2-judge panel → 5 refute-by-default verifiers. Both judges independently ranked the demonstrable-first draft first (36/40 combined vs 32 and 31). Then `wf_9b50a003-a5b` (**Opus — a different engine**): 4 refute-by-default lanes over this document, including one aimed at the DIRECTION itself. |
| Verification state (P15, stated precisely) | The first five verifiers read the data-first RUNNER-UP, not this plan — a workflow scoring defect pointed them at the wrong draft. Their transferable findings are folded (Part 6). **This document's own verification is the Opus pass: 62 findings, 5 BLOCKING, 27 HIGH (Part 6b).** That pass is the first genuine different-engine proof at a planning gate on this project; every prior gate's evidence shared the authoring engine. It changed the plan substantially — the direction's stated rationale was false, the wave's XL was unprecedented in the repo's history, and three slices were not independently mergeable as claimed. |
| P20 (T1) | NO row is slice-ready today. Exactly four CURRENT adjudications exist (REQ-PPM-001/-007/-008/-009 — all built). **Every row entering scope needs a fresh owner adjudication at this gate, AND the ratification commit must carry the amended text plus a re-hashed ledger entry per row — adjudicating pre-amendment text does not clear P20 T1** (DP-19-12; the 2026-08-15 batch made exactly this mistake and left ten rows lapsed). |

## Part 0 — Organizing facts (recon-verified; corrected where the Opus pass refuted them)

1. **All platform data is synthetic.** The only external dataset is TB3MS: 30 hand-encoded literals (`marketdata/tb3ms_rates.py:43-77`). The ingestion module's own docstring says it "maps NOTHING into canonical domain tables" (`ingestion/service.py:19-21`). The owner's data-inflow question triggered the 2026-08-12 re-baseline.
2. **INGEST-1 is RATIFIED (2026-08-12, OQ-ING-1..4 all = A) but unplaced.** Its rails are shipped; the record's "one missing hook" line understates what a slice costs — see S3a/S3b, which carry three migrations between them.
3. **The frontend has zero charts** (`apps/frontend/package.json:16-20`; no SVG under `src`). The owner's ratified premise: "the math and visualization need to be the star of the show" (`product_rebaseline.md:20-22`).
4. **Identity is NOT a dev shim.** OIDC is shipped and default (`auth.py`; `config.py:58-77`), with a checked-in Keycloak realm. **But the deployed proof stack deliberately runs dev_header, and that is load-bearing:** three deployed-proof scripts create their principals over HTTP at runtime, so those principals can have no IdP identity (`deps.py:88-90` states the design assumption; `prove_onboarding.sh:85-99`). Flipping the one scripted deploy to OIDC turns the stack-proof CI job red. S5 is scoped around this fact, not against it.
5. **Why pricing/decomposition does not open this wave — the honest reason.** It is XL and its build was never measured ("six to ten governed families", `product_rebaseline.md:151-152`). *An earlier revision of this record claimed three unfrozen owner blockers at `:352-353`. That was false and is withdrawn: only one of those bullets is a pricing blocker (the error-function algorithm); the other blocks the Q2 factor model. The "fixings / bootstrapping / curve-set" items are unbuilt code, not undecided questions.* The one genuine owner decision — the error-function algorithm — is put at THIS gate (DP-19-2) rather than deferred a second time, because it has research lead time.
5b. **A fourth direction the drafts never scored:** the re-baseline's own §5 order is pricing AND the chart in parallel (`:243-248`). None of the three scored drafts was §5's sequence. It is scored in DP-19-1 so the owner sees that this plan departs from the sequencing he ratified, argued rather than obscured.
6. **The "Show it to someone" thesis was reserved as the owner's sequencing decision** (`g2_adjudication_proposals_wave18.md:253-256`). Its DEMO-1 leg matters here: today "the only way to populate a deployed database is to run a 24-file developer test battery — not something anyone would do in front of an audience" (`ingest_1_decision_record.md:130-134`).
7. **Register:** 104 rows. Two false-stale Status cells (MKT-004, MDG-003) repaired at this gate. REQ-MKT-002a duplicates REQ-MKT-002 (DP-19-10).
8. **Both control-mint candidates have complete evidence.** Backup/restore: CI stack-proof (`ci.yml:980`, step :1000), both arms, mutation-proven. Aggregation contracts: `aggregation/contracts.py` + two censuses + HTTP firings + mutants, green on main. **Recoverability is anchored**: NFR-03 quantifies RPO ≤ 24h / RTO ≤ 8h (`architecture_baseline.md:131`), AD-010 commits to "DR per NFR-03". The gap is that the requirements REGISTER has no recoverability row.
9. **Curve provenance cannot distinguish external from fixture** (`marketdata/curve.py:73-75, 421-442`): every capture roots an ORIGIN edge to one hard-coded VENDOR_CURVE source. Any "asserted EXTERNAL by ORIGIN provenance" clause is vacuous until a distinguishable source identity exists.
10. **The no-live-adapters posture rests on the ratified Wave-14 trigger** ("NO live adapters; trigger: a real vendor contract"). The old "FRED refused this environment's fetcher" claim was refuted by execution and grounds P12 — it is cited nowhere in this plan as evidence.
11. **Standing touch-triggers D1/D2** (ratified 2026-08-17) — each slice carries an argued disposition, not an asserted one.
12. **PPM-006/PPM-010 stay lapsed per ratified D3.** Neither enters a Wave-19 slice, so neither is re-asked at this gate.
13. **Every render input to a report is PINNED, by shipped invariant.** `regenerate_report` re-renders from the stored row plus pinned snapshot only and refuses on divergence: "Every render input is pinned and immutable, so this is a RENDERER change or a TAMPERED stored hash" (`report/service.py:508-513`). This governs the presentation-contract design (S1) and is the reason the first draft of the PRS-001 amendment was withdrawn.
14. **Every ReportFamily must resolve a model version** (`report/families.py:105-175`), and the exposure family has none (`exposure/models.py` has no `model_version_id`; the scheduler declares `requires_model_version=False`). RPT-1 deliberately refused to invent a report model. A Wave-18-content report family therefore needs an owner decision (DP-19-6), not a build assumption.

## Part 1 — Scope boundary

IN (base wave): REQ-PRS-001, REQ-PRS-002 (S1); **REQ-RPT-004 + REQ-RPT-001 (S2)**; REQ-INT-001, REQ-PPM-002 (S3a/S3b); REQ-ADM-001 (S5).
OPTIONAL, owner's call: REQ-PUB-005 capture half (S4 — the credit enabler); REQ-LIM-002 + REQ-LIM-004 (S6 flex).

OUT (each with its named trigger, P19):
- **Pricing + risk decomposition + derivative expressibility (SCOPE-02 spine):** no mechanical trigger; an owner decision — DP-19-1 ratifies it as Wave-20's spine, with the error-function algorithm frozen at THIS gate (DP-19-2) so the research lead time is spent during Wave 19.
- **Credit (CRD-005..-008):** CRD-005's trigger — "real curve feeds land" — fires only if S4 ratifies; otherwise the trigger stands unfired and credit opens at Wave 20 cold.
- **PUB-005's valuation clauses:** trigger — the standing Wave-18 OUT trigger "instrument terms can express a swap".
- **REQ-PRS-003** (audience-tiered rendition): trigger — REQ-RPT-004 lands. **REQ-PRS-004** (drill-down): trigger — the decomposition slice (it needs contributors that do not exist). **REQ-PRS-005** (exploration tier): **nothing blocks it** — named for the Wave-20 gate as a labelled deferral decision, because "we did not get to it" is not a trigger.
*(REQ-RPT-004 was on this OUT list in the pre-ratification draft. It is now **IN**, at S2 — see DP-19-6's recorded call. The OUT entry is deleted rather than left contradicting the IN list, which is how the ratification review found it.)*
- **REQ-DQR-002 reconciliation:** trigger — a genuine second source. **REQ-DQR-004 exception management:** trigger — the first real load producing failures nobody owns.
- **REQ-INT-002 (API & SFTP adapters):** trigger — a real vendor contract. **Scenario depth (SCN-003, MKT-004a), LIQ-004:** the Wave-20 gate (a guaranteed event under Part 4, but labelled a deferral decision, not dressed as a mechanical trigger). **Internet-facing + enterprise IdP:** RTM-P9. **Evidence egress / INT-004:** first assessor or filer export ask. **Report sign-off rail:** ratified Q9 defers it; no trigger text exists in that ratification, so this is a labelled deferral decision. **Backup/DR Operational:** the four preconditions in CTRL-038's row. **TS→7:** dependency trigger, not fired. **PERF-0's four carries:** parallelization or grain-level perf work — none here.
- **DEMO-1 (seed-the-demo-book command):** enters S5's scope if the demo walk is ratified (DP-19-8); otherwise trigger — the first external demo session.
- Closed as ratified, not re-opened: Monte-Carlo VaR, counterparty, mandate comparison, CPT-002/004.

## Part 2 — Proposed slice order

**The wave's real internal order is S3a → S3b → S1 → S2 → S5.** Only S3a and S1 are independently mergeable; S2 embeds S1's fragments, and S5 integrates all of them. *(An earlier revision claimed every slice merged independently. The Opus pass refuted it.)* **Cut line, in order: S5 first, then S6, then S4** — S5 is cut first precisely because it is the terminal integration slice and its acceptance is unsatisfiable if anything upstream slips.

Each slice merges with its own adversarial review, `make check`, full-PG, fe-check, and CI-watch-to-green.

### W19-S3a — INGEST-1 spine: mapping version + interpreter + load path (L), migrations ×2

Rows: REQ-INT-001 (AMENDED, DP-19-6). Build: ENT-077 `ingestion_mapping_version` (migration, P17 populated-DB proof); the `ingestion_batch` mapping-version bind (migration, P17); the interpreter over the closed operation set (rename, cast, scale, parse-date, code-lookup, constant, concatenate) with every refusal P9-fired and an unsupported operation refused BY NAME; the drafting AI registered as a per-tenant ModelVersion (SYSTEM-tenant path explicitly ruled out — model tables sit outside the hybrid set); **a PROPOSED mapping ratified end to end**, because the ratified thesis is "the AI proposes, a human ratifies, the platform executes" and a hand-authored mapping passing every clause would delete that leg (O-7); single-actor ratification in this slice. Rule 7: the mapping detail screen (versions, proposal provenance, ratification state).

D2: the end-to-end proof runs the exposure family over the loaded book at a NON-ROOT node — the D2 discharge for the touched chain. D1: **argued, not asserted** — the loaded book is a NEW book, not one of the shared flat demo books the D1 residual rests on, so D1 does not fire; if the slice touches a shared book's goldens, the fresh post-rename re-run lands in-slice.

### Amendment — W19-S3a's slice gate (2026-08-21): two ratified scope changes, recorded here

The S3a paragraph above says *"single-actor ratification in this slice"* and files the ``MAPPING.*``
audit codes with S3b. The owner ratified two departures at the slice gate (`w19_s3a_remit.md`
DS3a-2, DS3a-3), and they are written into this record rather than left to disagree with the build:

- **DS3a-2 — the audit-code mint MOVED into S3a.** S3a is where the PROPOSED → RATIFIED →
  SUPERSEDED lifecycle is born and no existing code covers it (`DATA.INGEST` is scoped to the
  `ingestion_batch` lifecycle, `DATA.VALIDATE` to DQ runs), so S3a as planned would have shipped a
  governed status lifecycle emitting NOTHING — something no other lifecycle on this platform does.
  ONE code, `DATA.MAPPING`, with two actions on the `DATA.INGEST` shape. **The PERMISSION codes are
  unchanged and still land at S3b** with the four-eyes lifecycle.
- **DS3a-3 — `SelfRatificationError` ships in S3a.** The refusal half of four-eyes only; the
  permission separation that makes four-eyes real is still S3b's. Ten lines, strictly safer, and
  surfaced as a widening of a ratified scope line rather than taken as a builder's call.

Two further calls the owner ratified that do NOT change this plan's scope, recorded for the reader:
**DS3a-1** keeps the ratify act at the service tier (the three new HTTP routes are READS behind the
existing `data.upload`), and **DS3a-4** gives the position binders an explicit lineage-source
override so a file-loaded holding is attributed to the INGESTION source rather than to MANUAL entry
— the first design used the existing lineage edge unchanged, and the remit's verification killed it
by reading the code.

**Three defects were found by S3a's own proofs, none by reading**, and each is recorded where it
was fixed: `ingestion_batch.status` was `varchar(20)` while its vocabulary declared a 23-character
value (four waves old, invisible because SQLite ignores VARCHAR length); the anti-corruption layer's
CSV-injection prefix made every SHORT position unparseable; and the on-ingest DQ rule selection had
no tenant predicate, so a superuser-path upload ran another tenant's rules.

### W19-S3b — INGEST-1 governance: four-eyes, attribution, screens (M/L), migration ×1

Rows: REQ-PPM-002 (fresh adjudication on amended text + the mechanical-discovery clause). Build: the **governed R-07 mint** — the mapping-ratifier permission code(s), never co-granted with the proposer path, plus the `MAPPING.*` audit event codes, with P11's holder-set pin, route census and SoD row; four-eyes as a parallel resolution-row lifecycle on ENT-077 (the ENT-075/breach_action pattern — NOT an ENT-075 CHECK widening, whose rail is hard-constrained to three entitlement actions and fails closed on a fourth); **hard-FK attribution on canonical `position` rows** (migration, P17 over a table populated since 0014; `position_source` free text is not attribution and the amended row bans it); the PPM-002 census, hosted here and enforced unconditionally — the loaded-book read resolves through the position master's as-of reconstruction. Rule 7: batch lineage + the loaded-book read with mapping-version provenance.

*Why split:* as one slice this carried three migrations, a new entity, an R-07 mint, a four-eyes lifecycle, a per-tenant model registration, a new interpreter and three screens. **No commit in this repo's history has ever added more than one migration** — verified at this gate by walking `git log --diff-filter=A` over `migrations/versions`: 72 commits added exactly one, and the single two-file commit is the genesis scaffold adding `0001` plus a `.gitkeep`. The repo's own precedent for this exact composition is ONBOARD-1 — sized L and delivered as two PRs.

### W19-S1 — PRESENT-1: presentation contract + the governed chart (L)

Rows: REQ-PRS-001, REQ-PRS-002 (both AMENDED, DP-19-6).

**Chart subject: an existing REPORT_FAMILY — `var` recommended** (it demos best and is off the D1 chains). *The earlier revision charted exposure/FX, which is not a report family at all; since PRS-002 requires the chart be emitted by the report section renderer and covered by the report content hash, that made S1 depend on S2 — the reverse of the stated order.* With a shipped family as the subject, S1 is genuinely independent.

Build: per-family presentation contracts (mark type, axes, units, precision, identity fields) with an exact-set census against the run-type registry — **with a declared exclusion vocabulary**, since a presentation contract for REPRODUCTION is meaningless and the census would otherwise force a dishonest declaration (the DP-13 precedent); **the resolved contract is PINNED into the section's GOVERNED_VALUE content**, beside model_code and methodology_ref, so a regenerated historical report renders the contract that was pinned, not today's. The chart is a server-rendered inline-SVG fragment, Decimal projection, byte-identical from the same pinned inputs, covered by the report content hash. Mutation proof at GENERATION time, both halves: generate either side of a contract edit — the new report's bytes move, and the old report still regenerates identically.

*Why pinned:* the shipped invariant is that every render input is pinned; a render-time contract lookup would make one precision edit mark every pre-edit report DIVERGED in the CTRL-018 reproduction sweep, which is the platform's loudest alarm. This was the Opus pass's BLOCKING finding against my own drafted amendment.

Rule 7: the chart on the run-detail screen in-slice. No migration. Risks: SVG byte-determinism — fonts, timestamps, locale, **and the Decimal context, which this repo has been bitten by before**; the unescaped-markup path a server-rendered fragment opens into the report (the first one), which needs its own escaping test.

### W19-S2 — RPT-W19: the report definition entity + RPT-001's census clause (M/L), migration ×1

Rows: **REQ-RPT-004** (adjudicated REBUTTED at the gate) and REQ-RPT-001 (**AMENDED, not rebutted** — the amended text binds scope to `REPORT_FAMILIES`, an editable code constant, so "do not add the family" and "delete a family" both keep exact-set equality true; and "the reproduction proof" has no defined referent, while the deployed proof the register names exercises ONE of four families).

Build: **REQ-RPT-004's report definition entity** — an append-only versioned definition carrying the declared family set, audience tiers and section order; a generation binds a `report_definition_version_id`; editing mints a NEW version; a generation bound to version N re-renders from N's declarations after N+1 exists. New canonical entity + migration, P17-proven over a populated DB. Then close RPT-001's exact-set-equality clause between the families the **named deployed proof artifact** exercises and the registry, and extend `prove_report_identity.sh` accordingly. Embed S1's chart fragments under the existing content hash.

*Why RPT-004 and not a fifth report family (the ratification call, DP-19-6):* the re-baseline instructs that the definition entity is built BEFORE the other reporting rows (`product_rebaseline.md:226`), and a Wave-18-content family would have needed a model version the exposure rollup does not have — `ReportFamily.read_provenance` refuses to render a governed number with no resolvable model version, and RPT-1 deliberately refused to invent a report model. Taking RPT-004 obeys the ratified order and dissolves the provenance problem instead of weakening an invariant to route around it. Cost: S2 grows S/M → M/L and gains a migration.

**Carry into S2's build, from the ratification review (do not lose this):** RPT-004's acceptance says a definition carries "declared families, audience tiers and section order", but those words live in the register's *Requirement* column, which the G2 hash does not cover — so all three acceptance clauses are satisfiable by a definition carrying one cosmetic field while families and section order stay hard-coded in the renderer. Real version plumbing, nothing versioned that matters. **S2 must therefore assert what the ratification review specified: adding a family at version N+1 and re-rendering a generation bound to N must still render N's family set.** If that assertion is written into the acceptance cell rather than only the build, the row re-enters G2 at its own slice gate — which is the honest path and is recommended.

### W19-S5 — SHOW-1: deployed demo posture (M/L — re-sized), **first on the cut line**

Row: REQ-ADM-001 (AMENDED, DP-19-6 — **including the MFA clause, which the earlier draft silently dropped**; the current cell says "Principal comes from OIDC; MFA enforced (AD-007)", AD-007 is CISO-approved, and the lever ships OFF).

Build, scoped around Part 0.4 rather than against it: **a second deploy target running oidc + TLS, beside the existing dev_header proof stack** — the proof scripts keep their runtime-created principals and the stack-proof job stays green. TLS terminates in front (none exists in the repo today; this is new build, which is why the size moved). The dev_header refusal is proven over HTTPS on the OIDC target, asserted **by the specific refusal, not by any 401** — with `auth_mode=oidc` the dev-header branch is never reached, so a bare 401 proves nothing. MFA asserted via `oidc_require_mfa` + `oidc_acr_values`, refusal fired — or explicitly deferred with a trigger, the owner's call at DP-19-6.

**The demo walk (login → file load → chart → report) is conditional** (DP-19-8): it needs S3a+S3b, S1, S2, realm users carrying the right verbs, and a seeded book — today the only way to populate a deployed database is a 24-file developer test battery. Either DEMO-1 (a seed command) enters S5 and the slice is re-sized again, or the walk clause is deferred with its trigger. "File load" in the clause means a positions file loaded through a ratified mapping version, naming the `mapping_version_id` — never a seeded fixture.

NOT in scope: internet-facing hosting, enterprise IdP (RTM-P9). P16: touches `infra/deploy`, so CTRL-038's citation is re-taken in this slice's commit.

### W19-S4 (OPTIONAL, DP-19-9) — ING-2: external market data beside the spine (M)

Row: REQ-PUB-005 capture half (AMENDED — entering it as written was a BLOCKING finding: every clause is valuation-shaped, no floating-leg valuer exists, instrument terms cannot express a swap). Build: a credit-spread curve and an index fixing history captured from operator file drops through the proven capture verbs plus a fixings entity (ENT-078, migration, P17); **a distinguishable external-source identity** (a DataSource per named publisher, never the shared VENDOR_CURVE constant, with file identity recorded) — without it the downstream "asserted EXTERNAL" clause is vacuous; **CTRL-034 checklist Executions 3 and 4** before any governed use. Honestly titled "beside the spine": this rides pre-INGEST capture verbs, and OQ-ING-4 sequences market data into the spine later — DP-19-9 has the owner ratify that bypass with its unification trigger. **A clause must require something to CONSUME the fixings**, or this repeats the declaration-without-consumption defect already folded on PRS-001/002 in this same document. Effect if ratified: CRD-005's trigger fires and Wave 20 opens with credit actionable.

### W19-S6 (OPTIONAL, DP-19-9) — LIM-3: stored utilization + strategy-node limits (M)

Rows: REQ-LIM-002, REQ-LIM-004. The utilization table **REALIZES the already-reserved ENT-032 `limit_utilization`** — it does not mint a new id (`canonical_data_model_standard.md:97`; minting over a reservation is the REF-1 namespace-collision class). Migration + P17.

**Correction to the earlier justification:** this was recommended on the grounds that it gives the wave "a new governed number". By this platform's own definition it does not — the amended row binds only the calculation_run, with no snapshot and no model_version, which is the Breach evidence class, not the governed-number class. The flex choice must rest on demo value alone, or the row must gain those bindings and be priced for them. Two further gaps for the owner: the row has **no direction semantics** (the platform admits floor limits, where a ceiling-shaped ratio and "headroom" invert), and **no clause says what a refused or metric-cold evaluation stores** — the lazy answer is zero, which a screen renders as full headroom.

**Recommendation: neither optional slice.** A wave whose XL had to be split into two slices should not also carry a flex slice. S4 and S6 are Wave-20's first two candidates.

## Part 3 — Wave-level decision ledger (Tier-3 — ratify at this gate)

| # | Decision | Recommendation |
|---|---|---|
| DP-19-1 | Wave direction | **The demo wave as sequenced above.** Four options now on the table: this wave; the pure data spine (32/40); the risk-depth wave (31/40); and **the re-baseline's own §5 order — MKT-007 linear-first plus PRESENT-1 in parallel — which no draft scored.** The §5 option is real and the owner ratified that sequencing nine days ago; my read is it still loses, because INGEST-1 answers the owner's own triggering question and pricing is a full wave on its own — but it is presented, not obscured |
| DP-19-2 | The error-function algorithm | **Freeze it at THIS gate, or commission the research in-wave.** It is the one genuine unfrozen owner decision behind pricing, it has research lead time, and deferring it to the Wave-20 gate would be the second deferral of the same decision |
| DP-19-3 | INGEST-1 posture | **Ratify the revision** of the 2026-07-15 "not before the build completes" note, by the owner's own later ask; file-drop only |
| DP-19-4 | Mint CTRL-038 backup/DR | **Mint as docs, Implemented (OBSERVED), H-05 act.** Anchored to **NFR-03 + AD-010** (the register-row gap stated precisely, never "no anchor exists"). Birth citation = the current GREEN stack-proof run at head `7dcb3a3`, with the mutation-red run kept as historical proof. The four Operational preconditions named in-row as the P19 trigger; CTRL-001's row-42 flag amended in the same commit |
| DP-19-5 | Mint CTRL-039 aggregation-contract enforcement | **Mint as docs, Implemented (OBSERVED),** citing the green run id + head SHA. Two boundaries in-row or it overclaims: NodeRollup translated totals sit outside the contract vocabulary by design; non-root execution is 4/21 families per ratified D2 |
| DP-19-6 | The G2 batch + three unresolved acceptance questions | **Adjudicate on the drafted texts below**, and answer three questions those texts cannot settle alone: (a) the Wave-18 report family's provenance — mint a model version for the exposure rollup (contradicting RPT-1's recorded reasoning), admit a MODEL_LESS provenance class, or pick a model-bound subject; (b) MFA — assert it on the deployed stack, or defer with a trigger; (c) REQ-RPT-004 — move it into S2, or record who pays the re-binding when it lands later |
| DP-19-7 | Restatement semantics | **Fail-closed**: an overlapping re-load REFUSES unless flagged a restatement; a flagged restatement supersedes bitemporally. Decided now because it gates the loader. Note the refusal it mints must be bound by an acceptance clause and named in Part 4's P9 list — both done below |
| DP-19-8 | The demo walk | **Defer the walk clause with its trigger**, or bring DEMO-1 (a seed-the-demo-book command) into S5 and re-size again. Recommend deferring: S5 is already first on the cut line |
| DP-19-9 | The two optional slices | **Neither.** S4 (ING-2) and S6 (LIM-3) become Wave-20's first two candidates. If the owner wants credit warm for Wave 20, S4 is the one to take — it fires CRD-005's trigger |
| DP-19-10 | REQ-MKT-002a duplicate | **Withdraw into REQ-MKT-002 now** |
| DP-19-11 | The actual source file | Owner names the client-shaped positions file for S3a (recommend a realistic multi-asset CSV in a public broker-statement shape) |
| DP-19-12 | The ratification commit's full obligations | **All of:** (i) write the DP-19-6 amended texts into `requirements_backbone.md` **and the RTM**; (ii) append one `g2_adjudication_ledger.jsonl` entry per row with the hash recomputed from the **post-amendment** cells (the PPM-008 pattern, not the 2026-08-15 pattern that left ten rows lapsed); (iii) set `g2_slice_scope.json` slice + scope to the first slice's rows, the rest declared at their own slice entries; (iv) repair the two false-stale Status cells (Status-only, no hash lapse); (v) land roadmap Part 2.21 + the overdue Part 5 amendment row; (vi) EARMARK ENT-077 for S3a's mapping version **in this record only — the catalog pointer is NOT pre-stamped, because P17 says a mint is not minted until a migration delivers it, and a catalog row ahead of its migration is the same false-record class the pointer-decay correction fixed**; record that LIM-3 would REALIZE the reserved ENT-032 rather than mint a new id. **Note the sequencing constraint:** an AMENDED disposition needs the amendment commit to exist before its hash is computed, so this is two commits, not one |

### Calls made at ratification that the owner did not explicitly decide — flagged for reversal

The owner's "proceed" ratified the recommendations. Two DP-19-6 sub-questions carried NO recommendation from me, so I decided them at ratification rather than block the wave. Both are cheap to reverse before S2 starts; neither touches a slice already in flight.

1. **DP-19-6(a) + (c), resolved together: S2 builds REQ-RPT-004 (the report definition entity), not a fifth report family.** The re-baseline's own §4 instruction is "the report definition entity: BUILD BEFORE THE OTHER REPORTING ROWS", and a Wave-18-content family would have needed a model version the exposure rollup does not have — forcing a choice between inventing a report model (which RPT-1 deliberately refused) and weakening the provenance invariant. Taking RPT-004 dissolves both problems and obeys the ratified order. Cost: S2 grows from S/M to M/L and gains a migration. **Reverse by** naming a model-bound Wave-18 subject for a fifth family instead.
2. **DP-19-6(b): MFA is ASSERTED, not deferred.** The clause is CISO-approved via AD-007, the lever (`oidc_require_mfa` + `oidc_acr_values`) is already shipped and merely ships OFF, and the row's own text has always said "MFA enforced". Deferring a commitment that is one config assertion away from provable would be the kind of quiet lapse this project keeps paying for. **Reverse by** replacing the clause with an explicit deferral naming its trigger.

### DP-19-6 — the drafted acceptance texts (what the owner adjudicates)

**REQ-INT-001 (AMEND):** A positions file loads only through a RATIFIED mapping version. (1) Loading with no ratified mapping version REFUSES, fired. (2) Every ingestion batch and every loaded position row binds the ratifying mapping version by hard FK — never free text — tenant-filtered on re-resolution. (3) Ratifying an EDITED mapping version and re-loading the same file produces canonically different rows exactly where the edit says. (4) The interpreter is the ONLY write path from staged rows to canonical positions, asserted by a census that **discovers write paths mechanically, never a hand list**. (5) Each closed-set operation's refusal FIRES; an unsupported operation is refused BY NAME. (6) Ratification is four-eyes: the ratifier differs from the proposer, refusal fired. (7) **Every mapping version records the proposing model version and prompt identity, or is explicitly marked HAND_AUTHORED; the demonstrating flow ratifies a PROPOSED mapping end to end.** (8) The demonstrating file exercises at least three distinct operation kinds. (9) A load is reproducible from the mapping version, the staged file, **and the code-lookup reference data as of the load** — reproducibility names all three inputs, because one of the seven ratified operations resolves against reference data held in neither of the other two. (10) An overlapping re-load REFUSES unless flagged a restatement (DP-19-7), fired.

**REQ-PRS-001 (AMEND):** existing clauses, plus: the section's pinned content carries the presentation contract the render used; a regenerated historical report renders the PINNED contract, not the current one; changing a family's declared precision, unit or mark changes the bytes of a NEWLY generated report while leaving every previously generated report byte-identical on regeneration, both halves asserted; a family whose contract no renderer can resolve FAILS; families outside the presentable set are named in a declared exclusion, never given a stub contract.

**REQ-PRS-002 (AMEND):** existing clauses, plus: the SVG is produced FROM the family's pinned contract (a contract differing at generation moves the bytes) and contains the declared MARK SHAPES — path, rect, line or circle elements per the declared mark type — not only text nodes.

**REQ-RPT-001 (AMEND, replacing the proposed rebuttal):** exact set equality between the families exercised by **the named deployed proof artifact (`infra/deploy/prove_report_identity.sh`)** and REPORT_FAMILIES; the registry must cover every governed family that has a shipped report subject, so declining to add a family is a failure rather than a way to keep the equality true.

**REQ-ADM-001 (AMEND):** the scripted deploy stands up an OIDC target running `auth_mode=oidc` against the checked-in realm with TLS in front; the deployed OIDC target refuses a dev-header request **by the dev-header refusal specifically**, fired against the deployed stack; **MFA is asserted via `oidc_require_mfa` + `oidc_acr_values`, refusal fired** (or deferred with a named trigger per DP-19-6b); the existing dev_header proof stack continues to pass its four deployed proofs unchanged. Internet-facing hosting and enterprise IdP remain RTM-P9.

**REQ-PPM-002 (one-clause AMEND):** the amended 2026-08-15 text, plus: the holdings-consuming set is discovered MECHANICALLY, never hand-listed.

**REQ-PUB-005 (AMEND, conditional on DP-19-9):** capture half — missing-fixing lookup REFUSES naming index and date, never interpolating or carrying forward; an appended fixing cannot change an as-of reconstruction at a pinned as-known time; each index declares its coverage window; rows append-only; **and a governed read CONSUMES a fixing, with the fixing used recorded on what it produced**. Valuation half trigger-parked on "instrument terms can express a swap".

**REQ-LIM-002 / REQ-LIM-004 (conditional on DP-19-9):** adjudicate with the direction-semantics and refused-evaluation gaps closed first (S6 above).

## Part 4 — Standing-rule application map

- **P9**: every refusal minted this wave is named in a test that FIRES it — no-ratified-mapping; each closed-set operation; unsupported-operation-by-name; four-eyes self-ratification; **overlapping-reload-without-restatement-flag (DP-19-7)**; dev-header-on-the-OIDC-target; MFA-not-asserted (if ratified); missing-fixing lookup and LIM refusals if the optional slices ratify.
- **P11**: S3b's R-07 mint carries the holder-set pin, route census and SoD row.
- **P15**: this document's verification is the Opus different-engine pass (Part 6b). The five Fable verifiers read a different draft; their transferable findings are folded but they are not this plan's proof. The different-engine trigger stands for the build.
- **P16**: CTRL-038/039 bind from birth; S5 re-takes CTRL-038's citation.
- **P17**: S3a ×2, S3b ×1, S4 ×1, S6 ×1 — each proven over a populated DB, harnesses committed. **The flex slice is included** (it ALTERs the limit family).
- **P18/P19/P20**: as stated; every OUT item names a slice, a mechanical condition, or is **labelled a deferral decision** where neither exists (the two that could not be honestly triggered are labelled rather than dressed).
- **Rule 6(a)**: no methodology slice in the base wave, so no citation lane is owed.
- **Rule 7**: S3a mapping screen; S3b lineage + loaded-book read; S1 chart on run detail; S5 the deployed surface. No governed number ships endpoint-only.
- **D1/D2**: argued per slice, never asserted.

## Part 5 — Pre-emption ledger (what the Wave-19 close must carry)

1. G4: the capability-coverage table, worded as delivered substance.
2. The seven-ledger omission sweep, verified on main after the last merge.
3. Roadmap rows stamped with merge identities in the following slice's first commit.
4. OUT-list triggers re-checked; CRD-005's fires only if S4 ratified.
5. CTRL-038/039 P16 re-takes verified current.
6. Requirement Status cells checked in BOTH backbone and RTM (the Wave-18 BLOCKING recurrence class).
7. D1/D2 dispositions re-verified against the whole wave diff.
8. **The outward-facing benchmark review** (roadmap Part 4 rule 6(b), ratified 2026-07-08).
9. **The public+private destination evaluation** (differentiation thesis §4).

*Items 8 and 9 are restorations, and the lapse is recorded rather than repeated silently. Both are ratified standing obligations, and **they lapsed by DIFFERENT amounts — one count does not cover both:***

- ***Item 8, the outward-facing benchmark review: lapsed at waves 13–18. Six consecutive closes.*** Wave 13's close says so in its own words — "No outward architecture/benchmark sweep beyond §4's destination re-check" (`wave_13_close_review.md:38-39`).
- ***Item 9, the public+private destination evaluation: lapsed at waves 14–18. Five closes*** — `wave_13_close_review.md:146` carries `## 4. Outward destination (rule 6b)` as a substantive section.
- **Waves 1 through 12 all carry the section.**

*This paragraph has now been wrong twice, and the sequence is the lesson. The Opus verification lane said "eight consecutive closes"; I re-ran its grep, found waves 11 and 12 matched, and corrected it to "six" — presenting that correction as the P13 discipline working. **The adversarial review of the ratification commit then refuted my correction too:** applying one number to two obligations hid that wave 13 carried the destination half, and my supporting enumeration ("waves 1, 10, 11 and 12") omitted eight waves that also carry it. A re-measurement is not automatically right because it is a re-measurement. Both prior versions are left visible here rather than tidied away, because the failure mode — a confident count, corrected confidently, still wrong — is the thing worth carrying forward.*

*Wave 19 advances the public+private destination by zero — no private-asset math is in any slice — and the close must say so rather than omit the section.*

## Part 6 — First verifier pass (Fable, against the runner-up draft): transferable findings, folded

41 findings (3 BLOCKING, 7 HIGH). The ledger is unchanged from the 2026-08-19 revision and is retained below in condensed form; the folds it produced are live in Parts 1–4.

INT-001's inert-mapping exploit → the load-bearing clauses (3)(4)(8). The R-07 mint and the ENT-075 CHECK collision → S3b. Free-text attribution → the position-table migration. ModelVersion tenancy → per-tenant, SYSTEM ruled out. PPM-002 bypass → census enforced in-slice. The 10 MiB cap → an early decision, trigger honestly not fired. PUB-005 valuation-shaped → the capture/valuation split. ORIGIN provenance vacuous → the external-source identity mint. Spine bypass → DP-19-9. The refuted FRED claim → removed (P12). PRS declaration-without-consumption → the amended texts. CTRL-034 executions → S4's DoD. CTRL-038 anchor and citation → NFR-03/AD-010, green run. PPM-006/010 re-asks → dropped per D3. Canonical-id accounting → DP-19-12 (and ENT-032, caught during synthesis). DQR-004 "degenerate-proof as written" refuted → the row left out of the wave with its amendment set recorded. CRD-1's method fork, censuses, sizing and oracle independence → recorded as Wave-20 credit-slice entry conditions.

## Part 6b — Different-engine verification (Opus): 62 findings, 5 BLOCKING, 27 HIGH

Everything above the line — five readers, three drafts, two judges, five verifiers, the synthesis — was **Claude Fable**. This pass is **Claude Opus**. Under P15 two proofs sharing an engine count as one proof, and every prior planning gate on this project had only same-engine evidence. The switch was not chosen for rigor: Fable's weekly allocation ran out mid-pass and the first attempt died with zero agents completed. The result satisfies the standing rule properly anyway, and it is recorded as it happened.

**The five BLOCKING findings, and what each changed:**

| id | Finding | Disposition |
|---|---|---|
| DIR-1 | The stated reason for deferring pricing was FALSE at its own citation: only one of the two cited bullets is a pricing blocker, the others are unbuilt code rather than undecided questions — and this plan splits PUB-005 capture-from-valuation to make it deliverable while refusing the identical move on MKT-007 | Part 0.5 rewritten with the honest reason and the citation withdrawn; DP-19-2 freezes the one real decision at this gate; DP-19-1 scores the §5 option the drafts never considered |
| OPUS-S1-1 | The PRS-001 amendment I drafted made the presentation contract an UNPINNED render input, contradicting the shipped pin-everything invariant — one precision edit would mark every historical report DIVERGED in the CTRL-018 sweep | Contract pinned into section content; the mutation proof moved to generation time and given both halves (new bytes move, old reports still regenerate) |
| O-1 | S5's "the scripted deploy runs auth_mode=oidc" breaks all four deployed proofs and reddens the stack-proof job — those scripts create ~11 principals over HTTP at runtime, so they can have no IdP identity | S5 rescoped to a SECOND deploy target beside the dev_header proof stack; re-sized M → M/L |
| O-2 | The demo walk is unsatisfiable as scheduled: a fresh stack has no tenant and no users, the realm's users are pinned to a tenant only the test battery creates, and DEMO-1 is not in the plan | DP-19-8: defer the walk clause with its trigger, or bring DEMO-1 into S5 and re-size again |
| W19C-1 | DP-19-12 omitted the three G2 artifacts the ratification must move; the 2026-08-15 batch made this exact mistake and left ten rows lapsed, and `make check` runs g2-check | DP-19-12 rewritten with all six obligations and the two-commit sequencing constraint |

**The structural HIGHs that changed the shape:** the wave's XL carried three migrations when no slice in 73 has landed more than one → split into S3a/S3b on the ONBOARD-1 precedent (DIR-5). "Each slice merges independently" was false → the real order is stated and S5 moved to the head of the cut line (DIR-4). S1's chart subject was not a report family → an existing family (DIR-3/OPUS-S1-2). A Wave-18 report family needs a model version the exposure rollup lacks → DP-19-6a (OPUS-S2-1). RPT-001's rebuttal was wrong → AMENDED (OPUS-S2-2). The ADM-001 amendment silently retired a CISO-approved MFA clause → restored (O-5/W19C-4). INT-001 required no mapping PROPOSAL, deleting the AI-drafting leg that is the ratified slice's whole thesis → clause (7) (O-7). LIM-002's "governed number" justification was false by the platform's own definition → struck (O-12). Six consecutive wave closes dropped two ratified obligations → Part 5 items 8 and 9 (the lane reported eight; re-measured at this gate, DIR-6). Three PRS rows in the wave's own headline domain had no trigger → Part 1 (DIR-7).

**The remaining MED/LOW findings** (census universe vocabulary, code-lookup reproducibility, RPT-004 build order, the dev-header 401 exploit, direction semantics on utilization, ENT-078 versus the existing rail, citation line errors, the wave's cut-line slack) are each either folded above or carried as named slice-entry conditions.

**One honest note on what this pass means.** Five Fable verifiers, two Fable judges and three Fable drafts did not catch that the chart's declared subject had no host section, that the wave's XL was unprecedented, or that the direction's own rationale was false at its citation. A different engine found all three in one pass. That is the fourth consecutive time on this project that a second engine has broken a green surface, and it is the argument for making the different-engine pass a standing part of the planning gate rather than a quota accident.
