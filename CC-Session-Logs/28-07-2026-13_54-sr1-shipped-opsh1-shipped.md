# Session Log: 28-07-2026 13:54 - SR-1 Shipped, OPS-H1 Shipped

## Quick Reference (for AI scanning)

**Confidence keywords:** SR-1, OPS-H1, Sharpe ratio, ENT-065, migration-0055, 22nd-governed-number,
sharpe_ratio_result, Sharpe-1994, differential-return, n-1-divisor-divergence, single-quantization,
month-key-join, risk-free-capture, ENT-052, benchmark_return, magnitude-gate, suppress-and-disclose,
demo-stage-17, stage9zzzzzzzz, count-pin-relay, 25/40/133, four-finder-review, snapshot-builder-window,
d0-month, span_end, last-business-day, GIPS-2.A.23.b, select_overdue_breaches, N+1, D9-template,
greatest-n-per-group, M-C1, FK-KEY-SHARE, 40P01, deadlock_503, interleave-regression,
seed-relative-clock, OQ-W12C-3d, DEMO_TENANT_ID, IRP_TENANT_IDS, GUC-canonicalization, L4-seams,
teardown-narrowing, role-census, ALERTS_PAGE, conformance-pin, client.ts-success-parse,
mutation-testing, stale-pyc, COMPUTE_PREC, git-add-A-contamination, ledger-omission-sweep,
c9d0374-never-merged, PR-139, PR-140, PR-141, CI-663, CI-669, Wave-13, FE-M1

**Projects:** investment-risk-platform (ghostai8088/investment-risk-platform)

**Outcome:** Shipped and closed TWO Wave-13 slices end-to-end — SR-1 (the Sharpe ratio, the 22nd
governed number, ENT-065/migration 0055, counts → 25/40/133) and OPS-H1 (the ten-item operations
hygiene slice, no migration, counts unchanged) — through plan → verify → ratify → implement →
adversarial review → fold → gates → PR → CI-green → closeout, with four PRs merged (#139, #140,
#141, and #142 pending) and every claim mutation-tested.

---

## Decisions Made

### SR-1 (ratified 2026-07-28, OQ-SR-1-1…6, all approved as recommended)

- **Sharpe (1994)'s differential-return form**, not Sharpe (1966). The denominator is σ of the
  EXCESS series, not of the portfolio series — the two coincide only when `r_f` is constant, so
  RM-1's persisted `ROLLING_VOLATILITY` is deliberately NOT reused.
- **The n−1 divisor divergence is DISCLOSED, not branded away.** Sharpe (1994)'s own endnote 1 uses
  the population σ (divisor T); ours is n−1, making the ratio ~4.3% smaller at n=12. That is above
  the platform's own materiality bar, so it is stated in the registered `model_assumption` rows.
- **Single-quantization** — operands unquantized at 50 digits, division there, the RATIO quantized
  once. The alternative was executed and refuted: a NON-constant series can quantize to σ = `0E-12`
  and raise `DivisionByZero` on a legal input.
- **The suppression predicate names the SAME unquantized σ**, so predicate and arithmetic cannot
  disagree, and the reason a consumer reads stays true.
- **A NEW entity (ENT-065), not an ENT-064 column** — Sharpe rows carry `risk_free_benchmark_id`
  provenance that rolling-risk rows have no meaning for; extending would mean a nullable placeholder
  on every existing row (the 0028 doctrine).
- **The risk-free leg rides ENT-052** as an ordinary captured benchmark (vendor-published RETURNS
  only, never derived from levels), joined by **MONTH KEY** with binder-enforced completeness and
  uniqueness.
- **Magnitude gate + PG enforcement suite FROM BIRTH** (RM-1 shipped without a PG suite and was
  found by review to be the only governed family lacking one).

### OPS-H1 (ratified 2026-07-28, OQ-OPS-H1-1/2/3, all approved as recommended)

- **Scope as verified**: the four fired-trigger items + six recorded LOWs, nothing added or dropped.
- **The demo-clock discharge is a documented CONSEQUENCE, not a prohibition.** Regeneration removes
  the absurdity (a year-stale instant escalation), not the mutation — an overdue breach under a
  running tick escalates because that is what the platform is FOR. Backdated seed-relative offsets
  preserve the curated walk exactly; the config flip stays an operator choice.
- **The interleave test attempts the TRUE deadlock first**, with a disclosed synthetic fallback only
  if un-forcible. (It was forcible — no fallback needed.)

### Process decisions

- Presented both gates via `AskUserQuestion` in plain language with recommendations first.
- Ran a **pre-ratification verifier pass on both slices** before the gate; both returned NOT
  RATIFIABLE as drafted and both sets of findings were folded before the user saw the gate.
- Scaled the post-implementation review to the slice: **4 finders for SR-1** (a governed number),
  **2 finders for OPS-H1** (hygiene).

---

## Key Learnings

1. **A fixture derived FROM the thing under test cannot test it.** SR-1's demo derived its
   risk-free dates from the book's own month-ends, making the capture tautologically date-identical
   to the pins — so the month-key join, which the record called the slice's load-bearing new
   criterion, was exercised *not at all*. This concealed BOTH of the slice's real product defects.
   Fixed by dating the demo on the calendar month end against a last-weekday book, with a test
   asserting the two date sets differ.

2. **The two worst SR-1 findings were PRODUCT defects, and the ratified prose specified one of
   them.** The snapshot builder's risk-free window was wrong at both edges: the lower edge pinned
   `d_0`'s month (never a measured month ⇒ only rows the binder must refuse ⇒ a legal continuous
   vendor capture produced a PERMANENTLY unrunnable immutable snapshot); the upper edge truncated at
   `span_end`, a DATE, while the binder joins by MONTH (a last-business-day book vs a
   calendar-month-end vendor lost its final month, ~5 months in 12).

3. **Hollow guards appear at every level, including in the slice that is fixing them.** SR-1's test
   named as the control for its headline n−1 divergence never called the kernel — under the exact
   mutation it names, it PASSED while five other tests failed. And the "platform-wide" GS2 test
   scanned 5 of 18 run types; an injected collision in `risk.events` stayed green. The second is the
   FE-2 sampled-guard lesson committed *by the slice fixing GS2*.

4. **Measured beats cited — for a census exactly as for demo counts.** OPS-H1's first exact census
   pin used a reviewer's "the campaign grants auditor_3l 11 perms" (read from the source of a
   DIFFERENT wiring path); the live battery measured 2.

5. **A register entry is a CLAIM about the code and can be stale the day it is written.** OPS-H1's
   H1-9 planned a backend pager for a route that does not exist, paying a debt NOTIF-1 had already
   shipped *before* OPS-1 recorded the LOW. The real residual was FE-side truncation.

6. **A census claim ("every existing X already satisfies Y") belongs in the verifier pass, not in
   the fold that depends on it.** SR-1's ratified `_persist_snapshot` fold claimed to be additive;
   `PROXY_WEIGHT_INPUT`/`RESIDUAL_SHRINKAGE_INPUT` were never members and their builders pass them
   straight through, so applying it verbatim would have broken PA-3 and RS-1. Third slice running.

7. **An omission sweep that ends in an unmerged commit has the effect of never running it.** The
   RM-1 session's systematic sweep (`c9d0374`) was authored but never merged — PR #137 carried only
   the two incidental fixes. `current_state.md` sat four merged PRs stale and ENT-061…064 had no
   registry rows. The sweep now gains a final step: **verify the fix is on `main`**.

8. **Mutation testing and a wildcard `git add` cannot share a working tree.** A `git add -A` during
   the SR-1 review committed a finder's live source mutation (a deleted fail-closed guard) plus a
   247-line scratch file that would have entered the governed suite *pinning defects as expected
   behaviour*. Restoring the tree does not restore the commit — grep the COMMIT.

9. **A stale `.pyc` can serve a mutant while the source reads clean.** `COMPUTE_PREC` imported as 20
   while the file said 50, invalidating every test result in that window. Purge `__pycache__` and
   re-run before trusting any post-mutation gate.

10. **`make check` must run WITHOUT `DATABASE_URL` exported** — a leaked env points the SQLite tier
    at the seeded PG and the campaign set-equality pins fail on demo pollution. A red herring that
    cost one debugging cycle.

11. **Sizing honesty is improving.** SR-1 was revised S/M → M at verification and ran as M; OPS-H1
    was estimated S/M and ran as S/M. The two preceding slices were both under-sized.

---

## Files Modified

### SR-1 (PRs #139 impl, #140 closeout)

**New:**
- `migrations/versions/0055_sharpe_ratio_result.py` — ENT-065; four-column grain; suppression CHECK
  suffix-only on BOTH sides; symmetric FORCE RLS + append-only trigger; 63-char identifier assert.
- `packages/shared-python/src/irp_shared/perf/sharpe_kernel.py` — the pure kernel: `month_key`,
  `build_excess_series`, `sharpe_ratio` (single-quantization, `None` = suppressed),
  `annualize_sharpe` (×√12 from the STORED value), `sharpe_windows`.
- `packages/shared-python/src/irp_shared/perf/sharpe_service.py` — the binder: pre-create gate,
  rf month-key join with three refusals, magnitude gate on the emitted value covering `_ANN`,
  rule-7 reads.
- `packages/shared-python/src/irp_shared/demo/sr1_stage17.py` — stage 17: 18-row USD-cash rf series
  dated on the CALENDAR month end; deterministic upstream-run discovery.
- `packages/shared-python/tests/test_sharpe_kernel.py`, `test_sharpe.py`, `test_sharpe_pg.py`,
  `test_demo_stage9zzzzzzzz_sr1_pg.py` (EIGHT `z`).
- `05_analytics_methodologies/sharpe_v1.md` — ten sections, per-source grades.

**Changed:**
- `perf/stats_kernel.py` — `mean_and_stdev_unquantized` lifted; `sample_stdev` a quantizing wrapper
  (bit-identity preserved incl. error behaviour).
- `perf/models.py` — `SharpeRatioResult` + metric constants; the RM-1 lying ORM comment corrected;
  the new `n_observations` comment corrected after review.
- `snapshot/service.py` — `build_sharpe_snapshot` (window fixed at BOTH edges after review); the
  purpose allow-list moved INTO `_persist_snapshot`; `_BINDING_PREDICATES` completed.
- `snapshot/models.py` — `PURPOSE_SHARPE_INPUT` + the two long-omitted purposes added.
- `apps/backend/src/irp_backend/api/perf.py` — `/perf/sharpe{,/latest,/{id}}`.
- `apps/frontend/src/api/decimal-contract.ts` + regenerated openapi/types.
- `02_requirements/requirements_backbone.md` + `requirements_traceability_matrix.md` — REQ-PRF-004,
  CAP-20.6.
- `04_data_model/canonical_data_model_standard.md` — ENT-061…065 registry rows; next free → ENT-066.
- `04_data_model/audit_event_taxonomy.md`, `09_compliance_controls/control_matrix_skeleton.md`,
  `docs/project_memory/current_state.md`, `10_delivery_backlog/sr_1_decision_record.md`.
- 21 test files: migration head pins → `0055_sharpe_ratio_result`; `test_synthetic.py` glob → `0056`
  plus its stale 0053-era comment block.

### OPS-H1 (PRs #141 impl, #142 closeout pending)

- `packages/shared-python/src/irp_shared/limit/lifecycle.py` — `select_overdue_breaches` batched to
  ONE statement via the D9 template; SQLite/PG datetime bind normalization.
- `packages/shared-python/src/irp_shared/demo/ops_stage14.py` — `_seed_now()` seed-relative and
  backdated two days, threaded as a per-run value.
- `packages/shared-python/src/irp_shared/db/tenant.py` — `_canonical_tenant` for the L4 seams.
- `apps/backend/src/irp_backend/deps.py` — dev-header tenant canonicalized before arming the GUC.
- `apps/frontend/src/api/client.ts` — success parse guarded (200-with-HTML → `server`).
- `apps/frontend/src/views/ops/BreachDetail.tsx` — explicit `limit=200` + visible truncation notice.
- Tests: `test_breach_lifecycle.py` (equivalence over 7 shapes, statement-count, boundary, 8-row
  lock-order), `test_breach_lifecycle_pg.py` (the TRUE 40P01 interleave),
  `test_demo_stage9zzzzz_ops_pg.py` (narrowed teardown + first role census),
  `test_tenant_context.py` (spy-based canonicalization pin), `test_auth_config.py`,
  `test_breaches_endpoint.py` (ALERTS_PAGE conformance pin), `ops.test.tsx`, `client.test.ts`.
- `.github/workflows/ci.yml` — two SR-1 PG steps; the stale RM-1 count-pin comment corrected.
- `10_delivery_backlog/ops_h1_decision_record.md`, `wave_12_close_review.md` §6d,
  `docs/project_memory/claude_operating_instructions.md` (interim rule retired).

### Memory
- NEW `shared-tree-mutation-hazard.md`, `sr-1-planning-state.md`, `ops-h1-planning-state.md`;
  `delivery-roadmap-state.md` and `MEMORY.md` updated (frontmatter repaired on the roadmap file).

---

## Pending Tasks

1. **Merge the OPS-H1 closeout PR** — `ops-h1-closeout` = `811a8fe`,
   https://github.com/ghostai8088/investment-risk-platform/compare/ops-h1-closeout?expand=1
   (docs only: decision record CLOSED, roadmap DONE row + dated log, `current_state`, and the
   operating-instructions interim-rule retirement).

2. **FE-M1 — React-19 / react-router-8 migration.** The last Wave-13 slice. Allowlist expiry
   **2026-10-24**, CI-enforced fail-closed; the Wave-12 close permanently foreclosed the downgrade
   escape (OQ-1=C). Recommended: Opus 5 high effort for planning/forks, Fable for codemods.

3. **The Wave-13 close review** after FE-M1. Agenda already carries three ratification proposals
   from this session:
   - the six-ledger omission sweep as a standing closeout step, **with the new
     *verify-the-fix-is-on-`main`* clause**;
   - the shared-tree mutation rules (never `git add -A` while agents hold the tree; grep the COMMIT;
     purge `__pycache__`);
   - "a register entry is a claim about the code — verify it at planning recon."

4. **Wave-14 tee = real-data onboarding**, carrying the dimensional analytics and the newly
   DECLARED rf-capture convention: *a vendor's `return_date` must fall INSIDE the month its return
   is for* — a first-of-following-month series joins one month late and **nothing in the data can
   detect it** (row counts match exactly).

---

## Quick Resume Context

`main` = `03da139` (PR #141, OPS-H1 merged); the OPS-H1 closeout sits unmerged on `ops-h1-closeout`
= `811a8fe`. Wave 13 has FOUR slices closed (SCH-2, RM-1, SR-1, OPS-H1) with only **FE-M1**
(React-19/router-8, hard expiry 2026-10-24) remaining before the mandatory Wave-13 close review.
Demo counts are **25/40/133**, migration head `0055`, next free entity id **ENT-066**. Start FE-M1
by reading `10_delivery_backlog/delivery_roadmap.md` slice-4 row and the Wave-12 close register's
TIPPED item 2, then run the standard plan → verifier → gate cycle.
