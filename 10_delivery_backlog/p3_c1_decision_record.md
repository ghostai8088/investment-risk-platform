# P3-C1 Decision Record — Hardening / Consolidation Slice (the deferral-register paydown)

| Field | Value |
|---|---|
| Status | **PLANNING RATIFIED** — OQ-P3-C1-1…8 approved by the user at the commit gate (2026-07-07, after a plain-language decision briefing); implementation is a SEPARATE approval |
| Date | 2026-07-07 |
| Basis | The recorded deferral registers of the P3-3/P3-4/P3-5 adversarial reviews (dispositions in each record's Part 7 / the retrospective audit); the R0 behavior-preserving-refactor precedent (`a9b6567`) |
| Grounding | Verified against shipped HEAD `d94e572` (CI #103): `ModelVersion.status` is a nullable String(20) commented "Non-enforcing version status placeholder … NOT a validation gate"; the four risk bootstrap registrars all set `status="REGISTERED"` while the generic `POST /models` path can mint `status=None`; `update_run_status` carries the additive-`outcome` precedent; `calculation_run` is IA status-mutable (the additive `environment_id` precedent); ten `_ERROR_MAP[type(exc)]` exact-type lookups exist; five binders silently prefer `snapshot_id` when both input modes are passed; seven result columns have float53-unsafe contracts (`sensitivity_value(28,12)`, `loading(20,12)`, `exposure_amount(28,6)`×2, `signed_quantity(28,8)`, `mark_value(20,6)`, `fx_rate(28,12)`); the run scaffold now has FOUR risk copies (+ exposure's fifth variant). |
| Sign-off | **OQ-P3-C1-1…8 — APPROVED / RATIFIED by the user (2026-07-07: "Proceed" on the full package, all eight as recommended, after the simplified decision-point briefing).** |

---

## Part 1 — Decisions at a glance

| ID | Decision | Summary |
|---|---|---|
| **OD-P3-C1-A** | slice character | A **hardening/consolidation slice**: NO new governed number, NO new entity/canonical id, NO new permission, NO new audit code. ONE additive migration (`0027_run_failure_reason`). Every change is either behavior-preserving (refactor/parity) or an explicit, tested fail-closed TIGHTENING recorded per item. |
| **OD-P3-C1-B** | REGISTERED-status bind check | **Tighten `assert_model_version_of` (the RISK-family gate all four risk binders route through)** to additionally require `version.status == "REGISTERED"` → `UnregisteredModelError` otherwise. The generic `assert_registered_model_version` and the P7 validation semantics are UNTOUCHED (its placeholder comment updated honestly: status is now ENFORCING at the risk bind, still not a validation gate). Rationale: the risk binders' own documented contract says "a REGISTERED model_version"; a generically-minted `status=None` version currently binds (the P3-5 review's recorded deferral). The four governed registrars already set REGISTERED — governed paths are behavior-unchanged. |
| **OD-P3-C1-C** | `failure_reason` persistence | **Additive `calculation_run.failure_reason` (Text, nullable)** — migration `0027` (the `environment_id` additive precedent on the status-mutable IA table). `update_run_status` gains an optional `failure_reason=None` param (additive; existing callers unchanged; the audit event payload is NOT changed — the reason lives on the run row, the DQ rows remain the durable defect evidence). The four risk binders persist their existing reason strings at the FAILED transition VERBATIM; the four GET-run endpoints surface `run.failure_reason` instead of the hardcoded `None`. |
| **OD-P3-C1-D** | run-scaffold extraction | **Extract the shared governed-run tail** (`create_run` → RUNNING → DEPENDS_ON → compute → fail-closed gate → [FAILED + persisted reason] or [row write + per-row ORIGIN + COMPLETED]) into one helper consumed by the FOUR risk binders — **behavior-preserving** (the R0 contract): identical operation ORDER, identical audit/lineage sequences, each binder's reason format preserved verbatim via a formatter callback. Exposure's fifth variant is a recorded follow-up (its model-less shape differs; not forced into this mold). |
| **OD-P3-C1-E** | result-column `PreciseDecimal` parity | Convert the SEVEN float53-unsafe **result/derived** columns to `PreciseDecimal` (PG DDL is IDENTICAL — `NUMERIC(p,s)`; NO migration; SQLite gains fixed-scale TEXT — the P3-4/P3-5 lesson applied to the shipped tables): `sensitivity_result.sensitivity_value(28,12)`; `factor_exposure_result.loading(20,12)` + `.exposure_amount(28,6)`; `exposure_aggregate.signed_quantity(28,8)` + `.mark_value(20,6)` + `.fx_rate(28,12)` + `.exposure_amount(28,6)`. `bump_bps(10,4)` stays plain (10 significant digits — float-safe by contract). **Captured-input tables** (position/valuation/fx_rate/price/curve/factor_return/benchmark) are a FURTHER named deferral (read-path inputs; PG-authoritative; a wider parity slice). |
| **OD-P3-C1-F** | `_ERROR_MAP` MRO lookup | Replace the ten `_ERROR_MAP[type(exc)]` exact-type lookups with one `_map_error(exc)` helper walking `type(exc).__mro__` (first mapped ancestor wins) — a SUBCLASS of a mapped exception currently KeyErrors into a 500. Behavior identical for every exact match. |
| **OD-P3-C1-G** | ambiguous-input refusal | All FIVE snapshot-consuming binders (exposure, sensitivities, factor-exposure, covariance, VaR) currently prefer `snapshot_id` SILENTLY when build-path arguments are also passed. Tighten: passing BOTH modes is a pre-create refusal (the binder's InputError, 422) — an ambiguous request must not guess. (No known caller passes both; the endpoints' DTOs allow it.) |
| **OD-P3-C1-H** | P3-3 mixed-base adjudication | Close the recorded LATENT mixed-base hole at its adjudication (not the schema): `factor_service._adjudicate_pins` gains the base-currency-uniformity check its P3-5 twin already has (a hand-minted FACTOR_EXPOSURE_INPUT snapshot pinning mixed-base atoms currently flows into rows). The 4-tuple grain is UNCHANGED (base stays run-uniform by construction on the governed path). |

---

## Part 2 — Decision detail (the non-obvious ones)

### OD-P3-C1-B — why the risk gate and not the generic resolver
`ModelVersion.status` was designed as a non-enforcing placeholder and other (non-risk) consumers may
legitimately resolve DRAFT versions; the P7 validation workflow owns the wider lifecycle question. What the
P3-5 review actually established is narrower: the RISK binders document and rely on "REGISTERED" while their
shared gate never checks it. Tightening `assert_model_version_of` (risk/bootstrap.py) enforces exactly the
documented contract at exactly its scope, with zero effect on the generic registry semantics. The
`UnregisteredModelError` class is reused (semantically exact: the version is not a registered one); the
endpoints already map it to 422.

### OD-P3-C1-C — why a column and not read-time reconstruction from DQ evidence
The DQ rows are the durable defect EVIDENCE, but reconstructing the human-readable reason at read time would
re-derive presentation from evidence with join logic in four readers — and the binders already build the exact
string at failure time. An additive nullable column on the status-mutable run row (set once, at the FAILED
transition) is the minimal honest persistence; the audit payload is deliberately unchanged (no event-shape
drift; `outcome='failure'` already marks the transition).

### OD-P3-C1-D — the behavior-preservation contract (the R0 bar)
The extraction is correct only if the full suite passes UNCHANGED (minus the tests extended for the new
failure_reason persistence) and the per-binder audit/lineage row sequences are byte-equal for identical inputs.
The four binders differ in: rows-vs-single-row writes, gap formatting, and result entity types — all callback
parameters. The compute step stays IN each binder (pre-adjudicated pins in, rows/gaps out); the scaffold owns
only the lifecycle. If during implementation any binder's shape cannot be preserved exactly, that binder is
LEFT UNTOUCHED and the divergence recorded (no force-fit).

### OD-P3-C1-E — why no migration and why the captured tables wait
`PreciseDecimal.load_dialect_impl` returns `Numeric(precision, scale)` on PostgreSQL — the DDL is
byte-identical, `alembic check` stays clean (proven at P3-4/P3-5). SQLite (test engine only) switches to
fixed-scale TEXT, making dev-engine roundtrips exact. The captured-input tables have the same latent contract
gap but a different risk profile (they feed content HASHES — changing their dev-engine storage alters what the
serializer sees for >float53 test values) and a much wider blast radius; they get their own recorded slice.

---

## Part 3 — Governance amendments (folded at the implementation slice, R-07)
- **Control matrix** — the CTRL-003 rows gain the status-checked-bind note (the risk gate now enforces
  REGISTERED); CTRL-012/CTRL-032 notes for the persisted `failure_reason` (durable refusal evidence surfaced on
  read). No new CTRL.
- **Canonical model** — ENT-026 `calculation_run` row: the additive `failure_reason` column annotated.
- **Model docs** — the `ModelVersion.status` placeholder comment updated honestly (enforcing at the RISK bind
  since P3-C1; still not a validation gate; P7 unchanged).
- **Audit taxonomy / entitlement / RTM** — UNTOUCHED (no new codes, no new permission, no REQ movement).
- **No-status-decay checklist** — at implementation close, flip the planning-era qualifiers introduced here.

---

## Part 4 — Open decisions (OQ-P3-C1-1…8) — **APPROVED / RATIFIED by the user (2026-07-07, the plan-commit gate)**
**Status: RATIFIED.** The eight defaults below are fixed inputs to the P3-C1 implementation. *(The original recommendations are retained verbatim.)*
- **OQ-P3-C1-1 — recommend APPROVE.** The slice scope = the eight OD items; one additive migration; no new number/entity/permission/audit code. (OD-P3-C1-A.)
- **OQ-P3-C1-2 — recommend APPROVE.** REGISTERED-status bind at the RISK gate only; `UnregisteredModelError`; generic resolver + P7 semantics untouched. (OD-P3-C1-B.)
- **OQ-P3-C1-3 — recommend APPROVE.** `failure_reason` as an additive `calculation_run` column + `update_run_status` param; audit payload unchanged; GETs surface it; migration `0027`. (OD-P3-C1-C.)
- **OQ-P3-C1-4 — recommend APPROVE.** The run-scaffold extraction across the four risk binders under the R0 behavior-preservation bar (verbatim reason formats; leave-untouched escape hatch); exposure's variant a recorded follow-up. (OD-P3-C1-D.)
- **OQ-P3-C1-5 — recommend APPROVE.** `PreciseDecimal` parity for the seven contract-unsafe result columns; NO migration; captured-input tables a further named deferral. (OD-P3-C1-E.)
- **OQ-P3-C1-6 — recommend APPROVE.** The MRO-walking `_map_error` helper replacing the ten exact-type lookups. (OD-P3-C1-F.)
- **OQ-P3-C1-7 — recommend APPROVE.** Ambiguous-input (both-modes) refusal across the five binders — an explicit, tested TIGHTENING (422). (OD-P3-C1-G.)
- **OQ-P3-C1-8 — recommend APPROVE.** The P3-3 base-uniformity adjudication check (closes the latent mixed-base hole; grain unchanged). (OD-P3-C1-H.)

---

## Part 5 — Adversarial review log (8 lenses, disciplined single-pass)
Planning documents take the disciplined single-pass floor. Each lens re-verified against shipped HEAD
`d94e572` — the status-column comment, registrar status values, the ten lookup sites, the five silent-preference
sites, the seven column contracts, and the update_run_status/audit shapes read from the repo, not recalled.

| Lens | Outcome |
|---|---|
| Product/Requirements | No REQ moves; the slice repays recorded debt. **Folded:** the record states explicitly that a FAILED run's reason becomes READ-visible (a small consumer-facing improvement) so the closeout notes don't undersell the change. |
| Chief-Architect | The scaffold extraction is the riskiest item — the R0 bar + the leave-untouched escape hatch folded into OD-P3-C1-D; verified the four shapes are parameterizable without semantic force-fit. **Folded:** exposure's variant explicitly OUT (model-less shape). |
| Data-Architecture | ENT-026 additive column follows the `environment_id` precedent exactly (status-mutable IA table, nullable add); the PreciseDecimal conversions change NO PG DDL (verified type rendering). **Folded:** `bump_bps` left plain with the contract-safety rationale recorded (no cargo-cult uniformity). |
| Security/RLS | No RLS/tenancy surface changes; the status-bind check REDUCES what can bind. Verified `UnregisteredModelError` maps to 422 at every risk endpoint. No defect. |
| Audit/Controls | The audit event payload is deliberately unchanged (no event-shape drift); the persisted reason is row-state, not a new event; `audit/service.py` FROZEN. CTRL-003 note is a tightening record, not a new control. No defect. |
| Lineage/Data-Quality | DQ rows remain the durable evidence; the reason column is presentation-persistence (stated in OD-P3-C1-C so nobody later treats the string as the evidence of record). **Folded:** that sentence. |
| Model-Governance/Quant | The status placeholder's recorded "non-enforcing" design honored by scoping enforcement to the risk gate; P7 untouched. No numeric semantics change anywhere (parity conversions are storage-representation only). No defect. |
| Scope | Planning-only; the tightening items (B/G/H) are each explicit + tested, never silent; nothing new pulled forward; the captured-table parity and exposure-scaffold follow-ups recorded, not smuggled. No defect. |

**Not folded / refuted:** none withheld.

---

## Part 6 — P3-C1 implementation readiness gate
Implementation-ready once OQ-P3-C1-1…8 are ratified. Build contract = `p3_c1_implementation_plan.md`.
**P3-C1 planning implements nothing.**
