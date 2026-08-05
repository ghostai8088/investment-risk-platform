# RPT-1 slice record — the first reproducible risk report

**Status:** built, gated, awaiting the pre-merge fresh-context audit.
**Branch:** `rpt-1-methodology-prework` · **Head:** `8985967`
**Entity:** ENT-072 `report_generation` · **Migration:** `0063_report_generation`

This is the slice record the operating model asks for: what the remit specified, what was
delivered, where the build DEVIATED, and what it found. The audit checks the proofs below, not
step-compliance.

---

## 1. The invariants, each to its named proof

| # | Invariant | Proof, by name | State |
|---|---|---|---|
| I1 | Bound at generation, never re-derived at render | `test_the_report_does_NOT_RE_READ_the_source_rows_even_if_they_MOVE` — mutation **N10** | PROVEN |
| I2 | Byte-identical regeneration | `test_generate_then_regenerate_is_BYTE_IDENTICAL` **and** `infra/deploy/prove_report_identity.sh` in CI's `stack-proof` job | PROVEN, both tiers |
| I3 | A superseded input regenerates the ORIGINAL — and SAYS so | `test_a_SUPERSEDING_correction_does_not_reach_a_historical_report` + `test_the_report_SAYS_as_of_when_its_inputs_were_KNOWN` — mutations **N8/N10** | PROVEN |
| I4 | Hostile inputs REFUSED with nothing persisted | six refusal tests, each asserting the absence of state; cross-tenant arms use REAL foreign-owned objects | PROVEN |
| I5 | Every number carries its provenance; every `methodology_ref` resolves | provenance resolved FROM THE BOUND RUN; allowlist census; `test_the_rendered_methodology_refs_are_the_REGISTERED_ones` — mutations **N1/N2/N3/N6/N7/N11** | PROVEN, after a redesign — see §3 |
| I6 | IA append-only on the governed rails | `test_report_pg.py` — 7 controls, mutations **M1–M6** against the LIVE schema | PROVEN |

**Eleven mutations (N1–N11) and seven PG mutations (M1–M6 + M2b), each killed by its intended
test.** The mutation list lives in the commit bodies; three of them found real gaps rather than
confirming existing ones (N10, M2, N11).

## 2. Named proofs and their captured exit codes (P14)

| Proof | Evidence |
|---|---|
| `make check-all` | `CHECK_ALL_EXIT=0` — ruff format 562 clean, ruff `All checks passed!`, mypy `no issues found in 286 source files`, pytest **2461 passed / 593 skipped**, FE **208 passed** |
| Full-PG fresh-schema battery | see §7 — reset + `alembic upgrade head` to `0063`, `PYTEST_EXIT` quoted |
| Restore-cycle identity (I2) | `RESTORE_PROOF_EXIT=0` locally; in CI run `31048172308`, step *"Prove a governed report regenerates identically after a restore (I2)"* → `success` |
| CI on the head SHA | see §7 |

## 3. The finding that reshaped the slice

`ReportFamily` declared ONE `model_code` + ONE `methodology_ref` per family. True for the three
single-model families; **false for VaR**. Seven registered models write into `var_result` under the
single `VAR` run_type — `events.py` states outright that run_type must never equal metric_type — and
`metric_type` does not identify the model either, because `risk.var.parametric_es` and
`risk.var.parametric_es_total` both write `ES_PARAMETRIC`.

A static pair would therefore have printed a **false methodology citation on a board-facing governed
number for six of the seven**, with no error and full confidence.

Provenance is now resolved from the bound run's own `model_version_id`, checked against a declared
allowlist that is census-verified against the risk bootstrap's source. The load-bearing refusal:
the resolved `methodology_ref` must equal the REGISTERED one. That field is tenant-supplied —
`POST /models` stamps any string — so without the check a tenant could make a board report cite a
methodology document of their own choosing while the number itself stayed genuine.

## 4. Deviations from the remit, recorded

1. **VaR/ES was written SECOND, not first.** The registry shipped with three single-run-type
   families so the identity machinery was proven on clean ground before being taken through the
   shared-`var_result` trap (the PPF-2 defect class). Both halves land in this slice.
2. **`ReportFamily`'s shape changed mid-slice** (§3). The remit did not anticipate a family whose
   provenance is per-run; the alternative was a knowingly false citation.
3. **I5 was extended beyond the remit's letter.** The remit names "model version" among the
   provenance; the first implementation pinned only the model CODE. Both the version id and the
   source snapshot id are now pinned and rendered.
4. **A cross-tenant provenance fence was added** that the remit does not mention (§5).

## 5. Defects found, and by what

| # | Defect | Found by |
|---|---|---|
| 1 | Family readers took `metric_value` for every row kind — every DETAIL row would have rendered `"None"` | executing the e2e test |
| 2 | `generate_report` constructed `CalculationRun` directly — **no audit event at all** | executing the e2e test |
| 3 | The NULL-refusal control was VACUOUS | mutation M2 |
| 4 | `_read_rolling_risk` stringified NULL — every SUPPRESSED window would have rendered `"None"` (3rd instance of this class) | reading the schema |
| 5 | The knowledge time rendered differently on PostgreSQL vs SQLite — **the identity claim was engine-dependent** | executing the I3 test |
| 6 | The I3 supersession test did not discriminate a LIVE re-read | mutation N10 |
| 7 | `report_generation.portfolio_id` FK had never been satisfied — 18 tests bound a portfolio that did not exist | the FIRST run of the restore proof, on the deployed stack |
| 8 | The provenance reader did not check the model version's TENANT — **a report could cite another tenant's model** | rewriting a refusal test to use a REAL foreign-owned object |
| 9 | The PG suite proved the RLS policy LOOKED symmetric but nothing proved what asymmetry PERMITS | mutation M2 (PG) |

Seven of the nine were found by EXECUTION or MUTATION. Two were found by reading — and both of
those were found only after execution had taught what to look for.

## 6. Carries, with triggers

| Carry | Detail | Trigger |
|---|---|---|
| **The SQLite FK gap** | The shared unit engine leaves `PRAGMA foreign_keys` OFF. MEASURED: **115 failures across 12 suites** with it on — sharpe 29, rolling_risk 28, breach_lifecycle 25, report_generation 12 (PAID here), notification 10, private_capital 3, ingestion 2, es_backtest 2, and 1 each in scheduler_dispatch, pacing, limit, demo_stage4. The remaining **103 are a slice of their own**. | The next slice that touches any of the named suites, or a dedicated hardening slice. Do NOT flip the pragma globally without budgeting for 103 fixtures. |
| **Methodology-doc retrofit** | 25 of 30 methodology docs do not carry the 8-section house form (measured in the pre-work census, `_FULL_FORM_DOCS`). | A ratification-gate decision, not a test's authority. |
| **Reports are not scheduled** | Explicitly OUT of the remit; the SCH machinery exists and is unwired for `REPORT`. | A slice that asks for periodic reports. |

## 7. Gate evidence

**Full-PG fresh-schema battery — `PYTEST_EXIT=0`.** Schema reset (`DROP SCHEMA public CASCADE` +
`GRANT USAGE ON SCHEMA public TO PUBLIC`) then `alembic upgrade head` → `0063_report_generation`,
then the full battery against `IRP_TEST_DATABASE_URL`.

*Outcome census, derived — and the derivation is stated because the summary line is missing.* The
run reached `[100%]` and exited 0, but pytest's final `N passed` line does not appear in the log.
Rather than assert a number I do not have, the census counts the progress marks:
**3,054 marks, all `.`; zero `F`, zero `E`, zero `s`; zero `FAILED` and zero `ERROR` lines.**

That number cross-checks exactly against the SQLite run: `2461 passed + 593 skipped = 3054`. Every
test skipped for want of PostgreSQL ran here, and none failed. (P14's corollary cuts both ways — an
implausible gate result is a signal, and so is a *missing* one. The missing summary is recorded as
an anomaly rather than smoothed over; the census and the cross-check are what the claim rests on.)

**CI on the head SHA — see the PR close comment.** Run `31048172308` on the parent `9bd5423`
already reported `success` with the new `stack-proof` step *"Prove a governed report regenerates
identically after a restore (I2)"* → `success`, so the restore-cycle proof is CI-executed, not
merely local.

## 8. OQ-RPT-1-3: the three carries, fires / does-not-fire

| Carry | Verdict |
|---|---|
| LIM-2 breach DTO echoes | **DOES NOT FIRE** — breaches are not in v1 report content (OQ-RPT-1-1 ratified the §2.1 spine). |
| REF-1 alpha-3 / M49 | **DOES NOT FIRE** — no regulatory-format section in v1, as recommended and ratified. |
| CON-1 effective-number 1/HHI | **DOES NOT FIRE as a blocker** — the concentration section renders the pinned `(metric, value)` pairs the family already produces, including its `MAX_SHARE_*` summary; it does not add a detail view that would need the effective-number metric. Re-evaluate when a report gains a concentration DETAIL breakdown. |
