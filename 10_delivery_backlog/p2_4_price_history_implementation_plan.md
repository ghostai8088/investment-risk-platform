# P2-4 Implementation Plan — Captured Price History (`price_point`, ENT-020)

## Document Control

| Field | Value |
|---|---|
| Purpose | The detailed P2-4 build plan: realize **`price_point`** (ENT-020, **FR/bitemporal**) — **captured security/vendor price history** — as the second member of the `irp_shared/marketdata` package (the P2-2 `fx_rate` protocol precedent). **Captured market data, NOT a pricing model.** Companion to `p2_4_decision_record.md` (OD-P2-4-A…L). |
| Status | **Implementation PLAN — PLANNING ONLY; NO code, NO migrations, NO P2-4 implementation.** |
| HEAD at writing | `0b12d85`; origin/main clean; migration head `0018_exposure_aggregate`. P2-1 (`3629baa`) + P2-2 (`c257e5c`) + P2-3 (`da178fc`) all CI-green. |
| Predecessors | `p2_4_decision_record.md`; `p2_2_fx_rate_implementation_plan.md` (the FR capture protocol + `marketdata` package mirrored); `p2_0_decision_record.md` (AD-004-R1; the subphase sequencing). |
| Review | 8-lens UltraCode review — **§26** (filled after the review workflow). |

> **What P2-4 is — and is NOT.** P2-4 **captures** vendor prices the way P2-2 captured FX rates: an FR bitemporal `price_point` (create / effective-dated supersede / as-known correction / `reconstruct_price_as_of`), governed by `MARKET.PRICE_*` audit + VENDOR `data_source` lineage + a fail-closed DQ gate, under symmetric tenant RLS. It computes **nothing**: **NO pricing model, NO valuation model, NO return/performance analytics, NO factor/covariance/risk/VaR/ES, NO FX conversion, NO corporate-action adjustment engine, NO exposure recalculation, NO `calculation_run` change, NO `dataset_snapshot` schema change.** It is the captured **price input** future calculations will consume; the snapshot/run binding is **readiness-only** (the P2-3 `COMPONENT_KIND_FX` precedent — pin when a calc needs it).

---

## Specific decisions settled (the 12 the user asked to confirm)
Full detail in `p2_4_decision_record.md` Part 2. Summary:

| # | Question | **Decision** |
|---|---|---|
| **1** | entity naming | **`price_point`** (ENT-020 canonical; not `price`/`market_price`/`instrument_price`). |
| **2** | temporal class | **FR / bitemporal** (`FullReproducibleMixin`; **NOT append-only**; the `fx_rate`/`valuation` protocol verbatim). |
| **3** | grain (logical key) | **`(tenant, instrument_id, price_date, price_type, currency_code, price_source)`** — 6-part current-head partial-unique; `price_source` **in the key** (multi-vendor coexistence); `venue`/`adjustment_basis` deferred. |
| **4** | `price_date` | a **separate immutable logical-key `Date`** (the `valuation_date`/`rate_date` precedent), DISTINCT from `valid_from`. |
| **5** | `price_type` vocab | **`{CLOSE, MID, NAV}`** v1 (controlled-vocab String); **BID/ASK reserved** (paired quotes). |
| **6** | adjusted vs raw | **RAW vendor prices ONLY** — no `adjustment_basis` column, no corporate-action adjustment engine, no implied adjustment; ADJUSTED is a future *captured* value. |
| **7** | currency | **captured `currency_code`** (in the key); **NO conversion in P2-4** (FX conversion is a later calc via the P2-2 `convert`); `price` `Numeric(20,6)`. |
| **8** | source | **`price_source` label (in the key)** + a **VENDOR `data_source` ORIGIN lineage** edge (`ensure_vendor_source(VENDOR_PRICE)`); **NO feed pipeline.** |
| **9** | snapshot integration | **READINESS ONLY** — no `COMPONENT_KIND_PRICE`, no binder change (pin later when a calc consumes prices); no `dataset_snapshot` redesign. |
| **10** | entitlement | **reuse `marketdata.view`/`.ingest`** (market-data family; no new permission). |
| **11** | DQ | required-field NOT_NULL + strictly-positive `RANGE` (reuse; Protocol untouched); staleness/completeness deferred. |
| **12** | audit | **reuse `MARKET.*`** — `MARKET.PRICE_CREATE`/`PRICE_UPDATE`/`PRICE_CORRECTION` (EVT-200; `audit/service.py` FROZEN). |
| **(instrument)** | FK | `instrument_id` NOT-NULL FK; reused `resolve_instrument` (cross-tenant fail-closed). |
| **(calculation_run)** | binding | **NONE in P2-4** (captured data; no run/exposure change). |

---

## 1. Requirements included
**REQ-PUB-001** — "Market prices (time-series)" (CAP-3.1; `requirements_backbone.md`) — whose **named realizing entity IS `price_point` (FR)**. P2-4 realizes `price_point` (an FR bitemporal captured-vendor-price entity, reproducible on both axes, joining the market-data family) + the **"price reconstructable as-of"** acceptance leg. P2-4 **advances REQ-PUB-001 to In-Progress (partial)** — it does **NOT close** it: the **"stale flagged (QS-16)" / staleness-test** acceptance leg is **DEFERRED** (OQ-P2-4-4 — staleness needs a window policy; tracked, not dropped). (REQ-PPM-004 is **NOT** a `price_point` REQ — it only consumes a converted price as a future *calculation* input; do not cite it as a P2-4 REQ.)

## 2. Requirements excluded (hard)
**NO pricing model / valuation model**; **NO return / performance analytics** (no return field, no return calc); **NO factor / covariance model**; **NO VaR / Expected Shortfall / risk / sensitivities / stress / scenario**; **NO exposure recalculation / `exposure_aggregate` change**; **NO `calculation_run` wiring change**; **NO `dataset_snapshot` schema redesign**; **NO `fx_rate` schema redesign**; **NO curves (P2-5) / benchmark (P2-6)**; **NO market-data feed-ingestion pipeline**; **NO corporate-action adjustment engine**; **NO reporting/dashboard / frontend**; **NO P3+**; **NO broad DQ/lineage rewrite**; **NO `audit/service.py` change**; **NO BYPASSRLS**; **NO hybrid/SYSTEM_TENANT** (price is per-tenant vendor-licensed). **REQ-PUB-001 advances to In-Progress (partial)** (the as-of leg met; the staleness/QS-16 leg deferred — §1) — it does NOT close; **no other REQ status changes.**

## 3. Proposed entities / modules
- **`price_point`** (ENT-020, FR) — the single new domain table; **a new migration `0019_price_point`** (FR, symmetric RLS, NOT append-only — mirroring `0017_fx_rate`). The promoted key columns **`price_type` / `currency_code` / `price_source` are DB-level `NOT NULL`** (review fold — so the current-head partial-unique is not defeasible by a NULL key component; unlike the inert nullable `rate_source`).
- **`irp_shared/marketdata` extension (additive):** `PricePoint` model (in `marketdata/models.py` or a new `marketdata/price.py`); the price binder (`capture_price` / `supersede_price` / `correct_price` / `reconstruct_price_as_of` / `resolve_price`) + the DQ gate (in `marketdata/service.py` or `price.py`); `MARKET.PRICE_*` constants + `PriceActor` + `ensure_vendor_source(VENDOR_PRICE)` + the ORIGIN edge (in `marketdata/events.py`). The package's leaf one-way imports `{reference, lineage, dq, audit, db}` are unchanged; imports NO `calc`/`exposure`/`snapshot` symbol; nothing new imports `marketdata` beyond the P2-3 readers.
- **`reference` reuse:** `resolve_instrument` (the FK gate) + `resolve_currency` (currency validation) — reused, **unchanged**.
- **New backend `api/marketdata.py` endpoints** (extend the existing file): the price capture/supersede/correct/read endpoints (§13).
- **`entitlement/bootstrap.py`:** **UNCHANGED** — `marketdata.view`/`.ingest` already exist (the reusable verb); only the parity test extends.

## 4. Temporal classification
`price_point` = **FR / fully-reproducible / bitemporal** (`FullReproducibleMixin`; `__temporal_class__ = FULL_REPRODUCIBLE`; **NOT** in `APPEND_ONLY_TABLES` — no `irp_prevent_mutation` trigger, no ORM guard; close-out UPDATEs required; content-immutability service-enforced + tested). The `fx_rate`/`valuation` FR contrast with the IA append-only entities.

## 5. Price grain — **recommended: `(instrument_id, price_date, price_type, currency_code, price_source)`**
**Recommendation + rationale.** The v1 current-head partial-unique is **`(tenant_id, instrument_id, price_date, price_type, currency_code, price_source) WHERE valid_to IS NULL AND system_to IS NULL`** — exactly one open price per that 6-tuple; the FR axes version the price for the fixed key. **`price_source` is a key component** (unlike inert `rate_source`) because multiple vendors realistically publish a price for the same `(instrument, date, type, currency)` and the platform keeps them all (comparison/fallback) — a real difference from the single authoritative FX MID. Minimal + auditable: one open price per (instrument × business-date × type × currency × vendor); `venue`/`exchange` (intra-day / multi-listing) and `adjustment_basis` (raw/adjusted) are **deferred** additive key extensions (OQ-P2-4-1/3). Each row is independently traceable to one `instrument` + one VENDOR `data_source` ORIGIN edge.

## 6. Price date / valid-time convention
`price_date` is a **separate immutable logical-key `Date`** (the business date the price is FOR), carried forward verbatim, **never mutated**, DISTINCT from the FR `valid_from` axis. `valid_from`/`valid_to` (valid-time) + `system_from`/`system_to` (knowledge-time) version the *price* for a fixed `price_date`. Many `price_date`s per key coexist as separate open heads. `reconstruct_price_as_of(valid_at, known_at)` reads the price true-at `valid_at` as-known-at `known_at` for a given logical key (the `reconstruct_fx_rate_as_of` shape).

## 7. Price value / price type / adjustment convention
`price` = **`Numeric(20,6)`** (the `valuation.mark_value` money scale; OQ-P2-4-2). `price_type` controlled-vocab String, v1 **`{CLOSE, MID, NAV}`** (BID/ASK reserved). **RAW vendor prices ONLY** — no `adjustment_basis` column, no corporate-action adjustment engine, no implied adjustment (a scope-fence test forbids any split/dividend/adjust symbol in the price module). `currency_code` captured + in the key; **no conversion** here.

## 8. Currency convention
Captured `currency_code` (ISO String(3)), validated via the reused hybrid-aware `resolve_currency` (own OR SYSTEM), **in the logical key**. The price is stored in its native currency; **converting to a base currency is a later calculation** (via the P2-2 `convert` helper), never in the P2-4 capture path. No `convert` import in the price binder.

## 9. Source / provenance model
`price_source` a controlled-vocab String label (e.g. `BLOOMBERG`/`REFINITIV`/`EXCHANGE`) — a **key** component — plus a **VENDOR `data_source` ORIGIN lineage edge** per new physical version via a new `ensure_vendor_source(VENDOR_PRICE)` (the `VENDOR_FX` sibling; REUSES `record_lineage` UNCHANGED). **No market-data feed-ingestion pipeline / connector / scheduler** — captures arrive through the governed binder, one governed write at a time (the `fx_rate` precedent).

## 10. Relationship to `instrument`
`instrument_id` **NOT-NULL FK** to the P1B-3 `instrument` head; resolved via the **reused `resolve_instrument`** (tenant-predicated; cross-tenant/unknown → `InstrumentNotVisible`, fail-closed **before any write**) — the `corporate_action` precedent. PROPRIETARY/symmetric (the symmetric by-id resolver, NOT the currency hybrid).

## 11. Relationship to `dataset_snapshot`
**READINESS ONLY** — P2-4 mints **NO `COMPONENT_KIND_PRICE`** and changes **NO `build_snapshot`/`_reresolve_content`**. A price component is pinned **only** when a future calculation consumes prices (the P2-3 `COMPONENT_KIND_FX` precedent — minted at P2-3, not at P2-2). **NO `dataset_snapshot` schema redesign** (the tables are untouched).

## 12. Relationship to `calculation_run`, if any — **expected: none in P2-4**
**NONE.** Captured price data wires no `calculation_run`; the `calc`/`exposure` packages are **untouched**; `exposure_aggregate` is **unchanged**. Binding a price into a run is a future *calculation* slice (P3+), explicitly out of P2-4.

## 13. APIs (extend `api/marketdata.py`)
- **`POST /prices`** (gated **`marketdata.ingest`**; 201) — capture one price; whole-unit rollback + 403/404/409/422 mapping (unknown/cross-tenant instrument or currency → 404; out-of-vocab `price_type` → 422; DQ failure → 409).
- **`POST /prices/{id}/supersede`** (gated `marketdata.ingest`) — effective-dated re-quote for the SAME key.
- **`POST /prices/{id}/correct`** (gated `marketdata.ingest`) — as-known restatement (TR-08).
- **`GET /prices/as-of`** (gated `marketdata.view`) — `reconstruct_price_as_of` for a logical key.
- **`GET /prices`** (gated `marketdata.view`) — range/list read.
- **No PUT/PATCH/DELETE** (FR is superseded/corrected, never edited/deleted).

## 14. Audit events
**Reuse the `MARKET.*` category** — mint **`MARKET.PRICE_CREATE` / `MARKET.PRICE_UPDATE` / `MARKET.PRICE_CORRECTION`** at the EVT-200 block (caller-side constants in `marketdata/events.py` to the FROZEN `record_event`; per-op grain capture=1, supersede=2 (UPDATE close-out + CREATE), correct=2 (UPDATE close-out + CORRECTION); DC-2 metadata only — `instrument_id`/`price_date`/`price_type`/`currency_code`/`price_source`, **never a vendor-licensed payload dump**; zero on read). Per-tenant chain (PROPRIETARY, no SYSTEM chain). **`audit/service.py` FROZEN.**

## 15. Entitlement checks
**Reuse `marketdata.view` / `marketdata.ingest`** (already minted P2-2 as the reusable market-data verb — `.ingest` is the governed canonical-write verb, `.view` the read; `data_steward` maker; risk tiers `.view`; `auditor_3l` excluded). **No new permission, `bootstrap.py` UNCHANGED**; the `test_marketdata_permissions_grants_as_ratified` parity test stands (asserts price reuses the same grants). Deny-by-default.

## 16. RLS behavior
`price_point` = **symmetric tenant-scoped** (`USING == WITH CHECK == own-tenant`, ENABLE+FORCE; migration `0019`); **NEVER hybrid** (per-tenant vendor-licensed, MNPI-adjacent; the closed 5-table hybrid set asserted unchanged); cross-tenant `instrument_id`/currency fail closed at the service layer; no BYPASSRLS. A new price symmetric-RLS CI step. PG-proven as `irp_app`.

## 17. Lineage behavior
One **VENDOR `data_source` ORIGIN edge** per NEW physical version (capture / new-open-row-of-supersede / correction; the prior-head close-out roots NONE) via `ensure_vendor_source(VENDOR_PRICE)` — REUSES `record_lineage` UNCHANGED. `price_source` (the row label) is DISTINCT from the governed VENDOR `data_source` ORIGIN edge. **Not a framework rewrite** (one new source-type token).

## 18. Data-quality behavior
A governed fail-closed gate (co-transactional; `DATA.VALIDATE`; CTRL-032 rollback) reusing the shipped evaluators: **required-field NOT_NULL** (the sentinel-null derived dataset, the P2-2 pattern) + **strictly-positive `RANGE`** on `price` (`{column:"price", min:0, min_inclusive:false}`). The `(params, dataset)` **Protocol is UNTOUCHED**; the two/three shipped evaluators behavior-unchanged. **Staleness / completeness gates DEFERRED** (OQ-P2-4-4 — staleness needs a window policy; not v1).

## 19. Tests
SQLite logic + PG FORCE-RLS + endpoint + parity (the `fx_rate` test shape):
- **FR protocol (positive):** capture → reconstruct (both axes: a valid-time supersede + an as-known correction reconstruct correctly); content-immutability-on-correction (prior row's content columns never mutated — only `valid_to`/`system_to`); the 6-part current-head partial-unique (one open price per key; many `price_date`s/sources coexist); multi-vendor coexistence (two `price_source`s for the same instrument/date/type/currency are two open heads).
- **DQ fail-closed:** a non-positive price → `DataQualityError` → CTRL-032 rollback (no row, no ORIGIN edge, no `MARKET.PRICE_CREATE`); a missing required field → fail closed.
- **Audit:** `MARKET.PRICE_CREATE` (1) on capture; `MARKET.PRICE_UPDATE`+`PRICE_CREATE` (2) on supersede; `MARKET.PRICE_UPDATE`+`PRICE_CORRECTION` (2) on correct; `verify_chain` ok (PG); **NO event on read**; `audit/service.py` untouched.
- **Lineage:** one VENDOR (`VENDOR_PRICE`) ORIGIN edge per physical version; the close-out roots none; CTRL-032 rollback (monkeypatch the emitter → zero rows), mirroring the `fx_rate` precedent.
- **Instrument FK / currency:** cross-tenant/unknown `instrument_id` → `InstrumentNotVisible` (fail closed pre-write); unknown currency → `CurrencyNotVisible`; out-of-vocab `price_type` → `PriceValueError`.
- **Entitlement:** deny-by-default 403 (no DB side-effect on denial); the parity test (price reuses `marketdata.*`); 404/409/422 mapping.
- **PG (`irp_app`):** tenant isolation + no-context → 0 rows; forged-tenant `WITH CHECK` 42501; **closed-hybrid-set-unchanged**; (FR — NO P0001 trigger, so the content-immutability is service-level, like `fx_rate`).
- **Scope fences (load-bearing):** AST/import — the price module imports NO `calc`/`exposure`/`snapshot`/`convert` symbol and references NO pricing/valuation/return/factor/covariance/VaR/ES/scenario/**corporate-action/split/dividend/adjust** symbol; `ast.Mult` is NOT present (capture computes nothing — no `quantity × price`, no conversion). Nothing new imports `marketdata` beyond the P2-3 readers.
- **Migration:** `0019_price_point` applies (the FR table + symmetric RLS); `alembic check` drift-clean; downgrade `0019→0018→head` smoke. **Cross-slice fence flips (review fold — enumerate, don't say "any"):** remove `price_point` from the FOUR still-future "must not exist" lists — `test_transaction.py:276`, `test_position.py:134`, `test_valuation.py:132`, `test_reference_entities.py:634` — and **LEAVE `yield_curve`/`volatility_surface`/`credit_spread`/`holding`/benchmark in place** (still future). Update `test_synthetic.py`'s migration guard `0019→0020`. **Acceptance:** after `0019`, `grep price_point` across the test suite returns ZERO "must not exist" assertions.

## 20. Acceptance criteria
Captured vendor prices that are **fully reproducible on both axes** — the **REQ-PUB-001 "price reconstructable as-of" acceptance leg** (the staleness/QS-16 leg stays deferred) — governed (MARKET.PRICE_* audit + VENDOR lineage + fail-closed DQ), tenant-isolated (symmetric FORCE-RLS), and **compute nothing** (no pricing/valuation/return/factor/risk; no conversion; no adjustment); the FR protocol (create/supersede/correct/reconstruct) matches the `fx_rate`/`valuation` behavior; `make check` + PG green; **no `calculation_run`/`exposure_aggregate`/`dataset_snapshot` change.**

## 21. Risks
- **Scope creep into pricing/valuation/returns** → mitigated by the import/vocabulary scope-fence + the "captured-not-computed" + no-`ast.Mult` tests + the no-conversion rule.
- **Implied corporate-action adjustment** → mitigated by RAW-only (no `adjustment_basis`, no split/dividend symbol — fence-tested).
- **Multi-vendor key explosion** → bounded: `price_source` in the key is the only multiplicity beyond `fx_rate`; `venue`/`adjustment_basis` deferred.
- **Precision regret** (`Numeric(20,6)` vs vendor sub-cent) → OQ-P2-4-2; widening is an additive column-type change.
- **Storage** → AD-004-R1 (Postgres-first behind the market-data repo interface; Timescale deferred) — `price_point` is a time-series; high-volume intraday history is a future Timescale concern, not v1 EOD capture.

## 22. Open decisions — **ALL APPROVED at the recommended defaults (user sign-off 2026-06-27)**
- **OQ-P2-4-1 — APPROVED.** `price_source` **IS part of the key** — multiple vendor prices for the same instrument/date/type/currency may coexist.
- **OQ-P2-4-2 — APPROVED.** `price` value = **`Numeric(20,6)`**; widen later **only** if vendor requirements prove more precision is needed.
- **OQ-P2-4-3 — APPROVED.** **Defer `venue`/`exchange`** in the key — one trading venue per instrument in v1.
- **OQ-P2-4-4 — APPROVED.** **Defer staleness/completeness DQ** in v1 — P2-4 implements **required-field + positive-price** gates only (the staleness/QS-16 leg of REQ-PUB-001 stays deferred).
- **OQ-P2-4-5 — APPROVED.** v1 `price_type` vocabulary = **`{CLOSE, MID, NAV}`**; **BID/ASK deferred**.
- **OQ-P2-4-6 — APPROVED.** Snapshot integration is **readiness-only** — **do NOT mint `COMPONENT_KIND_PRICE` in P2-4**.

## 23. Controls impacted
Maps to **existing** CTRLs — **no new CTRL, no weakening**: **CTRL-006/013** (VENDOR `data_source` ORIGIN lineage; no bypass), **CTRL-017** (`price_point` declares `FULL_REPRODUCIBLE`; NOT append-only), **CTRL-011/023** (deny-by-default `marketdata.*` + symmetric FORCE-RLS + per-tenant vendor-license classification), **CTRL-026** (`MARKET.PRICE_*` hash chain), **CTRL-032** (fail-closed co-transactional rollback). A new price symmetric-RLS CI step. AD-004-R1 storage note applies. **CTRL-009/AD-014 UNTOUCHED** — P2-4 produces no governed derived number (price is captured input; the snapshot/run binding is readiness-only).

## 24. Documentation updates (in the P2-4 build commit; planning/governance markdown only)
Canonical (ENT-020 REALIZED); temporal §2A (`price_point` = FR); audit taxonomy (`MARKET.PRICE_*` activated at EVT-200); entitlement model (note `marketdata.*` reuse); lineage model (`VENDOR_PRICE` source-type); control matrix (P2-4 additions; the new RLS step); **RTM + backbone — REQ-PUB-001 Draft → In-Progress (partial)** (the as-of leg realized; the staleness/QS-16 leg deferred). This plan turn creates **only** the two P2-4 markdown docs.

## 25. Whether P2-4 is ready to implement
**Plan-ready, pending the user's calls on the §22 open decisions** (all with recommended defaults). The naming, temporal class, grain/key, `price_date`, `price_type` vocab, raw-only policy, currency/no-conversion, source/VENDOR-lineage/no-feed, the `instrument` FK, the snapshot **readiness-only** + **no `calculation_run`** stance, and the `marketdata.*`/`MARKET.PRICE_*`/`RANGE`-DQ/symmetric-RLS reuse are fixed against the ratified standards. Once §22 is confirmed, P2-4 is build-ready with no further design work.

## 26. Exact implementation kickoff prompt (when approved)
> "Begin P2-4 implementation only: captured price history (`price_point`, ENT-020), per `10_delivery_backlog/p2_4_price_history_implementation_plan.md` + `p2_4_decision_record.md`. Build EXACTLY: migration `0019_price_point` (the `price_point` FR table — `FullReproducibleMixin`, **NOT** append-only/no P0001 trigger; symmetric FORCE-RLS, closed-hybrid-set fence; `price` `Numeric(20,6)`; `instrument_id` NOT-NULL FK; 6-part current-head partial-unique `(tenant, instrument_id, price_date, price_type, currency_code, price_source) WHERE valid_to IS NULL AND system_to IS NULL`; `price_date` a separate immutable logical-key Date; `price_type` controlled-vocab `{CLOSE, MID, NAV}`); extend `irp_shared/marketdata` (the `PricePoint` model + the `capture_price`/`supersede_price`/`correct_price`/`reconstruct_price_as_of`/`resolve_price` binder reusing the `fx_rate` protocol verbatim — close-first, one-`now`, prior content never mutated; the required-field NOT_NULL + strictly-positive `RANGE` DQ gate via `run_quality_check`, Protocol untouched; `MARKET.PRICE_CREATE`/`PRICE_UPDATE`/`PRICE_CORRECTION` at EVT-200 to the FROZEN `record_event`; `ensure_vendor_source(VENDOR_PRICE)` + the per-physical-version ORIGIN edge; `resolve_instrument` + `resolve_currency` reused for the FK/currency gates); extend `api/marketdata.py` (`POST /prices`, `POST /prices/{id}/supersede`, `POST /prices/{id}/correct`, `GET /prices/as-of`, `GET /prices`); **reuse `marketdata.view`/`.ingest`** (entitlement/bootstrap.py UNCHANGED; the parity test extends). The §19 test matrix (FR create/supersede/correct + both-axes reconstruct + content-immutability; multi-vendor coexistence; DQ fail-closed + CTRL-032 rollback; `MARKET.PRICE_*` audit + verify_chain + no-emit-on-read; VENDOR `VENDOR_PRICE` ORIGIN lineage; the `instrument`/currency cross-tenant fail-closed; entitlement parity/403/404/409/422; PG FORCE-RLS + forged-tenant + closed-hybrid-set; the scope fences — no `calc`/`exposure`/`snapshot`/`convert`/pricing/valuation/return/factor/risk/corporate-action/split/dividend symbol, no `ast.Mult`; migration `0019` head/drift/downgrade; cross-slice fence flips incl. `price_point` removal from still-future lists + `test_synthetic` `0019→0020`). Governance-doc updates per §24. STRICT EXCLUSIONS: NO pricing/valuation/return/factor/covariance/VaR/ES/stress/scenario/risk; NO FX conversion; NO corporate-action adjustment engine; NO exposure/`calculation_run`/`dataset_snapshot`/`fx_rate` change; NO `COMPONENT_KIND_PRICE` (readiness only); NO curve/benchmark/feed-pipeline; NO reporting/dashboard/frontend; NO P2-5+/P3+; NO `audit/service.py` change; NO BYPASSRLS; NO hybrid. 8-lens UltraCode review; `make check` + PG green. Do not commit until I approve."

---

## 26b. UltraCode 8-lens adversarial review log
**8 lenses — verdicts: 4 `approve` + 4 `approve_with_changes`; 0 `block`. 4 in-scope findings folded** into §1/§2/§3/§19/§20/§24 + the decision record (Part 3 / OD-P2-4-C):
1. **REQ-PUB-001 (product):** `price_point` is the named realizing entity of **REQ-PUB-001** ("Market prices (time-series)") — not a generic prerequisite; P2-4 **advances it to In-Progress (partial)** (as-of leg realized; staleness/QS-16 leg deferred) — corrected the over-claimed "no REQ status changes" [§1/§2/§20/§24].
2. **NULL key (lineage-dq):** the promoted key columns `price_type`/`currency_code`/`price_source` are DB-level **`NOT NULL`** [§3].
3. **Fence enumeration (qa):** the four `price_point` "must not exist" lists enumerated + the post-`0019` zero-assertion grep acceptance [§19].

Scope / Security-RLS / Audit-Controls lenses returned `approve` (captured-not-computed; no pricing/return/factor/risk; readiness-only snapshot + no `calculation_run`; symmetric-never-hybrid; `MARKET.PRICE_*` reuse + `audit/service.py` frozen).
