# P3-1 Implementation Plan — Analytic Sensitivities (the first reproducible governed risk number)

## Document Control

| Field | Value |
|---|---|
| Purpose | The build contract for P3-1: the methodology-doc framework, the model-version-for-risk hardening, and **curve-node analytic DV01 / credit-spread-DV01** as the first governed, reproducible risk number — bound to `dataset_snapshot` + `calculation_run` + a **registered `model_version`**, IA append-only, audited, lineaged, DQ-gated. Companion to `p3_1_decision_record.md` (OD-P3-1-A…O). |
| Status | **Implementation PLAN — PLANNING ONLY; NO code, NO migrations, NO risk/sensitivity/model implementation.** |
| HEAD at writing | `07607a5`; migration head `0021_benchmark`; origin/main clean. |
| Predecessors | `p3_1_decision_record.md`; `p3_0_decision_record.md`; `p2_3_exposure_implementation_plan.md` (the `run_exposure` governed-run template mirrored verbatim). |
| Review | 8-lens UltraCode review — **Part 9**. |

> **Critical invariant (the gate every row passes):** no `sensitivity_result` row exists unless bound to **`dataset_snapshot` + `calculation_run` + a registered `model_version` + `methodology_ref` + `code_version` + `environment_id` + `CALC.RUN_*` audit + `snapshot→run→result` lineage + a passed fail-closed DQ gate**, and is **reproducible** from the snapshot-pinned curve content (no live read). **This plan builds NOTHING.**

---

## Part 1 — Module map (what the implementation slice will touch)

| Area | Change | New/Modified |
|---|---|---|
| `packages/shared-python/src/irp_shared/risk/__init__.py` | new package | NEW |
| `…/risk/models.py` | `SensitivityResult` (ENT-028) + constants (`SENSITIVITY_TYPE_DV01`/`_SPREAD_DV01`, `RUN_TYPE_SENSITIVITY`) + IA append-only ORM guard | NEW |
| `…/risk/kernel.py` | the **pure analytic kernel** (`node_dv01(...)`, `node_spread_dv01(...)`) — closed-form, no DB, no interpolation | NEW |
| `…/risk/service.py` | **`run_sensitivities(...)`** — the governed-run binder (mirrors `run_exposure`) | NEW |
| `…/risk/events.py` | `RUN_TYPE_SENSITIVITY`, `RISK_SENSITIVITY_CREATE_EVENT_RESERVED` (reserved, not emitted), `SensitivityActor` | NEW |
| `…/snapshot/models.py` | add `COMPONENT_KIND_CURVE="CURVE"` + `PURPOSE_SENSITIVITY_INPUT="SENSITIVITY_INPUT"` (app constants) | MODIFIED |
| `…/snapshot/serialize.py` | `curve_content(header, nodes)` serializer | MODIFIED |
| `…/snapshot/service.py` | the `PURPOSE_SENSITIVITY_INPUT` curve-pinning build path + `_reresolve_content` CURVE handler | MODIFIED |
| `migrations/versions/0022_sensitivity.py` | `sensitivity_result` table (IA append-only + P0001 trigger + symmetric RLS); **head `0021`→`0022`** | NEW |
| `apps/backend/src/irp_backend/api/risk.py` | `risk_router` (POST run, GET list) | NEW |
| `…/entitlement/bootstrap.py` (or catalog) | mint `risk.view` + `risk.run` | MODIFIED |
| `05_analytics_methodologies/` | the per-method template + `sensitivities_analytic_v1.md` | NEW |
| tests (shared + PG + endpoint) | the Part-7 test groups | NEW |
| governance docs (canonical / audit taxonomy / entitlement / control matrix / RTM / temporal) | R-07 amendments | MODIFIED |

**Untouched (hard):** `audit/service.py` (FROZEN); `curve.py`/`marketdata` (read-only via `reconstruct_curve_as_of`/`list_curve_points`/`resolve_curve`); `exposure/*`; the DQ `Protocol`; no BYPASSRLS; no hybrid path.

---

## Part 2 — `sensitivity_result` (ENT-028) table design
IA TRUE append-only, run-bound + snapshot-gated + model_version-bound. Columns:

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | GUID | NO | PrimaryKeyMixin |
| `tenant_id` | GUID | NO | TenantMixin (server-stamped) |
| `system_from` | DateTime(tz) | NO | ImmutableAppendOnlyMixin (append timestamp) |
| `calculation_run_id` | GUID FK→`calculation_run.run_id` | NO | indexed; the governing run |
| `input_snapshot_id` | GUID FK→`dataset_snapshot.id` | NO | indexed; the pinned curve snapshot |
| `model_version_id` | GUID FK→`model_version.id` | NO | **NON-NULL — registered** (the hardening vs exposure) |
| `curve_id` | GUID | NO | the pinned curve header version the node belongs to |
| `curve_type` | String(30) | NO | captured from the pinned curve |
| `currency_code` | String(3) | NO | the curve currency = the DV01 currency basis |
| `reference_key` | String(150) | NO | `"NONE"` (rate) / issuer-rating (credit) |
| `value_type` | String(30) | NO | `ZERO_RATE`/`DISCOUNT_FACTOR`/`SPREAD` |
| `tenor_days` | Integer | NO | the node key (`>0`) |
| `tenor_label` | String(10) | NO | captured label |
| `sensitivity_type` | String(30) | NO | `DV01` / `SPREAD_DV01` |
| `sensitivity_value` | Numeric(28,12) | NO | `quantize_HALF_UP(−T·DF·1bp, 12)`; per unit notional |
| `bump_bps` | Numeric(10,4) | NO | the convention (`1.0000` = 1bp) |

**Grain / unique:** the enforceable UNIQUE key is the **5-tuple `(calculation_run_id, curve_id, value_type, tenor_days, sensitivity_type)`** — `input_snapshot_id` + `model_version_id` are carried NON-NULL but functionally determined by `calculation_run_id` (one run → one snapshot + one model_version), so they are **not** in the key (reconciles OD-P3-1-B). **IA append-only:** `ImmutableAppendOnlyMixin` + `event.listen(before_update/before_delete → AppendOnlyViolation)` + migration `APPEND_ONLY_TABLES` + `irp_prevent_mutation` P0001 trigger. **RLS:** symmetric `tenant_isolation_sensitivity_result` (USING == WITH CHECK == own-tenant; ENABLE + FORCE). `portfolio_id`/`instrument_id` intentionally absent (curve-intrinsic v1, OD-P3-1-B).

---

## Part 3 — `run_sensitivities(...)` binder (mirrors `run_exposure`, with the model-version hardening)
```
run_sensitivities(session, *, acting_tenant, actor, code_version, environment_id,
                  model_version_id, curve_selectors, as_of_valid_at,
                  as_of_known_at=None, snapshot_id=None) -> SensitivityRunResult
```
Ordered steps (the P2-3 template + the model gate):
- **(a) pre-create gate** — validate `code_version`, `environment_id`, `actor.actor_id` truthy; **`assert_registered_model_version(session, model_version_id, tenant_id=acting_tenant)`** (→ `UnregisteredModelError` = **zero run/rows/audit**); validate `curve_selectors` non-empty (or a `snapshot_id`). Raise `SensitivityInputError` on the rest. **All pre-create ⇒ zero run/audit.**
- **(b) snapshot** — `resolve_snapshot` (validate `purpose==PURPOSE_SENSITIVITY_INPUT`) **or** `build_snapshot(purpose=PURPOSE_SENSITIVITY_INPUT, curve_selectors=…, as_of_valid_at=…)` pinning `COMPONENT_KIND_CURVE` component(s). A **`curve_selector` is the full `reconstruct_curve_as_of` logical key** `(curve_type, currency_code, reference_key, curve_date, curve_source)` resolved at `as_of_valid_at`/`as_of_known_at` → the curve header version + its `list_curve_points` node set. Cross-tenant/unknown/empty ⇒ pre-create refusal.
- **(c) run** — `create_run(run_type=RUN_TYPE_SENSITIVITY, initiated_by=actor.actor_id, input_snapshot_id=snapshot.id, model_version_id=model_version_id, code_version=…, environment_id=…)` → `CALC.RUN_CREATE`; `update_run_status(RUNNING)` → `CALC.RUN_STATUS_CHANGE`. **From here failures are post-create FAILED.**
- **(d) read pinned content** — `list_components(snapshot)` → parse `COMPONENT_KIND_CURVE` `captured_content` (header + nodes) **only** — **NO live `reconstruct_curve_as_of`/`list_curve_points`** (the AD-014 reproducibility invariant).
- **(e) compute** — for each pinned curve, for each usable node, call the pure kernel `node_dv01`/`node_spread_dv01` (OD-P3-1-G closed form); collect rows + `gaps` (unusable nodes / missing required value_type).
- **(f) DQ gate (fail-closed)** — `_run_sensitivity_gate` → `run_quality_check` (rule `risk.sensitivity.completeness`): curve present + required value_type nodes + `tenor_days>0` + no cross-tenant. `DataQualityError` ⇒ `update_run_status(FAILED, outcome='failure')` + return `rows=[]` (committed FAILED run, **zero result rows**).
- **(g) governed write** — `record_internal_lineage(snapshot→run, DEPENDS_ON)`; add rows + `flush`; `record_run_lineage(run→each row, ORIGIN)`; `update_run_status(COMPLETED)`. Any emit-path raise ⇒ co-transactional rollback (CTRL-032) = zero run/rows/audit.

**`SensitivityRunResult(run, status, rows, failure_reason)`.** Differences from `run_exposure`: `model_version_id` **mandatory + asserted** (not N/A); inputs are curves (not positions/marks/FX); the kernel is analytic (not a captured-mark rollup).

---

## Part 4 — Pure analytic kernel (`risk/kernel.py`)
No DB, no I/O, fully unit-testable, deterministic. Per node `(tenor_days, value_type, point_value=v)`:
- `T = Decimal(tenor_days) / Decimal(365)` (ACT/365F).
- `DF`: `ZERO_RATE` → `exp(−v·T)`; `DISCOUNT_FACTOR` → `v` **used directly** (the captured `DF`; no implied-zero on the compute path — `DV01=−T·DF·1bp` holds however `DF` was obtained); `SPREAD` → `exp(−v·T)` (spread node standalone).
- `DV01 = quantize_HALF_UP(Decimal(-1) · T · DF · Decimal("0.0001"), 12)`.
- `node_spread_dv01` = the same closed form on a `SPREAD` node → `sensitivity_type=SPREAD_DV01`.
- `PAR_RATE` → **rejected** (raises; deferred — bootstrapping out of scope). The exact formulas + worked examples live in the methodology doc (Part 6).

---

## Part 5 — Snapshot extension (curve pinning)
- `COMPONENT_KIND_CURVE="CURVE"` added to `SNAPSHOT_COMPONENT_KINDS`; `PURPOSE_SENSITIVITY_INPUT="SENSITIVITY_INPUT"` added to `SNAPSHOT_PURPOSES`. **No migration** (`component_kind`/`purpose` are unconstrained strings).
- `curve_content(header, nodes)` in `serialize.py` — header immutable fields (`id/tenant_id/curve_type/currency_code/reference_key/curve_date/curve_source/record_version/valid_from/system_from`) + the ordered node list (`tenor_days/tenor_label/value_type/point_value`); excludes close-out markers; `content_hash=sha256_hex(canonicalize(...))`.
- `build_snapshot` `PURPOSE_SENSITIVITY_INPUT` path: for each curve selector, `reconstruct_curve_as_of(...)` → `list_curve_points(header.id)` → `_append_spec(COMPONENT_KIND_CURVE, "curve", header, curve_content(header, nodes))`; empty ⇒ `EmptySnapshotError`. `_reresolve_content` CURVE handler re-resolves for hash verification.

---

## Part 6 — Methodology doc (`05_analytics_methodologies/sensitivities_analytic_v1.md`)
Linked from `model_version.methodology_ref`. Sections: **Purpose & applicability** (analytic curve-node DV01/spread-DV01; curve-intrinsic; not instrument-attributed). **Inputs + data policy** (captured `curve`/`curve_point`; point-in-time as-of; **no history/estimation window**). **Formulas + numerical standards** (`T=days/365` ACT/365F; continuous compounding; `DF` per value_type; `DV01=−T·DF·1bp`; `quantize_HALF_UP(...,12)`; worked examples). **Assumptions** (→ `model_assumption`: ACT/365F, continuous compounding, nodes-only/no-interpolation, unit notional). **Limitations** (→ `model_limitation`: curve-intrinsic — not instrument/position DV01; no PAR_RATE; no interpolation between nodes; no cross-gamma/convexity). **Validation/reproduction tests** (closed-form vs hand-computed ε; re-run identical; invariant under later curve correction). **Known limitations + scope-out.** A `README.md`/template generalizes the section set for later methods.

---

## Part 7 — Tests
1. **Kernel** (pure): `node_dv01`/`node_spread_dv01` vs hand-computed references within ε; `ZERO_RATE`/`DISCOUNT_FACTOR`/`SPREAD` paths; `PAR_RATE` rejected; quantization HALF_UP.
2. **Reproducibility:** re-run over the same snapshot → byte-identical rows; result **invariant under a later curve supersede/correction** (snapshot-pinned, no live read).
3. **Model-governance:** run with an **unregistered** `model_version` → `UnregisteredModelError`, **zero run/rows/audit**; run with a registered version → bound `model_version_id` + `methodology_ref`.
4. **Output contract:** every row has non-null `input_snapshot_id`/`calculation_run_id`/`model_version_id`; `code_version`+`environment_id` on the run.
5. **IA append-only:** UPDATE/DELETE blocked (ORM `AppendOnlyViolation` + PG P0001 trigger).
6. **RLS (PG):** cross-tenant read/write blocked under FORCE; symmetric.
7. **Entitlement:** `risk.run`/`risk.view` deny-by-default; **auditor_3l can `.view` not `.run`**.
8. **Lineage:** `snapshot --DEPENDS_ON--> run --ORIGIN--> sensitivity_result` edges present.
9. **DQ fail-closed:** missing required value_type node / `tenor_days≤0` → `FAILED` run (`outcome='failure'`) + zero rows.
10. **Endpoint:** POST run (201/200) + GET list (200); unknown read → 404; unauthorized → 403.
11. **Scope fences:** no `VaR`/`factor`/`covariance`/`stress`/`volatility_surface`/interpolation symbol in the risk package (AST/grep fence — the P2-3 fence precedent).

PG-backed variants (`test_*_pg.py`) for RLS + the P0001 trigger. `make check` green (ruff/mypy/pytest/secret-scan/docs-check).

---

## Part 8 — Acceptance criteria
- Analytic DV01/spread-DV01 **reproduce within ε** vs reference (REQ-MKT-002 "greeks reproduce within ε; conventions declared"). 
- The critical invariant holds for every row (snapshot+run+registered model_version+methodology_ref+code_version+environment_id+audit+lineage+DQ).
- **Reproducible under a later curve correction** (TR-09/CTRL-018).
- IA append-only + symmetric RLS enforced; DQ fail-closed; `audit/service.py` untouched; head `0022`.
- **CTRL-003 executable** (assert_registered_model_version load-bearing). **REQ-MKT-002 → In-Progress.**

## Part 9 — UltraCode review log
8-lens adversarial review (shared with `p3_1_decision_record.md` Part 5; full per-lens log there). **Tally: 5 approve · 3 approve_with_changes · 0 block; 0 high / 0 medium.** The Model-Governance/Quant lens **explicitly verified the DV01 math** (`−T·DF·1bp`, ACT/365F, continuous compounding, DISCOUNT_FACTOR-direct, PAR_RATE-deferred, nodes-only, HALF_UP-12) and the `assert_registered_model_version` pre-create hardening. Folds touching THIS plan (all LOW): the unique-key reconciled to the 5-tuple (`input_snapshot_id`/`model_version_id` carried-but-functionally-dependent — Part 2); the DISCOUNT_FACTOR kernel uses the captured DF directly (implied-zero illustrative only — Part 4); `curve_selector` specified as the full `reconstruct_curve_as_of` logical key (Part 3). No high/block; nothing implemented; VaR/ES not pulled forward; gaps honest; no frontend.

## Part 10 — Risks & open questions
- **Over-narrowing risk:** curve-intrinsic v1 may read as "not a portfolio risk number" → mitigated by framing it as the analytic key-rate building block + the explicit instrument-attribution deferral (OD-P3-1-A); **OQ-P3-1-1 sign-off.**
- **Convention disputes** (ACT/365F vs ACT/360; continuous vs annual) → mitigated by declaring them in the methodology doc + `model_assumption` (a reader reproduces exactly); revisable in a v2 model_version.
- **Snapshot-curve-selector ergonomics** (which curves to pin) → the implementation plan's `curve_selectors` (logical keys/ids); a later slice can add scope-driven selection.
- **Model registration mechanism** (seed vs operator) → OD-P3-1-M; decided at build.

## Part 11 — Implementation kickoff prompt (when approved)
> "Begin P3-1 implementation only: analytic sensitivities + methodology framework + model-governance hardening, per `p3_1_decision_record.md` (OD-P3-1-A…O) + this plan. Build EXACTLY: the `irp_shared/risk/` package (`models.py` `SensitivityResult` ENT-028 IA append-only; `kernel.py` pure analytic `node_dv01`/`node_spread_dv01`; `service.py` `run_sensitivities` mirroring `run_exposure` **with `assert_registered_model_version` in the pre-create gate + a mandatory registered `model_version_id`**; `events.py` `RUN_TYPE_SENSITIVITY` + reserved `RISK.SENSITIVITY_CREATE`); the snapshot `COMPONENT_KIND_CURVE` + `PURPOSE_SENSITIVITY_INPUT` + `curve_content` + the curve-pinning build path; migration `0022_sensitivity` (table + P0001 trigger + symmetric RLS; head `0021`→`0022`); `api/risk.py`; mint `risk.view`+`risk.run` (auditor_3l in `.view`); register the sensitivity model + v1 `model_version` (methodology_ref → `05_analytics_methodologies/sensitivities_analytic_v1.md`); write that methodology doc; the Part-7 tests. Conventions: ACT/365F, continuous compounding, 1bp, analytic closed-form, nodes-only/no-interpolation, `ZERO_RATE`+`DISCOUNT_FACTOR`+`SPREAD` (PAR_RATE rejected), `quantize_HALF_UP(...,12)`. STRICT EXCLUSIONS: NO instrument/position key-rate DV01; NO interpolation/bootstrapping/pricing engine; NO PAR_RATE; NO VaR/ES/factor/covariance/stress/scenario; NO options/vega/`volatility_surface`; NO ratings/adjusted-prices/benchmark-relative; NO model-validation workflow; NO reporting/frontend; NO `audit/service.py` change; NO BYPASSRLS/hybrid. 8-lens UltraCode review; `make check` + PG validation. Do not commit until I approve."
