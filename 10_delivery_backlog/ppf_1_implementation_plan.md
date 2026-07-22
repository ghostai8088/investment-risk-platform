# PPF-1 Implementation Plan — the pure-private factor return series (Wave-10 slice 3, §2.1 arc slice 1)

Companion to `ppf_1_decision_record.md` (read it first — the ODs/OQs/verifier folds govern). One commit per step; `make check` green at every step boundary; full-PG + migration smoke at the gate step. Model counts move 17→18 governed numbers at the demo step.

## Step sequence

1. **Vocab mints + the isolation guards (OD-A/OD-B — the verifier-mandated trio).**
   `FACTOR_FAMILY_PRIVATE` into `FACTOR_FAMILIES`; `FREQUENCY_APPRAISAL` admitted at factor registration ONLY for PRIVATE-family factors (all other families stay DAILY-only). Split the capture-admission set: `PROXY_MAPPING_CAPTURE_FAMILIES = LOADING_FACTOR_FAMILIES + (PRIVATE,)` used by `_resolve_factor_id` (`marketdata/proxy_mapping.py:356-361`) ONLY — the FL-1 binder gate and RBSA candidate gate keep `LOADING_FACTOR_FAMILIES` byte-identical; update the shared-verbatim comment (`marketdata/models.py:160-163`) to record the deliberate split. Capture invariant: a PRIVATE-family row MUST be `MANUAL` (new validation + test). Family-filter the proxy-row query in `build_factor_exposure_snapshot` (`snapshot/service.py:717-730`) to the binder-admitted families. **Regression proof: existing exposure/VaR/covariance suites byte-identical; a new test seeds a PRIVATE membership row and proves PA-2/FL-1/total-VaR runs are unchanged (the exact scenario the verifier showed would refuse pre-create unguarded).**

2. **The shared alignment helper extraction (OD-C fold).**
   Extract `_compound` + the per-period window-compounding core of `_build_design` from `risk/proxy_weight_service.py:202-210,338-351` into a shared module (e.g. `risk/period_alignment.py`), PA-3 delegating. Behavior-preserving: the PA-3 suite passes byte-identical; the half-open `(period_start, period_end]` window and the fail-closed per-period coverage gate move verbatim.

3. **Migration `0047_private_factor_return` + the result model.**
   `private_factor_return_result` (next free ENT, confirmed at the docs census): run-grain rows — `PURE_PRIVATE_PERIOD` (segment factor FK, period_start/end, metric_value 12dp, member_count) + `PURE_PRIVATE_SUMMARY` (member_count, period_count, pooled stdev). Template = `0045_pacing_projection` verbatim: PK, NOT-NULL run/snapshot/model-version FKs, entity FKs, run-grain UNIQUE, tenant/FK indexes, ENABLE+FORCE RLS symmetric own-tenant policy, append-only trigger reusing `irp_prevent_mutation()`, honestly-destructive downgrade, ≤63-char assert, NO grants. Advance the per-slice migration-guard ledger (0046→0047) + the synthetic guard comment.

4. **The snapshot builder + serializer.**
   `build_private_factor_return_snapshot`: pins per member — the COMPLETED desmoothing run's `DESMOOTHED_PERIOD` rows (existing kind/serializer), the current-head REGRESSION proxy blend (the var-total flavor, `snapshot/service.py:2504-2561` precedent, single-cited-run adjudication), the factor returns covering the union of member periods, the membership rows (MANUAL, PRIVATE-family — the new pin flavor). Fail-closed: no membership rows → refuse; a member without a REGRESSION blend → named-gap refusal (P3-7 rule).

5. **The binder + kernel (`risk/private_factor_service.py` + kernel).**
   Model code `risk.factor_return.pure_private` (registrar + declared parameters: pooling convention, intercept convention, min_members — the model identity); `run_private_factor_return` via `execute_governed_run`: adjudicate pins pre-create → per member `pp_i,t = desmoothed_i,t − Σ_f w_i,f·R_f,t` (the shared helper compounds `R_f` over each member period) → identical-interval pooling (grid mismatch = named-gap refusal) → persist PERIOD rows + the SUMMARY row (member_count disclosed). min_members gate fail-closed. Runaway/envelope guards per the CC-2 lesson (values are returns — the (28,6)-class column cap is far; still assert finiteness + a sane envelope).

6. **API reads (rule 7, in-slice) + OpenAPI regen.**
   `GET /risk/private-factor-returns` (list; filters: segment factor_id, period range) + `/latest` (newest-run resolver via `calc/reads.py` — declared before any `/{id}`), `risk.view`-gated. Regenerate `openapi.json` + FE types (`make gen-api-check` clean; the decimal fields serialize `string`; `member_count`/`period_count` join the known-integer-counts guard).

7. **Demo stage + docs.**
   Seed the 2 segment factors (PRIVATE_CREDIT_GLOBAL, PRIVATE_EQUITY_GLOBAL or region-graind names per the census) + 2 MANUAL membership rows; run both segments at min_members=1 (PC-BRIDGEWATER-II; PE-HARBOR-IV) — zero new book data; counts advance by the stage's codes/records/runs only. Docs: ENT census + REALIZED stamp, the 18th-governed-number counts sweep, roadmap dated log row (at closeout), `list_proxy_mappings` interleaving disclosure.

8. **Gate + review.**
   Full battery: `make check`, full-PG affected-family suites (fresh schema + the drop-role isolation recipe), 0047 downgrade/upgrade smoke, `alembic check`, `make fe-check`, `make gen-api-check`, pip-audit. Then the 4-finder adversarial review: (1) econometric correctness vs the cited construction (Shepard 2014/2025; the two-step disclosure honest); (2) doctrine/security (6 hard invariants; FORCE RLS on 0047; no new mint beyond the ratified vocab); (3) family-isolation adversarial (attack the three guards — try to make a PRIVATE row move ANY existing number); (4) read-correctness + demo honesty (the single-member disclosure legible; no fabricated pooling). Fold; closeout per the closure-discipline check.

## Effort/model note
Steps 1-2 are the risk-bearing surgery on shipped families (regression-heavy); steps 3-6 are the well-worn governed-number template; step 5's kernel is small (the math is subtraction + pooling — the rigor is in the pinning and the refusal paths).
