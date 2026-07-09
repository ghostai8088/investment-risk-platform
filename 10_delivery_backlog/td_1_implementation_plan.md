# TD-1 Implementation Plan — Test-data realism audit + remediation (build contract)

> Executes `td_1_decision_record.md` (OD-TD-1-A…F) once OQ-TD-1-1…6 are ratified. Test-and-example
> files only; NO production/schema/migration/permission/audit change. **Planning implements nothing;
> implementation starts on separate explicit approval.**

## Step 0 — Inventory (read-only, produces the worklist)
1. Enumerate every economic-value fixture site: grep the capture/fixture helpers (`_fx`/`_holding`/
   `_price`/`_mark`/`capture_factor_return`/`_valuation`/covariance+VaR seeders/endpoint request
   bodies) across `packages/shared-python/tests/`, `apps/backend/tests/`, any `synthetic`/seed
   scripts, and doc snippets. Produce a checklist grouped BY DOMAIN (fx → price → curve → benchmark
   → factor_return → holdings/valuation → exposure → covariance → VaR), each site tagged with a
   provisional bucket (1 ordinary / 2 boundary / 3 signal-forcing).

## Step 1 — Remediate, domain by domain (captured-market FIRST)
2. Order: captured-market fixtures first (highest bug-catch value, least assertion entanglement),
   then derived-number fixtures (exposure/covariance/VaR — where re-derivation is needed).
3. Per site, apply OD-TD-1-D:
   - **Bucket 1 (ordinary):** set a plausible value from the OD-E band. If it feeds an assertion,
     RE-DERIVE the expected value in the SAME edit (recompute by hand/with the kernel's own quantize;
     never loosen the assert to a range or `approx` to dodge the work).
   - **Bucket 2 (boundary):** leave the value; ensure it is unmistakably a boundary probe (inside
     `pytest.raises`, or add a one-line comment/docstring naming it a boundary/limit test).
   - **Bucket 3 (signal-forcing):** first attempt a plausible value that still yields a
     distinguishable output (re-derive expected); if realism truly collapses the signal, keep the
     exaggerated value and add a comment: `# exaggerated input: forces a distinguishable <X> delta`.
4. Commit discipline within the slice: keep edits reviewable per domain; run the touched suite after
   each domain so a broken re-derivation is caught immediately, not at the end.

## Step 2 — Guard against recurrence (near-free, durable)
5. Add "fixture realism (three-bucket rule)" as a standing **adversarial-review angle** in the
   review skill/checklist wording used by future slices (so new fixtures are checked at review time)
   — a docs/process note, not a code gate (OD-E: no realism CHECK constraint).
6. Add a short `docs/` or test-README note stating the rule + the three buckets + the per-domain
   bands, so contributors have the reference (the plausibility bands live here).

## Step 3 — Validation (unreduced — OD-TD-1-F)
7. `make check` (all green — every re-derived assertion holds).
8. Full-PG suite (schema reset per the recorded recipe incl. the PUBLIC grant).
9. `make fe-check` (green; only corrected example values, if any, changed).
10. **Diff fence — the load-bearing gate:** assert the diff touches ONLY test files / seed-synthetic
    scripts / docs / example bodies. ZERO changes under `packages/*/src/`, `apps/*/src/` runtime,
    `migrations/`, `audit/service.py`, `entitlement/bootstrap.py`, permission/role code. If any
    production file appears in the diff, STOP — the slice has exceeded its fence.

## Step 4 — Review
FULL 6-finder adversarial review, angled at the re-derivation risk specifically:
- a finder that INDEPENDENTLY recomputes a sample of the re-derived expected values (the highest-risk
  defect is a green-but-wrong test from a bad hand re-derivation);
- a finder verifying no bucket-2/3 test lost its discriminating power (mutation-probe a few: does the
  test still fail if the code under test regresses?);
- the usual line-scan / governance / cross-file / plan-conformance angles;
- diff-fence conformance (test-and-example-only).
Fold findings → revalidate → HOLD for Tier-2 commit approval.

## Escape hatch (OD-TD-1-6)
If the derived-number re-derivation (covariance/VaR/exposure domains) proves larger than one slice,
STOP at a clean domain boundary, ship the completed domains as TD-1, and split the remainder into a
briefed TD-2 (roadmap Part-4 rule-2 re-sequence) — never loosen an assert or rush a re-derivation to
fit.

## Sizing
M–L (honest: larger than TC-1). Captured-market domains are quick (bucket-1-heavy, low entanglement);
the derived-number domains carry the re-derivation cost and the real risk.
