# Session Log: 28-07-2026 15:46 - FE-M1 Shipped, Wave 13 Complete

## Quick Reference (for AI scanning)

**Confidence keywords:** FE-M1, React-19, react-router-8, react-router-dom-removed,
GHSA-qwww-vcr4-c8h2, audit-allowlist, npm-dedupe, duplicate-React, lockfile-delta-12,
node-24-slim, EBADENGINE, engines-floor, check_frontend_audit, evaluateAudit, eslint-flat-config,
no-restricted-imports, write-fence, router-fence, dependency-fence, single-React-pin,
BrowserRouter, useParams, MemoryRouter, jsx-fence-hole, executed-dry-run, mutation-control,
V-1, V-2, V-3, V-4, V-5, V-6, R-1, R-2, R-3, R-4, code-review-ultra, independence-ladder,
Wave-13-close, PR-142, CI-30388265933, CI-30388621527, CI-30392210205, 25/40/133, 32-files-190-tests

**Projects:** investment-risk-platform (ghostai8088/investment-risk-platform)

**Outcome:** FE-M1 shipped on branch `fe-m1` (`4209dfb` → `a0f7528`, 6 commits) — React 19 +
react-router 8 with the High-severity supply-chain exception retired **by fix, not by expiry**
(`npm audit --omit=dev` 2 High → 0, ~3 months before the 2026-10-24 cliff). Wave 13 is
functionally complete; next is the Wave-13 close review.

---

## Decisions Made

### Ratified at the Tier-3 gate (OQ-FE-M1-1…6, all approved as recommended)

- **OQ-1 = A** — caret ranges (`react@^19.2.8`, `react-dom@^19.2.8`, `react-router@^8.3.0`,
  `@types/react@^19.2.17`, `@types/react-dom@^19.2.3`), consistent with the rest of the manifest;
  the lockfile is the reproducibility boundary. 8.3.0 is the *only* version clearing the advisory,
  so its youth (published 2026-07-22) was not a choosable variable.
- **OQ-2 = A** — bump `infra/docker/frontend.Dockerfile` `node:20-slim` → `node:24-slim` in this
  slice, since FE-M1 is what introduces the `>=22.22.0` engines floor.
- **OQ-3 = A** — empty the allowlist but **keep the mechanism**, and give the gate its first
  automated test. (Deleting `audit-allowlist.json` was rejected: the script reads it
  unconditionally, and the mechanism is the standing answer to the *next* advisory.)
- **OQ-4 = D** — **all three** fences: eslint import ban + manifest pin + single-React pin.
  Justification is empirical, not theoretical: `npm audit`'s own `fixAvailable` field on the
  pre-migration tree recommended `react-router-dom@7.11.0` — the exact downgrade OPS-1's OQ-1=C was
  refuted in build for.
- **OQ-5 = A** — the full verification ladder including a real container build and a
  `BrowserRouter` deep-link test (the two paths nothing else covers).
- **OQ-6 = A** — scope held to the five declared packages + the Dockerfile base, **via the
  `npm dedupe` path**; the other 11 `npm outdated` drifts recorded as debt.

### Process decisions

- **Ran the pre-ratification verifier pass as a FULL EXECUTED DRY RUN** in a throwaway workspace
  copy (`scratchpad/dryrun*`, outside the repo) rather than as analysis. Three trees were built to
  separate variables (incremental install / lockfile regeneration / dedupe).
- **Did not run `git init` in the parent directory** when `/code-review ultra` failed there —
  that would have created a repo whose working tree contains the real repo plus `.claude`.
  Chose "open the inner folder as the VS Code workspace root" instead, which also permanently
  retires the exit-127 path trap.
- **Left Part 6 row 11 (CI) as an explicit `pending` marker** rather than asserting a result while
  runs were queued; filled in only from observed `conclusion=success`.
- **Recorded the review-method limitation in the decision record itself** — subagents/workflows
  were unavailable, so the in-session adversarial pass ran inside the authoring context, the
  weakest rung of the operating instructions' independence ladder.

---

## Key Learnings

1. **For a migration or dependency-floor slice, READING IS NOT ENOUGH.** Reading, `grep`, and the
   official react-router v7→v8 upgrade guide all missed both blocking findings. Performing the
   migration in a throwaway tree surfaced them within ten minutes. *(Proposed as a fourth standing
   rule for the Wave-13 close.)*

2. **V-1 — a plain `npm install` leaves TWO React copies.** Over the existing lockfile,
   `@testing-library/react` keeps a stale `react@18.3.1` peer resolution hoisted at the root while
   the app resolves `19.2.8`. Measured consequence: **73 of 150 tests fail — yet `tsc --noEmit`
   PASSES and `vite build` succeeds and emits a bundle.** `npm dedupe` is the fix and is a separate
   command nobody would think to run.

3. **V-2 — a slice's own scope promise can be unachievable by the route that fixes its own
   blocker.** The obvious remedy for V-1 (regenerate the lockfile) moves **61 packages, 49
   unrelated**, silently contradicting OQ-6=A. The dedupe path moves exactly **12**, all
   attributable. OQ-6=A survived only because the alternative was *measured* rather than assumed.

4. **Declaring the expected delta before implementing turns drift into a defect.** Part 2 declared
   "exactly 12, a 13th is a defect"; the measured delta came back 12, line for line. Same
   discipline as the demo-counts pin.

5. **A register entry is a claim about the code — third slice running.** Two findings no register
   held: the shipped container built on **EOL `node:20-slim`** below the new engines floor
   (invisible to CI *because CI never builds the image*), and **the fail-closed audit gate this
   slice exists to satisfy had no test at all** while about to enter its never-exercised
   `exceptions: []` state.

6. **State a finding at its true severity.** V-4: there is no `.npmrc`, so npm `engines` are
   **advisory** — the Node-20 build emitted `EBADENGINE` and still produced a bundle. The finding
   stands on EOL + CI/deploy asymmetry, *not* on "the build breaks".

7. **ESLint flat config REPLACES a rule's options when a later block names the same rule.** A
   second block declaring `no-restricted-imports` over overlapping files silently disables the
   first. Both fences now live in one rule; per-file differences are expressed by *re-declaring*
   the rule with a different pattern set, never by an overlapping block.

8. **V-3 — `"rule": "off"` as an exemption is a hole waiting for a second tenant.** The write
   fence's `writes.ts` exemption switched off the *whole* rule; correct while the rule carried one
   fence, and a free pass the moment a second joined it.

9. **R-1 — fences have TWO axes: the shapes they must catch AND the file types they must see.** A
   `.jsx` file was linted by **nothing** ("File ignored because no matching configuration was
   supplied", exit 0), so one JSX component could have imported `react-router-dom` or reached
   `client.ts::request` past the OPS-1 write fence. This is the Wave-12 close HIGH's own class one
   axis over. *(Worth generalizing at the close.)*

10. **R-4 — the independent cloud review earned its cost by killing a test I wrote to close a
    coverage gap.** The M1-6 deep-link-with-a-parameter case booted at `/runs/risk/{uuid}`, but
    `risk` is a permissionFamily **value** in `FAMILIES`, not a key — so `RunDetail`'s allowlist
    resolved `validFamily=null`, the effect early-returned **without fetching**, and the component
    rendered "Unknown run family in the URL" rather than the 404 branch the mock staged. Both
    assertions (pathname unchanged; walk text absent) were satisfied by that page too, so **a real
    break in `useParams` over the History API — the only reason M1-6 exists — would have left the
    test green.** Fixed by using `vars`, and by raising the assertions from *by-absence* to
    *by-evidence* (fetch called exactly once with `/risk/vars/runs/{uuid}`; the rendered text
    asserted to be the not-found branch).

11. **The independence ladder is not theory.** The in-context pass found R-1/R-2/R-3; the
    independent cloud review found R-4 — a vacuous assertion in the author's own new test, which
    is precisely the class an author's own review cannot see.

12. **A guard's honest justification matters.** V-6: the single-React pin was about to be justified
    as "the suite cannot see a duplicate". Measured, the suite sees it loudly (73 failures). It
    shipped as a **diagnostic** (naming the cause and the `npm dedupe` fix) plus cover for the one
    shape `tsc` and `vite build` both pass.

13. **R-2 — do not ship a new untrue claim in the file whose purpose is replacing an untested
    one.** The refactor header said "behaviour UNCHANGED… same order"; decisions and exit code were
    unchanged but console output was regrouped (info → warnings → errors). Corrected in place.

14. **Environment:** the GitHub unauthenticated REST API rate-limits at ~60 req/hr — a 30s CI poll
    exhausts it. Check `x-ratelimit-reset` and schedule a single post-reset query instead.

---

## Files Modified

### New (all in `apps/frontend/`)

- `audit-gate.test.ts` — first-ever test of the audit gate; 13 cases: empty-allowlist pass/fail,
  absent-allowlist-key fail, valid exception, expired exception (incl. when the advisory is gone),
  inclusive `review_by == today` boundary, JSON-drift fail-closed + its negative control,
  moderate/low gate boundary, one-advisory-per-GHSA parsing, housekeeping warn-without-fail.
- `router-fence.test.ts` — 11 cases: the ban at six sites incl. `writes.ts` (the V-3 hole), deep
  subpaths, `.jsx`; positive controls for `react-router` and for a package merely *containing* the
  banned name.
- `dependency-fence.test.ts` — 8 cases: manifest + lockfile absence of `react-router-dom`,
  `react-router >= 8.3.0`, exactly one `react`/`react-dom`, the 19.2.7 peer floor, react/react-dom
  version pairing.
- `src/App.browserrouter.test.tsx` — 5 cases; the platform's first `BrowserRouter` coverage
  (index, deep link, deep link with a param, catch-all redirect, session gate). **Rewritten at R-4.**

### Changed

- `apps/frontend/package.json` — react/react-dom → 19.2.8, `react-router-dom` removed,
  `react-router@^8.3.0` added, `@types/*` → 19.
- `package-lock.json` — exactly 12 version deltas (incl. `scheduler` 0.23.2→0.27.0, `cookie-es`
  added; `loose-envify`, `@types/prop-types`, `cookie`, `set-cookie-parser` removed).
- 18 files under `apps/frontend/src/` — `react-router-dom` → `react-router`, **specifier only**
  (verified: the diff contains nothing else).
- `apps/frontend/eslint.config.js` — restructured; `WRITE_FENCE` + `ROUTER_FENCE` consts, the
  `writes.ts` exemption re-declares rather than disables, plus a fourth disjoint block for
  `**/*.{js,jsx,mjs,cjs}` with `ecmaFeatures.jsx`.
- `scripts/check_frontend_audit.mjs` — `evaluateAudit(report, allowlist, today)` and
  `collectAdvisories(report)` exported; CLI behind an `import.meta.url`/`argv[1]` main guard.
- `audit-allowlist.json` — `exceptions: []` + a `_history` field recording retirement **by fix**.
- `infra/docker/frontend.Dockerfile` — `node:20-slim` → `node:24-slim`.
- `apps/frontend/README.md` — current-truth fix + two operational warnings
  (`npm install && npm dedupe`; do not run `npm audit fix` blindly).
- `10_delivery_backlog/fe_m1_decision_record.md` — the slice record (Parts 0–7).
- `10_delivery_backlog/delivery_roadmap.md`, `10_delivery_backlog/wave_12_close_review.md` (§5
  TIPPED item 2 → PAID), `docs/project_memory/current_state.md` (CURRENT TRUTH → 2026-07-28c).
- `CC-Session-Logs/28-07-2026-13_54-sr1-shipped-opsh1-shipped.md` — committed (was untracked).

### Memory (outside the repo)

- NEW `fe-m1-planning-state.md`; updated `delivery-roadmap-state.md` and `MEMORY.md`.

### Commits on `fe-m1`

`4209dfb` (planning DRAFT→VERIFIED) → `c2e5965` (RATIFIED) → `8f9711c` (implementation) →
`b8767ce` (folds R-1/R-2/R-3) → `a5e69be` (observed CI) → `922cf20` (fold R-4, from the cloud
review) → `a0f7528` (observed CI for R-4).

---

## Pending Tasks

1. **Merge `fe-m1` to `main`** — 6 commits, all gates green.
2. **FE-M1 closeout** — stamp the decision record CLOSED with the merge commit + PR number, and run
   the six-ledger omission sweep once more **against `main`** (the SR-1 clause: *verify the fix is
   on `main`* — an unmerged sweep equals no sweep).
3. **The WAVE-13 CLOSE REVIEW** — the mandatory Part-4 rule-2 re-baseline over SCH-2, RM-1, SR-1,
   OPS-H1, FE-M1. Agenda carries **four** standing-rule proposals:
   - ratify the six-ledger omission sweep as a closeout step, with *verify the fix is on `main`*;
   - ratify the shared-tree mutation rules;
   - ratify "a register entry is a claim about the code — verify it at planning recon" (three
     slices now);
   - **NEW:** for a migration/dependency-floor slice, run the pre-ratification pass as an
     **executed dry run**.
   - Also worth generalizing: fences have two axes (shapes *and* file types).
4. **FE-toolchain debt, recorded and deliberately not taken:** TypeScript 5.9→7.0, eslint 9→10,
   jsdom 29→30, five patch bumps; and the frontend `tsconfig.json` `include` omitting the
   root-level guard tests — cost **measured** at 12 errors, all `@types/node` resolution, no
   substantive defects (closing it needs a new dev dependency).
5. **Wave-14 tee = real-data onboarding**, carrying the dimensional analytics and the declared
   rf-capture convention (a vendor's `return_date` must fall INSIDE the month its return is for —
   a first-of-following-month series joins a month late undetectably).

---

## Custom Notes

None.

---

## Quick Resume Context

FE-M1 (Wave-13 slice 4, the last) is **built, reviewed, folded and CI-green on branch `fe-m1`
(`a0f7528`), awaiting merge**. It migrated the frontend to React 19.2.8 + react-router 8.3.0,
taking `npm audit --omit=dev` from 2 High to 0 and emptying `audit-allowlist.json` — retiring
`GHSA-qwww-vcr4-c8h2` by fix roughly three months before its 2026-10-24 CI-enforced expiry. No
migration, no governed number, zero Python; counts unchanged at **25/40/133**; frontend tests
28 files/150 → **32/190**.

The slice's defining lesson is that its two blocking findings came from *executing* the migration
in a throwaway tree, not from reading it — and a third (R-4) came from the independent
`/code-review ultra`, which caught a test the author had written to close a coverage gap but that
would have stayed green through a real break.

**Next:** merge `fe-m1`, run the FE-M1 closeout (including the ledger sweep verified against
`main`), then the **Wave-13 close review**. Recommended for that: Opus 5 at high effort.

---

## Raw Session Log

*Not reproduced verbatim.* Rendering a session of this length from memory would produce a
plausible-looking transcript that is partly invented — which, in a project whose recurring lesson
is that a confident claim is not evidence, would be the wrong artifact to write. Every section
above is grounded in commit hashes, CI run ids, measured counts and executed command output.

The verbatim archive is the session JSONL at
`/Users/andrewcox/.claude/projects/-Users-andrewcox-Projects-investment-risk-platform/19fbf1ce-c768-4810-a4da-2751c2f1a3fc.jsonl`
— note that the `/code-review ultra` run and the R-4 fold happened in a **different** session
(after switching the VS Code workspace root to the repo), so this file does not contain them; only
their commits (`922cf20`, `a0f7528`) are visible here.
