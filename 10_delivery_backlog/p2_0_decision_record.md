# P2-0 Decision Record — Market Data, Reproducible Snapshots & the First Governed Compute

## Document Control

| Field | Value |
|---|---|
| Purpose | Ratify the **reproducibility-first** P2 sequencing and settle the open P2 decisions **before any implementation**, so P2-1 can be planned against a fixed contract. Companion to `p2_implementation_plan.md`. |
| Status | **Decision record — PLANNING ONLY; NO code, NO migrations, NO P2 implementation.** |
| HEAD at writing | `7070dff` (P1C closeout / P2 readiness review committed; CI run #62 green); origin/main clean and in-sync. |
| Predecessors | `p1c_closeout_p2_readiness.md`; `p1c0_decision_record.md` (the decision-record-before-build precedent). |
| Decisions | **OD-P2-A … OD-P2-L (12).** User-item → decision crosswalk below. |
| Review | 8-lens UltraCode adversarial review — **Part 5** (8 × approve_with_changes, 0 block; in-scope findings folded into Parts 1–4 + the plan). |
| Governance | Decisions are **recorded** here; their amendment into the governance source-of-truth is a **separate ratification step** (the P1C-0 `705d3ba` → `dca7bc0` precedent) — Part 3. |

> **User-item → decision crosswalk:** (1)→OD-P2-A · (2)→OD-P2-B · (3)→OD-P2-C · (4)→OD-P2-D · (5)→OD-P2-E · (6)→OD-P2-F · (7)→OD-P2-G · (8)→OD-P2-H · (9)→OD-P2-I · (10)→OD-P2-J · (11)→OD-P2-K · (12)→OD-P2-L.

> **Grounding (verified this turn against the repo):** `calc/models.py` — `CalculationRun(PrimaryKeyMixin, TenantMixin, ImmutableAppendOnlyMixin, Base)`, `IMMUTABLE_APPEND_ONLY`, columns `run_id, run_type, status, initiated_by, input_snapshot_id, model_version_id, assumption_set_id, random_seed, code_version, created_at, completed_at` (**no `environment_id`, no `scenario_version`**); `calc/service.py` `create_run` emits **`CALC.RUN_CREATE`**, `update_run_status` emits **`CALC.RUN_STATUS_CHANGE`** (status MUTATES in place ⇒ `calculation_run` is **IA-classed but status-mutable, NOT in `APPEND_ONLY_TABLES`**). `audit_event_taxonomy.md:63` lists `CALC.RUN_START/.RUN_COMPLETE/.RUN_FAIL` (EVT-040) — **reserved, unwired** (doc-vs-code drift). AD-004 (`foundational_adrs.md:45`): "Time-series/market data: **TimescaleDB initially**, behind a market-data repository interface" (revisit "volume/perf exceeds Timescale"); related OPEN: **OD-014** (canonical L169), **OD-046** (foundational_adrs L159), **OD-005** (architecture_baseline L145). AD-014 = "No governed derived output without a bound, reproducible input snapshot." AD-013-R1 closed hybrid set = the 5 P1B-1 reference tables. §2A: market data ENT-020..025 = **FR**; exposure_aggregate ENT-014 = IA; §5 FW-RUN/**TR-15** = the 7-item bind; **TR-09** = a snapshot pins exact versions; **TR-13** = result reproduction is tolerance-based (ε_rel 1e-12). FX is ratified by **QS-07** (USD base default, configurable per tenant/portfolio), **QS-08** (explicit pair direction; cross-rates by triangulation-through-base), **QS-09** (MID rates; rate as-of; rate version bound to run), **OD-030**; canonical ENT-024 annotated "FX (QS triangulation)". `dq/rules.py` — exactly two generic evaluators (`not_null`/`allowed_values`), `DQEvaluator(params, dataset)` Protocol; `run_quality_check` + the no-silent-failure gate emit `DATA.VALIDATE`. `lineage/service.py` `record_lineage()` is **data_source-only** (hardcodes `source_type='data_source'`, accepts only a resolved `DataSource`); `lineage/models.py:29` carries a `data_snapshot` forward-compat comment (no constant). `entitlement/bootstrap.py:68` seeds `exposure.aggregate.run` (reserved-unwired); the only steward template is `data_steward`. REQ-PPM-004 = **Draft** (RTM L36 binds CTRL-006/018 + FW-RUN + DEP-LIN + CAP-1). The TRANSACTION precedent (ENT-012, in `APPEND_ONLY_TABLES` + `irp_prevent_mutation` P0001 trigger + ORM guard) is the true-append-only exemplar.

---

## Part 1 — Decisions at a glance

| ID | Decision | Resolution |
|---|---|---|
| **OD-P2-A** | `dataset_snapshot` temporal class | **IA, TRUE append-only** (in `APPEND_ONLY_TABLES`; P0001 trigger + ORM guard — the TRANSACTION pattern, NOT the status-mutable calculation_run pattern) |
| **OD-P2-B** | `dataset_snapshot` structure | header + per-input **component** rows pinning exact physical versions **+ captured value/content-hash** (app-side canonical serialization) + cutoff `(as_of_valid_at, as_of_known_at)` + manifest hash. **No `status`; no MODEL_VERSION component.** |
| **OD-P2-C** | `calculation_run` binding | run binds `input_snapshot_id` (non-null at the governed-write path) + **`code_version` (the deterministic-rollup anchor)** + `model_version_id`/`assumption_set_id`/`scenario`/`random_seed` **N/A-with-rationale** + a **new additive `environment_id`** column; emits the **shipped `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`** |
| **OD-P2-D** | P2 sequencing | **reproducibility-first**: P2-1 snapshot → P2-2 FX → P2-3 run-wiring + basic exposure → P2-4 price → P2-5 curves → P2-6 benchmark |
| **OD-P2-E** | FX entity design | `fx_rate` **FR**; **USD-base default (configurable, QS-07)**; explicit pair direction (QS-08); **MID rates, rate-version-bound-to-run (QS-09)**; conversion = published-rate lookup ± reciprocal **+ ratified triangulation-through-base (QS-08/OD-030)**; no model/curve-implied rates |
| **OD-P2-F** | basic exposure foundation | **ENT-014 `exposure_aggregate` ONLY** (IA, in `APPEND_ONLY_TABLES`) as a `calculation_run` result; Σ(signed qty × captured-mark), FX-converted; **NOT ENT-028 sensitivity**; no risk |
| **OD-P2-G** | market-data tenancy | **symmetric tenant-scoped** default (incl. benchmark definition); NO SYSTEM_TENANT/hybrid unless a future **AD-013-R2** reopens the closed set |
| **OD-P2-H** | storage strategy | **Postgres-first behind the AD-004 repo interface — a proposed AD-004 refinement (DEVIATES from "Timescale initially")**; Timescale on AD-004's own threshold; resolves OD-014/OD-046/OD-005 **pending ratification** |
| **OD-P2-I** | DQ extensions | add generic evaluators (non_negative/range pure; gap/monotonic caller-pre-sorted) as REGISTRY adds; **staleness + snapshot-completeness = caller-side gates** (Protocol untouched); reuse `DATA.VALIDATE`; no-regression on the 2 shipped evaluators |
| **OD-P2-J** | lineage semantics | vendor→series ORIGIN reuses `record_lineage` (no code); **snapshot/component/run edges need a NEW non-data_source lineage writer** (table unchanged); token = `data_snapshot` (+ `calculation_run`) |
| **OD-P2-K** | factor-model readiness | historical-depth = **non-binding** estimates; estimation-window = a `model_version` assumption; **no factor model in P2** |
| **OD-P2-L** | synthetic data use | P1C-6 input-only; the existing AST fence already blocks compute — **add a negative test that no synthetic module imports/writes `exposure_aggregate`/`calculation_run`** + extend `_SYN_MODULES`; no real data; never-auto-run |

---

## Part 2 — Decision detail

### OD-P2-A — `dataset_snapshot` temporal class → **IA, TRUE append-only**
**Decision.** `dataset_snapshot` + `dataset_snapshot_component` are **Immutable Append-Only and genuinely immutable** — in `APPEND_ONLY_TABLES`, protected by the `irp_prevent_mutation` **P0001 trigger** + the ORM `before_update`/`before_delete` guard (the **TRANSACTION (ENT-012) exemplar**), **not** the status-mutable `calculation_run`/`ingestion_batch` projection pattern.
**Rationale.** A snapshot is a **knowledge-time pin** (TR-09), created once and **never mutated** — immutability *is* the reproducibility guarantee. It has **no valid-time of its own**; the as-of-ness lives in the bound input versions. A new input set ⇒ a **new** snapshot, never an edit. (FR rejected — a snapshot is never effective-dated or superseded.) **Contrast:** `calculation_run` is IA-classed but its `status` mutates in place (`update_run_status`), so it is **NOT** in `APPEND_ONLY_TABLES`; do not model the snapshot on the run.

### OD-P2-B — `dataset_snapshot` structure
**Decision.** Two append-only tables:
- **Header — `dataset_snapshot`** (IA, trigger-protected): `id`, `tenant_id`, `system_from`; `label`/`purpose` (controlled-vocab); **cutoff `as_of_valid_at` + `as_of_known_at`**; `manifest_hash`; `created_by`. **No mutable `status`** (a snapshot is created-complete; if a lifecycle is ever needed it is a write-once value, not an in-place mutation).
- **Components — `dataset_snapshot_component`** (IA, trigger-protected): `id`, `tenant_id`, `system_from`, `snapshot_id` FK; `component_kind` controlled-vocab (`POSITION` / `VALUATION` / `REFERENCE` / `FX` / `PRICE` / `CURVE` — **no `MODEL_VERSION`**, see OD-P2-C); **the physical-version pin** = the FR row's `(surrogate_id, valid_from, system_from)` tuple resolved via `reconstruct_*_as_of` at create-time; per-component `content_hash` over the **captured value** (not just the row pointer — FR prior-version content-immutability is *service*-enforced, not trigger-enforced, so the pin must capture the value/hash).
- **Reproducibility metadata + canonical serialization.** The `content_hash`/`manifest_hash` are computed in **application code over a fixed canonical serialization** — explicit column set + order, `DECIMAL` scale-10 normalization (QS-01/03), UTC microsecond timestamps (QS-12), GUID canonical form, a null sentinel — so the hash is **engine-independent** across the AD-011 SQLite/PG split.
**Scope of "byte-stable".** The byte-stability guarantee is for **INPUT re-resolution** (pinned physical versions re-resolve identical bytes under later supersede/correction — TR-09). **Result** reproduction is **TR-13 tolerance-based** (ε_rel 1e-12), not byte-equal.
**Rationale.** Pinning physical versions + a canonical hash gives reproducibility under later mutation (the P2-1 mutation test); the component table keeps the header thin and lets market kinds join additively.

### OD-P2-C — `calculation_run` binding
**Decision.** Reuse the shipped **`calculation_run` (ENT-026, IA, status-mutable — NOT in `APPEND_ONLY_TABLES`)** as the binding vehicle:
- **run ↔ snapshot:** `calculation_run.input_snapshot_id` → `dataset_snapshot.id`, **enforced non-null at the governed-write path** for any derived output (nullable at the column for the skeleton; a negative test proves the service refusal + zero result rows + no orphan run).
- **outputs ↔ run:** every `exposure_aggregate` row carries `calculation_run_id` (run-tracked).
- **the reproducibility anchor is `code_version`, not `model_version`:** basic exposure is a **deterministic rollup with NO estimation model**, so FW-RUN item 1 ("Code/model version(s)") is satisfied by the **shipped `code_version`** (mandatory); `model_version_id` is **N/A-with-recorded-rationale** ("no estimation model — deterministic rollup"), the same disposition pattern as the RNG seed — **never mint a sham model_version** to satisfy the gate. `assumption_set_id` and `scenario` likewise recorded **N/A-with-rationale**; `random_seed` NULL-with-"deterministic".
- **a new additive `environment_id` column** is added to `calculation_run` in P2-3 (an additive, non-breaking migration on the status-projection table) so FW-RUN item 7 (run timestamps + environment) is bindable — the shipped table has no such column.
- **audit:** the run reuses the **shipped emitters `CALC.RUN_CREATE` (create) + `CALC.RUN_STATUS_CHANGE` (per transition; `outcome='failure'` on FAILED)** from `calc/service.py` (the ingestion_batch precedent); `audit/service.py` stays **FROZEN** (emission is caller-side, `event_type` free-form). The taxonomy's `CALC.RUN_START/.RUN_COMPLETE/.RUN_FAIL` labels are a **doc-vs-code reconciliation item for R-07** — P2-3 does **not** silently invent them.
- **FW-RUN §5 / TR-15 bind (the full gate):** all seven items must bind or carry a recorded N/A: (1) **code_version** (+ model_version N/A), (2) input_snapshot (non-null), (3) assumption-set (N/A), (4) parameters incl. seed (N/A), (5) scenario (N/A), (6) initiator/trigger, (7) run timestamps + **environment_id**. **A result that cannot bind all seven is incomplete and must not be published (TR-15)** — the negative test asserts that a run missing **any** item raises + writes ZERO result rows.
**Rationale.** Binding *through* the run is the ratified contract (§6, BR-6/BR-13); using `code_version` (not a fabricated model_version) keeps the model registry + SoD clean for a model-less compute; the `environment_id` add is the minimal schema change FW-RUN actually requires.

### OD-P2-D — P2 sequencing → **reproducibility-first** (user-approved)
**Decision.** P2-1 `dataset_snapshot` → P2-2 `fx_rate` → P2-3 `calculation_run` wiring + `exposure_aggregate` → P2-4 `price_point` → P2-5 `yield_curve`/`credit_spread` → P2-6 benchmark (conditional). Detail in `p2_implementation_plan.md`.
**Rationale.** The AD-014-gated first compute (captured-mark exposure) needs only positions + valuations (+ FX) — not price/curve/benchmark history. Snapshot-before-exposure is airtight (AD-014); market-data-before-snapshot is not required. User-approved over the market-data-first example, including the `calculation_run` insertion.

### OD-P2-E — FX entity design (per ratified QS-07/08/09 + OD-030)
**Decision.** `fx_rate` (ENT-024):
- **Temporal: FR** (§2A) — `rate_date` = valid-time as-of; ingest = system-time; vendor restatement = as-known correction.
- **Base & direction:** **USD base default, configurable per tenant/portfolio (QS-07)**; store the pair with an **explicit direction** (QS-08) — `base_currency` + `quote_currency` + `rate` meaning "1 base = rate quote" — no inversion ambiguity.
- **Rate type & as-of:** **MID rates** (QS-09); controlled-vocab `rate_type` label; `rate_date` distinct from `system_from`; **the rate version is bound to the consuming run** (QS-09 / OD-P2-C).
- **Conversion:** a **pure published-rate** helper — direct-pair **lookup ± read-time reciprocal**, and **triangulation-through-the-configured-base (the ratified QS-08/OD-030 mechanism)** for currencies not directly quoted — i.e. defined arithmetic over published rates (lookup × lookup), **NOT** a model. The scope-fence forbids **return/vol/curve-implied/model-derived** rates, **not** the ratified triangulation arithmetic. (Canonical ENT-024 is annotated "FX (QS triangulation)" — this design conforms.)
- **Source:** a registered VENDOR `data_source` (`source_type` token e.g. `VENDOR_FX`); one ORIGIN edge per ingested series version (reuses `record_lineage`, no new code).
- **Base currency** is a property of the **consuming exposure run / portfolio**, not the `fx_rate` row.
**Rationale.** Aligns the entity to the already-ratified FX standards instead of reinventing a pair convention; including ratified base-triangulation keeps the first multi-currency exposure unblocked while the fence still excludes genuine analytics.

### OD-P2-F — basic exposure foundation
**Decision.** "Basic exposure" = a **deterministic** market-value/exposure rollup = Σ (signed `quantity` × captured `mark_value`), **FX-converted** to a base currency, grouped by a ratified dimension. It is **ENT-014 `exposure_aggregate` ONLY** (IA, **in `APPEND_ONLY_TABLES`**, derived, run-tracked) produced **as a `calculation_run` result**. It is **NOT** a read model, **NOT** the P1C-5 holdings composition, and **explicitly NOT ENT-028 `sensitivity`** (a distinct P3+ analytic).
**Excluded (hard):** any risk; **VaR / Expected Shortfall**; factor/covariance/vol; **sensitivities/Greeks (ENT-028)**; scenario/stress; attribution; pricing/valuation models; any P3+ analytic.
**Rationale.** A governed derived number must be reproducible, audited, run-bound — an entity behind the AD-014/FW-RUN gate, not a view. Pure arithmetic over *captured* marks keeps it inside the P2 boundary.

### OD-P2-G — market-data tenancy
**Decision.** **Symmetric tenant-scoped** RLS for **all** P2 market-data entities **and the benchmark definition** (`USING == WITH CHECK == own-tenant`, ENABLE+FORCE). **NO SYSTEM_TENANT / NO hybrid** unless a future **AD-013-R2** reopens the closed 5-table hybrid set. Every market-data migration carries the **"closed hybrid set asserted unchanged"** fence.
**Rationale.** Vendor market data is **per-tenant licensed** and MNPI-adjacent (AD-008); a shared-global set would EXPAND the ratified closed set — an AD-013-R2 governance event, not a default.

### OD-P2-H — storage strategy (a proposed AD-004 refinement; resolves OD-014/OD-046/OD-005 **pending ratification**)
**Decision.** **Postgres-first, behind the AD-004-prescribed repo interface.** P2 market-data entities land in **PostgreSQL** (reusing the proven RLS/audit/lineage/DQ rails) **through a thin repository interface**, so a **TimescaleDB** backing can be swapped in **without a breaking change** at a measured volume/performance threshold (AD-004's own revisit trigger).
**Honest framing.** This **DEVIATES from AD-004's "TimescaleDB initially"** by choosing Postgres-first for P2 volumes (adopting the interface now). It is therefore a **proposed AD-004 refinement** to be ratified at the Part 3 step — **not** "honoring AD-004 as written," and **OD-014/OD-046/OD-005 are resolved only PENDING that ratification**, not unilaterally here.
**RLS forward-constraint.** A future Timescale backing does **not** inherit FORCE-RLS for free — the repo interface MUST enforce tenant scoping + an isolation test equivalent to FORCE-RLS before any market data leaves Postgres. Recorded as a standing constraint on the Timescale leg.
**Rationale.** Keeps P2 on proven rails at proportionate cost while preserving the AD-004 path; the interface makes the future swap non-breaking.

### OD-P2-I — data-quality extensions
**Decision.** Reuse the DQ **persistence + no-silent-failure gate + lineage/audit plumbing UNCHANGED**. Split the new rules:
- **Pure intra-row** (`non_negative`/`range`) → **new generic evaluator functions** + REGISTRY entries over the existing `(params, dataset)` Protocol.
- **Cross-row stateful** (`gap`/`continuity`, `monotonic_sequence`) → also `(params, dataset)`, but the **caller pre-sorts/groups** the dataset (documented as a caller responsibility; the evaluator is order-sensitive).
- **External-context** (`staleness` — needs an `as_of` instant; **snapshot-completeness** — needs an `expected_keys` universe) → **caller-side gates** that compute the context and persist via the `run_quality_check` path, **leaving the `(params, dataset)` Protocol UNTOUCHED** (the most additive option; the Protocol signature is NOT widened).
- **No-regression invariant:** the two shipped evaluators (`not_null`/`allowed_values`) + their REGISTRY entries are behavior-unchanged; a regression test asserts it. **All DQ runs reuse `DATA.VALIDATE`.** No broad new DQ framework.
**Rationale.** The engine ships only two generic evaluators, so the P2 rules genuinely need new *functions* (the readiness review's "config not framework" correction); routing the two external-context checks through caller-side gates avoids a rail-wide Protocol change while preserving the fail-closed gate that the AD-014 completeness control depends on.

### OD-P2-J — lineage semantics
**Decision.**
- **Vendor → market-series ORIGIN:** reuses the shipped `record_lineage(source: DataSource, …)` **unchanged** — registration of a VENDOR `data_source` + a token (`VENDOR_FX`/`VENDOR_PRICE`/…) only; **no code change**.
- **Snapshot/component/run edges need a NEW lineage writer.** The shipped `record_lineage()` is **data_source-only** (hardcodes `source_type='data_source'`, accepts only a resolved `DataSource`), so the three shapes with a non-`data_source` source node — snapshot→component→input, result→`calculation_run`→(snapshot + code_version) — require either a sibling `record_internal_lineage(source_type, source_id, target…)` or a generalized `record_lineage`, **RLS-stamping `tenant_id` from an equally RLS-scoped source resolution** (snapshot/run), never caller input. The **`lineage_edge` table needs no migration** (polymorphic, GUID `source_id`, carries `run_id`).
- **Tokens:** adopt **`data_snapshot`** (matching the existing forward-compat comment — avoids a second rename) for the snapshot source node, and **`calculation_run`** for the run source node; confirm whether result→run is a `source_type='calculation_run'` edge or rides `lineage_edge.run_id`. Update the `lineage/models.py` comment in P2-1.
**Rationale.** Separating the no-code vendor shape from the new-writer snapshot/run shapes makes the "no schema change" framing precise (table yes, service no).

### OD-P2-K — factor-model & real-data readiness
**Decision.** Historical-depth guidance is **NON-BINDING** planning estimates (ratified at the P3 factor phase): **3y pilot / 5y prod / 10y+ strategic / 15–20y stress**. **Store as much clean history as available.** Each `model_version` declares its estimation window as an assumption/limitation (the shipped `model_assumption`/`model_limitation` ORMs — no new field). **No factor model / no risk math in P2.**
**Rationale.** The depth numbers have no AD/REQ backing yet; flagging them non-binding prevents a phantom capture SLA.

### OD-P2-L — synthetic-data use in P2
**Decision.** P1C-6 supports P2 tests/demos — snapshot/run/exposure fixtures + synthetic FX/price/curve fixtures (SYNTHETIC tenant only). The **existing** synthetic AST fence already forbids all `ast.Mult` + `.execute()`/`text()` + wall-clock/random across `_SYN_MODULES`, so the seed **already cannot compute**. The residual risk is the seed **importing/writing** `exposure_aggregate`/`calculation_run` models — so P2-3 **adds a negative test** that no synthetic module imports or writes those models (and the SYNTHETIC tenant has **zero** `exposure_aggregate`/`calculation_run` rows after a seed), and **adds the new fx/price/curve seed modules to `_SYN_MODULES`** so they inherit the no-compute fence. **No real client/vendor data; never-auto-run + refusal guard preserved.**
**Rationale.** Keeps the AD-014/FW-RUN gate the **sole** producer of governed numbers; targets the test at the real residual risk (model import/write), not a redundant compute-block.

---

## Part 3 — Governance amendments to ratify (follow-up, separate approval)

Recorded; amended into the source-of-truth at a separate ratification step (the `dca7bc0` precedent), **not** this turn:
- **AD-004 refinement / OD-014 + OD-046 + OD-005** — ratify **Postgres-first-behind-the-interface** (a deviation from "Timescale initially"; Timescale on a measured threshold; the future-Timescale tenant-scoping constraint).
- **AD-014** — revisit trigger reached at P2-1 (the `dataset_snapshot` skeleton lands); record the IA structure + the FW-RUN bind.
- **AD-013** — record market-data + benchmark-definition tenancy = **symmetric**; hybrid ⇒ a new **AD-013-R2**.
- **REQ-PPM-004** — **promote Draft → In-Progress**, keeping its RTM control set satisfied: **CTRL-006/018, FW-RUN, DEP-LIN, CAP-1**.
- **Audit taxonomy (R-07)** — the exposure run **reuses the shipped `CALC.RUN_CREATE`/`CALC.RUN_STATUS_CHANGE`**; reconcile the doc-only `RUN_START/.RUN_COMPLETE/.RUN_FAIL` labels; reuse `DATA.VALIDATE`; **reserve `SNAPSHOT.*` + `MARKET.*`** in a fresh contiguous EVT block (proposed).
- **Entitlement (R-07)** — **wire `exposure.aggregate.run`**; mint additively `snapshot.view`/`.create`, `marketdata.view`/`.ingest`, `exposure.view`; **maker = the existing `data_steward`** (no new role minted — vendor-license isolation is enforced by tenant-scoped RLS, not a role); reconcile `marketdata.ingest` vs the existing `data.upload` (recommend `marketdata.ingest` = governed canonical-write, distinct from raw staging upload); `auditor_3l` excluded *(— **SUPERSEDED for `exposure.view` at P2-3**: OD-P2-3-I / OQ-P2-3-2 (user sign-off) **INCLUDE `auditor_3l` in `exposure.view`** — a governed derived OUTPUT is 3L-oversight scope; `auditor_3l` stays excluded from `snapshot.*` / `marketdata.*`, which are inputs)*; deny-by-default.
- **Canonical model** — **mint canonical ENT ids for `dataset_snapshot` + `dataset_snapshot_component`** (contiguous block; assert §4 common-column + §2A IA conformance) and add the new additive `calculation_run.environment_id`; `benchmark_level` (if P2-6) is a separate canonical addition gated on a confirmed P3 dependency.

---

## Part 4 — Open questions remaining (for P2-1 planning)
- **OQ-P2-1** Snapshot `manifest_hash` algorithm + the canonical component serialization spec (column set/order, decimal/timestamp/GUID/null normalization) — engine-independent.
- **OQ-P2-3** FX configurable-base set (beyond USD default) + the explicit triangulation pivot rule.
- **OQ-P2-4** Exposure grouping dimensions (portfolio-only vs node/instrument) for v1.
- **OQ-P2-6** Private-asset (ENT-015..019) capture sub-band sequencing (a separate later P2 effort).
- **OQ-P2-7** Price `adjusted` vs `raw` scope for P2-4.
- *(Resolved this record: OQ-P2-2 → DQ external-context rules are caller-side gates; OQ-P2-5 → lineage token `data_snapshot`.)*

---

## Part 5 — UltraCode 8-lens adversarial review log

Read-only review of both P2-0 artifacts + the repo. **Outcome: 8 × `approve_with_changes`, 0 block.** All material in-scope findings folded into Parts 1–4 + the plan. Reviewers independently re-verified: HEAD `7070dff`; working tree clean except the two untracked artifacts; `calc/models.py` columns + the `CALC.RUN_CREATE/STATUS_CHANGE` emitters; AD-004/AD-013-R1/AD-014/§2A/§5; the seeded `exposure.aggregate.run`; the two-evaluator DQ engine; the data_source-only `record_lineage`.

| # | Lens | Verdict | Headline in-scope findings → disposition |
|---|---|---|---|
| 1 | Product / Requirements | approve_with_changes | `CALC.RUN_*` doc-vs-code **(MED)** → OD-P2-C/Part 3 corrected; RTM control set CTRL-006/018/FW-RUN/DEP-LIN/CAP-1 **(LOW)** → Part 3; benchmark_level not canonical **(LOW)** → gated; DQ contract under-specified **(LOW)** → OD-P2-I decided; user-item crosswalk **(INFO)** → added (Part 1). |
| 2 | Chief Architect | approve_with_changes | **AD-004 contradiction/misframe + premature "resolved" (HIGH)** → OD-P2-H reframed as a deviation pending ratification; `CALC.RUN_*` **(HIGH)** → corrected; snapshot/component need canonical ENT ids **(MED)** → Part 3; model_version dual-source **(MED)** → MODEL_VERSION component dropped; lineage token + benchmark tenancy **(LOW)** → fixed. |
| 3 | Data Architecture | approve_with_changes | **`environment_id` column missing for FW-RUN bind (HIGH)** → P2-3 additive migration; `CALC.RUN_*` **(HIGH)**; **FX vs ratified QS-07/08/09+OD-030 (HIGH)** → OD-P2-E rewritten; snapshot "mirrors calc_run" misleading **(MED)** → TRANSACTION exemplar; byte-stable scoping + canonical serialization **(MED)** → OD-P2-B; DQ Protocol change not "minimal" **(MED)** → caller-side gates. |
| 4 | Security / RLS | approve_with_changes | **Cross-tenant snapshot binding integrity untested (HIGH)** → invariant + negative test (OD-P2-B/plan P2-1); **non-null model_version over-binds a model-less rollup (HIGH)** → `code_version` anchor + model_version N/A; market-data-steward role doesn't exist **(MED)** → `data_steward`; `CALC.RUN_*` **(MED)**; `marketdata.ingest` vs `data.upload` **(LOW)** → Part 3. |
| 5 | Audit / Controls | approve_with_changes | `CALC.RUN_*` **(HIGH)** → corrected; DQ contract honesty **(MED)** → caller-side; assumption-set N/A disposition **(LOW)**; ENT-014 vs ENT-028 **(LOW)** → OD-P2-F; full TR-15 negative test (not just snapshot) **(LOW)** → OD-P2-C/plan. |
| 6 | Lineage / Data Quality | approve_with_changes | **`record_lineage` is data_source-only — snapshot/run edges need a NEW writer (HIGH)** → OD-P2-J; `CALC.RUN_*` **(HIGH)**; staleness/completeness exceed the (params,dataset) contract **(MED)** → caller-side gates; evaluator split + token set **(MED/LOW)** → OD-P2-I/J. |
| 7 | QA | approve_with_changes | **Exposure fence is vocabulary/import, NOT a no-Mult fence (HIGH)** → plan P2-3 (permit `ast.Mult`, forbid risk symbols, + a positive correctness test); `CALC.RUN_*` **(HIGH)**; snapshot mutation-test pin mechanism **(MED)** → OD-P2-B physical-version tuple; synthetic fence reframe **(MED)** → OD-P2-L; benchmark tenancy / FX triangulation / token **(LOW)**. |
| 8 | Scope | approve_with_changes | **Confirmed NO code this turn; P2 not implemented; P3+/ENT-022/ENT-025/SSO not pulled forward.** `CALC.RUN_*` **(INFO)**; AD-004 "initially" inversion + OD-046/OD-005 uncited **(LOW)** → OD-P2-H/Part 3; run IA status-mutable vs snapshot true-append-only **(INFO)** → clarified; benchmark_level canonical id is a governance event **(INFO)** → Part 3. |

**Net effect:** no decision was overturned, but several were **made more precise and build-correct** — the `CALC.RUN_CREATE/STATUS_CHANGE` reality, the additive `environment_id` column, `code_version` (not a sham model_version) as the deterministic anchor, the FX standards (QS-07/08/09/OD-030), the AD-004 honest-deviation framing, the cross-tenant snapshot binding-integrity test, the new lineage writer, the vocabulary (not no-Mult) exposure fence, and the caller-side DQ gates. **No finding blocks the conclusion that P2-0 is ready and P2-1 is plan-ready.**

---

## Part 6 — P2-1 readiness gate
P2-1 (`dataset_snapshot`) is **plan-ready** once this record is approved: the temporal class (IA true-append-only), structure (header+components+physical-version pin+canonical hash), the `calculation_run` binding (code_version anchor + `environment_id` add + shipped `CALC.RUN_*` emitters + full TR-15 bind), tenancy (symmetric), storage (Postgres-first-pending-ratification), DQ posture (caller-side gates for staleness/completeness), lineage (new internal writer; `data_snapshot` token), and the cross-tenant binding-integrity invariant are all fixed. The exact P2-1 planning prompt is in `p2_implementation_plan.md` Part 8 + the chat return.
