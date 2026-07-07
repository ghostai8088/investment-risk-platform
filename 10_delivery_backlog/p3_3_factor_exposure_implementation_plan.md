# P3-3 Implementation Plan — Factor-Exposure Engine (allocation v1)

## Document Control

| Field | Value |
|---|---|
| Purpose | The build contract for P3-3: **indicator-loading currency-factor exposures over pinned `exposure_aggregate` atoms** — the second governed derived risk number, bound to `dataset_snapshot` + `calculation_run` + a **registered `model_version`**, IA append-only, audited, lineaged, DQ-gated, reproducible under input correction. Companion to `p3_3_decision_record.md` (OD-P3-3-A…O). |
| Status | **Implementation PLAN — PLANNING ONLY; NO code, NO migrations, NO factor/risk/model implementation.** |
| HEAD at writing | `c452229` (CI #90 green; P3-2 impl `402cb12`, CI #89 green); migration head `0023_factor_return`; origin/main in-sync. |
| Predecessors | `p3_3_decision_record.md`; `p3_1_sensitivities_implementation_plan.md` + the shipped `irp_shared/risk/` package (**the `run_sensitivities` exemplar mirrored step-for-step**); `p3_2_factor_return_inputs_implementation_plan.md` (the factor universe consumed); `p2_3_exposure_implementation_plan.md` (the atom producer). |
| Review | 8-lens adversarial review — **Part 9** (shared with the decision record Part 5). |

> **Critical invariant (the gate every row passes):** no `factor_exposure_result` row exists unless bound to **`dataset_snapshot` (`FACTOR_EXPOSURE_INPUT`) + `calculation_run` (`FACTOR_EXPOSURE`) + a registered `model_version` + `methodology_ref` + `code_version` + `environment_id` + `CALC.RUN_*` audit + `snapshot→run→result` lineage + a passed fail-closed DQ gate**, and is **reproducible** from the snapshot-pinned content alone (no live exposure/factor read). **Contributions sum to the pinned input total exactly (ε=0).** **This plan builds NOTHING.**

---

## Part 1 — Module map (what the implementation slice will touch)

| Area | Change | New/Modified |
|---|---|---|
| `packages/shared-python/src/irp_shared/risk/factor_kernel.py` | the **pure allocation kernel** — `build_factor_index(factors)` (currency_code → factor; duplicate ⇒ error) + `allocate_atom(atom, index)` (exact match ⇒ `(factor, loading=1, quantize_HALF_UP(amount, 6))`; no match ⇒ gap) — no DB, no I/O | NEW |
| `…/risk/factor_service.py` | **`run_factor_exposure(...)`** — the governed-run binder (mirrors `run_sensitivities`) + `list_factor_exposures` / `resolve_factor_exposure_run` / `resolve_factor_exposure` readers | NEW |
| `…/risk/models.py` | add `FactorExposureResult` (ENT-028 family; IA append-only ORM guard) | MODIFIED |
| `…/risk/events.py` | add `RUN_TYPE_FACTOR_EXPOSURE = "FACTOR_EXPOSURE"` + `RISK_FACTOR_EXPOSURE_CREATE_EVENT_RESERVED = "RISK.FACTOR_EXPOSURE_CREATE"` (reserved, NOT emitted) + `FactorExposureActor` (or reuse the actor shape) | MODIFIED |
| `…/risk/bootstrap.py` | add `register_factor_exposure_model` (governed `register_model` + `register_model_version`; idempotent; `FACTOR_EXPOSURE_MODEL_CODE = "risk.factor_exposure.allocation"`, `v1`; `methodology_ref` → the Part-6 doc; assumptions/limitations from the methodology) | MODIFIED |
| `…/snapshot/models.py` | add `COMPONENT_KIND_EXPOSURE = "EXPOSURE"` + `COMPONENT_KIND_FACTOR = "FACTOR"` + `PURPOSE_FACTOR_EXPOSURE_INPUT = "FACTOR_EXPOSURE_INPUT"` (app constants — NO migration) | MODIFIED |
| `…/snapshot/serialize.py` | `exposure_content(row)` (the atom's immutable fields incl. `mark_currency`/`exposure_amount`) + `factor_content(row)` (the EV definition's identity + scope + `record_version`) | MODIFIED |
| `…/snapshot/service.py` | `build_factor_exposure_snapshot(session, *, acting_tenant, actor, exposure_run_id, factor_ids, …)` — pins one `COMPONENT_KIND_EXPOSURE` component per atom (**IA pin flavor**: `pinned_valid_from`/`pinned_record_version` NULL, `pinned_system_from` = row `system_from`) + one `COMPONENT_KIND_FACTOR` per factor (EV pin flavor) + the two `_reresolve_content` handlers | MODIFIED |
| `migrations/versions/0024_factor_exposure.py` | `factor_exposure_result` table (IA append-only: `APPEND_ONLY_TABLES` + `irp_prevent_mutation` P0001 trigger; symmetric FORCE RLS); **head `0023` → `0024`** | NEW |
| `apps/backend/src/irp_backend/api/risk.py` | factor-exposure endpoints on the existing `risk_router` (POST run + reads; POST model registration) — gated by the **existing** `risk.run`/`risk.view`/`model.inventory.register` | MODIFIED |
| `05_analytics_methodologies/factor_exposure_allocation_v1.md` | the methodology doc (Part 6) | NEW |
| tests (shared + PG + endpoint) | the Part-7 test groups (`test_factor_exposure.py` / `_pg.py` / `_endpoint.py`) | NEW |
| governance docs | the R-07 amendments of the decision record Part 3 (canonical / audit / entitlement / control matrix / RTM / temporal) | MODIFIED |

**Untouched (hard):** `audit/service.py` (FROZEN); `entitlement/bootstrap.py` (**no new permission — `risk.*` reused**); `marketdata/factor.py` + `exposure/service.py` (read-only consumers via the existing `resolve_*`/`list_*`); `risk/service.py`/`kernel.py` (the sensitivity slice untouched); the DQ `Protocol`; no BYPASSRLS; no hybrid path; no `COMPONENT_KIND_FACTOR_RETURN`.

---

## Part 2 — `factor_exposure_result` (ENT-028 family) table design
IA TRUE append-only, run-bound + snapshot-gated + model_version-bound. Columns:

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID | NO | PrimaryKeyMixin |
| `tenant_id` | GUID | NO | TenantMixin (server-stamped) |
| `system_from` | DateTime(tz) | NO | ImmutableAppendOnlyMixin (append timestamp) |
| `calculation_run_id` | GUID FK→`calculation_run.run_id` | NO | indexed; the governing run |
| `input_snapshot_id` | GUID FK→`dataset_snapshot.id` | NO | indexed; the pinned atoms+factors snapshot |
| `model_version_id` | GUID FK→`model_version.id` | NO | **NON-NULL — registered** (asserted pre-create) |
| `portfolio_id` | GUID | NO | carried from the pinned atom |
| `instrument_id` | GUID | NO | carried from the pinned atom |
| `factor_id` | GUID | NO | the pinned `factor` EV head id — **NOT a hard FK** (the `COMPONENT_KIND_FACTOR` pin is the authoritative version; the `fx_legs`/`curve_id` precedent) |
| `factor_code` | String(150) | NO | carried captured label |
| `factor_family` | String(30) | NO | carried (`CURRENCY` in v1) |
| `base_currency` | String(3) | NO | carried from the atom (run-uniform) |
| `mark_currency` | String(3) | NO | **the mapping attribute** — carried for auditability |
| `loading` | Numeric(20,12) | NO | v1 constant `1`; the beta-extension seam (extend by value, not migration) |
| `exposure_amount` | Numeric(28,6) | NO | `quantize_HALF_UP(loading × atom.exposure_amount, 6)`; signed, base currency |

**Grain / unique:** UNIQUE **4-tuple `(calculation_run_id, portfolio_id, instrument_id, factor_id)`** — `input_snapshot_id`/`model_version_id` carried NON-NULL but functionally run-determined ⇒ out of the key (OD-P3-1-B pattern). **No stored per-factor TOTAL rows** (deterministic Σ, test-asserted). **IA append-only:** `ImmutableAppendOnlyMixin` + ORM `before_update`/`before_delete` guard + migration `APPEND_ONLY_TABLES` + P0001 trigger. **RLS:** symmetric `tenant_isolation_factor_exposure_result` (USING == WITH CHECK == own-tenant; ENABLE + FORCE); never hybrid. Register the model class in `irp_shared.models`.

---

## Part 3 — `run_factor_exposure(...)` binder (mirrors `run_sensitivities` step-for-step)
```
run_factor_exposure(session, *, acting_tenant, actor, code_version, environment_id,
                    model_version_id, exposure_run_id=None, factor_ids=None,
                    snapshot_id=None) -> FactorExposureRunResult
```
Ordered steps (the shipped P3-1 template):
- **(a) pre-create gate** (any failure ⇒ `FactorExposureInputError`/`UnregisteredModelError` ⇒ **ZERO run/rows/audit**): `code_version`/`environment_id`/`actor.actor_id`/`model_version_id` truthy; **`assert_registered_model_version(session, model_version_id, tenant_id=acting_tenant)`** (CTRL-003); then either `snapshot_id` (resolve + `purpose == PURPOSE_FACTOR_EXPOSURE_INPUT`) or `exposure_run_id` + `factor_ids`: `exposure.resolve_run` (own-tenant, `run_type='EXPOSURE_AGGREGATE'`) with **status `COMPLETED`**; `list_exposure(run_id=…)` **non-empty**; each factor via `resolve_factor` (own-tenant, fail-closed); factor set non-empty, **all `factor_family == 'CURRENCY'`** (v1 supported set — anything else refused), every factor's `currency_code` **non-null**, **no duplicate `currency_code`** in the set (ambiguous partition refused pre-create).
- **(b) snapshot** — `build_factor_exposure_snapshot(...)`: one `COMPONENT_KIND_EXPOSURE` component per atom (IA pin: `captured_content = exposure_content(row)`, `pinned_system_from = row.system_from`, valid_from/record_version NULL) + one `COMPONENT_KIND_FACTOR` per factor (EV pin: `factor_content(row)`, `pinned_record_version = row.record_version`), `purpose = PURPOSE_FACTOR_EXPOSURE_INPUT`; SHA-256 content hashes + `manifest_hash` (the shipped serializer rails); `SNAPSHOT.CREATE` emitted by the existing snapshot binder. No as-of parameter is needed: atoms are immutable and the run's valid-time provenance flows transitively from the consumed exposure run's own snapshot.
- **(c) run** — `create_run(run_type=RUN_TYPE_FACTOR_EXPOSURE, initiated_by=actor.actor_id, input_snapshot_id=snapshot.id, model_version_id=…, code_version=…, environment_id=…)` → `CALC.RUN_CREATE`; `update_run_status(RUNNING)` → `CALC.RUN_STATUS_CHANGE`. From here failures are **post-create FAILED**.
- **(d) input lineage BEFORE the gate** — `record_internal_lineage(snapshot → run, DEPENDS_ON, run_id)` (the P3-1 fold: a committed FAILED run keeps its input link).
- **(e) compute from pinned content ONLY** — `list_components(snapshot)`; parse the `COMPONENT_KIND_FACTOR` contents → `build_factor_index` (pure; a duplicate currency here is defense-in-depth — (a) already refused it); parse each `COMPONENT_KIND_EXPOSURE` content → `allocate_atom` by exact `mark_currency` match → `(factor, loading=1, quantize_HALF_UP(amount, 6))`; collect `rows` + `gaps` (one gap per unmapped atom). **NO live `list_exposure`/`resolve_factor`/`reconstruct_*` read** (the AD-014 invariant; import-fenced).
- **(f) DQ gate (fail-closed)** — rule **`risk.factor_exposure.completeness`** (resolve-or-register; reused `run_quality_check` NOT_NULL over `{'present': None}` gap rows; Protocol UNTOUCHED; emits `DATA.VALIDATE`). `DataQualityError` ⇒ `update_run_status(FAILED, outcome='failure')` ⇒ return `rows=[]` (**committed FAILED run, ZERO result rows** — the durable refusal evidence).
- **(g) governed write** — add rows + `flush`; `record_run_lineage(run → each row, ORIGIN)`; `update_run_status(COMPLETED)`. Any emit-path raise ⇒ co-transactional rollback (CTRL-032).

**`FactorExposureRunResult(run, status, rows, failure_reason)`.** Differences from `run_sensitivities`: the inputs are pinned exposure atoms + factor definitions (not curves); the kernel is an allocation (not a closed-form derivative); the pre-create gate additionally validates the factor set's partition-well-formedness.

---

## Part 4 — Pure allocation kernel (`risk/factor_kernel.py`)
No DB, no I/O, fully unit-testable, deterministic:
- `build_factor_index(factors: list[FactorPin]) -> dict[str, FactorPin]` — keys each pinned factor by its `currency_code` (exact captured string); a duplicate key raises (`AmbiguousFactorSet` — defense-in-depth behind the pre-create refusal).
- `allocate_atom(atom: AtomPin, index) -> AllocatedExposure | None` — exact `mark_currency` lookup; hit ⇒ `loading = Decimal(1)`, `amount = quantize_HALF_UP(loading * atom.exposure_amount, 6)` (idempotent on the already-6dp atom — exact by construction, the QS-04 registered HALF_UP exception); miss ⇒ `None` (the caller records a gap).
- Signs preserved (a short atom allocates negative exposure; QS-22 — no abs/gross/net coercion; those variants are deferred).
- **Sum-to-total is structural:** every atom maps to exactly one factor (or the run FAILS) ⇒ `Σ rows.exposure_amount == Σ pinned atoms.exposure_amount` exactly (**ε = 0**); asserted in tests, never stored.

---

## Part 5 — Snapshot extension (atom + factor pinning)
- `COMPONENT_KIND_EXPOSURE = "EXPOSURE"` + `COMPONENT_KIND_FACTOR = "FACTOR"` added to `SNAPSHOT_COMPONENT_KINDS`; `PURPOSE_FACTOR_EXPOSURE_INPUT = "FACTOR_EXPOSURE_INPUT"` added to `SNAPSHOT_PURPOSES`. **No migration** (unconstrained strings). `COMPONENT_KIND_FACTOR_RETURN` remains readiness-noted, NOT minted.
- `exposure_content(row)` — the atom's immutable fields (`id/tenant_id/calculation_run_id/input_snapshot_id/portfolio_id/instrument_id/base_currency/mark_currency/signed_quantity/mark_value/fx_rate/exposure_amount/exposure_type/system_from`); canonical serialization + SHA-256 (the shipped rails; Decimal fixed-scale HALF_UP).
- `factor_content(row)` — the EV definition's identity + scope (`id/tenant_id/factor_code/factor_source/factor_family/factor_type/region/currency_code/asset_class/frequency/record_version`); EV pin (NULL system axis; `record_version` the drift discriminator — the `PORTFOLIO` flavor).
- `build_factor_exposure_snapshot(...)` — resolves the exposure run + rows and the factor set **under the acting tenant** (fail-closed), `_append_spec` per atom + per factor, header `manifest_hash`; empty atoms ⇒ pre-create refusal upstream. `_reresolve_content` handlers: `EXPOSURE` re-reads the immutable row by id (byte-identical unless tampered); `FACTOR` re-resolves the EV head (a bumped `record_version` reports drift — exactly what verify exists to show).

---

## Part 6 — Methodology doc (`05_analytics_methodologies/factor_exposure_allocation_v1.md`)
Linked from `model_version.methodology_ref` (the OD-P3-0-C §-template). Sections: **Purpose & applicability** (indicator-loading allocation factor exposure; fundamental-model membership form; CURRENCY family v1). **Inputs + data policy** (pinned `exposure_aggregate` atoms of one COMPLETED exposure run + pinned `factor` EV definitions; point-in-time — **no history/estimation window**; factor returns NOT consumed). **Formulas + numerical standards** (`loading = 1`; `factor_exposure = quantize_HALF_UP(loading × exposure_amount, 6)`; exact-match partition; Σ-to-total ε=0; signed). **Assumptions** (→ `model_assumption`: the currency dimension = the atom's captured `mark_currency` — a declared proxy for denomination currency; indicator loadings; one factor per atom per run). **Limitations** (→ `model_limitation`: not beta/regression exposures; mark-currency proxy (denomination-currency mapping deferred); CURRENCY family only; no residual bucket — unmapped input fails the run; no contribution-to-risk). **Validation / reproduction tests** (hand-computed allocation vs kernel; re-run identical; invariant under later factor amend / exposure re-run). **Known limitations + scope-out** (no covariance/VaR/ES/stress/attribution/benchmark-relative).

---

## Part 7 — Tests
1. **Kernel** (pure): index build + duplicate-currency raise; exact-match allocation; miss ⇒ None; sign preservation; HALF_UP idempotence; hand-computed references.
2. **Sum-to-total (REQ-MKT-003):** Σ result rows == Σ pinned atoms **exactly**, per factor and overall; multi-currency portfolio across ≥3 factors.
3. **Reproducibility:** re-run over the same snapshot ⇒ identical rows; result **invariant under a later factor-definition amend** (EV `record_version` bump) and **under a later exposure re-run** (new atoms don't touch the pinned ones); consume-existing `snapshot_id` path identical to build-in-request.
4. **Model governance:** unregistered `model_version` ⇒ `UnregisteredModelError`, **zero run/rows/audit**; registered ⇒ bound `model_version_id` + `methodology_ref`; `register_factor_exposure_model` idempotent + emits `MODEL.REGISTER`/`MODEL.VERSION`.
5. **Pre-create refusals (zero run/audit):** missing prerequisites; FAILED/RUNNING exposure run; empty/foreign exposure run; empty factor set; non-CURRENCY family; NULL-scope factor; duplicate `currency_code`; cross-tenant factor id.
6. **DQ fail-closed (post-create):** an unmapped atom (`mark_currency` not in the factor set) ⇒ committed **FAILED** run (`outcome='failure'`) + **zero rows** + readable via the run endpoint.
7. **Output contract:** every row non-null `input_snapshot_id`/`calculation_run_id`/`model_version_id`; `code_version`+`environment_id` on the run; snapshot `purpose == FACTOR_EXPOSURE_INPUT`.
8. **IA append-only:** UPDATE/DELETE blocked (ORM `AppendOnlyViolation` + PG **P0001 trigger**, with `irp_app` granted UPDATE/DELETE so the trigger is what's proven).
9. **RLS (PG):** symmetric + FORCE; cross-tenant invisibility; forged-tenant insert 42501; closed 5-table hybrid set unchanged.
10. **Entitlement:** endpoints deny-by-default; **`risk.run`/`risk.view` REUSED — parity test asserts NO grant/catalog change**; `auditor_3l` can `.view` not `.run`.
11. **Lineage:** `snapshot --DEPENDS_ON--> run --ORIGIN--> factor_exposure_result` edges (`run_id` stamped); the DEPENDS_ON edge present on a FAILED run.
12. **Snapshot pins:** EXPOSURE component IA pin shape (NULL valid_from/record_version); FACTOR EV pin `record_version`; `verify` reports factor drift after an amend; content hashes stable.
13. **Endpoint:** POST run (200/201; 422 refusals; 404 unknown; 403 unauthorized); GET run (FAILED surfaced); GET rows; GET one row.
14. **Scope fences:** no `covariance`/`VaR`/`ES`/`stress`/`scenario`/`attribution`/`tracking`/`benchmark`/`regression`/`factor_return` symbol in the factor-exposure modules; no live `list_exposure`/`resolve_factor`/`reconstruct_*` in the compute path (import/AST fence — the P2-3/P3-1 fence precedent); `audit/service.py` byte-unchanged.
15. **Migration:** `0024` applies; `alembic check` drift-clean; downgrade `0024`→`0023` smoke; `APPEND_ONLY_TABLES` includes the new table.

PG-backed variants (`test_factor_exposure_pg.py`) ride the migration job (the P2-6/P3-2 auto-cover precedent). `make check` green (ruff/mypy/pytest/secret-scan/docs-check) + full PG validation on `postgres:16` (`irp_pg_local`).

---

## Part 8 — Acceptance criteria
- Factor exposures **reproduce exactly** from the pinned snapshot; **contributions sum to total within ε (= 0)** — the REQ-MKT-003 acceptance for the allocation leg. **REQ-MKT-003 → In-Progress (partial).**
- The critical invariant holds for every row (snapshot + run + registered model_version + methodology_ref + code_version + environment_id + audit + lineage + DQ).
- **Reproducible under input correction** (factor amend / exposure re-run — TR-09/CTRL-018); IA append-only + symmetric RLS enforced; DQ fail-closed both timings; `audit/service.py` untouched; **no new permission**; head `0024_factor_exposure`.
- CTRL-003 exercised on the second model-driven run; CTRL-009/002/014/017/018/006/013/011/023/026/029/032 evidenced per the decision record Part 3.

## Part 9 — Adversarial review log
Shared with `p3_3_decision_record.md` **Part 5** (disciplined single-pass 8-lens review; all material findings folded — the RTM partial-advancement wording, the rejected re-roll alternative, the no-hard-FK `factor_id`, the CTRL-003 "exercised again" correction, the duplicate-currency refusal moved pre-create, and the housekeeping scope confinement). Nothing implemented; no P3-4+ scope pulled forward; no frontend.

## Part 10 — Risks & open questions
- **"Currency bucketing" critique** — v1 may read as an exposure breakdown rather than a factor model → mitigated by the honest fundamental-model-membership framing + the named beta/regression prerequisites (OD-P3-3-A) + the dimension-generic kernel; **OQ-P3-3-1 sign-off.**
- **Mark-currency proxy** — `mark_currency` ≈ denomination currency is a declared assumption; instruments marked in a non-native currency would misallocate → recorded as a limitation; the instrument-denomination dimension is the ASSET_CLASS-era extension (needs the instrument EV pin).
- **Atom-set size** — one component per atom; large portfolios mean many components → acceptable at current volumes (the AD-004-R1 Postgres-first stance; revisit with the same volume trigger).
- **No residual bucket** — an unmapped atom fails the whole run; operationally a tenant must hold a complete currency-factor set → intended v1 rigor (fail-closed over silent residual); a governed UNMAPPED/residual convention is a recorded v2 option.
- **Open (settled at build):** exact endpoint paths/response DTOs; whether `FactorExposureActor` is a new dataclass or the shared actor shape; the `FactorPin`/`AtomPin` kernel dataclass shapes.

## Part 11 — Implementation kickoff prompt (when approved)
> "Begin P3-3 implementation only: the factor-exposure engine (allocation v1), per `p3_3_decision_record.md` (OD-P3-3-A…O) + this plan. Build EXACTLY: `risk/factor_kernel.py` (pure `build_factor_index` + `allocate_atom`; indicator loading 1; exact `mark_currency` match; `quantize_HALF_UP(…, 6)`); `risk/factor_service.py` (`run_factor_exposure` mirroring `run_sensitivities` — `assert_registered_model_version` pre-create; exposure-run `COMPLETED` + factor-set CURRENCY-family/non-null-scope/no-duplicate-currency pre-create gates; DEPENDS_ON before the DQ gate; `risk.factor_exposure.completeness` fail-closed; post-create FAILED + zero rows on an unmapped atom; readers); `FactorExposureResult` in `risk/models.py` (ENT-028 family; IA append-only; UNIQUE `(calculation_run_id, portfolio_id, instrument_id, factor_id)`; carried non-null `input_snapshot_id`/`model_version_id`; `loading` Numeric(20,12) v1=1; `exposure_amount` Numeric(28,6)); `RUN_TYPE_FACTOR_EXPOSURE` + reserved `RISK.FACTOR_EXPOSURE_CREATE` in `risk/events.py`; `register_factor_exposure_model` in `risk/bootstrap.py` (`risk.factor_exposure.allocation` v1; `methodology_ref` → `05_analytics_methodologies/factor_exposure_allocation_v1.md`); snapshot `COMPONENT_KIND_EXPOSURE` (IA pin) + `COMPONENT_KIND_FACTOR` (EV pin) + `PURPOSE_FACTOR_EXPOSURE_INPUT` + `exposure_content`/`factor_content` + `build_factor_exposure_snapshot` + `_reresolve_content` handlers; migration `0024_factor_exposure` (table + P0001 trigger + symmetric FORCE RLS; head `0023`→`0024`); the `api/risk.py` factor-exposure endpoints gated by the EXISTING `risk.run`/`risk.view`/`model.inventory.register`; write the methodology doc; the Part-7 tests; the R-07 governance-doc amendments (ENT-028 second realization — NO new canonical id; RISK.FACTOR_EXPOSURE_CREATE reserved; entitlement-reuse note; control-matrix P3-3 block; REQ-MKT-003 → In-Progress partial; temporal note). STRICT EXCLUSIONS: NO covariance/volatility model; NO VaR/ES; NO stress/scenario; NO benchmark-relative/active-risk/tracking-error; NO performance attribution; NO regression/beta estimation; NO factor-loading capture; NO `factor_return` consumption or `COMPONENT_KIND_FACTOR_RETURN`; NO new permission or audit emitter; NO `audit/service.py` change; NO BYPASSRLS/hybrid; NO reporting/dashboard/frontend; NO P3-4…P3-7 work. 8-lens adversarial review; `make check` + full PG validation (`irp_pg_local`). Do not commit until I approve."
