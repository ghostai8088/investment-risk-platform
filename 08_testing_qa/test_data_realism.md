# Test-data realism (standing rule, 2026-07-09; TD-1)

All dummy/fixture/seed data used in the build must be **economically plausible by default**. Implausible
fixture values make tests misleading as documentation and can mask unit/scale errors (percent vs. fraction,
bps vs. decimal, a mark off by 10²). This is a **reviewer guideline**, NOT a code gate — the DQ sanity bands
are the hard floor; realism is the plausibility *target* on top of them (an over-tight economic CHECK would
wrongly reject legitimate stress fixtures and real tail data).

## The three-bucket rule
Classify each economic-value fixture site into exactly one bucket:

1. **Ordinary** — a representative value with no special role ⇒ use a plausible value (per the bands below). If
   it feeds an assertion, RE-DERIVE the expected in the same change (never loosen an assert to dodge the work).
2. **Boundary / adversarial** — an intentionally extreme value testing a guard/limit/precision (17-sig-digit
   probes, column-envelope breaches, non-PSD matrices, NaN/±Inf guards, below/above-band DQ rejections) ⇒
   KEEP the value, but ensure it is unmistakably a boundary probe (inside `pytest.raises`, or a name/docstring/
   inline comment saying so). These are load-bearing and must NOT be "fixed" into realism.
3. **Signal-forcing** — an implausible value chosen only to make an output *distinguishable* (e.g. a large
   return to force a visibly different covariance/VaR) ⇒ FIRST try a plausible value that still yields a
   distinguishable output (re-derive the expected); only if realism genuinely destroys the signal, KEEP the
   exaggerated value and RELABEL it with a comment stating why (the escape hatch, not the default).

## Per-domain plausibility bands (the target; the DQ bands are the hard floor)
- **FX rate:** O(0.5–200) depending on the pair.
- **Index level / equity-bond price:** O(1–10⁴); index levels typically O(10²–10⁴).
- **Simple DAILY return:** a small decimal fraction, target abs(r) ≲ 0.05 (hard band > −1; 0.01 = 1%, NOT
  percent/bps).
- **Weights:** within [0, 1], summing sensibly per set.
- **Mark / quantity / cost_basis:** realistic instrument scales.
- **Covariance inputs:** daily-return-scale, so variances land ~O(1e-4).
- **Confidence levels** (0.90/0.95/0.99, and formula-exercising values like 0.60/0.75/0.80) are parameters,
  not returns — legitimate as-is.

## What is out of scope
Plumbing values — tenant/actor/GUID ids, `code_version`, `environment_id`, opaque labels — where realism is
meaningless. Do not churn them.

## Provenance
TD-1 (`td_1_decision_record.md`, OD-TD-1-A…F) established this rule and remediated the pre-existing fixtures.
(The representative market-value fixtures — fx / price / mark / weight / quantity — were already plausible;
the offenders were a handful of signal-forcing / ordinary values in the synthetic hand-reference factor-return,
covariance, and VaR test fixtures.)
