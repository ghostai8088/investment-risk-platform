# P3-2 Implementation Plan — Factor-Return Input Foundation (captured/vendor)

## Document Control

| Field | Value |
|---|---|
| Purpose | The build contract for P3-2: a governed **captured factor-return input** substrate — a `factor` (EV definition) + `factor_return` (FR series) — mirroring the `fx_rate`/`curve`/`benchmark` captured-market-data slices. Companion to `p3_2_decision_record.md` (OD-P3-2-A…O). |
| Status | **Implementation PLAN — PLANNING ONLY; NO code, NO migrations, NO implementation.** |
| Connectivity | **DEGRADED-CONNECTIVITY MODE (2026-07-02).** P3-1 commit `e8e2e59` is LOCAL, PUSH-PENDING, NOT remote-CI-green (safety bundle `/tmp/irp_p3_1_e8e2e59.bundle`). This plan is LOCAL-PENDING. **Implementation is gated on GitHub push/CI being restored** (P3-1 must push + go CI-green first). |
| HEAD at writing | `e8e2e59` (local); origin/main `1a8b2a4`; ahead 1 / behind 0; clean. migration head `0022_sensitivity` (local). |
| Predecessors | `p3_2_decision_record.md`; `p3_0_decision_record.md`; the captured-market-data slices `fx_rate`/`curve`/`benchmark` (the verbatim pattern). |
| Review | 8-lens UltraCode review — **Part 9**. |

> **What P3-2 is — and is NOT.** P3-2 captures a **governed factor-return INPUT** (a vendor time series + its factor definition), reproducible-by-capture (FR bitemporal), audited, lineaged, DQ-gated, tenant-isolated — exactly like FX/curve/benchmark. It **computes no number, binds no `calculation_run`, binds no `model_version`, pins no snapshot**. It is the input the P3-3 factor-exposure engine will later consume. **This plan builds NOTHING** — it is the contract; implementation is a separately-approved slice, gated on connectivity. **NO factor exposure / covariance / VaR / ES / stress / scenario / attribution / benchmark-relative; NO computed returns; NO adjusted-price engine; NO `audit/service.py` change; NO snapshot/run/model_version control weakening.**

---

## Part 1 — Module map (when implementation is approved + connectivity is restored)

| Area | Change | New/Modified |
|---|---|---|
| `packages/shared-python/src/irp_shared/marketdata/factor.py` | the capture binder — `capture_factor` / `update_factor` / `resolve_factor` / `list_factors` (EV definition) + `capture_factor_return` / `supersede_factor_return` / `correct_factor_return` / `reconstruct_factor_return_as_of` / `list_factor_returns` (FR series) — mirroring `benchmark.py` | NEW |
| `…/marketdata/models.py` | `Factor` (EV) + `FactorReturn` (FR) classes + constants (`RETURN_TYPE_SIMPLE`, `FREQUENCY_DAILY`, `FACTOR_TYPE_*`) | MODIFIED |
| `…/marketdata/events.py` (or `factor` events) | `MARKET.FACTOR_RETURN_CREATE/_UPDATE/_CORRECTION` (series) + `REFERENCE.*` reuse (definition) constants; `VENDOR_FACTOR` source; `FactorActor` | MODIFIED |
| `…/models.py` (metadata aggregator) | import `Factor`, `FactorReturn` | MODIFIED |
| `migrations/versions/0023_factor_return.py` | `factor` (EV) + `factor_return` (FR) tables; symmetric RLS; **NEITHER append-only** (FR close-out-updated); head `0022`→`0023` | NEW |
| `apps/backend/src/irp_backend/api/marketdata.py` | a `factor_router` (capture/supersede/correct/reconstruct/list) — the `benchmark_router` shape; gated `marketdata.ingest` (writes) / `marketdata.view` (reads) | MODIFIED |
| governance docs | R-07: canonical (mint `factor` id + realize ENT-025), audit taxonomy, entitlement note, control matrix, RTM, temporal standard | MODIFIED |
| tests | shared + PG + endpoint (Part 7) | NEW |

**Untouched (hard):** `audit/service.py` (FROZEN); `calc`/`model`/`risk`/`snapshot` (P3-2 is an input — no run/model/snapshot binding); the DQ `Protocol`; no BYPASSRLS; no hybrid path.

---

## Part 2 — Entity design

### `factor` (EV definition — net-new canonical id; the `benchmark` header precedent)
`EffectiveDatedMixin` + `record_version`. Columns: `factor_code` (String, immutable logical-key part), `factor_source` (String — vendor; logical-key part), `factor_family` (String — e.g. `STYLE`/`INDUSTRY`/`COUNTRY`/`MACRO`), `factor_type` (String — controlled vocab), `region` / `currency_code` / `asset_class` (scope), `frequency` (String — `DAILY` v1), `description`. **Identity key** `(tenant, factor_code, factor_source)` (the `benchmark` `(tenant, benchmark_code, benchmark_source)` precedent). EV: an amend bumps `record_version`; `REFERENCE.*` audited. Symmetric RLS.

### `factor_return` (FR series — ENT-025; the `fx_rate`/`benchmark_constituent` precedent)
`FullReproducibleMixin` (bitemporal `valid_from`/`valid_to` + `system_from`/`system_to`) + `record_version` + `restatement_reason` + `supersedes_id`. Columns: `factor_id` (NOT-NULL FK → `factor.id`, indexed), `return_date` (Date — separate immutable logical key), `return_type` (String — `SIMPLE` v1), `return_value` (`Numeric(20,12)` — decimal fraction). **Current-head partial-unique** `(tenant, factor_id, return_date, return_type) WHERE valid_to IS NULL AND system_to IS NULL`. **NOT append-only** (FR close-out-UPDATEs `valid_to`/`system_to`; prior-version content is service-immutable — the `curve`/`benchmark_constituent` precedent, NO P0001 trigger). Symmetric RLS.

---

## Part 3 — Capture binder (mirrors `benchmark.py` / `fx_rate` — captured, never computed)
- **`capture_factor` / `update_factor`** (EV): first-open / amend the definition; `REFERENCE.CREATE`/`REFERENCE.UPDATE` audit; `VENDOR_FACTOR` ORIGIN lineage; validate `factor_type`/`frequency`/scope vocab pre-write (→ 422).
- **`capture_factor_return`** (FR): first-open a `(factor, return_date, return_type)` return; `MARKET.FACTOR_RETURN_CREATE`; DQ gate (finite, `> -1`, in-vocab) fail-closed; ORIGIN lineage.
- **`supersede_factor_return`** (effective-dated re-capture) / **`correct_factor_return`** (as-known restatement, `restatement_reason` TR-08): close-first the prior head (`valid_to`/`system_to`), insert the new version; `MARKET.FACTOR_RETURN_UPDATE` (close-out) + `_CREATE`/`_CORRECTION`. Prior content NEVER mutated.
- **`reconstruct_factor_return_as_of(factor, return_date, valid_at, known_at)`** — bitemporal read (the `reconstruct_fx_rate_as_of`/`reconstruct_curve_as_of` precedent); returns the version true-at/known-at → **reproducibility-by-capture**. `resolve_factor`/`list_factor_returns` fail-closed tenant-predicated.
- **NO return arithmetic** — values captured verbatim (the "captured, never computed" scope fence; no `Mult` on returns, no price read, no regression).

---

## Part 4 — Audit / entitlement / RLS / lineage / DQ
- **Audit (OD-P3-2-J):** `factor` def → `REFERENCE.CREATE`/`UPDATE`; `factor_return` series → `MARKET.FACTOR_RETURN_CREATE`/`_UPDATE`/`_CORRECTION` (EVT-200; per-op capture=1/supersede=2/correct=2; DC-2 metadata `factor_code/source/return_date/return_type` — **never a vendor payload**; no event on read). `audit/service.py` FROZEN.
- **Entitlement (OD-P3-2-K):** reuse `marketdata.view` (reads) / `marketdata.ingest` (writes); no new permission; `auditor_3l` excluded (captured proprietary input SoD).
- **RLS (OD-P3-2-L):** symmetric tenant-scoped ENABLE+FORCE on `factor` + `factor_return`; NEVER hybrid; cross-tenant fail-closed; closed hybrid set unchanged.
- **Lineage (OD-P3-2-L):** a `VENDOR_FACTOR` `data_source` → `factor`/`factor_return` ORIGIN edge (`record_lineage` reused unchanged).
- **DQ (OD-P3-2-M):** fail-closed at capture — required fields (NOT_NULL); `return_type` ∈ vocab (ALLOWED_VALUES); `frequency` consistent; economic-sanity `return_value > -1` (RANGE); missing-data flagged (never filled); outlier flagged (never auto-corrected). **Finiteness:** a **binder-side pre-write guard** `Decimal.is_finite()` → `FactorValueError` (422) BEFORE the DQ gate (the `fx_rate._validate_pair` precedent — the min-only `> -1` RANGE does NOT reject `+Infinity`, so it is guarded caller-side). Reuses the shipped NOT_NULL/ALLOWED_VALUES/RANGE evaluators; Protocol untouched.

---

## Part 5 — Reproducibility, snapshot, run, model_version
- **No `calculation_run`, no `model_version`, no snapshot pin** (OD-P3-2-G/H/I) — a captured input. Reproducibility is **by-capture** (FR bitemporal reconstruct), the `fx`/`curve`/`benchmark` model.
- `COMPONENT_KIND_FACTOR_RETURN` **reserved (readiness-note only)** — minted when P3-3/P3-4 pins factor returns into a run's snapshot.

---

## Part 6 — Data-history + input-dependency register (OD-P3-2-N)
| Item | P3-2 status |
|---|---|
| History depth (3y/5y/10y/15–20y targets) | Additive; **no depth limit**; **not load-bearing for capture** (load-bearing at P3-4 covariance) |
| Adjusted/total-return prices (P2-4 RAW) | **Not required** — captured vendor returns are supplied externally; the gap bites only *computed* returns (deferred) |
| `benchmark_level`/`benchmark_return` | **Not required** — factor returns are a separate vendor input |
| `volatility_surface` / `rating` | Not required (unrelated) |

---

## Part 7 — Tests
1. **EV definition:** capture/amend `factor`; `record_version` bump; `REFERENCE.*` audit; vocab validation (422).
2. **FR series:** capture/supersede/correct `factor_return`; bitemporal `reconstruct_as_of` (as-known stability); current-head partial-unique; `MARKET.FACTOR_RETURN_*` per-op grain; **prior content immutable** after correction.
3. **Reproducibility-by-capture:** a vendor correction after a read doesn't change the as-of-known earlier read.
4. **DQ fail-closed:** out-of-vocab / `return_value ≤ -1` / missing required field → rejected at capture (zero row). **Finiteness:** `+Infinity` AND `NaN` `return_value` are BOTH rejected (zero row) — asserting the binder-side `Decimal.is_finite()` guard catches `+Infinity` (which the min-only `> -1` RANGE would otherwise admit).
5. **RLS (PG):** cross-tenant invisibility; no-context zero rows; symmetric + FORCE; **NEITHER table append-only** (a current-head close-out UPDATE succeeds — no P0001 trigger; the `benchmark_constituent` precedent).
6. **Lineage:** `VENDOR_FACTOR` → `factor`/`factor_return` ORIGIN edge.
7. **Entitlement parity:** `marketdata.ingest` (write) / `marketdata.view` (read); deny-by-default; auditor_3l excluded.
8. **Endpoint:** capture/supersede/correct/reconstruct/list; 422/404/409; no unauthorized write.
9. **Scope fences:** no `calculation_run`/`model_version`/`snapshot`/`risk` import; **no return arithmetic** (no `ast.Mult` on returns; no price/regression symbol); no exposure/covariance/VaR/factor-model identifier.
10. **Migration:** `0023` applies cleanly; `alembic check` drift-clean; downgrade `0023`→`0022` smoke.

PG-backed variants for RLS + the no-append-only close-out. `make check` green.

---

## Part 8 — Acceptance criteria
- A vendor factor + its return series capture, supersede, and correct as an FR bitemporal series, reproducible-by-capture (a correction never changes a historical as-of-known read).
- Every write is audited (`MARKET.FACTOR_RETURN_*`/`REFERENCE.*`), lineaged (VENDOR ORIGIN), DQ-gated (fail-closed), tenant-isolated (symmetric RLS).
- **No `calculation_run`/`model_version`/snapshot** is created or bound; `audit/service.py` untouched; head `0023_factor_return`.
- REQ-MKT-003 **input** prerequisite satisfied (the exposure output advances it at P3-3).

## Part 9 — UltraCode review log
8-lens adversarial review (shared with `p3_2_decision_record.md` Part 5; full per-lens log there). **Tally: 5 approve · 3 approve_with_changes · 0 block; 0 high / 0 medium.** Folds touching THIS plan (all LOW): the **finiteness DQ gap** — the shipped min-only `> -1` RANGE admits `+Infinity`, so a **binder-side `Decimal.is_finite()` pre-write guard** (the `fx_rate._validate_pair` precedent) is added (Part 4 DQ) + a `+Infinity`-rejection test (Part 7 test 4). The other two folds (an OD cross-ref, a control-matrix mapping) are in the decision record. Architect/Security/Model-Gov/Scope approve — the `benchmark`/`fx_rate` captured-market-data mirror, the no-run/no-model/no-snapshot input stance, and the honest degraded-connectivity status all verified clean. Nothing implemented; no analytics pulled forward.

## Part 10 — Risks & open questions
- **Captured-only misread as "factor analytics done"** → mitigated by the explicit input-vs-output framing + the P3-3 deferral.
- **Vendor-payload licensing** → DC-2 metadata-only audit (never the payload), the `fx`/`benchmark` precedent.
- **Multi-currency / multi-frequency factors** → v1 one currency + `DAILY` per factor; multi-* deferred (grain extensible).
- **The net-new `factor` canonical-id mint** → a Part-3 ratification at implementation (not a free build choice).
- **Open:** the exact `factor_type`/`factor_family` vocab (settled at implementation with the first vendor); whether `return_type` needs `LOG` in v1 (reserved).

## Part 11 — Implementation kickoff prompt (when approved + connectivity restored)
> "Begin P3-2 implementation only: the captured factor-return input foundation, per `p3_2_decision_record.md` (OD-P3-2-A…O) + this plan. Build EXACTLY: `marketdata/factor.py` (`capture_factor`/`update_factor`/`resolve_factor`/`list_factors` EV definition + `capture_factor_return`/`supersede_factor_return`/`correct_factor_return`/`reconstruct_factor_return_as_of`/`list_factor_returns` FR series — mirroring `benchmark.py`, captured-never-computed); `Factor` (EV) + `FactorReturn` (FR) models + `MARKET.FACTOR_RETURN_*`/`REFERENCE.*` constants + `VENDOR_FACTOR` source; migration `0023_factor_return` (both tables, symmetric RLS, NEITHER append-only; head `0022`→`0023`); the `factor_router` (gated `marketdata.ingest`/`marketdata.view`); metadata import; the Part-7 tests; the R-07 governance-doc updates incl. the net-new `factor` canonical-id mint + realize ENT-025. Conventions: `return_value` decimal fraction `Numeric(20,12)`; `return_type` `SIMPLE` (`LOG` reserved); `frequency` `DAILY`; grain `(tenant, factor_id, return_date, return_type)` current-head partial-unique. STRICT EXCLUSIONS: NO `calculation_run`/`model_version`/snapshot binding; NO return arithmetic / price-adjustment / regression / computed returns; NO factor exposure / covariance / VaR / ES / stress / scenario / attribution / benchmark-relative; NO `audit/service.py` change; NO BYPASSRLS/hybrid. 8-lens UltraCode review; `make check` + PG validation. Do not commit until I approve; note push/CI is pending if Zscaler egress is still blocked."
