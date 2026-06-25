# P1C-6 Implementation Plan — Deterministic Synthetic Portfolio Dataset (labeled, never-auto-run)

## Document Control

| Field | Value |
|---|---|
| Document ID | `p1c6_implementation_plan` |
| Version | 1.0 (planning) |
| Status | DRAFT — planning only; not approved; no code written |
| Owner | Platform engineering (Claude Code, UltraCode cadence) |
| Approver | H-06 Engineering Lead (sign-off pending) |
| Created | 2026-06-25 |
| Related documents | `10_delivery_backlog/p1c_implementation_plan.md` (§P1C-6); `p1c0_decision_record.md` (OD-P1C-L); `p1c5_implementation_plan.md`; `p1b_closeout_p1c_readiness.md` (Part 6, synthetic-data strategy); `06_security/entitlement_sod_model.md` (§8 DC); `09_compliance_controls/control_matrix_skeleton.md`; `11_decision_log/architecture_decision_log.md` (AD-017); `packages/shared-python/src/irp_shared/entitlement/bootstrap.py` (uuid5 precedent); `irp_shared/reference/bootstrap.py` (SYSTEM-seeder never-auto-run precedent) |
| Supported build rules | BR-11 (deny-by-default), BR-12 (tenant isolation / RLS), BR-13 (lineage on governed writes), BR-18 (audit chain), and AD-017 capture-only (the seed creates only captured rows; **computes nothing**) |
| Decisions inherited | **OD-P1C-L** (deterministic synthetic-data strategy: `uuid5` ids + fixed timestamps passed in, through the governed binders, DC-1/DC-2 demo fixtures, labeled never-auto-run module); AD-017 (P1C capture-only); OD-P1C-A (anchor-not-enforce — acceptable *because* P1C data is synthetic); the SYSTEM-seeder precedent (`seed_system_reference`, test-proven, not wired to a prod post-migrate path) |

> **One-line framing.** P1C-6 adds a **labeled, never-auto-run synthetic-data seed module** that builds a **deterministic** demo dataset — a synthetic reference seed pack + portfolio hierarchy + transactions + positions + valuations — **through the already-shipped governed binders** (so every seeded row carries the same audit + MANUAL-source lineage + RLS as production), with **`uuid5` ids + injected fixed timestamps** (no wall-clock, no random). It enables tests / demos / UI / future visualization. **It creates no new entity, no migration, no HTTP surface; it weakens no control; it computes no market value / risk / exposure; and it must never run in production.**

> **Existing fixture audit conclusions (read-only audit, folded in).** A read-only reasonability audit of all existing synthetic/seed/fixture/test data (8 categories, adversarially verified) found **0 BLOCKER, 0 HIGH, 0 MEDIUM** findings (6 LOW naming/test-quality nits + 6 INFO). Conclusions: **(a)** existing test fixtures are **acceptable for their current test-local purpose** (synthetic codes like `PF`/`BOND1`/`LE1`, fake LEIs, structurally-invalid ISINs; capture-only stance intact — no fixture computes `quantity × mark` / market value / exposure); **(b)** those fixtures are **NOT** the formal P1C-6 synthetic/demo dataset; **(c)** **no existing fixture cleanup is required before P1C-6** — and **no cleanup of existing tests is part of this plan** (optional renames of the LOW vendor-name labels — `Bloomberg Prices`, `agency="MOODYS"` — can be done later as a separate narrow cleanup if desired); **(d)** the **formal P1C-6 synthetic data must follow the STRICTER naming + determinism + no-real-data + edge-case standards below** (§4 *Synthetic-data standards*); **(e)** P1C-6 implementation **must not weaken audit, lineage, RLS, entitlement, or temporal rules**.

---

## 1. Requirements included

- **Not a product REQ** — P1C-6 is a **test/demo/UI/visualization enabler** (OD-P1C-L), realized as the synthetic reference seed pack + the synthetic portfolio / transaction / position / valuation dataset over it.
- It **exercises** (does not advance) the already-realized capture capabilities: REQ-PPM-001 (portfolio hierarchy), REQ-PPM-002 (position as-of), REQ-PPM-003 (transaction IA + valuation FR), and the P1B reference entities — by producing governed rows that look exactly like production rows.

**Net:** P1C-6 changes **no REQ status**; it is tooling that produces governed demo data.

---

## 2. Requirements excluded (and where they live)

| Excluded | Where it lives / why |
|---|---|
| Real client data / vendor data | Permanently excluded — synthetic-only (OD-P1C-L); real DC-3 data stays gated behind P6+ ABAC |
| Production auto-run seed | Permanently excluded — labeled never-auto-run, not in migrations, not in app startup (OD-P1C-L) |
| Bulk reference ingestion | **P1B-5** (conditional/deferred) — the synthetic pack replaces it *for P1C* |
| Market-data ingestion / price lookup / pricing model / valuation model | **P2** (AD-017 / OD-P1C-F) — valuations are captured marks |
| Risk calculations / exposure aggregation / `dataset_snapshot` | **P2** (AD-014 / AD-017 / OD-P1C-G/H) |
| Reporting / dashboard build | P2+ |
| Any change to existing domain semantics | Out of scope — the seed reuses the binders as-is (see §13 / OD-P1C6-1 for the only proposed seam, which is additive + prod-unchanged) |
| Weakening of audit / lineage / RLS / entitlement controls | Out of scope — every seeded row is governed, audited, lineage-rooted, RLS-scoped (CTRL-005/006/011/012/013 all preserved) |
| DC-3 / DC-4 data | Out of scope — synthetic instances are DC-1/DC-2 demo fixtures |

---

## 3. Synthetic data goals

1. **Reproducible** — re-running the seed on a fresh database under the same fixed SYNTHETIC tenant id yields a byte-identical dataset on the **deterministic surface** (same `uuid5` ids, same caller-supplied business data, and — with the OD-P1C6-1 seam — same injected `system_from`/`event_time` and audit chain).
2. **Governed** — seeded rows carry the production audit events + MANUAL-source lineage + RLS isolation (no back door).
3. **Non-sensitive** — no real client/vendor data; clearly labeled synthetic; DC-1/DC-2 demo fixtures.
4. **Representative** — exercises the FR as-of axes (multiple valid/known versions via supersede/correct) so holdings/portfolio views (P1C-5) and future UI/visualization have realistic time-travel data.
5. **Safe** — never auto-runs; never runs against a non-synthetic/production database.

---

## 4. Data classification and labeling

- **Entity TYPE is canonically DC-3** (client portfolios/positions are Confidential — `entitlement_sod_model.md` §8); the synthetic **instances** carry no real data, so they are treated as **DC-1/DC-2 demo fixtures** (OD-P1C-L; `p1b_closeout` Part 6). This is exactly what lets P1C ship before ABAC enforcement — the demo data is non-sensitive *because it is synthetic*.
- **Machine-readable labels (defense-in-depth):**
  1. A **reserved SYNTHETIC tenant** with a fixed `uuid5` tenant id (mirrors `SYSTEM_TENANT_ID`); ALL synthetic rows live under it, RLS-isolated from any real tenant.
  2. **Lineage provenance.** By **default** every seeded row's ORIGIN edge attributes to the per-tenant **`MANUAL` `data_source`** (the binders root it via `ensure_manual_source`; `data_source` is not a binder parameter today — so this is what ships unless a source-override axis is added). A distinct **`SYNTHETIC` `data_source`** (`source_type/code="SYNTHETIC"`) on the edge is an **OD-P1C6-7 option contingent on the OD-P1C6-1 source-override axis**; it is NOT assumed by default. Either way the SYNTHETIC tenant boundary is the primary machine label.
  3. **Naming convention** — tenant / portfolio / instrument codes prefixed `SYNTH-` or `DEMO-`.
- Audit `before/after` carry only DC-2 metadata (no sensitive plaintext); the synthetic instances are non-sensitive regardless.

### Synthetic-data standards (folded from the read-only fixture audit — binding for the P1C-6 build)

**Synthetic naming rule.** All formal synthetic tenants, portfolios, instruments, `data_source`s, actors, and labels MUST use **obvious `SYNTH_*` / neutral synthetic names**. **Do NOT use any real vendor, agency, exchange, firm, client, fund, or issuer name** (this is the stricter standard the existing test fixtures' LOW vendor-name labels — `Bloomberg Prices`, `S&P`, `MOODYS`, `XNYS` — must NOT be replicated into the formal dataset). Use names like:
- `SYNTH_PX` / "Synthetic Price Feed"
- `GEN_LT` / "Generic Long-Term Scale"
- `XTST` / "Test Exchange"

**No-real-data rule.** No real client data; no vendor data; no copied market / security / vendor dataset; **no real ISIN / CUSIP / SEDOL / LEI**. Use **clearly fake or structurally-invalid synthetic identifiers** (e.g. a reserved `ZZ` ISIN country prefix with an invalid body, `LEI…` placeholders that fail the 20-char/checksum format) so a synthetic value can never collide with or be mistaken for a real security/entity.

**Edge-case coverage (required — the seeded dataset must include all of these so as-of/holdings reads and the governed paths are exercised):**
- one **short position** (signed `quantity < 0`);
- one **transaction reversal with a non-null `price`** (via `reverse_transaction` — closes the audit's LOW L5 coverage gap);
- one **position correction / restatement** (`correct_position`, as-known);
- one **valuation correction / restatement** (`correct_valuation`, as-known);
- **multiple `valuation_date` marks** for a holding (distinct open heads under the 4-part key);
- a **stale / missing valuation scenario** (a position with no current mark for a requested `valuation_date`);
- an **identifier-ambiguity scenario** (if identifiers are seeded — to exercise the deterministic single-result-or-`AmbiguousIdentifier` resolution);
- a **bounded subtree scenario** (a fund → strategy → account tree so P1C-5 subtree holdings composition has real descendants).

**Deterministic-generation requirements.** `uuid5` ids (fixed namespace); **fixed injected timestamps**; **NO `datetime.now` / `utcnow` / `uuid4` / `new_uuid` / `uuid1` / `random`** anywhere in the seed module; an **AST / source-fence test MUST enforce** the absence of all of those tokens (see §16).

---

## 5. Deterministic ID strategy

- **`uuid5` with a fixed namespace** — mirror the shipped `entitlement/bootstrap.py` precedent (`_NS = uuid.UUID("…00a1")`, `permission_id(code)=uuid5(_NS, f"permission:{code}")`). Define a new synthetic namespace constant and per-entity key strings:
  - `synthetic_tenant_id = uuid5(_SYN_NS, "tenant:synthetic")`
  - `synthetic_actor_id = uuid5(_SYN_NS, "user:synthetic-seed")`
  - `portfolio_id = uuid5(_SYN_NS, f"portfolio:{code}")`, `instrument_id = uuid5(_SYN_NS, f"instrument:{code}")`, etc.
  - version rows keyed by their business identity, e.g. `position:{portfolio}:{instrument}:{valid_from}`.
- **Constraint surfaced (the crux):** the governed binders (`create_portfolio`, `record_transaction`, `create_position`, `create_valuation`, `create_instrument`) generate the surrogate `id` internally (`PrimaryKeyMixin` → `default=new_uuid`, `mixins.py:32`) and accept **no caller-supplied id**. Delivering literal `uuid5` surrogate ids therefore requires the deterministic-injection seam in **OD-P1C6-1**. **OD-P1C-L makes `uuid5` ids non-negotiable**, so the seam is the conformant path; the fallback (logical-determinism-only — identical business content every run, wall-clock `uuid4` surrogate ids) is an explicit **partial-conformance compromise to OD-P1C-L**, not full conformance.

---

## 6. Fixed timestamp strategy

- An **injected seed clock** — a fixed base instant (e.g. `2026-01-01T00:00:00Z`) plus deterministic per-row offsets — replaces `utcnow()` for the seed run. No `datetime.now()`, no `random`, no host-clock dependence (the `Date.now`/random discipline already used in workflows).
- **Business dates are caller-supplied today** and need no seam: `position.valid_from`, `valuation.valid_from`, `valuation.valuation_date`, `record_transaction`'s `trade_date` are explicit binder parameters → fully deterministic now.
- **System-time axis is NOT caller-controllable today:** for the FR entities `system_from` is computed `utcnow()` *inside* `create_position`/`create_valuation` (`position.py:156`); for the EV `portfolio` and IA `transaction` it is the mixin `default=utcnow` (`mixins.py`), not in-function — either way the caller cannot inject it. The binders' audit `_emit` helpers call `record_event` **without** `event_time`, so audit `event_time` is server-stamped (even though `record_event` itself accepts `event_time`). Making `system_from` + audit `event_time` deterministic requires the OD-P1C6-1 seam (inject the seed clock into the binders). With **a fresh database under the same fixed SYNTHETIC tenant id** + deterministic insertion order + injected clock, the **audit hash chain is also byte-reproducible**.

---

## 7. Synthetic tenant / user assumptions

- **One reserved SYNTHETIC tenant** (fixed `uuid5` id) for v1 (a small fixed set is OD-P1C6-6). All writes run under `set_tenant_context(session, SYNTHETIC_TENANT_ID)` — **never BYPASSRLS** (CTRL-011 preserved).
- **A synthetic seed actor** (fixed `uuid5` user id) as `actor_id` on every governed write; the seed actor's entitlement grants are produced **only by the governed entitlement path** (clone the existing SYSTEM role templates via the `entitlement/bootstrap.py` helpers under the synthetic tenant) — **never ad-hoc `Permission`/`Role`/`UserRole` inserts** — so the actor legitimately holds the maker permissions it exercises and the catalog mints nothing new (any genuinely new grant goes through R-07).
- The synthetic tenant is **distinct from `SYSTEM_TENANT_ID`** (which holds global reference/entitlement templates) and from any real tenant.

---

## 8. Synthetic reference-data pack

Built through the governed reference binders (so each row carries `REFERENCE.CREATE` + its per-tenant MANUAL-source lineage, the binder default):
- **SYSTEM globals** reused via the shipped `seed_system_reference` (currencies USD/EUR/GBP/JPY, the XNYS calendar, the SP_LT rating scale) under SYSTEM context.
- **Synthetic-tenant reference**: a handful of `legal_entity` + `issuer`/`counterparty`, several `instrument` + `instrument_terms` (FR — to exercise as-of), `identifier_xref`, and one or two `corporate_action` — via `create_instrument` / the legal-entity / identifier / corporate-action binders, under the synthetic tenant.
- Fixed, small, documented set (exact counts → OD-P1C6-5).

---

## 9. Synthetic portfolio hierarchy

- A fixed tree via `create_portfolio` — e.g. a `FUND` → `STRATEGY` → `ACCOUNT` chain (plus a sibling subtree) so P1C-5 subtree-holdings composition has real descendants to walk. Deterministic `code`s; `uuid5` ids (via the seam) or wall-clock ids (fallback).

---

## 10. Synthetic transaction set

- A fixed set of `transaction` rows via `record_transaction` (IA append-only): trades + cashflows across the synthetic portfolios/instruments, with deterministic `trade_date`, `external_ref` (idempotency key), `quantity`/`price`/`gross_amount` (inert captures), and at least one **reversal-as-new-record** via `reverse_transaction` to exercise that path. **No** position derivation from these (positions are captured directly — OD-P1C-E).

---

## 11. Synthetic position set

- A fixed set of `position` rows via `create_position` (FR), captured directly: per `(portfolio, instrument)` with deterministic `valid_from`, signed `quantity`, opaque `cost_basis`. At least one **effective-dated supersede** and one **as-known correction** per a couple of holdings, so both bitemporal axes (and thus P1C-5 as-of/known-at reads) have real multi-version data.

---

## 12. Synthetic valuation set

- A fixed set of `valuation` rows via `create_valuation` (FR, captured marks): per `(portfolio, instrument, valuation_date)` with deterministic `mark_value`, `currency_code`, `mark_source` (an inert row label, distinct from the lineage `data_source`). At least one supersede + one correction. **No** `quantity × mark`, **no** market value, **no** rollup — captured marks only.

---

## 13. Audit & lineage: governed services vs controlled test utilities

**Decision (recommended): through the GOVERNED services (OD-P1C-L; OD-P1C6-2).** The seed calls `create_portfolio` / `record_transaction` (+ `reverse_transaction`) / `create_position` / `create_valuation` / the reference binders, so each row emits its real `*.CREATE`/`RECORD` audit event and roots its ORIGIN lineage edge — **identical to production**. **Default provenance is the per-tenant `MANUAL` `data_source`** (the binders root it via `ensure_manual_source`; `data_source` is **not** a binder parameter today). Attributing the edge to a distinct `SYNTHETIC` source instead is **contingent on the OD-P1C6-1 source-override axis** (see OD-P1C6-7); absent that axis, synthetic-ness is carried by the reserved SYNTHETIC tenant + naming, and the edge stays MANUAL. This *proves the seed path is governed, not a back door*, and **preserves CTRL-005/006/012/013** (no control weakening). Direct-ORM insertion of rows (bypassing audit/lineage) is **rejected** — it would weaken the very controls the exclusions protect.

---

## 14. Loading mechanism: API vs service-layer seed utility vs offline fixture

**Decision (recommended): a SERVICE-LAYER seed module (OD-P1C6-3).** A Python entrypoint (e.g. `build_synthetic_dataset(session)`) that runs under a synthetic-tenant session and calls the governed binders, invoked **explicitly** — from a CLI/management entrypoint and from test fixtures. **Not** an HTTP API (no runtime surface, no new endpoint/permission), **not** an offline raw-SQL fixture (would bypass governance). Mirrors the shipped `seed_system_reference` shape (a function taking a `Session`, caller owns context + commit).

---

## 15. Never-auto-run safety controls

Layered (architectural + test-proven + explicit opt-in — the recommended OD-P1C6-4):
1. **Architectural** — the module lives **outside `migrations/`** and **outside app/worker startup**; nothing imports it on a normal path (mirrors the SYSTEM seeder, which is deliberately unhooked from migrations).
2. **Explicit invocation contract** — the entrypoint refuses to run unless an explicit confirmation is passed (e.g. an `allow_synthetic_seed=True` argument **and** an `IRP_ALLOW_SYNTHETIC_SEED=1` env gate), and **refuses if the target tenant is not the reserved SYNTHETIC tenant** (it can only ever write to the synthetic tenant).
3. **Guard test** — a test asserts the module is **not** imported by any migration, by `apps/*/main.py`, or by any CI auto-path; and that invoking it without the explicit confirmation is a no-op/raise.
4. **Labeled blast-radius** — even if mis-invoked, every row is under the reserved SYNTHETIC tenant + SYNTHETIC source, RLS-isolated from real tenants.

---

## 16. Tests

- **Determinism** — two runs **on a fresh database, each under the SAME fixed SYNTHETIC tenant id** (not "a fresh tenant"), produce byte-identical values on the **deterministic surface**: the `uuid5` surrogate ids, the caller-supplied business dates/quantities/marks, and — **with the OD-P1C6-1 seam** — the injected `system_from`/`event_time` and thus the audit chain. *(Without the seam, the byte-comparison covers only the seam-independent surface; surrogate ids + system-time vary — the fallback's documented partial conformance.)*
- **Non-determinism fence (AST/source scan of the seed module)** — forbid **every** wall-clock/random vector in THIS repo, not just `datetime.now`: `datetime.now`, `datetime.utcnow`, `utcnow` (the `irp_shared.db.mixins.utcnow` helper), `uuid4`, `new_uuid`, `uuid1`, and `random` / `secrets`. The seed must derive every id from the `uuid5` namespace and every time from the injected seed clock.
- **Governed-path proof** — after seeding, every synthetic row has its `*.CREATE`/`RECORD` audit event and an ORIGIN lineage edge (`assert_has_lineage`); **the test loads the edge's `source_id → DataSource` and asserts its `code`/`source_type` is the intended provenance** (MANUAL by default, or SYNTHETIC if OD-P1C6-7's source axis ships); the per-tenant audit chain `verify_chain` passes.
- **FR as-of exercised** — the seeded supersede/correct produce multiple valid/known versions; `reconstruct_*_as_of` + the P1C-5 holdings views return the expected as-of slices.
- **Never-auto-run guard** — the module is not on any migration/startup/CI auto-path; invocation without the explicit confirmation does not write; invocation against a non-synthetic tenant is refused.
- **Labeling** — all seeded rows are under the SYNTHETIC tenant; the provenance `data_source` is the intended one; codes carry the synthetic prefix.
- **Tenant isolation** — under PG FORCE-RLS as `irp_app`, a different tenant sees none of the synthetic rows; the seed never uses BYPASSRLS.
- **No-compute fence** — the seed module contains no multiplication of quantity×mark, no aggregate, no market-value/exposure (AST fence, mirroring P1C-5).
- **Prod-call-site-unchanged (with the seam)** — a test asserts the governed binders' production call sites (which pass no seam argument) produce byte-for-byte the same behavior as before the seam (default-None ⇒ wall-clock id/time, server-stamped audit), so the seam cannot alter any real-tenant write.

---

## 17. Acceptance criteria

1. A **reproducible, non-sensitive** demo dataset (synthetic reference + portfolios + transactions + positions + valuations, with FR multi-version data) exists for tests/demos/UI.
2. **Deterministic** — re-run (fresh DB, same fixed SYNTHETIC tenant) yields byte-identical values on the deterministic surface: `uuid5` ids + business data, plus injected timestamps + audit chain **with the seam**; no wall-clock/random (`utcnow`/`uuid4`/`new_uuid`/`random` all fenced out of the seed module).
3. **Governed** — every seeded row carries its audit event + lineage; `verify_chain` passes; RLS-isolated under the SYNTHETIC tenant; never BYPASSRLS.
4. **Never auto-runs** — not in migrations/startup/CI; explicit-confirmation-gated; refuses non-synthetic targets (guard-tested).
5. **No real data; no new compute** — no market value / risk / exposure / snapshot / aggregation; no new entity/migration/endpoint/permission; `migration_head` stays `0015_valuation`.

---

## 18. Risks

| Risk | Mitigation |
|---|---|
| Synthetic data leaking into a prod path | Labeled never-auto-run module; not in migrations; reserved SYNTHETIC tenant + source; explicit-confirm gate; refuse-non-synthetic-target; guard test |
| Non-determinism (machine/run variance) | `uuid5` + injected seed clock; AST fence forbidding `datetime.now`/`random` |
| The OD-P1C6-1 seam being misused to inject ids/timestamps in PROD | Keyword-only, default-None; prod call sites pass nothing and are byte-for-byte unchanged (asserted by a prod-call-site test); the seam only ever activated by the seed module |
| Weakening audit/lineage/RLS | Seed goes through governed binders (all controls fire); never BYPASSRLS; `verify_chain` + `assert_has_lineage` tested |
| Audit-chain bloat on a shared tenant | Isolated reserved SYNTHETIC tenant (its own chain), distinct from real tenants and SYSTEM |
| Scope creep into market/risk/valuation compute | No-compute AST fence; captured values only; reuse binders as-is |

---

## 19. Open decisions (sign-off before build)

| ID | Decision | Recommendation | Status |
|---|---|---|---|
| OD-P1C6-1 | How to deliver literal `uuid5` ids + fixed `system_from`/audit `event_time` (+ optional SYNTHETIC source) given the binders generate ids, stamp `utcnow()`, and root `ensure_manual_source` internally — **`uuid5` ids are REQUIRED by OD-P1C-L, not optional** | Add a **narrow, keyword-only, default-None deterministic-injection seam** to the governed binders along **up to three axes**: (a) `entity_id` (caller `uuid5`); (b) a `seed_clock`/`now` injector that sets `system_from`/`valid_from` and flows to `record_event(event_time=…)`; (c) *(optional, only if OD-P1C6-7 wants a SYNTHETIC source)* a `data_source`/`origin_source` override that replaces the default `ensure_manual_source` root. All keyword-only, **default-None ⇒ prod call sites byte-for-byte unchanged** (asserted by a prod-call-site test); used **only** by the seed. Honors OD-P1C-L literally + preserves every control + no prod-semantics change. **Fallback** (if the seam is rejected): logical-determinism-only — identical business content every run, but wall-clock `uuid4` surrogate ids + wall-clock system/audit time + MANUAL source (**explicit partial conformance to OD-P1C-L**, no binder change). | ✅ Approved — deterministic-injection seam with default-None keyword-only axes for `entity_id`, `seed_clock`, and the optional `data_source`/provenance source; **production call sites remain unchanged** |
| OD-P1C6-2 | Generate audit/lineage via governed services, or insert via controlled test utilities | **Governed services** — proves the seed is not a back door; preserves CTRL-005/006/012/013 | ✅ Approved — use the governed binders/services for **audit, lineage, RLS, and entitlements** |
| OD-P1C6-3 | Loading mechanism | **Service-layer seed module** (function taking a `Session`); explicit CLI/test invocation; NOT an API, NOT a raw-SQL fixture | ✅ Approved — **service-layer seed module only; no API and no raw SQL** |
| OD-P1C6-4 | Never-auto-run enforcement | **Architectural (not in migrations/startup) + explicit-confirm gate (arg + env) + refuse-non-synthetic-target + guard test** | ✅ Approved — **never-auto-run; explicit confirmation and a non-production / synthetic-tenant guard required** |
| OD-P1C6-5 | Dataset size/shape (how many tenants/portfolios/instruments/versions) | A **small fixed documented set** (1 synthetic tenant; ~1 fund / 2 strategies / 3–4 accounts; ~5 instruments; a handful of txns/positions/valuations with 1–2 supersede/correct each) — enough to exercise subtree + as-of; finalize counts at sign-off | ✅ Approved — **small fixed deterministic dataset** (must include the §4 edge-case coverage) |
| OD-P1C6-6 | One synthetic tenant vs a small set | **One** reserved SYNTHETIC tenant for v1 (a second tenant only if cross-tenant demos are needed) | ✅ Approved — **one reserved SYNTHETIC tenant for the initial dataset** |
| OD-P1C6-7 | Module placement; **and (separately) provenance source label** | **New `irp_shared/synthetic/` package** (seed builder + `uuid5` helpers + constants). **Provenance label is a distinct sub-decision:** default to the binders' per-tenant **MANUAL** source (no source axis needed) with synthetic-ness carried by the SYNTHETIC tenant + naming; **opt into a `SYNTHETIC` `data_source` only if OD-P1C6-1 axis (c) ships** (the source override). The module placement does not depend on the source choice. | ✅ Approved — **new `irp_shared/synthetic/` package; provenance source defaults to MANUAL** unless the optional source-injection seam is implemented safely |

---

## 20. Controls impacted

- **Preserved + exercised (not weakened):** **CTRL-005/012** (audit emitted by the binders for every seeded row — `verify_chain` passes), **CTRL-006/013** (per-tenant MANUAL-source — or SYNTHETIC if OD-P1C6-7 ships it — ORIGIN lineage per row, `assert_has_lineage` with a source-identity assertion), **CTRL-011** (tenant isolation + RLS under the SYNTHETIC tenant; never BYPASSRLS), **CTRL-001** (the determinism/governed/guard tests), **CTRL-004** (no new fields — reuses existing data-dictionary entities).
- **Not applicable:** any compute/derivation control (no market value / risk / exposure); **CTRL-017** applies to the underlying entities (already declared), not the seed.
- **No control is weakened** — the seed strengthens coverage by exercising the governed path end-to-end on a reproducible dataset.

---

## 21. Documentation updates (in the BUILD slice, not this plan)

- `09_compliance_controls/control_matrix_skeleton.md` — P1C-6 coverage note (governed seed exercises CTRL-005/006/011/012/013; never-auto-run guard).
- `11_decision_log/` / `10_delivery_backlog/` — record **OD-P1C-L REALIZED**; the synthetic-data labeling + never-auto-run contract.
- `04_data_model/` — the SYNTHETIC tenant/source constants + the synthetic dataset shape (reference doc).
- P1C-6 closeout note; project-memory refresh (separate closeout turn).
- **No** entitlement/audit-taxonomy/migration governance change beyond the seed-actor grants (which reuse the governed bootstrap pattern; if any new grant is needed it goes through R-07).
- **No cleanup or rename of existing tests/fixtures** is part of this slice (the read-only audit found 0 BLOCKER/HIGH/MEDIUM); the optional LOW vendor-name-label renames (`Bloomberg Prices`, `agency="MOODYS"`) are a **separate, later, narrow cleanup** only if explicitly approved.

---

## 22. Whether P1C-6 is ready to implement

**Ready — OD-P1C6-1…7 are SIGNED OFF (see §19 + the sign-off block below).** OD-P1C6-1 is approved as the **deterministic-injection seam** (keyword-only, default-None axes `entity_id` / `seed_clock` / optional `data_source`; production call sites unchanged). The build composes shipped, governed surfaces; the only shared-package touch is the additive, prod-unchanged binder seam. **No blockers; no existing-fixture cleanup is in scope.** Implementation proceeds only on a separate, explicit "begin P1C-6 implementation" approval.

---

## 23. Exact implementation kickoff prompt

> "Begin P1C-6 implementation only: deterministic synthetic portfolio dataset (labeled, never-auto-run). Sign-offs (ALL APPROVED): OD-P1C6-1 the **deterministic-injection seam** (keyword-only, default-None axes `entity_id` + `seed_clock` + optional `data_source`; prod call sites unchanged); OD-P1C6-2 governed binders/services for audit+lineage+RLS+entitlements; OD-P1C6-3 service-layer seed module (no API, no raw-SQL fixture); OD-P1C6-4 never-auto-run (not in migrations/startup + explicit-confirm gate + non-production/synthetic-tenant guard + guard test); OD-P1C6-5 small fixed deterministic dataset incl. the required edge cases; OD-P1C6-6 one reserved SYNTHETIC tenant; OD-P1C6-7 new `irp_shared/synthetic/` package (provenance source = MANUAL by default, SYNTHETIC only if the source-injection seam is implemented safely).
> Synthetic-data standards (binding): all synthetic tenants/portfolios/instruments/sources/actors/labels use obvious `SYNTH_*`/neutral names (e.g. `SYNTH_PX`/"Synthetic Price Feed", `GEN_LT`/"Generic Long-Term Scale", `XTST`/"Test Exchange") — NO real vendor/agency/exchange/firm/client/fund/issuer names; NO real client/vendor data, NO copied market/security/vendor dataset, NO real ISIN/CUSIP/SEDOL/LEI (use clearly-fake/structurally-invalid synthetic identifiers). Required edge cases: one short position; one transaction reversal with a non-null price; one position correction/restatement; one valuation correction/restatement; multiple `valuation_date` marks; a stale/missing-valuation scenario; an identifier-ambiguity scenario (if identifiers seeded); a bounded subtree. Do NOT clean up or rename existing test fixtures as part of this slice.
> Implement: a new `irp_shared/synthetic/` package — `uuid5` id helpers (fixed namespace, mirroring `entitlement/bootstrap.py`) + the SYNTHETIC tenant/actor constants + a `build_synthetic_dataset(session, *, allow_synthetic_seed=False)` builder that, under `set_tenant_context(SYNTHETIC_TENANT_ID)`, calls the governed binders (`seed_system_reference`, the reference binders, `create_portfolio`, `record_transaction` + `reverse_transaction`, `create_position` + supersede/correct, `create_valuation` + supersede/correct) with deterministic codes / business dates / quantities / marks and [the OD-P1C6-1 mechanism]; the seed actor's grants cloned from the SYSTEM role templates via the governed `entitlement/bootstrap.py` helpers (no ad-hoc grant inserts); refusing to run without the explicit confirm + against any non-synthetic tenant. [If OD-P1C6-1 = seam: add the narrow keyword-only default-None seam (`entity_id` + `seed_clock`; + a `data_source` override only if OD-P1C6-7 wants a SYNTHETIC source) to the governed binders, leaving prod call sites byte-for-byte unchanged — asserted by tests.]
> Tests: determinism (byte-identical re-run on a fresh DB under the SAME fixed SYNTHETIC tenant + a fence forbidding `datetime.now`/`utcnow`/`uuid4`/`new_uuid`/`random` in the seed module), governed-path proof (`*.CREATE`/`RECORD` audit + ORIGIN lineage per row with a source-identity assertion; `verify_chain`; `assert_has_lineage`), FR as-of (multi-version reconstruction + P1C-5 holdings views), never-auto-run guard (not on migration/startup/CI; refuses without confirm; refuses non-synthetic target), labeling (SYNTHETIC tenant + provenance source + code prefix), PG tenant-isolation under FORCE-RLS as `irp_app`, and a no-compute AST fence. [If OD-P1C6-1 = seam: a prod-call-site test proving prod behavior is byte-for-byte unchanged.]
> STRICT EXCLUSIONS: NO real client/vendor data; NO production auto-run seed; NO market-data ingestion / price lookup / pricing model / valuation model; NO risk calculations / exposure aggregation / `dataset_snapshot`; NO reporting/dashboard; NO new entity / migration / HTTP endpoint / permission beyond the governed seed-actor grants; NO weakening of audit / lineage / RLS / entitlement; NO change to existing prod domain semantics (any binder seam is additive, keyword-only, default-None, prod-unchanged); NO P2+ work. `audit/service.py` stays frozen. `migration_head` stays `0015_valuation`.
> Then run an 8-lens UltraCode adversarial review, fix in-scope findings, run `make check` (+ Docker PG), and **do not commit until I approve**."

---

### Sign-off block

> Sign-offs recorded (H-06 Engineering Lead, 2026-06-25):
> - ⚑ OD-P1C6-1 — ✅ signed off — **deterministic-injection seam** with default-None keyword-only axes for `entity_id`, `seed_clock`, and the optional `data_source`/provenance source; **production call sites remain unchanged**.
> - ⚑ OD-P1C6-2 — ✅ signed off — use the **governed binders/services** for audit, lineage, RLS, and entitlements.
> - ⚑ OD-P1C6-3 — ✅ signed off — **service-layer seed module only; no API and no raw SQL**.
> - ⚑ OD-P1C6-4 — ✅ signed off — **never-auto-run**; explicit confirmation and a non-production / synthetic-tenant guard required.
> - ⚑ OD-P1C6-5 — ✅ signed off — **small fixed deterministic dataset** (including the required edge-case coverage).
> - ⚑ OD-P1C6-6 — ✅ signed off — **one reserved SYNTHETIC tenant** for the initial dataset.
> - ⚑ OD-P1C6-7 — ✅ signed off — new **`irp_shared/synthetic/` package**; provenance source **defaults to MANUAL** unless the optional source-injection seam is implemented safely.
>
> **Audit fold + scope guard:** the read-only fixture audit (0 BLOCKER / 0 HIGH / 0 MEDIUM) is folded into §4 *Synthetic-data standards*; **no cleanup or rename of existing tests/fixtures is part of this plan** (optional later narrow cleanup only). P1C-6 implementation **must not weaken audit, lineage, RLS, entitlement, or temporal rules**.
> - ⚑ OD-P1C6-3 — service-layer seed module (no API / no raw-SQL fixture)
> - ⚑ OD-P1C6-4 — never-auto-run enforcement (architectural + explicit-confirm + refuse-non-synthetic + guard test)
> - ⚑ OD-P1C6-5 — dataset size/shape
> - ⚑ OD-P1C6-6 — one SYNTHETIC tenant
> - ⚑ OD-P1C6-7 — `irp_shared/synthetic/` package + SYNTHETIC data_source
