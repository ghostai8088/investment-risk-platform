# P2-4 Decision Record — Captured Price History (`price_point`, ENT-020)

## Document Control

| Field | Value |
|---|---|
| Purpose | Settle the open P2-4 decisions **before any implementation**, so the build plan (`p2_4_price_history_implementation_plan.md`) runs against a fixed contract. P2-4 is the **second market-data entity** — **captured security/vendor price history** — joining the `irp_shared/marketdata` package additively (the P2-2 `fx_rate` protocol precedent). **Captured market data, NOT a pricing model.** |
| Status | **Decision record — PLANNING ONLY; NO code, NO migrations, NO P2-4 implementation.** |
| HEAD at writing | `0b12d85` (P2-3 closeout memory; P2-1 `dataset_snapshot` `3629baa` + P2-2 `fx_rate` `c257e5c` + P2-3 `exposure_aggregate` `da178fc` all CI-green). origin/main clean. migration head `0018_exposure_aggregate`. |
| Predecessors | `p2_0_decision_record.md` (the reproducibility-first subphase sequencing; AD-004-R1 Postgres-first; OD-014 resolved). `p2_2_fx_rate_implementation_plan.md` (the captured-market-data **FR protocol** + `marketdata` package + `MARKET.*`/VENDOR-lineage/`RANGE`-DQ that P2-4 mirrors). `p2_3_*` (the snapshot `COMPONENT_KIND_*` extension pattern P2-4 stays a *reader* of). |
| Canonical | `price_point` = **ENT-020** ("Time-series prices", Market Data BC-02). |
| Decisions | **OD-P2-4-A … OD-P2-4-L (12).** Specific-decision crosswalk below. |
| Review | 8-lens UltraCode adversarial review — **Part 5** (filled after the review workflow). |
| Governance | Decisions recorded here; the R-07 mint (`MARKET.PRICE_*` at EVT-200; `VENDOR_PRICE` source; reuse `marketdata.*`) is folded into the P2-4 implementation build (the P1B-1/P2-2/P2-3 precedent). |

> **Specific-decision → OD crosswalk:** (1 naming)→A · (2 temporal)→B · (3 grain)→C · (4 price_date)→D · (5 price_type)→E · (6 adjusted/raw)→F · (7 currency)→G · (8 source)→H · (9 snapshot)→J · (10 entitlement)→L · (11 DQ)→L · (12 audit)→L · (instrument)→I · (calculation_run)→K.

> **Grounding (verified against shipped HEAD `0b12d85`).** `marketdata/models.py` — `FxRate(PrimaryKeyMixin, TenantMixin, FullReproducibleMixin, TimestampMixin)`, `FULL_REPRODUCIBLE`, **NOT** in `APPEND_ONLY_TABLES` (FR close-out UPDATEs; content-immutability service-enforced); `rate` `Numeric(28,12)`; 5-part current-head partial-unique `(tenant, base, quote, rate_date, rate_type) WHERE valid_to IS NULL AND system_to IS NULL`; `rate_date` a separate immutable logical-key `Date`; `rate_type` controlled-vocab String (MID only); `rate_source` an **inert** label. `marketdata/service.py` — `capture_fx_rate` / `supersede_fx_rate` (effective-dated, close-first, one-`now`) / `correct_fx_rate` (as-known restatement) / `reconstruct_fx_rate_as_of` (bitemporal read) + the `_run_fx_dq_gate` (required-field NOT_NULL + strictly-positive `RANGE`, fail-closed → CTRL-032). `marketdata/events.py` — `MARKET.FX_CREATE/UPDATE/CORRECTION` (EVT-200; caller-side to the FROZEN `record_event`) + `ensure_vendor_source` (`VENDOR_FX` `data_source`) + the per-physical-version ORIGIN edge. `reference/instrument.py` — `resolve_instrument(session, id, *, acting_tenant)` (tenant-predicated; `InstrumentNotVisible` cross-tenant fail-closed) — the `corporate_action` FK precedent. `dq/rules.py` — `RULE_TYPE_RANGE` (the strictly-positive evaluator). `entitlement/bootstrap.py` — `marketdata.view` / `marketdata.ingest` (REUSABLE across all market data; `data_steward` maker; risk tiers `.view`; `auditor_3l` excluded). `audit_event_taxonomy.md` — the `MARKET` row: "Price/curve/benchmark join this block additively (P2-4/5/6)." AD-004-R1 / OD-014 — Postgres-first behind the market-data repo interface for ENT-020…025; Timescale deferred. |

---

## Part 1 — Decisions at a glance

| ID | Decision | Resolution |
|---|---|---|
| **OD-P2-4-A** | entity naming | **`price_point`** (ENT-020) — align with the canonical model ("Time-series prices"). NOT `price`/`market_price`/`instrument_price`. |
| **OD-P2-4-B** | temporal class | **FR / fully-reproducible / bitemporal** (`FullReproducibleMixin`; `FULL_REPRODUCIBLE`; **NOT append-only** — close-out UPDATEs; content-immutability service-enforced + tested) — the `fx_rate`/`valuation` protocol verbatim. |
| **OD-P2-4-C** | grain (logical key, v1) | **`(tenant_id, instrument_id, price_date, price_type, currency_code, price_source)`** — a 6-part current-head partial-unique `WHERE valid_to IS NULL AND system_to IS NULL`. **`price_source` IS in the key** (multi-vendor prices for the same instrument/date/type coexist — the realistic price need, unlike single-quote FX MID). `venue`/`exchange` + `adjustment_basis` **deferred** (OQ-P2-4-1/3). |
| **OD-P2-4-D** | `price_date` convention | a **separate immutable logical-key `Date`** (the `valuation_date`/`rate_date` precedent) — the business date the price is FOR; carried forward verbatim by supersede/correct, **never mutated**, DISTINCT from the FR `valid_from` axis. |
| **OD-P2-4-E** | `price_type` vocabulary (v1) | controlled-vocab plain String — **`{CLOSE, MID, NAV}`** v1 (single-representative prices: CLOSE for exchange-traded, MID for OTC/quote midpoint, NAV for funds). **`BID`/`ASK` reserved** (paired quotes need a quote model). Additive vocab. |
| **OD-P2-4-F** | adjusted vs raw | **RAW vendor prices ONLY in v1** — **NO `adjustment_basis` column, NO corporate-action adjustment engine, NO implied adjustment calculation.** An ADJUSTED price (if ever) is a **future CAPTURED value the vendor supplies** (never computed by the platform), added by a later additive slice (which would add `adjustment_basis` to the key). |
| **OD-P2-4-G** | currency | **captured `currency_code`** (an ISO String(3), **in the key** — a dual-listed security may be priced in >1 currency). **NO conversion in P2-4** (FX conversion happens in a *later* calculation via the P2-2 `convert` helper, never here). `price` value `Numeric(20,6)` (the `valuation.mark_value` money scale; OQ-P2-4-2). |
| **OD-P2-4-H** | source / provenance | **`price_source`** a controlled-vocab String label (the `rate_source` shape — BUT a **key** component, not inert) + a **VENDOR `data_source` ORIGIN lineage edge** per new physical version (`ensure_vendor_source`, a new `VENDOR_PRICE` source). **NO market-data feed-ingestion pipeline** (capture via the governed binder, the `fx_rate` precedent). |
| **OD-P2-4-I** | relationship to `instrument` | `instrument_id` **NOT-NULL FK** to the P1B-3 `instrument` head; resolved via the **reused `resolve_instrument`** (tenant-predicated; cross-tenant/unknown → `InstrumentNotVisible`, fail-closed pre-write) — the `corporate_action` precedent. PROPRIETARY/symmetric (NOT the currency hybrid resolver). |
| **OD-P2-4-J** | relationship to `dataset_snapshot` | **READINESS ONLY** in P2-4 — **NO `COMPONENT_KIND_PRICE` minted, NO `build_snapshot` change**; price components are pinned **LATER**, when a calculation consumes prices (the P2-3 `COMPONENT_KIND_FX` precedent — minted only when exposure needed it). **NO `dataset_snapshot` schema redesign.** |
| **OD-P2-4-K** | relationship to `calculation_run` | **NONE in P2-4** — captured price data wires no run; **NO `calculation_run` change, NO `exposure_aggregate` change.** Binding a price into a run is a future *calculation* slice (P3+ / a later derived number), not P2-4. |
| **OD-P2-4-L** | entitlement + audit + DQ + RLS + module | **Reuse `marketdata.view`/`.ingest`** (the market-data family; no new permission). **Reuse `MARKET.*`** — mint `MARKET.PRICE_CREATE`/`PRICE_UPDATE`/`PRICE_CORRECTION` at the EVT-200 block (caller-side; `audit/service.py` FROZEN). DQ: **required-field NOT_NULL + strictly-positive `RANGE`** (reuse the P2-2 evaluators; `(params, dataset)` Protocol UNTOUCHED); optional staleness/completeness = caller-side gates, **deferred** (OQ-P2-4-4). **Symmetric tenant-scoped RLS** (NEVER hybrid). Module: **extend `irp_shared/marketdata`** (price joins `fx_rate`; no new package). |

---

## Part 2 — Decision detail

### OD-P2-4-A — entity naming → **`price_point` (ENT-020)**
The canonical model already names **ENT-020 `price_point`** ("Time-series prices"). Use it verbatim — `price`/`market_price`/`instrument_price` would mint a non-canonical synonym. (`yield_curve` ENT-021, `volatility_surface` ENT-022, `credit_spread` ENT-023 stay future; P2-4 realizes ENT-020 only.)

### OD-P2-4-B — temporal class → **FR / bitemporal (NOT append-only)**
`price_point` is **captured vendor market data**, exactly the `fx_rate` (ENT-024) kind. It reuses the shipped FR protocol **verbatim**: `FullReproducibleMixin` (`valid_from`/`valid_to` + `system_from`/`system_to`); `__temporal_class__ = FULL_REPRODUCIBLE`; **NOT** in `APPEND_ONLY_TABLES` (no `irp_prevent_mutation` trigger, no ORM guard — the FR protocol requires close-out UPDATEs; prior-version **content** immutability is service-enforced + tested). Capture → effective-dated supersede (a re-quote for the same key) → as-known correction (a vendor restatement). **NOT IA** (a price is effective-dated/superseded), **NOT EV** (it needs both axes for reproducibility — TR-21).

### OD-P2-4-C — grain (logical key, v1) → `(tenant, instrument_id, price_date, price_type, currency_code, price_source)`
**Decision.** The v1 current-head partial-unique is **`(tenant_id, instrument_id, price_date, price_type, currency_code, price_source) WHERE valid_to IS NULL AND system_to IS NULL`** — exactly one open price per that 6-tuple; the FR axes version the *price* for a fixed logical key. **`price_source` IS a key component** (the deliberate departure from `fx_rate`, where `rate_source` is inert): multiple vendors commonly publish a price for the same `(instrument, date, type, currency)` and a platform keeps them all (comparison/fallback) — unlike a single authoritative FX MID. **The promoted key columns `price_type` / `currency_code` / `price_source` are DB-level `NOT NULL`** (review fold — lineage-dq #3; unlike the inert *nullable* `rate_source`), so a NULL key component cannot defeat the current-head partial-unique on PG; the service-layer required-field NOT_NULL DQ gate is the additional fail-closed check. `venue`/`exchange` (intra-day / multi-listing granularity) and `adjustment_basis` (OD-P2-4-F) are **deferred** — each is an additive future key extension, not v1. (See **OQ-P2-4-1** for the source-in-key vs source-inert alternative.)

### OD-P2-4-D — `price_date` convention → a separate immutable logical key
`price_date` is a **separate immutable logical-key `Date`** — the business date the price is FOR — carried forward verbatim by supersede/correct, **never mutated**, DISTINCT from the FR `valid_from` axis (the `valuation_date`/`rate_date` precedent). (If `price_date` were `valid_from`, a supersede's new valid period would change the date the price is "for" — breaking the semantics; hence a separate key, as for `valuation`/`fx_rate`.) Many `price_date`s per `(instrument, type, currency, source)` coexist as separate open heads.

### OD-P2-4-E — `price_type` vocabulary (v1) → `{CLOSE, MID, NAV}`
A controlled-vocab plain String (no enum/CHECK; app-side allow-list — the `rate_type` shape). v1 admits **CLOSE** (the end-of-day exchange close — the primary equity/bond price), **MID** (the quoted midpoint for OTC/quote-driven instruments), and **NAV** (the fund net-asset-value). All three are **single representative prices**. **BID/ASK are reserved** (a bid/ask is a *paired* quote — it needs a two-sided quote model, out of scope; an out-of-vocab `price_type` → `PriceValueError` 422). (See **OQ-P2-4-5** to trim to `{CLOSE}` if a stricter v1 is preferred.)

### OD-P2-4-F — adjusted vs raw → **RAW only; no adjustment engine**
**Decision.** v1 captures **RAW vendor prices ONLY.** There is **NO `adjustment_basis` column, NO corporate-action adjustment engine, NO split/dividend back-adjustment, NO implied adjustment calculation** — the platform stores exactly what the vendor supplies. An ADJUSTED price, if ever needed, is a **future captured value the vendor itself supplies** (the platform never *computes* the adjustment — that would be the deferred corporate-action engine), added by a later additive slice that introduces `adjustment_basis` as a key component. A scope-fence test forbids any corporate-action/split/dividend symbol in the price module. This guarantees "no implied adjustment."

### OD-P2-4-G — currency → captured, no conversion; money scale
**Decision.** Each price carries a **captured `currency_code`** (ISO alpha-3 String(3)), validated via the hybrid-aware `resolve_currency` (own OR SYSTEM — the `fx_rate` currency-validation precedent), and **in the logical key** (a dual-listed security priced in USD and EUR is two open heads). **NO FX conversion in P2-4** — `price_point` stores the price in its native currency; converting a price to a base currency is a *later calculation* (via the P2-2 `convert` helper), never in the capture path. The `price` value is **`Numeric(20,6)`** — the `valuation.mark_value`/`cost_basis` money scale (a price IS a per-unit money value of the same kind as a mark). (See **OQ-P2-4-2** on widening to `Numeric(28,12)` if sub-6dp vendor precision must be preserved.)

### OD-P2-4-H — source / provenance → label-in-key + VENDOR lineage; no feed pipeline
**Decision.** `price_source` is a **controlled-vocab String label** (e.g. `"BLOOMBERG"`, `"REFINITIV"`, `"EXCHANGE"`) — a **key** component (OD-P2-4-C), so multi-vendor prices coexist. The **governed provenance** is a **VENDOR `data_source` ORIGIN lineage edge** per new physical version, via a new `ensure_vendor_source(VENDOR_PRICE)` (the `VENDOR_FX` precedent; REUSES `record_lineage` UNCHANGED — no new lineage framework). **NO market-data feed-ingestion pipeline / connector / scheduler** — captures arrive via the governed binder (the `fx_rate` precedent), one governed write at a time.

### OD-P2-4-I — relationship to `instrument`
`instrument_id` is a **NOT-NULL FK** to the P1B-3 `instrument` head, resolved via the **reused `resolve_instrument`** (tenant-predicated; cross-tenant/unknown → `InstrumentNotVisible`, fail-closed **before any write**) — the `corporate_action` precedent. `instrument` is PROPRIETARY/symmetric, so the resolver is the symmetric `tenant_id == acting_tenant` by-id form (NOT the hybrid currency resolver). The RLS `WITH CHECK` gates only the row's own `tenant_id` (the P1B-3 rls-1 lesson — the service-layer predicate is the cross-tenant gate).

### OD-P2-4-J — relationship to `dataset_snapshot` → readiness only
**Decision.** P2-4 makes `price_point` **available** to the reproducibility machinery but **pins nothing**: **NO `COMPONENT_KIND_PRICE` minted, NO `build_snapshot`/`_reresolve_content` change, NO `fx_content`-style serializer.** This mirrors P2-1→P2-3 exactly: `COMPONENT_KIND_FX` was minted **only at P2-3**, when the exposure run needed to pin FX — not at P2-2 when `fx_rate` was captured. A price component is pinned **only** when a future calculation consumes prices (a later derived-number slice). **NO `dataset_snapshot` schema redesign.** (See **OQ-P2-4-6** to confirm readiness-only vs pin-now.)

### OD-P2-4-K — relationship to `calculation_run` → none
**Decision.** P2-4 wires **no** `calculation_run` and changes **no** `exposure_aggregate` — captured price data is an input, not a run. Binding a price into a run (e.g. a price-based valuation or a factor input) is a **future calculation** (P3+ / a later derived-number slice), explicitly out of P2-4. The `calc`/`exposure` packages are **untouched**.

### OD-P2-4-L — entitlement + audit + DQ + RLS + module
**Decision.**
- **Module** — **extend `irp_shared/marketdata`** (the shared market-data home; `price_point` joins `fx_rate`). New `marketdata/price.py` (model `PricePoint` + the binder) or fold into `models.py`/`service.py`/`events.py`; the package's leaf one-way imports `{reference, lineage, dq, audit, db}` are unchanged.
- **Entitlement** — **reuse `marketdata.view` / `marketdata.ingest`** (REUSABLE across all market data — minted P2-2 exactly for this). `.ingest` gates capture/supersede/correct; `.view` gates reads. **No new permission**; the existing parity test extends. `auditor_3l` stays excluded (vendor-license isolation by RLS, not a role).
- **Audit** — **reuse the `MARKET.*` category**: mint **`MARKET.PRICE_CREATE` / `MARKET.PRICE_UPDATE` / `MARKET.PRICE_CORRECTION`** at the EVT-200 block (caller-side constants in `marketdata/events.py` to the FROZEN `record_event`; per-op grain capture=1, supersede=2, correct=2; DC-2 metadata only — `instrument_id`/`price_date`/`price_type`/`currency_code`/`price_source`, never a vendor-licensed payload dump; zero on read). **`audit/service.py` FROZEN.**
- **DQ** — a governed fail-closed gate reusing `run_quality_check`/`DATA.VALIDATE`: **required-field NOT_NULL** (`instrument_id`/`price_date`/`price`/`price_type`/`currency_code`/`price_source`) + **strictly-positive `RANGE`** on `price` (`{min:0, min_inclusive:false}` — the shipped P2-2 evaluator). The `(params, dataset)` **Protocol is UNTOUCHED** (caller-side gate, the P2-1/P2-2 pattern). Optional **staleness / completeness** caller-side gates are **deferred** (OQ-P2-4-4).
- **RLS** — **symmetric tenant-scoped** (`USING == WITH CHECK == own-tenant`, ENABLE+FORCE; the new migration); **NEVER hybrid** (per-tenant vendor-licensed price data, MNPI-adjacent — a shared-global price set would be an AD-013-R2 event); the **closed 5-table hybrid set asserted unchanged**; no BYPASSRLS.

---

## Part 3 — Governance amendments (folded into the P2-4 build, R-07)
Recorded; realized in the P2-4 implementation commit (the P1B-1/P2-2/P2-3 precedent — not a separate ratification turn):
- **Canonical model** — annotate **ENT-020 `price_point`** REALIZED (FR; the grain/key + scale above); assert §4 common-column + §2A FR conformance; note `yield_curve`/`volatility_surface`/`credit_spread` stay future.
- **Temporal standard §2A** — `price_point` = FR (captured market data; NOT append-only) — the `fx_rate`/`valuation` row.
- **Audit taxonomy (R-07)** — extend the `MARKET` row: **`MARKET.PRICE_CREATE`/`PRICE_UPDATE`/`PRICE_CORRECTION` ACTIVATED** at EVT-200 (the second `MARKET.*` member after FX).
- **Entitlement model** — note `price_point` **reuses** `marketdata.view`/`.ingest` (no new code; the reusable-market-data verb realized as intended).
- **Lineage model** — a new `VENDOR_PRICE` `data_source` source-type (the `VENDOR_FX` sibling); reuses `record_lineage`.
- **Control matrix** — `price_point` maps to the **existing** CTRLs (006/013 lineage; 011/023 deny-by-default + symmetric RLS + classification; 017 FR temporal-class declared; 026 `MARKET.*` chain; 032 fail-closed rollback). **No new CTRL; none weakened.** AD-004-R1 storage note (Postgres-first; Timescale deferred) applies.
- **RTM** — **REQ-PUB-001** ("Market prices (time-series)", CAP-3.1 — its realizing entity IS **`price_point` (FR)**, `requirements_backbone.md`) **advances to In-Progress (partial)** (review fold — product #1/#2): P2-4 realizes `price_point` + the **"price reconstructable as-of"** acceptance leg; the **"stale flagged (QS-16)" leg is DEFERRED** (OQ-P2-4-4 staleness — tracked, not dropped). The REQ does **NOT close** (the staleness conjunct stays open). (REQ-PPM-004 is **NOT** a `price_point` REQ — it only *consumes* a converted price as a future **calculation** input.)

---

## Part 4 — Open questions — **ALL APPROVED at the recommended defaults (user sign-off 2026-06-27)**
- **OQ-P2-4-1 — APPROVED.** `price_source` **IS part of the logical key** — multiple vendor prices for the same `(instrument, date, type, currency)` coexist (NOT the `fx_rate` single-source model).
- **OQ-P2-4-2 — APPROVED.** `price` = **`Numeric(20,6)`** (the `valuation.mark_value` money scale); widen later **only** if vendor requirements prove more precision is needed.
- **OQ-P2-4-3 — APPROVED.** **Defer `venue`/`exchange`** in the key — one trading venue per instrument in v1.
- **OQ-P2-4-4 — APPROVED.** **Defer staleness/completeness DQ** in v1 — P2-4 implements **required-field + positive-price** gates only (the staleness/QS-16 leg of REQ-PUB-001 stays deferred).
- **OQ-P2-4-5 — APPROVED.** v1 `price_type` = **`{CLOSE, MID, NAV}`**; **BID/ASK deferred**.
- **OQ-P2-4-6 — APPROVED.** Snapshot integration is **readiness only** — **do NOT mint `COMPONENT_KIND_PRICE` in P2-4** (pin it when a future calc consumes prices).

---

## Part 5 — UltraCode 8-lens adversarial review log
**8 lenses (Product, Chief-Architect, Data-Architecture, Security/RLS, Audit/Controls, Lineage/DQ, QA, Scope) — verdicts: 4 `approve` + 4 `approve_with_changes`; 0 `block`. 4 findings verified REAL + in-scope; all folded** into Part 3 / OD-P2-4-C + the plan. The folds:
- **REQ-PUB-001 traceability (product #1/#2):** I copied the `fx_rate` "no REQ named" template, but `price_point` is the **direct named realizing entity of REQ-PUB-001** ("Market prices (time-series)", CAP-3.1; `requirements_backbone.md`). **Fold (Part 3 + plan §1/§2/§20/§24):** name REQ-PUB-001; P2-4 **advances it to In-Progress (partial)** (the "price reconstructable as-of" leg realized; the "stale flagged / QS-16" leg deferred, OQ-P2-4-4) — it does NOT close; correct the over-claimed "no REQ status changes." (`fx_rate` was correctly "no REQ named" because no REQ-PUB row names it — it's only an *input* to REQ-PPM-004.)
- **NULL key component (lineage-dq #3):** `price_source` (+ `price_type`/`currency_code`) are promoted into the partial-unique; **Fold (OD-P2-4-C + plan §3):** they are DB-level **`NOT NULL`** (unlike the inert nullable `rate_source`), so a NULL key cannot defeat the current-head uniqueness on PG.
- **Cross-slice fence enumeration (qa #4):** `price_point` sits in FOUR "must not exist" lists; **Fold (plan §19):** enumerate `test_transaction.py:276` / `test_position.py:134` / `test_valuation.py:132` / `test_reference_entities.py:634` (leave `yield_curve`/`holding`/benchmark), + the `0019→0020` synthetic guard + a post-`0019` zero-`price_point`-assertion grep acceptance.

The Security/RLS, Audit/Controls, and Scope lenses returned `approve` (symmetric-never-hybrid correct; `MARKET.PRICE_*` reuse + `audit/service.py` frozen confirmed; no pricing/return/factor/risk pulled forward; readiness-only snapshot + no `calculation_run` confirmed). Lower-severity LOW/INFO notes were confirmations or non-material.

---

## Part 6 — P2-4 readiness gate
P2-4 is **plan-ready** once this record is approved: the naming (`price_point`/ENT-020), temporal class (FR, NOT append-only), grain/key (`(instrument, price_date, price_type, currency, source)`), `price_date` (separate immutable logical key), `price_type` vocab (`{CLOSE, MID, NAV}`), raw-only policy (no adjustment engine), currency (captured, no conversion, money scale), source (label-in-key + VENDOR lineage; no feed pipeline), the `instrument` FK, the snapshot **readiness-only** + **no `calculation_run`** stance, and the `marketdata.*`/`MARKET.PRICE_*`/`RANGE`-DQ/symmetric-RLS reuse are all fixed. The detailed build plan is `p2_4_price_history_implementation_plan.md`.
