# P3-6 Implementation Plan — stress/scenario analytics (factor-shock v1)

> Companion to `p3_6_decision_record.md`. Gated behind OQ-P3-6-1…6 ratification. The TENTH governed
> number, realizing ENT-029 + ENT-030 (migration `0035_scenario`). Sequenced so the tree stays green
> between steps; every element mirrors a shipped exemplar (named per step). Fixtures follow the
> TD-1 realism rule; goldens ship their derivation (the MD-H1 rule); the MD-H1 design-completeness
> checklist is applied at each gate below.

## Step 0 — Branch + baseline
- Branch `p3-6` off `main` (`b90481f`); confirm `make check` green at baseline.

## Step 1 — Migration `0035_scenario` + ORM models
- `scenario_definition` (EV; per-tenant unique `code`; `scenario_type` String(20), binder-enforced
  vocab; `record_version`) — the `factor` EV exemplar.
- `scenario_shock` (FR bitemporal; current-head partial-unique on `(tenant_id,
  scenario_definition_id, factor_id)` WHERE both axes open; `shock_value PreciseDecimal(20,12)`;
  `shock_type` String(20) default `RETURN`; hard FKs to definition + factor) — the
  `proxy_mapping`/`benchmark_constituent` exemplar.
- `scenario_result` (IA TRUE append-only → `APPEND_ONLY_TABLES` + P0001 trigger + ORM guard; grain
  `(calculation_run_id, metric_type, factor_id)`, `factor_id` nullable; `pnl Numeric(28,6)`;
  echoed `shock_value`/`exposure_amount`; coverage counts on the TOTAL row; `base_currency`) — the
  `factor_exposure_result` exemplar.
- All three symmetric FORCE RLS; register models in `irp_shared.models`; the MD-H1 identifier
  sweeps validate names automatically. Downgrade tested `0035 ↔ 0034`.

## Step 2 — `scenario` binder (`irp_shared/risk/scenario.py` or sibling module)
- Definition: `create_scenario_definition` / `update_scenario_definition` (EV; `REFERENCE.CREATE`/
  `REFERENCE.UPDATE`; MANUAL-source ORIGIN lineage via the race-safe `resolve_or_insert`).
- Shocks (FR): `capture_scenario_shock` / `supersede_scenario_shock` / `correct_scenario_shock` /
  `reconstruct_shock_as_of` / `list_scenario_shocks` — the membership protocol; the MD-H1
  window-coherence guard wired from birth; finiteness guard on `shock_value`
  (`parse_strict_decimal`); CURRENCY-family factor scope ENFORCED at capture (the PA-0 fold);
  EMPTY-set refusal: a definition with zero open shocks cannot be run (422, checked at
  adjudication) and `capture` requires ≥1 shock value semantics per row anyway.
- DQ gate: required-fields NOT_NULL presence rule (race-safe from birth).

## Step 3 — Model bootstrap
- `register_scenario_model` in `risk/bootstrap.py` via `resolve_or_register_model`/`_version`
  (`risk.scenario.factor_shock` v1; `code_version`-only identity; assumptions/limitations per
  OD-D). Methodology ref → Step 7's doc.

## Step 4 — Snapshot builder
- `PURPOSE_SCENARIO_INPUT` + NEW `COMPONENT_KIND_SCENARIO`. Pins: the exposure rows of ONE
  COMPLETED `FACTOR_EXPOSURE` run (`COMPONENT_KIND_FACTOR_EXPOSURE`, reused) + the definition
  header AND its OPEN shock set as one hashed component (`COMPONENT_KIND_SCENARIO`). Refuses
  pre-write: non-COMPLETED/foreign exposure run; zero open shocks; empty exposure content
  (the BT-1 empty-list fold, applied at design time).

## Step 5 — `run_scenario` service
- `execute_governed_run` scaffold (the model-bound variant); uniform pre-create adjudication on
  BOTH entry paths (build-in-request + consume-existing snapshot — the P3-3 lesson):
  tenant guard (`assert_portfolio_in_tenant`), model identity (`assert_model_version_of`),
  pinned-only reads (AD-014), `parse_strict_decimal` on every consumed decimal, exposed-factor ↔
  shock join per OD-G/OQ-3 semantics, magnitude gate BOTH sides + echo gate (the P3-8/BT-1
  lessons), `_MAX_RESULT_ABS` envelope. Failure paths leave no RUNNING orphan
  (`assert_no_running_orphan` in every refusal test).
- Kernel is a one-liner per factor (`pnl_i = quantize_HALF_UP(exposure_i × shock_i, 6)`); total =
  Σ of the quantized rows (declared convention; exact by construction — asserted).

## Step 6 — API + FE
- `/risk/scenarios` (create/update definition; capture/supersede/correct shocks; as-of + list) —
  `risk.run` gated writes, `risk.view` reads; the family `_WRITE_ERRORS` map dispatched through the
  MD-H1 `_raise_mapped_write` core (window-coherence → 422; duplicates → discriminated 409).
- `/risk/scenario-runs` (run + get + list) mirroring the VaR/backtest endpoints; runs surface in
  the existing risk runs FE listing (verify the new `run_type` renders; extend the FE family map if
  the listing filters by known types).

## Step 7 — Methodology doc
- `05_analytics_methodologies/scenario_factor_shock_v1.md`: the linear application rule, shock
  semantics (RETURN fractions; unnamed = unchanged with the coverage rails), quantization, TR-09,
  the v2 (historical replay) + v3 (plausibility search) seams, Part-2 citations.

## Step 8 — Tests
- SQLite: definition EV protocol; shock FR protocol (incl. window-coherence negative + the
  differing-`valid_from` loop-coverage pattern where multi-row); CURRENCY-scope refusal; empty-set
  refusals; full-stack golden over a REAL chain (portfolio → exposure → factor-exposure → scenario)
  with the derivation comment; TR-09 BOTH sides (post-run supersede immovability + byte-identical
  re-run); coverage-count assertions; append-only + run_type + zero-`RISK.*`-audit + migration-head
  + entitlement-parity guards.
- PG: RLS isolation ×3 tables; append-only trigger; the FR close-out; downgrade smoke.
- Endpoint: happy paths, 403 deny-by-default, 404 cross-tenant, 409 duplicate/no-head, 422
  window-coherence + vocab + empty-set.
- CI: new PG RLS step(s) for the three tables.

## Step 9 — Docs alignment (impl commit)
- `canonical_data_model_standard.md` ENT-029/030 realization notes; RTM REQ-MKT-004 →
  In-Progress; `audit_event_taxonomy.md` `RISK.SCENARIO_CREATE` reservation appended to the
  EVT-220 row; roadmap slice row updated at closeout.

## Step 10 — Validation + review + gate
- Full battery: `make check` (incl. format), full local-PG clean-schema + downgrade smoke,
  fe-check, diff fences (`audit/service.py` FROZEN; no permission/audit/role mint beyond the
  reserved-not-emitted comment).
- **Full 4-finder review** (OD-J); fold pre-commit per the clean-code bar; Part 6 dispositions.
- Tier-2 gate: commit + push `p3-6` on explicit approval; USER opens+merges the PR; CI-watch;
  closeout PR follows (Part 6 + docs refresh + the Wave-2 close review readiness note).
