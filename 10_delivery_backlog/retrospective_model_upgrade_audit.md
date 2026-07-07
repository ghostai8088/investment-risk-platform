# Retrospective Model-Upgrade Audit (Fable 5) — 2026-07-06

## Document Control

| Field | Value |
|---|---|
| Purpose | Record the targeted retrospective audit run after the Opus 4.8 → Fable 5 model change: (1) the P3-1 quant kernel + methodology verified against **externally computed ground truth**; (2) a systematic **governance-drift sweep** (docs vs shipped code); (3) a **cross-cutting invariants confirmation**. Findings + dispositions below; the fixes land in this commit. |
| Status | **Audit record — read-only review + docs-only fixes; NO code, NO migration, NO behavior change.** |
| HEAD at audit | `b3d3923` (operating-discipline modernization; P3-3 plan `f941d50` = CI #91 green); migration head `0023_factor_return`. |
| Method | Per the modernized `claude_operating_instructions.md` review pattern: refute-by-default; every claim verified by **reading code / executing checks**, not recall; quant references recomputed via an **independent code path** (`math.exp` float arithmetic + first-principles re-derivation — fully separate from the kernel's `Decimal.exp`); findings recorded with dispositions, no verdict tallies. |

---

## Part 1 — Quant kernel + methodology (`risk/kernel.py`, `sensitivities_analytic_v1.md`)

**Verified sound (executed evidence, not assertion):**
- The closed form was re-derived from first principles: `PV = DF(T) = e^(−zT)` under continuous compounding ⇒ `∂PV/∂z = −T·DF` ⇒ `DV01 = −T·DF·1bp`. The DISCOUNT_FACTOR-direct path is correct (`∂PV/∂z = −T·DF` holds however `DF` was obtained, given the bumped rate is the continuously-compounded zero).
- **All four test reference values recomputed independently** (float `math.exp` path) and matched exactly after HALF_UP-12 quantization: 1Y ZERO 5% → `−0.000095122942`; 2Y DF 0.90 → `−0.000180000000`; 5Y SPREAD 1% → `−0.000475614712`; 2Y DF 1.0 → `−0.000200000000`. Rounding-boundary distances checked (13th-dp fractions 0.45 / 0.25 — decisively far from the 0.5 boundary, so the independent float check is conclusive).
- The 7 pure kernel tests **executed green** in this session.
- Sign convention (negative DV01 for a long claim under a rate rise) is declared in the methodology and consistent across kernel/doc/tests. Negative rates (DF > 1) and the `tenor_days > 0` guard behave correctly. Kernel `exp` at 50-digit `Decimal` precision then quantized — deterministic, no engine split.
- The methodology doc's Assumptions/Limitations match the `risk/bootstrap.py` `SENSITIVITY_ASSUMPTIONS`/`SENSITIVITY_LIMITATIONS` constants (the registry-mirrored rows) — no doc-vs-registry drift.

**Finding Q-1 (LOW, disposition: DEFERRED to the v2 methodology version).** The spread-DV01 is computed on the spread node **standalone** (`DF = e^(−sT)` — the spread as the only discount driver). A jointly-discounted credit claim's CS01 would be `−T·e^(−(r+s)T)·1bp` (smaller in magnitude). The formula is declared exactly (reproducible), but the Limitations list does not name the standalone-spread simplification explicitly. The v1 referent is declared immutable and the registered `model_limitation` rows are IA — so the fix is **not** an edit to the v1 doc: the limitation line ("spread-DV01 discounts at the spread alone; joint base+spread discounting needs a curve-join convention — deferred") is recorded HERE and MUST be carried into any v2 sensitivity methodology / consumed by P3-4+ planning. No code change; the number is correct as declared.

## Part 2 — Governance-drift sweep (docs vs shipped code)

**Theme found: "ratified-in-planning" annotations never flipped to REALIZED when the implementation shipped.** Ten stale status claims + two stale roadmap docs + one missing-annotation set — **all fixed in this commit**:

| # | Location | Stale claim | Fix |
|---|---|---|---|
| D-1 | `audit_event_taxonomy.md` SNAPSHOT row | "RESERVED …; NOT activated" | ACTIVATED at P2-1 (`3629baa`) |
| D-2 | `temporal_reproducibility_standard.md` §IA | ENT-049/050 "planned-not-implemented" | REALIZED P2-1 (`3629baa`, `0016`) |
| D-3 | `temporal_reproducibility_standard.md` P2-3 note | "Planned, NOT implemented … migration `0018`" | REALIZED P2-3 (`da178fc`, `0018`) |
| D-4 | `entitlement_sod_model.md` dataset_snapshot row | "RESERVED / PLANNED … NOT minted … will pin at implementation" | MINTED P2-1; pinned by `test_snapshot_permissions_grants_as_ratified` (verified to exist) |
| D-5 | `entitlement_sod_model.md` exposure row | "RATIFIED-IN-PLANNING … NOT yet wired … will pin at implementation" | WIRED P2-3 (`da178fc`); pinned by `test_exposure_permissions_grants_as_ratified` (verified to exist) |
| D-6 | `canonical_data_model_standard.md` ENT-014 | "RATIFIED-IN-PLANNING … Planned, NOT implemented … head stays `0017`" | REALIZED P2-3 (`da178fc`, `0018`) |
| D-7 | `canonical_data_model_standard.md` ENT-026 | "binding wired (ratified-in-planning)… environment_id ships with `0018`" | REALIZED `da178fc`; `environment_id` shipped |
| D-8 | `canonical_data_model_standard.md` P2-0 note | ENT-049/050 "Planned, NOT implemented; head stays `0015`" | REALIZED P2-1 (`3629baa`, `0016`) |
| D-9 | `control_matrix_skeleton.md` P2-0/P2-1 block | "PLANNED, NOT IMPLEMENTED … no code/migration this phase" | REALIZED P2-1 (`3629baa`) |
| D-10 | `control_matrix_skeleton.md` P2-3 block | "PLANNED, migration `0018` NOT yet built" | REALIZED `da178fc` |
| D-11 | `canonical_data_model_standard.md` ENT-020/021/023 rows | NO realization notes despite P2-4/P2-5 realization (every other realized ENT is annotated) | Concise realization notes added |
| D-12 | `docs/project_memory/build_plan.md` | Frozen at "NEXT: P2 closeout/P3 readiness"; "Still FUTURE: … sensitivities (ENT-027/028)" though ENT-028 is realized | P3 section added (P3-0…P3-3 status + P3-4…P3-7 sequence); Still-FUTURE list corrected |
| D-13 | `docs/project_memory/decision_summary.md` | Frozen at P2-6 — no OD-P3-0/P3-1/P3-2 entries; "factor_return + factor models → P3+" though ENT-025/028 realized | Compact P3-0/P3-1/P3-2/P3-3 ratified-decision entries added; deferral line + do-not-relitigate ledger corrected |

**Verified clean (no drift):** the `MARKET.FACTOR_RETURN_*` / `REFERENCE.*` / reserved `RISK.SENSITIVITY_CREATE` constants exist in code as documented; `CALC.RUN_CREATE`/`RUN_STATUS_CHANGE` match the shipped emitters; the EXPOSURE (EVT-210) and RISK (EVT-220) rows are genuinely reserved-not-emitted; the CTRL-003 evidence citation (`test_unregistered_model_version_refused_pre_create_zero_run_zero_rows`) and both entitlement parity tests exist verbatim; the `FACTOR_FAMILIES` vocab, factor identity key, and `Numeric` scales match the canonical annotations; REQ-MKT-003's acceptance text matches what the P3-3 plan cites.

## Part 3 — Cross-cutting invariants (confirmation pass; mostly CI-covered)

- `APPEND_ONLY_TABLES` per migration: `0022` = `sensitivity_result` only ✔; `0020` = `curve_point` ✔; `0023` installs **no** `irp_prevent_mutation` trigger (factor tables deliberately not append-only) ✔.
- The closed hybrid set is exactly the five P1B-1 tables (`currency, calendar, calendar_holiday, rating_scale, rating_grade` — migration `0008`) ✔; all risk/market tables symmetric.
- No stray `0024` migration exists (P3-3 not implemented) ✔.

## Dispositions summary
- **Q-1** deferred (recorded above; carries into v2 methodology + P3-4 planning).
- **D-1…D-13** fixed in this commit (docs-only).
- Nothing refuted-as-wrong in code; **zero code/behavior findings** — the kernel, constants, grants, and triggers all match their governance claims once the stale planning-era status text is corrected.

## Standing lesson (feeds the operating discipline)
The recurring defect class is **status decay**: a "ratified-in-planning / reserved / will-be-wired" annotation written at the planning slice is not revisited at the implementation slice. Rule going forward (add to the R-07 fold-at-implementation checklist): **an implementation slice's governance amendments MUST flip every planning-era status qualifier its plan introduced** — grep the five governance docs for `PLANNED / NOT implemented / NOT minted / NOT activated / will pin / ratified-in-planning` naming the slice before closing it.
