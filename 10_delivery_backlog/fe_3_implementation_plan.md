# FE-3 Implementation Plan — the product UI (governance-narrative walk), Wave-9 slice 4

Companion to `fe_3_decision_record.md` (RATIFIED 2026-07-21, OQ-FE-3-1..3). One commit per step; `make fe-check` green at each; tests ride along each step (not deferred); the 4-finder adversarial review after the last impl step; closeout after CI-green + user merge. **FE-ONLY: NO backend change, NO migration, NO new governed number/code/permission/role.** The GET-only `apiGet` fence + the decimals-strings-verbatim contract stay byte-behavior-identical.

## Step 0 — Verifier pass (V1–V5) — RAN 2026-07-21, folded (decision record Part 5)
Seeded the demo, booted the backend on `dev_header`, curled every walk read. All confirmed non-empty over `DEMO-GLOBAL`; decimals serialize `string`. **Load-bearing finding → the demo-viewer pre-step below:** no principal reads the whole walk. Pinned for the FE: `/models` is a bare array; the Validation step drills into model→version→`latest_validation` (the summary `validation_status` stays `UNVALIDATED`). The Class-C VaR-latest gap is handled by the seeded VaR-run series.

## Step 0.5 — Demo read-only viewer principal  (`campaign.py`) — the Step-0 fold
Add the read-only 3L `demo-auditor` to `_seed_principals` (OD-H) holding `_AUDITOR_PERMS` (the walk read set, reusing existing `*.view` codes — no mint, no migration, counts unchanged). Update the demo-subject test to pin all three principals + the auditor's grant coverage + the registrar/validator SoD non-holdings. `make check` green; the full-PG demo battery green (counts hold at 101). *(This is the one additive demo-seed change; the rest of FE-3 is FE-only.)*
**Commit:** `FE-3 step 0.5: read-only demo-auditor viewer principal (the Step-0 fold)`

## Step 1 — App shell + nav + routes + Vite proxy  (`App.tsx`, a new `AppShell`, `vite.config.ts`)
Add the shell (OD-B): header (product name, `DEMO-GLOBAL` context chip, session chip, `DevBanner` while `dev_header`) + a left nav listing the six walk steps AND the kept "Runs" browser. Add routes `/walk/:step` (capture|exposures|numbers|backtest|validation|limitations) with a placeholder per step; keep `/` (runs) + `/runs/:family/:runId` unchanged. Add the Vite proxy prefixes (`/perf`,`/exposure`,`/models`,`/snapshots`,`/audit`,`/pacing`,`/commitments`,`/lineage`) alongside `/risk`. Tests: routing renders each step shell; the run browser still renders; nav is keyboard-navigable (OD-G).
**Commit:** `FE-3 step 1: app shell + six-step walk nav + routes (run browser kept)`

## Step 2 — `GovernedNumber` + the provenance/validation/limitations sub-panes  (`components/`)
Build `GovernedNumber` (OD-C): the strings-verbatim value + a provenance strip (snapshot verify, run id, model+code version), a validation badge (tier/outcome/overdue), a limitations list, and a lineage/audit affordance. Each sub-pane takes a typed read result and renders a **"requires `<permission>`"** empty-state on a typed 403 (OD-E). Extend `types.ts` view-config for the new families (keys bound to generated `*RowOut`/`*Out`). Tests: the decimal renders verbatim (a governed string like `"0.01234500000000000000"` survives — the FE-2 contract on a NEW component); the 403 degradation state renders; the snapshot ✓/✗ states render.
**Commit:** `FE-3 step 2: GovernedNumber component + provenance/validation/limitations panes + 403 degradation`

## Step 3 — Walk steps 1–2: Capture + Exposures  (`views/walk/`)
Capture: `DEMO-GLOBAL` positions + valuations/marks, the 2026-05-22 drawdown day annotated (the limitation-in-waiting). Exposures: factor-exposures `/latest` + the exposure aggregate. Both consume the entity/`as_of` reads via `apiGet`; empty/lonely-book states handled. Tests: renders the seeded capture + exposures; degrades on `exposure.view`/`risk.view` absence.
**Commit:** `FE-3 step 3: walk steps Capture + Exposures over DEMO-GLOBAL`

## Step 4 — Walk step 3: Governed numbers (the heart)  (`views/walk/Numbers.tsx`)
Covariance (latest), the parametric-VaR **8-point series** (the legitimate multi-point view — a set of real runs, NOT a synthetic trend), HS-VaR, total-VaR, ES/ES-total, portfolio-return — each via `GovernedNumber` with full provenance/validation/limitations. **VaR/active-risk use by-id/run-id reads + the seeded series** and state plainly that "latest-for-portfolio arrives with API-1b" (OD-F, the Class-C gap — no faked resolver). Tests: each number renders its value + provenance; the VaR series renders as N runs; the API-1b honesty note is present.
**Commit:** `FE-3 step 4: walk step Governed numbers (verifiability first-class; VaR via seeded series, API-1b noted)`

## Step 5 — Walk steps 4–6: Backtest + Validation + Limitations  (`views/walk/`)
Backtest: VaR backtests (Kupiec/Basel zone) + the ES backtest domain-gate honesty (evidence, no off-domain verdict). Validation: `/models` (tier + status) → model detail → the **findings + evidence** detail read (governance made visible for the first time). Limitations: the `model_limitation` rows tied back to the step-3 numbers (currency-only blindness the drawdown exposes). Tests: the validation findings+evidence render; the domain-gated backtest shows evidence-without-verdict honestly; limitations link to their numbers; all three degrade on `model.inventory.view`/`lineage.view` absence.
**Commit:** `FE-3 step 5: walk steps Backtest evidence + Validation status + Disclosed limitations`

## Step 6 — Degradation polish + accessibility + styling pass  (`styles.css`, panes)
The partial-entitlement matrix from Step-0 V4 made consistent across every pane (OD-E); the WCAG 2.1 AA pass (OD-G: keyboard nav, contrast, `aria` on the stepper + badges, no color-only signals); the hand-written CSS grown (no framework, OD-FE-1-F). Tests: a `risk.view`-only session walks end-to-end with governance panes gracefully denied (no thrown screen); an axe-style/role assertion on the stepper.
**Commit:** `FE-3 step 6: partial-entitlement degradation matrix + WCAG 2.1 AA pass`

## Step 7 — `make fe-check` + `make gen-api-check` + push, then the 4-finder review
`make fe-check` green (typecheck/lint/format/tests/build); **`make gen-api-check` clean** (FE-3 changes no backend DTO → committed `openapi.json` byte-identical — if it drifted, a backend leak crept in; investigate); `make check` (Python) green trivially. Push `fe-3`; hand the compare link to the USER. Then the **4-finder adversarial review** (FE-weighted): the decimals-strings-verbatim contract holds on EVERY new screen (no `Number()`/`parseFloat` crept in — the FE-2 lesson); the GET-only fence intact (no non-GET path added); partial-entitlement degrades on every pane (no screen-level throw on a 403); **no fabricated/interpolated data** (the VaR "series" is real runs; no synthetic trend; the API-1b gap stated honestly, not hidden); accessibility; and that the walk renders truthfully against the seeded tenant. Fold, re-run gates, closeout.

## Risks / watch-items (seeded for the finders)
- **Decimal corruption on a new screen** — the exact FE-2 HIGH class; any new render path must be strings-verbatim. Finder target #1.
- **Fabricated data to fill a gap** — the Class-C VaR-latest gap and the absent time-series must be shown honestly (real series / "API-1b" note), never faked. Finder target #2.
- **Partial-entitlement screen-throw** — a 403 on one pane must not blank the walk. Finder target #3.
- **Silent backend drift** — if `make gen-api-check` is not clean, FE-3 accidentally touched a DTO; it must be FE-only.
- **Over-scope creep** — a second book, a summary read, or the OIDC login sneaking in (all out of scope: FE-3b / API-1b / later).
