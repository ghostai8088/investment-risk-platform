# P2-7 Decision Record — Benchmark price/level capture (Wave-1 slice 4; the ENT-052 mint)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-P2-7-1…8 approved by the user (2026-07-09, after a plain-language decision briefing); implementation is a SEPARATE approval |
| Date | 2026-07-09 |
| Basis | `delivery_roadmap.md` Wave 1, slice 4: "benchmark price/level capture — the captured-input slice (`benchmark_level`/`benchmark_return`, a NET-NEW canonical ENT id) that unblocks every return-based benchmark-relative analytic. Follows the P2 captured-data pattern (FR/bitemporal; no run/model/snapshot binding)." Discharges the recorded **OD-P2-6-K** deferral. |
| Grounding | Verified against shipped HEAD `13f71df` (P3-C2 closed): `benchmark` (ENT-009, EV definition header) + `benchmark_constituent` (FR membership) REALIZED in P2-6 (migration `0021`) with `VENDOR_BENCHMARK` lineage + `marketdata.view`/`.ingest` entitlement; NO level/return series tables exist. The direct template is P3-2's `factor_return` (ENT-025): FR bitemporal captured series over an EV definition — capture / effective-dated supersede / as-known correction / both-axes reconstruct; row-grained; binder finiteness guard; NOT_NULL + min-only RANGE DQ gates; `MARKET.FACTOR_RETURN_*` single-row-grain audit at the EVT-200 block. Canonical registry runs ENT-001…ENT-051 (ENT-051 minted at P3-4 — the Part-3 mint precedent); **ENT-052 is the next free id**. Migration head `0028_var_historical`. RTM home = REQ-PUB-003 (explicitly lists `benchmark_level`/`benchmark_return` as deferred legs). |
| Pre-ratified constraint | **OQ-P2-6-9 / OD-P2-6-K (already user-ratified at P2-6):** `benchmark_return` is **captured vendor-published values only — NO return calculation from levels**. This is a FIXED input to P2-7, not an open question. |
| Sign-off | **OQ-P2-7-1…8 — APPROVED / RATIFIED by the user (2026-07-09: "Yes" on the full package, all eight as recommended).** |

---

## Part 1 — Decisions at a glance

| ID | Topic | Decision |
|---|---|---|
| **OD-P2-7-A** | slice character | A **captured-INPUT data slice** (the P2 pattern, the `fx_rate`/`price_point`/`factor_return` family): FR/bitemporal vendor data captured verbatim — **NO `calculation_run`, NO `model_version`, NO snapshot pin, NO derived number** (an input, not a governed output; the ENT-025 precedent verbatim). ONE net-new canonical id (**ENT-052**) minted via the Part-3 ratification process (the ENT-051/P3-4 precedent). ONE migration (**`0029`**). **NO new permission** (reuse `marketdata.view`/`.ingest` — the ENT-009/ENT-025 precedent). Audit = **additive `MARKET.*` activation** at the established EVT-200 block (caller-side strings; `audit/service.py` FROZEN; the taxonomy update IS the R-07 mint record — the P2-4/P2-5/P2-6/P3-2 precedent). NO frontend change. |
| **OD-P2-7-B** | entity model | **TWO FR bitemporal tables realizing ONE canonical id (ENT-052 "benchmark time series")**: `benchmark_level` (captured vendor index levels) + `benchmark_return` (captured vendor-published returns) — the multi-table-per-id precedent (ENT-007 `rating_scale`/`rating`, ENT-016 `capital_call`/`distribution`). Both are children of the EXISTING ENT-009 `benchmark` EV header: `benchmark_id` NOT-NULL FK resolved fail-closed via `resolve_benchmark` (tenant-predicated; `BenchmarkNotVisible` → 404). Both `FullReproducibleMixin` (the ninth/tenth persisted FR users); **symmetric tenant-scoped RLS (NEVER hybrid); NEITHER append-only** (FR close-out UPDATEs — the `factor_return`/`benchmark_constituent` precedent; no `irp_prevent_mutation` trigger). |
| **OD-P2-7-C** | `benchmark_level` design | Grain `(tenant, benchmark_id, level_date, level_type)`; current-head partial-unique `WHERE valid_to IS NULL AND system_to IS NULL`; `level_date` a **separate immutable logical-key column** (the `rate_date`/`valuation_date`/`return_date` precedent). **`level_type` controlled-vocab plain String** (extend by value, MG-01): `PRICE_RETURN` / `TOTAL_RETURN` / `NET_TOTAL_RETURN` — one benchmark definition carries its variant series WITHOUT duplicating the (identical) constituent membership per variant; a tenant that registers variants as separate `benchmark` rows (the vendor SPX/SPXT convention) simply uses one type value each — both shapes work. `level_value` = **`PreciseDecimal(20, 6)`** (the `price_point.price` scale — an index level is price-like; PreciseDecimal from birth per the P3-C2 OD-D criterion, precision ≥ 16). Levels are denominated in the header's `benchmark_currency` (NO per-row currency column). |
| **OD-P2-7-D** | `benchmark_return` design | Grain `(tenant, benchmark_id, return_date, return_type, return_basis)`; current-head partial-unique; `return_date` immutable logical key. `return_type` = `SIMPLE` (`LOG` reserved by value — the ENT-025 vocabulary). **`return_basis`** (NOT NULL, controlled-vocab plain String, extend by value): `PRICE` / `TOTAL` / `NET_TOTAL` — WHICH index variant the vendor return describes (a vendor publishing both PR and TR returns for one benchmark/date must not collide; a feed always documents its basis — captured verbatim, never guessed). `return_value` = **`PreciseDecimal(20, 12)`** captured DECIMAL fraction (`0.01` = 1%, NOT percent/bps — the ENT-025 convention). **Captured vendor-published values ONLY — NO calculation from levels** (OQ-P2-6-9, pre-ratified; a level-derived return would require a registered `model_version` + methodology — the "computed factor returns" deferral precedent, untouched). |
| **OD-P2-7-E** | capture protocol + governance rails | The `factor_return` FR protocol VERBATIM, per table: **capture / effective-dated supersede / as-known correction (TR-08 `restatement_reason` on `justification`) / both-axes `reconstruct_*_as_of`**; row-grained (one `(benchmark, date, type…)` per call — bulk ingestion stays an ingestion-pipeline theme, NOT this slice). Binder-side **finiteness guard** (reject NaN/±Inf pre-write — the P3-2 lesson: a min-only RANGE does not catch +Inf). Fail-closed co-transactional **DQ gates** (the `(params, dataset)` Protocol UNTOUCHED): required-field NOT_NULL + a min-only RANGE sanity per table — `level_value` positive-sanity (min 0), `return_value` economic-sanity (min −1, the ENT-025 band). Lineage: **REUSE the existing per-tenant `VENDOR_BENCHMARK` `data_source`** (P2-6; no new source type) — one ORIGIN edge per NEW physical version row, targeted at the level/return row. Audit: **`MARKET.BENCHMARK_LEVEL_CREATE`/`_UPDATE`/`_CORRECTION` + `MARKET.BENCHMARK_RETURN_CREATE`/`_UPDATE`/`_CORRECTION`** — single-row grain (the `FACTOR_RETURN` precedent, NOT the set-grained `BENCHMARK_CONSTITUENT`); capture=1 event, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE + CORRECTION); `before/after` = DC-2 metadata only (code/source/date/type/record_version — never a vendor-licensed payload dump); **no emit on read**. ONE `now = utcnow()` per op; CLOSE-FIRST ordering; prior-row CONTENT never mutated. |
| **OD-P2-7-F** | API surface | Under the existing benchmark router (`api/marketdata.py`): per series — POST capture / supersede / correct (gated **`marketdata.ingest`**) + GET as-of reconstruct + list (gated **`marketdata.view`**), mirroring the factor-return endpoint family. Fail-closed maps: binder value errors → 422; `BenchmarkNotVisible`/unresolved refs → 404; no-current-row supersede/correct → 409/422 per the existing family convention. **No emit on read.** |
| **OD-P2-7-G** | registry/docs obligations | (1) Canonical registry: mint the **ENT-052** row (Market Data grouping) + update the ENT-009 Notes cell (deferral → realized pointer). (2) Audit taxonomy: extend the `MARKET` row with the six new codes (the R-07 activation record — the P3-2 wording precedent). (3) RTM: advance **REQ-PUB-003** (the `benchmark_level`/`benchmark_return` legs deliver; the REQ still does NOT close — `rating` + the full Coverage test remain deferred). (4) Roadmap Part 4 **rule 6 N/A** (captured data; no new math, no new number — the P3-C2 precedent), with a short non-normative design-grounding note: the PRICE/TOTAL/NET_TOTAL variant vocabulary follows published index-vendor methodology convention (S&P DJI / MSCI publish price-return, gross-total-return and net-total-return variants of one index). |
| **OD-P2-7-H** | proportionate review | **FULL 6-finder adversarial review + unreduced validation gates** (make check + full-PG + migration downgrade smoke + the frontend suite untouched-but-run): the slice ships a migration (two tables + RLS), activates audit codes, and mints a canonical id — governed surfaces warrant the full pattern even though the build is templated. |

## Part 2 — Rationale highlights

### OD-P2-7-B/C — why series tables under ONE definition (and why a `level_type` column)
Index vendors publish one index in several return-treatment variants (price return, gross total return, net
total return) with IDENTICAL constituent membership. Modelling variants as separate `benchmark` definitions
(the vendor SPX/SPXT code convention) would force tenants to capture the SAME membership set once per variant —
duplicated captured data that can drift. A `level_type`/`return_basis` discriminator in the series grain lets one
definition carry its variants while still permitting the separate-definition shape for tenants whose vendor feeds
are keyed that way. Both tables realize ONE canonical id: they are two faces of the same concept (the benchmark's
captured time series), exactly as ENT-007/ENT-016 name sibling tables.

### OD-P2-7-D — why returns are captured, never computed (restated)
OQ-P2-6-9 ratified this at P2-6 and the platform's own P3-2 stance enforces it structurally: computing a return —
even a trivial `L_t/L_{t-1} − 1` — is a methodology choice (which variant, which day-count on gaps, simple vs log)
and therefore requires a registered `model_version` + methodology doc under the governed derived-number contract.
P2-7 captures verbatim what the vendor published. If P3-7's tracking-error model prefers level-derived returns, it
declares that derivation INSIDE its registered methodology over snapshot-pinned levels — its decision, at its
slice, under its model version.

### OD-P2-7-A — why no snapshot/run/model binding
The ENT-025 precedent verbatim: captured inputs bind none of dataset_snapshot/calculation_run/model_version — the
CLAUDE.md invariant's second half ("captured inputs bind none of those. Pick the pattern correctly."). P3-7 will
pin these rows as new `COMPONENT_KIND_*` flavors into ITS input snapshots — component vocabulary is minted at the
CONSUMING slice (the ENT-050 rule), so P2-7 mints no component kind either.

## Part 3 — Out of scope (recorded)

NO analytics (tracking error / active risk / active return / attribution / performance = P3-7+); NO return
computation from levels (pre-ratified); NO adjusted-price series or computed factor returns (standing deferral);
NO bulk/batched vendor ingestion endpoint (ingestion-pipeline theme); NO benchmark `frequency` column or other
ENT-009 header schema change (date-grained capture is self-describing; P3-7 declares its own alignment rules —
the covariance precedent); NO new permission / audit-code family / role; NO snapshot `COMPONENT_KIND_*` mint; NO
frontend change; NO vol-surface (ENT-022) or other ENT-020…025 extensions; `methodology_label` and all captured
labels stay inert.

## Part 4 — Open decisions (OQ-P2-7-1…8) — **APPROVED / RATIFIED by the user (2026-07-09, the plan-commit gate)**
**Status: RATIFIED.** The eight defaults below are fixed inputs to the P2-7 implementation.

- **OQ-P2-7-1 — recommend APPROVE.** Slice scope = the two captured series tables discharging OD-P2-6-K; one
  migration; no new permission; no analytics. (OD-A.)
- **OQ-P2-7-2 — recommend APPROVE.** Mint **ENT-052** ("benchmark time series": `benchmark_level` +
  `benchmark_return`) via the Part-3 process — one id, two sibling tables. (OD-B.)
- **OQ-P2-7-3 — recommend APPROVE.** `benchmark_level` grain/typing incl. the `level_type` variant vocabulary
  (PRICE_RETURN/TOTAL_RETURN/NET_TOTAL_RETURN, extend-by-value) and `PreciseDecimal(20,6)`. *(Alternative
  considered: variants as separate benchmark definitions — rejected: duplicates identical constituent membership
  per variant; the discriminator design still permits that shape.)* (OD-C.)
- **OQ-P2-7-4 — recommend APPROVE.** `benchmark_return` grain/typing incl. `return_basis` in the grain and the
  captured-only constraint (OQ-P2-6-9 restated). (OD-D.)
- **OQ-P2-7-5 — recommend APPROVE.** The `factor_return` capture protocol verbatim: row-grained ops, finiteness
  guard, NOT_NULL + min-only RANGE DQ gates, `VENDOR_BENCHMARK` lineage reuse. (OD-E.)
- **OQ-P2-7-6 — recommend APPROVE.** The six additive `MARKET.BENCHMARK_LEVEL_*`/`_RETURN_*` audit codes at the
  EVT-200 block (single-row grain; taxonomy update = the R-07 record) + `marketdata.view`/`.ingest` reuse. (OD-E/F.)
- **OQ-P2-7-7 — recommend APPROVE.** Registry/docs obligations incl. rule-6-N/A with the design-grounding note;
  REQ-PUB-003 advanced-not-closed. (OD-G.)
- **OQ-P2-7-8 — recommend APPROVE.** Full 6-finder review + unreduced gates (migration + RLS + audit-code
  activation). (OD-H.)

## Part 5 — P2-7 implementation readiness gate

Implementation-ready once OQ-P2-7-1…8 are ratified. Build contract = `p2_7_implementation_plan.md`.
**P2-7 planning implements nothing.**
