# Temporal & Reproducibility Standard

## Document Control

| Field | Value |
|---|---|
| Document ID | DATA-TEMPORAL-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-05 Data Architect AI |
| Approver | H-04 Data Owner (H-02 consulted for model reproducibility) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | canonical_data_model_standard.md, numerical_quant_standards.md, audit_event_taxonomy.md, model_governance_independence_policy.md, foundational_adrs.md (AD-005, AD-006) |
| Supported Build Rules | BR-6, BR-7, BR-8, BR-9 |

## 1. Purpose

Define the temporal model and the reproducibility contract so that any risk result, report, or limit utilization can be
reconstructed exactly, and so that corrections never destroy history. This makes BR-6 (traceability), BR-8 (scenario
versioning), and BR-9 (report reproducibility) enforceable.

## 2. Two Time Axes (TR rules)

| ID | Rule |
|---|---|
| TR-01 | **Valid time** (`valid_from`/`valid_to`) records *when a fact is true in the business world* (e.g., a position's as-of date, a price's market date). |
| TR-02 | **System/transaction time** (`system_from`/`system_to`) records *when the system knew it* (knowledge time). |
| TR-03 | Stateful business entities are **bitemporal**: both axes are maintained. As-of queries specify both a business date and a knowledge date. |
| TR-04 | The current view = latest `system_*`; a historical reconstruction = `system_*` as-of a past knowledge time. |

## 2A. Selective Bitemporality — Entity Classification (Ratified, AD-005)

Full bitemporality is applied **selectively**, not universally. Every entity is assigned one of three temporal classes. The
default for a new entity is **EV**; promotion to **FR** requires it to be a risk-driving input that must be reconstructable on
both time axes. Class is recorded in the data dictionary alongside the entity.

| Class | Name | Time handling | Mutability | Use when |
|---|---|---|---|---|
| **FR** | Full Reproducible (bitemporal) | valid_from/to **and** system_from/to | Immutable history | Risk-driving inputs needing point-in-time reconstruction of *what was true* and *what was known* |
| **IA** | Immutable Append-only | system time (event/knowledge time) | Append-only; corrections = new record/version | Outputs, events, audit, overrides — pinned by their run/snapshot, so no second axis needed |
| **EV** | Effective-dated Versioned | system-time versioning + optional effective dating | Current-state queryable with retained history + audit | Reference/master/config where context history is needed but dual-axis as-of is overkill |

### FR — full point-in-time reproducibility required
Market data (ENT-020 price_point, ENT-021 yield_curve, ENT-022 volatility_surface, ENT-023 credit_spread, ENT-024 fx_rate,
ENT-025 factor_return); positions (ENT-011); valuations (ENT-013); external/internal & shadow ratings feeding credit
(ENT-007); private NAV/appraisals (ENT-017) and commitments (ENT-015); instrument economic terms that are effective-dated
(ENT-001, e.g., coupon/maturity schedules).

> **P2-2 realization note (FX, 2026-06-26):** **ENT-024 `fx_rate` is REALIZED** (migration `0017`, FR bitemporal — the fourth persisted `FullReproducibleMixin` user after `instrument_terms`/`position`/`valuation`): capture / effective-dated supersede / as-known correction / both-axes `reconstruct_fx_rate_as_of`; NOT append-only (close-out UPDATEs; content-immutability service-enforced); `rate_date`/`rate_type` immutable logical-key components; symmetric tenant-scoped RLS (NEVER hybrid). The remaining market-data FR entities (ENT-020/021/022/023/025) stay **P2-4+/P3**.

> **P2-6 realization note (benchmark, 2026-06-29):** **ENT-009 `benchmark` is REALIZED** (migration `0021`) as a split: the **`benchmark` definition = EV** (`EffectiveDatedMixin`; entity-versioned in place via `record_version`; `REFERENCE.*`-audited — the `corporate_action` precedent) + **`benchmark_constituent` membership = FR bitemporal** (`FullReproducibleMixin` — the SEVENTH persisted user after `instrument_terms`/`position`/`valuation`/`fx_rate`/`price_point`/`curve`; captured/superseded/corrected as a set per `(benchmark, effective_date)`; `MARKET.BENCHMARK_CONSTITUENT_*`-audited). **NEITHER table is append-only** (EV mutates in place; FR requires close-out UPDATEs — no `irp_prevent_mutation` trigger). `effective_date` is a separate immutable logical key. `benchmark_level`/`benchmark_return` stay future (OD-P2-6-K).

> **P3-2 realization note (factor; committed `402cb12`, CI #89 green):** **ENT-025 `factor_return` is REALIZED** (migration `0023_factor_return`) as a split mirroring `benchmark`: a **net-new `factor` definition = EV** (`EffectiveDatedMixin`; entity-versioned in place via `record_version`; `REFERENCE.*`-audited; identity `(tenant, factor_code, factor_source)`) + **`factor_return` series = FR bitemporal** (`FullReproducibleMixin` — the EIGHTH persisted user after `instrument_terms`/`position`/`valuation`/`fx_rate`/`price_point`/`curve`/`benchmark_constituent`; capture / effective-dated supersede / as-known correction / both-axes `reconstruct_factor_return_as_of`; **single-row** per `(factor, return_date, return_type)`; `MARKET.FACTOR_RETURN_*`-audited). **NEITHER table is append-only** (EV mutates in place; FR requires close-out UPDATEs — no `irp_prevent_mutation` trigger). `return_date` is a separate immutable logical key. `return_value` `Numeric(20,12)` DECIMAL fraction, guarded finite (NaN/±Inf rejected pre-write) + a `> -1` economic-sanity DQ RANGE. **Captured INPUT — NO `calculation_run`/`model_version`/snapshot pin** (reproducibility is the FR bitemporal reconstruct itself, not a run/snapshot pin — an INPUT, not a governed derived number; computed factor returns DEFERRED). `factor` is the net-new EV definition id minted for this split.

> **P3-3 realization note (factor exposure):** **`factor_exposure_result` is REALIZED** (migration `0024_factor_exposure`) as the SECOND ENT-028 realization — **IA TRUE append-only** (in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger + ORM guard; the `sensitivity_result`/`exposure_aggregate` exemplar; a re-run = a NEW run + new rows, never an edit); symmetric tenant-scoped RLS (NEVER hybrid). **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** — no row without a non-null `calculation_run_id` + `input_snapshot_id` (a `FACTOR_EXPOSURE_INPUT` snapshot) + a **registered** `model_version_id`. The snapshot pins introduce the **IA-row pin flavor** (`COMPONENT_KIND_EXPOSURE`: `pinned_valid_from`/`pinned_record_version` NULL, `pinned_system_from` = the atom's append time — an immutable pin, drift impossible) beside the EV flavor (`COMPONENT_KIND_FACTOR`: `record_version` the drift discriminator). Reproducible under a later factor amend or exposure re-run (snapshot-only compute; TR-09).

> **P3-4 realization note (covariance):** **`covariance_result` is REALIZED** (migration `0025_covariance`) as ENT-051 — **IA TRUE append-only** (in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger + ORM guard; a re-run = a NEW run + new rows, never an edit); symmetric tenant-scoped RLS (NEVER hybrid). **RUN-BOUND + SNAPSHOT-GATED + MODEL-BOUND** with the estimation window part of the model-version identity (OD-P3-4-G). The `COVARIANCE_INPUT` snapshot pins each factor's aligned FR return window as ONE `COMPONENT_KIND_FACTOR_RETURN` component (per-row immutable FR version content — `id`+`valid_from`+`system_from`+`record_version` captured per window row; close-out markers excluded), so a later vendor **supersede AND correction** of a pinned window return leave the component byte-stable and the covariance invariant (**TR-09, test-proven both ways**); an EV factor amend drifts only the paired `COMPONENT_KIND_FACTOR` definition pin.

> **P3-5 realization note (parametric VaR):** **`var_result` is REALIZED** (migration `0026_var`) as ENT-027 — **IA TRUE append-only** (in `APPEND_ONLY_TABLES`; `irp_prevent_mutation` P0001 trigger + ORM guard; a re-run = a NEW run + new rows); symmetric tenant-scoped RLS (NEVER hybrid). The first **derived-of-derived** governed number: its `VAR_INPUT` snapshot pins the IMMUTABLE result rows of TWO upstream governed runs (`COMPONENT_KIND_FACTOR_EXPOSURE` + `COMPONENT_KIND_COVARIANCE` — the IA-row pin flavor; byte-stable by construction), so a later upstream RE-RUN (new rows under a NEW run) leaves a pinned VaR INVARIANT (test-proven). The declared-parameter version identity (confidence/horizon/z as strict-parsed assumptions) extends the OD-P3-4-G window precedent.

### IA — immutable append-only
Reproducible input snapshots (**ENT-049 `dataset_snapshot` + ENT-050 `dataset_snapshot_component`** — the AD-014 reproducibility
primitive; **TRUE append-only**, in `APPEND_ONLY_TABLES` with the `irp_prevent_mutation` trigger + ORM guard — the `transaction`
precedent, distinct from the status-mutable `calculation_run`; ratified at P2-0, 2026-06-26; **REALIZED in P2-1 (`3629baa`, migration `0016_dataset_snapshot`)**);
calculation runs and outputs (ENT-026 calculation_run, ENT-027 risk_result, ENT-028 sensitivity/exposure, ENT-014
exposure_aggregate, ENT-030 scenario_result); versioned-immutable definitions (ENT-029 scenario_definition, ENT-036
model_assumption set, ENT-035 model_version); transactions as an event log (ENT-012); manual overrides (ENT-041); lineage
edges (ENT-042); DQ and reconciliation results (ENT-039, ENT-040); report versions (ENT-046); breach and breach actions as
append-only state transitions (ENT-033, ENT-034); audit events (ENT-045, additionally hash-chained per audit taxonomy).

### EV — effective-dated versioning (lighter)
Reference/master data (ENT-002 issuer, ENT-003 counterparty, ENT-004 identifier_xref, ENT-005 currency, ENT-006 calendar,
ENT-008 corporate_action, ENT-009 benchmark); limit definitions (ENT-031, effective-dated); security/admin (ENT-043 users/
service/agent principals, ENT-044 roles/permissions/grants — grants carry effective dates); ENT-038 data_source;
**ENT-010 portfolio/fund/strategy/account hierarchy** (P1C-1 domain hierarchy — single EV table + node_type);
**ENT-001 instrument identity** (master attributes) and **ENT-007 rating_scale/grade taxonomy** (the EV halves of the
P1B-0 splits below).

> **P1B-0 ratification note (intra-entity splits — conform to this §2A, no AD-005 amendment):**
> - **ENT-001** is realized as `instrument` (**EV** identity/master attributes) + `instrument_terms` (**FR** effective-dated
>   economic/legal terms — coupon/maturity/call schedules, the FR clause above) (OD-P1B-A).
> - **ENT-007** splits into `rating_scale`/grade **taxonomy = EV** (P1B-1) and rating **assignments feeding credit = FR**
>   (the FR clause above; deferred to a credit phase) (OD-P1B-J).
> - **ENT-008** corporate_action is **EV** (already classified here) — status/reason history flows through the `REFERENCE.*`
>   audit trail, not an IA table (OD-P1B-B).
>
> **P1B-1 realization note:** the EV halves of ENT-005 (`currency`), ENT-006 (`calendar`/`calendar_holiday`) and the ENT-007
> taxonomy (`rating_scale`/`rating_grade`) are now built (migration 0008) — all declare `__temporal_class__ = EFFECTIVE_DATED`,
> are EV-mutable (no `irp_prevent_mutation` trigger; a `REFERENCE.UPDATE` succeeds at the DB), and carry `record_version`. The
> FR halves (ENT-001 `instrument_terms`, ENT-007 rating **assignments**) remain unbuilt — **the `FullReproducibleMixin` (FR)
> still has no first persisted user; P1B-3 is its first exercise.**
>
> **P1B-2 realization note:** ENT-002 (`issuer`) and ENT-003 (`counterparty`) — realized as 1:1 role profiles over an
> implementation-only `legal_entity` core (migration 0009) — are now built, all `__temporal_class__ = EFFECTIVE_DATED`,
> EV-mutable (in-place supersede; one physical row per logical entity; history via the `REFERENCE.UPDATE` audit), carrying
> `record_version`. They are PROPRIETARY (symmetric RLS, never hybrid). **FR is still unexercised — P1B-3 remains its first use.**
>
> **P1B-3 realization note:** ENT-001 is now built (migration 0010) as `instrument` (**EV** identity) + `instrument_terms`
> (**FR** — the platform's **first persisted user of `FullReproducibleMixin`**). The FR protocol maintains both axes
> (`valid_from/valid_to` + `system_from/system_to`): create → effective-dated supersede (close prior `valid_to`) → as-known
> correction/restatement (close prior `system_to`, `restatement_reason` + `supersedes_id` — **TR-08**), with
> `reconstruct_terms_as_of(valid_at, known_at)` proving as-of reconstruction on BOTH axes (acceptance-gated tests). The FR
> table is **NOT** append-only (no `irp_prevent_mutation` trigger — the bitemporal protocol UPDATEs the close-out columns);
> content-immutability of prior versions is service-enforced + tested. ENT-004 (`identifier_xref`, EV) is also built.
> Remaining FR users (ENT-007 rating **assignments**, market data, positions, valuations) are still deferred.
>
> **P1B-4 realization note:** ENT-008 (`corporate_action`) is now built (migration 0011) as **EV** — capture-only effective-dated
> reference data. One physical row per logical action; amend = in-place EV supersede (`REFERENCE.UPDATE`); the status lifecycle
> (ANNOUNCED → CONFIRMED → CANCELLED) is the **first persisted user of `REFERENCE.STATUS_CHANGE` / EVT-143** (status/reason
> history via the audit trail, not an IA table — OD-P1B-B). It is EV-mutable (no `irp_prevent_mutation` trigger). The EV
> `valid_from/valid_to` record axis is distinct from the inert business-date columns; **no application/position/valuation logic**
> (application is P1C). The CAP-2 Security-Master reference block (ENT-001..006/008) is now EV/FR-complete for P1B.
>
> **P1C-0 ratification note (AD-017, 2026-06-23 — capture-only domain block; conforms to this §2A, no AD-005 amendment):**
> **ENT-010** (`portfolio`) is classified **EV** and **BUILT in P1C-1 (migration `0012`)** — a single `portfolio` table
> (`node_type` PORTFOLIO/FUND/STRATEGY/ACCOUNT + `parent_portfolio_id` adjacency; the entitlement scope anchor), EV-mutable
> (in-place supersede; `record_version`; declares `__temporal_class__ = EFFECTIVE_DATED`; NOT append-only; no `system_*`
> axis; history via the `PORTFOLIO.UPDATE` audit). Bounded cycle-safe ancestor + descendant resolvers; symmetric RLS.
> **ENT-011** position (**FR**) is **BUILT in P1C-3 (migration `0014`)** as the platform's **first FR DOMAIN entity** —
> captured/as-of-reconstructable via the P1B-3 `instrument_terms` FR protocol (create → effective-dated supersede → as-known
> correction; `reconstruct_position_as_of` on both axes); aggregated `(portfolio, instrument)` grain, signed quantity, opaque
> `cost_basis`. **NOT append-only** (no `irp_prevent_mutation` trigger — the FR protocol requires close-out UPDATEs; prior-version
> CONTENT immutability is service-enforced + tested) — the FR contrast with the IA `transaction`. **Captured directly, NOT
> derived from transactions** (OD-P1C-E). **ENT-013** valuation (**FR**) is **BUILT in P1C-4 (migration `0015`)** as the
> platform's **second FR DOMAIN entity** — captured marks via the `position`/`instrument_terms` FR protocol (create →
> supersede → as-known correction; `reconstruct_valuation_as_of` both axes); grain `(portfolio, instrument, valuation_date)`
> with `valuation_date` an immutable logical-key column DISTINCT from the FR `valid_from` axis (OD-P1C-F). **NOT append-only**;
> **captured marks, NOT computed by a valuation/pricing model, NO market-value rollup / NO position link** (OD-P1C-F). **ENT-012** transaction is **IA** (append-only event log) — **BUILT in P1C-2 (migration `0013`)** as the platform's **first DOMAIN append-only entity**: `__temporal_class__ = IMMUTABLE_APPEND_ONLY` (`system_from` only), in `APPEND_ONLY_TABLES` (the `irp_prevent_mutation` P0001 trigger) + the ORM `before_update`/`before_delete` guard; corrections are explicit reversal records (`reverses_transaction_id`), never updates (the original is never mutated). Capture-only — no position derivation. **ENT-014** `exposure_aggregate`
> (IA, derived) + `dataset_snapshot` stay **P2** (AD-014) — no governed derived output without a bound input snapshot.

> **P2-3 realization note (AD-018, 2026-06-26 — ratified-in-planning; conforms to §2A + §5, no AD-005 amendment):** `exposure_aggregate`
> (**ENT-014**, already classed **IA** in §2A above) is the platform's **FIRST executable instance of the FW-RUN §5 / TR-15
> run-bind** — the first official governed derived number. It is **IA, TRUE append-only** (in `APPEND_ONLY_TABLES`; a re-run is a
> NEW `calculation_run` + new rows, never an edit) and **RUN-BOUND + SNAPSHOT-GATED**: no row exists without a non-null
> `input_snapshot_id` + a complete run binding **`code_version`** (the deterministic anchor) + the additive **`environment_id`** (§5
> item 7) + the initiator. Of the §5 bind, items 3/4/5 (`assumption_set`, RNG seed, scenario) and `model_version` are
> **N/A-with-recorded-rationale** — a **model-less deterministic captured-mark rollup** (`signed_quantity × captured mark_value ×
> effective FX rate`, **signed market value v1**), never a sham binding. **TR-15 fail-closed, split by timing:** a **pre-create
> refusal** (missing prerequisite) leaves ZERO run + ZERO result + ZERO audit; a **post-create FAILED** run (a gate failing after
> RUNNING) commits a FAILED run + `CALC.RUN_STATUS_CHANGE` but ZERO result rows. **Reproducibility (TR-09/TR-13):** the exposure
> reads ONLY the snapshot's pinned components' **captured content** (positions, valuations, and FX as `COMPONENT_KIND_FX`) — **never
> a live `reconstruct_*`/`resolve_*` read**; the FX is the **effective composite** of the pinned legs (`fx_legs` are leg references,
> NOT a hard FK to a supersedable FR row), so a later vendor correction cannot change a historical exposure. **BASIC exposure ONLY —
> NOT risk** (no VaR/ES/factor/sensitivity/scenario/stress/pricing/valuation model). **REALIZED in P2-3 (`da178fc`, migration
> `0018_exposure_aggregate`)**.

### Rationale (TR-21)
| ID | Rationale |
|---|---|
| TR-21 | Bitemporality is the most expensive pattern (storage + query complexity). It is reserved for **FR** inputs because reproducing or defending a governed risk number requires reconstructing both what was true (valid time) and what was known (system time). **IA** outputs do not need a second axis: a run already pins its inputs by snapshot, so a result is reproduced from its run, not by as-of-querying the result. **EV** reference/config needs history for audit and context but rarely needs dual-axis as-of, so system-time versioning with effective dating is sufficient. Misclassification risk is mitigated by an explicit class on every entity and review when new entities are added. |

## 3. Immutability & Correction

| ID | Rule |
|---|---|
| TR-05 | Result, report, and audit records are **append-only**; no in-place update or delete. |
| TR-06 | Corrections create a **new version** (and, for facts, close the prior `system_*` interval and insert a successor); the prior value remains queryable. |
| TR-07 | A correction is itself an auditable event (`DATA.CORRECTION`, see audit taxonomy) and, for governed values, flows through `manual_override` with BR-7 fields. |
| TR-08 | Restatements are explicitly flagged with a restatement reason and link to the superseded version. |

## 4. Dataset Snapshots & Versioning

| ID | Rule |
|---|---|
| TR-09 | Inputs to any calculation are pinned by a **dataset snapshot ID** capturing the exact record versions (by system-time) used. |
| TR-10 | Scenario definitions are versioned with saved assumptions; a scenario run references a scenario version + dataset snapshot (BR-8). |
| TR-11 | Model code/methodology is versioned in the Model Registry; a run references a specific `model_version`. |
| TR-12 | Assumption sets are versioned objects referenced by runs (not inline literals). |

## 5. Calculation-Run Reproducibility Contract (FW-RUN)

Every `calculation_run` (ENT-026) binds, at minimum:

1. Code/model version(s) (`model_version` ids)
2. Input dataset snapshot id(s)
3. Assumption set version
4. Parameters (including RNG seed where stochastic — QS standards)
5. Scenario version (if applicable)
6. Initiator (user/system/agent principal) and trigger
7. Start/end timestamps (UTC) and environment id

| ID | Rule |
|---|---|
| TR-13 | **Reproduction guarantee:** re-executing a run with the same bound inputs reproduces identical results within the tolerances defined in numerical_quant_standards.md (QS tolerance). |
| TR-14 | Stochastic calculations must record and reuse the RNG seed and path count to satisfy TR-13. |
| TR-15 | A result that cannot bind all of items 1–7 is **incomplete** and must not be published or used for limits/reports (BR-6). |
| TR-16 | Reports bind the `calculation_run` ids and source metric versions they were generated from (BR-9); regenerating a report version reproduces it. |

## 6. Late / Out-of-Order Data

| ID | Rule |
|---|---|
| TR-17 | Late-arriving data is inserted with its true valid time and the actual system time of receipt (bitemporal); it does not silently alter prior results. |
| TR-18 | If late data changes a prior business date materially, a **restatement run** is created (new run, new results), leaving the original run reproducible. |

## 7. Retention

| ID | Rule |
|---|---|
| TR-19 | Bitemporal history, runs, results, and audit are retained per NFR-04 (≥ 7 years; confirm per jurisdiction) and never hard-deleted within retention. |
| TR-20 | Purge after retention is itself a controlled, audited, approved action (no ad-hoc deletion). |

## 8. Reproducibility Test (QA linkage)

A standing QA control re-runs a sample of historical `calculation_run` ids and asserts identical results (TR-13). Failure is a
release blocker and a control finding (control matrix CTRL — see compliance controls).

## 9. Open Decisions

| ID | Open Decision |
|---|---|
| OD-016 | Confirm retention period(s) by data class and jurisdiction (drives TR-19). |
| ~~OD-017~~ | **Resolved (Step 1C, AD-005):** selective bitemporality — FR/IA/EV classes in §2A. |
| ~~OD-018~~ | **Resolved (Step 1C):** reproduction tolerances set in numerical_quant_standards.md §2A (ε_rel=1e-12, ε_abs=1e-9). |
| OD-019 | Confirm restatement approval authority (H-01/H-04) and notification workflow. |

## 10. Dependencies

- canonical_data_model_standard.md (bitemporal columns, ENT-026/027/029).
- numerical_quant_standards.md (seeds, tolerances — TR-13/14/18).
- audit_event_taxonomy.md (`DATA.CORRECTION`, restatement events).
- AD-005 (temporal model), AD-006 (calc engine).
