# FE-M1 Decision Record — React 19 + react-router 8 migration (Wave-13 slice 4)

| | |
|---|---|
| Status | **RATIFIED 2026-07-28 — OQ-FE-M1-1…6 ALL approved as recommended. Previously: DRAFT → VERIFIED (the pre-ratification pass RAN as a full executed dry run, Part 1b, and refuted two of this record's own claims; both folded before the gate).** Implementation next |
| Slice | Wave-13 slice 4 — the LAST slice before the Wave-13 close, per the ratified sequence (OQ-W12C-2=A) |
| Kind | **Supply-chain / framework migration.** No governed number, no entity, no migration, no permission, no audit code, no RLS surface, no Python. Frontend + one Dockerfile line only |
| Counts | **UNCHANGED at 25/40/133.** Recorded NOW, before implementation, so a drift is a defect in the code rather than in the expectation (the SCH-2 lesson) |
| Demo | No new stage, no stage edited. The 8-z final-position count pin stays the baton holder |
| Deadline | The `GHSA-qwww-vcr4-c8h2` allowlist exception expires **2026-10-24**, CI-enforced fail-closed. ~3 months of runway remain — this slice spends it deliberately rather than under the cliff |
| Sizing | **M** as roadmapped. Part 1's measurements argue the *code* change is S — and Part 1b's dry run confirms it (150/150 green with zero test-file edits). The *verification*, the three fences and the untested audit gate are what make it M |

## Part 0 — What FE-M1 is

The platform's frontend runs `react-router-dom@7.18.1`, which is inside the affected range of a
**High** advisory (`GHSA-qwww-vcr4-c8h2`, RSC-mode CSRF). Wave 11 dispositioned it as a
time-bound, reachability-justified exception because the app is a client-only Vite SPA with no RSC
and no data-router actions — the vulnerable code path cannot execute here. That disposition bought
runway; it did not fix anything. OPS-1's `OQ-1=C` then tried the cheap escape (pin below the
affected range) and **was refuted in build** — 7.11.x re-exposes six advisories including a High
DoS and two *reachable* open-redirects. The downgrade is permanently foreclosed.

So the only remaining exit is forward, and forward is a framework migration: the advisory's patched
version is `react-router@8.3.0`, and v8 requires React 19.

FE-M1 performs that migration, retires the exception, and leaves behind two fences so the
migration cannot silently un-happen.

## Part 1 — Recon: every claim measured, none cited

The Wave-13 standing lesson — *a register entry is a CLAIM about the code that can be stale the day
it is written* — is applied here to the register entry for this very slice. Every fact below was
measured today against the live npm registry, the packed `react-router@8.3.0` tarball, and the tree
at `origin/main` = `223330f`.

| # | Claim under test | Measured result | How |
|---|---|---|---|
| **F1** | The advisory is still live and still needs 8.3.0 | **CONFIRMED.** `npm audit --omit=dev --json` on the current tree returns exactly **2 High** entries, both the single advisory `GHSA-qwww-vcr4-c8h2`, `range: ">=7.12.0 <8.3.0"`, effects `react-router → react-router-dom` | live `npm audit` |
| **F2** | `react-router-dom@8` does not exist (the allowlist's stated rationale) | **CONFIRMED.** `react-router-dom` `dist-tags.latest = 7.18.1`; the version list contains no `8.x` at all. `react-router` `dist-tags.latest = 8.3.0` | `npm view` |
| **F3** | React 19 is *required*, not merely recommended | **CONFIRMED and it is a hard floor.** `react-router@8.3.0` declares `peerDependencies: { react: ">=19.2.7", react-dom: ">=19.2.7" }`. Current tree is React 18.3.1. `react@latest = 19.2.8` clears it | packed tarball `package.json` |
| **F4** | The code change is an import restructure | **CONFIRMED, and it is a pure specifier swap.** All **11** router symbols this app uses — `BrowserRouter`, `MemoryRouter`, `Link`, `NavLink`, `Outlet`, `Navigate`, `Route`, `Routes`, `useLocation`, `useNavigate`, `useParams` — are exported from the **root** `react-router` entry in 8.3.0. The `react-router/dom` subpath (which the upgrade guide flags for "DOM-specific APIs") is **not needed by this app** | read the export list out of `dist/development/index.d.ts` in the packed tarball |
| **F5** | Blast radius of the swap | **18 files** import `react-router-dom` (10 source, 8 test). Zero use anything outside the 11 symbols above | `grep` |
| **F6** | The v8 `data` → `loaderData` breaking change applies | **REFUTED — not applicable.** The app has **zero** data-router surface: no `loader`, no `action`, no `useMatches`, no `RouterProvider`, no `createBrowserRouter`, no `meta`. It is 100% declarative-mode | `grep` over `src/` |
| **F7** | React 18 → 19 has a meaningful code surface here | **REFUTED — the surface is two sites and both are already 19-clean.** `main.tsx` uses `ReactDOM.createRoot` (unchanged in 19); `App.tsx:24` uses `useRef(false)` (already has an initializer, which 19's types require). **Zero** occurrences of `forwardRef`, `defaultProps`, `propTypes`, `React.FC`, `JSX.*`, `findDOMNode`, `ReactDOM.render`, `hydrate`, `unmountComponentAtNode`, string refs, or legacy context | `grep` over `src/` |
| **F8** | The test harness needs work for React 19 | **REFUTED.** `@testing-library/react@16.3.2` (already installed, already latest) declares `react: "^18.0.0 \|\| ^19.0.0"` and the same for `@types/react`/`@types/react-dom`. `jsdom@29` is unaffected. No test-harness dependency moves | `npm view` peerDependencies |
| **F9** | **NEW — the deployed image violates the Node floor** | **FOUND.** `react-router@8.3.0` declares `engines: { node: ">=22.22.0" }`. CI builds on Node **24** (`ci.yml:54,86`) and local is 24.18.0 — both fine. But `infra/docker/frontend.Dockerfile:2` builds the shipped bundle on **`node:20-slim`**, which (a) violates the new engines floor and (b) is on a line `ci.yml` itself records as **EOL 2026-04**. This is pre-existing CI/deploy harness drift that FE-M1 converts into an engines violation | packed `package.json` engines vs. Dockerfile |
| **F10** | **NEW — the gate this slice exists to satisfy has no test** | **FOUND.** `scripts/check_frontend_audit.mjs` — the fail-closed audit gate — is referenced only by `ci.yml` and the `Makefile`. **No automated test exists.** Its three failure paths were proven by hand once, in the Wave-11-close session, and never committed. FE-M1 will empty its allowlist, making the **empty-`exceptions` path the primary path** — currently untested | `grep -rl` across the repo |
| **F11** | Baseline, for the drift check | FE suite **28 files / 150 tests green**, measured today. `npm audit --omit=dev`: **2 High, 0 moderate, 0 critical** | executed |
| **F12** | The root-level FE tests are typechecked | **REFUTED.** `tsconfig.json` `include` is `["src", "vite.config.ts"]`, so `write-fence.test.ts`, `api-prefixes.test.ts` and `openapi-contract.test.ts` — three governance-guard tests — are **never typechecked**. Probed by adding `"*.ts"`: **12 errors, all `@types/node` resolution** (`node:fs`, `node:path`, `process`) and one implicit-`any`; **no substantive type defects**. Closing it needs a new `@types/node` dependency | ran `tsc` against a scratch config, then deleted it |
| **F13** | The rest of the dependency set | `npm outdated` shows 11 further drifts, incl. two majors: **TypeScript 5.9 → 7.0**, **eslint 9 → 10**, plus `jsdom 29 → 30` and five patch/minor bumps (`vite 8.1.3→8.1.5`, `prettier 3.8.4→3.9.6`, `@vitejs/plugin-react 6.0.3→6.0.4`, `typescript-eslint 8.61→8.65`, `eslint 9.39.4→9.39.5`) | `npm outdated` |

**What F4–F8 mean together:** the register's own framing — *"F1 shows this is a framework upgrade
(React 18→19 across 22 test files), not the specifier swap the roadmap assumed"* (OPS-1 `OQ-1=A`)
— was right to split the slice out, but the measured React-19 surface turns out to be **two lines,
both already compliant**. The honest characterisation is: *a dependency-floor migration with a
large blast radius (18 files) and a near-zero semantic delta.* The risk in this slice is therefore
**not** in the edit. It is in (i) what runs the build, (ii) whether the gate that certifies the
result actually works, and (iii) whether the change can silently regress. Parts 2–4 are shaped
around exactly those three.

## Part 1b — The pre-ratification dry run (RAN, before the gate)

The standing lesson from ES-1 is *run the verifier pass BEFORE ratification*; the standing lesson
from OPS-H1 is *measured beats cited*. Both were applied here in their strongest available form:
rather than reasoning about whether the migration works, **the migration was performed end-to-end
in a throwaway copy of the workspace** (`scratchpad/dryrun*`, outside the repo — no repo file was
touched) and every gate was executed against it. Three trees were built to separate the variables.

### What the dry run proved (the happy path is measured, not projected)

On the recommended install path, with **zero changes to any test file**:

| Gate | Result |
|---|---|
| `tsc --noEmit` (React 19 types + react-router 8) | **clean** |
| `eslint .` | **clean** |
| `prettier --check .` | **clean** |
| `vitest run` (frontend) | **28 files / 150 tests — all pass** |
| `vitest run` (shared-ts) | **1/1 pass** |
| `vite build` | **clean**, 287.95 kB / 87.96 kB gzip |
| `npm ci` from the produced lockfile | **reproducible** |
| `npm audit --omit=dev` | **0 vulnerabilities** (from 2 High) |
| `node scripts/check_frontend_audit.mjs` | **passes** — both with the stale exception still listed (emitting its housekeeping note) and with `exceptions: []` |

This retires the largest unknown in the slice. F7's claim that the React-19 code surface is two
already-compliant lines is no longer an inference from `grep`; it is a clean typecheck and a green
suite.

### What the dry run REFUTED (findings folded into Parts 2, 4 and 5)

| # | Finding | Severity |
|---|---|---|
| **V-1** | **The duplicate-React hazard.** A plain `npm install` over the *existing* lockfile leaves `@testing-library/react`'s stale React-**18** peer resolution hoisted at the root while the app resolves 19.2.8 from `apps/frontend/node_modules` — **two React copies in one tree**. Measured consequence: **73 of 150 tests fail**, yet `tsc --noEmit` **passes** and `vite build` **succeeds and emits a bundle**. The install procedure is therefore load-bearing and must be specified, not left implicit | **BLOCKING** |
| **V-2** | **This record's own OQ-FE-M1-6=A was unachievable as drafted.** The obvious fix for V-1 — delete the lockfile and re-resolve — was measured at **61 version deltas, 49 of them unrelated** (vite, prettier, eslint, typescript-eslint, postcss, lightningcss, undici…), directly contradicting "nothing else moves". The alternative was measured: `npm install` **followed by `npm dedupe`** fixes the duplicate and yields **12 deltas, every one attributable to the migration** (the five declared packages, the removed `react-router-dom` / `loose-envify` / `@types/prop-types` / `cookie` / `set-cookie-parser`, and `scheduler` 0.23.2→0.27.0 + `cookie-es` 3.1.1 arriving with React 19 / react-router 8). `vite` stayed at 8.1.3 on this path. **OQ-6=A survives, but only via the dedupe route** | **BLOCKING** |
| **V-3** | **The proposed eslint fence would have inherited a hole.** The existing `no-restricted-imports` config carries a second block that turns the rule **`off` entirely** for `src/api/writes.ts` (the write-fence exemption). Adding the router ban to that same rule would exempt `writes.ts` from it too. The ban must be its own config block with no exemption. Separately noted: `files: ["src/**/*.ts(x)"]` does not cover the three root-level test files | MED |
| **V-4** | **F9's severity was overstated by omission.** There is **no `.npmrc` anywhere in the repo**, so npm `engines` are advisory: `node:20-slim` would emit an `EBADENGINE` **warning**, not fail the build. The finding stands on its actual merits — an **EOL** base image, a violated declared floor, and a CI/deploy asymmetry CI cannot see — but must not be argued at the gate as "the container build breaks", because it would not | MED |
| **V-5** | **The doc sweep was under-specified.** `apps/frontend/README.md` names `react-router-dom` as *current truth* and must be corrected. The seven historical decision records that mention it (FE-1/2/3/3b, TC-1, OPS-1, the roadmap) quote it as **history** and stay — the SR-1 precedent that a historical record may quote a since-falsified claim as history | LOW |
| **V-6** | **The single-React pin was about to be justified on a false premise.** The intended argument was "the suite cannot see a duplicate React". Measured, **the suite sees it loudly** (73 failures). The pin is therefore a **diagnostic** aid, not a detector — 73 cryptic hook-call failures read as *"the migration broke everything"* rather than *"npm hoisted two Reacts"*. It is kept on that honest basis, and its failure message must name the cause | LOW |

**V-1 and V-2 are the reason this pass exists.** Both were invisible to reading, to `grep`, and to
the upgrade guide; both were found in the first ten minutes of actually running the thing. V-6 is
the third consecutive slice in which a guard was about to be justified by a claim that measurement
then contradicted.

## Part 2 — The work

### M1-1 — The dependency move (the slice's reason to exist)

`apps/frontend/package.json`:

- `react` `^18.3.1` → `^19.2.8`
- `react-dom` `^18.3.1` → `^19.2.8`
- **remove** `react-router-dom` `^7.18.1`
- **add** `react-router` `^8.3.0`
- `@types/react` `^18.3.5` → `^19.2.17` (dev)
- `@types/react-dom` `^18.3.0` → `^19.2.3` (dev)

**The install procedure is load-bearing (V-1, V-2) and is specified here, not left to the
implementer's habit:**

```bash
npm install     # at the workspace root — resolves the new manifest
npm dedupe      # MANDATORY: collapses @testing-library/react's stale React-18 peer resolution
npm ls react    # must show exactly one react@19.2.8, deduped everywhere
```

`npm install` **alone leaves two React copies** (V-1). Deleting the lockfile to force a clean
re-resolve also fixes it, but drags 49 unrelated packages with it (V-2) and would silently violate
OQ-FE-M1-6. `npm dedupe` is the only measured path that fixes the duplicate **and** holds the scope
boundary. The result is then verified reproducible with `npm ci` (the `fe-setup` contract).

**Expected lockfile delta: exactly 12 versions**, every one attributable to the migration —
`react` 18.3.1→19.2.8, `react-dom` 18.3.1→19.2.8, `react-router` 7.18.1→8.3.0, `@types/react`
18.3.31→19.2.17, `@types/react-dom` 18.3.7→19.2.3, `scheduler` 0.23.2→0.27.0, `cookie-es` added at
3.1.1, and `react-router-dom` / `loose-envify` / `@types/prop-types` / `cookie` / `set-cookie-parser`
removed. **A 13th delta is a defect**, and the review checks the count — this is the same
"declare the expectation before implementation so drift is a code defect" discipline the counts
line applies.

### M1-2 — The import swap

18 files, `react-router-dom` → `react-router`, symbol lists unchanged (F4 proves every symbol
resolves at the root entry). Mechanical; the diff should contain **nothing but** the specifier
string on 18 lines.

### M1-3 — The Node floor (F9)

`infra/docker/frontend.Dockerfile` build stage `node:20-slim` → `node:24-slim`, matching the two
`ci.yml` `setup-node` steps.

**Stated precisely (V-4):** there is no `.npmrc` in the repo, so npm `engines` are advisory — the
Node-20 build would emit an `EBADENGINE` **warning** and still produce a bundle. The argument for
this item is therefore *not* "the build breaks". It is that FE-M1 would otherwise ship a container
that (a) builds the production artifact on an **EOL** Node line — `ci.yml:54` records Node 20 EOL
as 2026-04 in its own comment — (b) violates a floor the slice itself introduces, and (c) diverges
from CI's Node 24 in a way **CI structurally cannot detect, because CI never builds the image**.
That is the same harness-drift class the Wave-12 CI-parity slice paid on the Python side, and it is
one line. Gated by **OQ-FE-M1-2**.

### M1-4 — Retire the exception, and test the gate that enforces it (F10)

- `audit-allowlist.json`: the `GHSA-qwww-vcr4-c8h2` entry is **removed**; `exceptions` becomes
  `[]`. The file itself stays — `check_frontend_audit.mjs` reads it unconditionally, and the
  mechanism (fail-closed, time-bound, reachability-justified) is the standing answer to the next
  advisory. Its `_comment` gains a line recording that FE-M1 retired the one entry it ever held.
- `scripts/check_frontend_audit.mjs` gains a **committed test** covering all five behaviours, each
  with an executed negative control: empty allowlist + no advisories → pass; empty allowlist + a
  moderate+ advisory → **fail**; a valid unexpired exception → pass; an **expired** exception →
  **fail**; `metadata` reports moderate+ but zero advisory ids parse → **fail-closed**. This
  requires a small, behaviour-preserving refactor: the evaluation logic is extracted to a pure
  exported function taking `(report, allowlist, today)` so the test can drive it without invoking
  `npm audit`; the CLI shell keeps calling `npm audit` exactly as today. Gated by **OQ-FE-M1-3**.

### M1-5 — The regression fences (so the migration cannot un-happen)

The failure mode here is specific and likely: **`npm audit` itself recommends the reintroduction.**
Today's report carries `fixAvailable: { name: "react-router-dom", version: "7.11.0",
isSemVerMajor: true }` — i.e. the tool's own advice is the refuted downgrade. A future contributor
(or a future model) following that advice would undo this slice and re-open six advisories.

Three fences, mirroring the platform's established patterns:

1. **An eslint `no-restricted-imports` ban on `react-router-dom`** in
   `apps/frontend/eslint.config.js` — **in its own config block, NOT appended to the write-fence
   rule (V-3)**, because that rule is switched `off` wholesale for `src/api/writes.ts` and the ban
   would inherit the hole. Proven by a test on the `write-fence.test.ts` pattern (drive the real
   resolved config through the ESLint API). **Already validated in the dry run**: the ban rejects
   `import { Link } from "react-router-dom"` with the intended message (exit 1) and passes
   `import { Link } from "react-router"` clean (exit 0) — both controls executed.
2. **A dependency conformance pin** asserting `react-router-dom` appears in neither
   `apps/frontend/package.json` nor the root `package-lock.json`. eslint cannot see manifests; this
   is the half the lint rule structurally cannot cover.
3. **A single-React pin** asserting exactly one resolved `react` and one `react-dom` in the tree.
   **Honestly scoped (V-6):** this is *not* the detector — the suite already fails 73 tests on a
   duplicate. It is the **diagnostic**: without it, a future contributor who runs `npm install`
   without `npm dedupe` sees 73 cryptic hook-call failures that read as "the migration broke
   everything". The pin's assertion message names the actual cause and the one-word fix. It also
   guards the case the suite would miss — `tsc` and `vite build` both pass a duplicate tree (V-1),
   so any future CI path that builds without testing would ship it.

Gated by **OQ-FE-M1-4**.

### M1-6 — The one path no existing test exercises

Every routing test in the suite mounts `MemoryRouter`. `BrowserRouter` — the thing `main.tsx`
actually ships — is exercised by **nothing**, and it is precisely the component whose package moved
and whose React peer floor rose. FE-M1 adds a jsdom test that mounts the real app tree under
`BrowserRouter` at a **deep path** (e.g. `/ops/breaches`) and asserts the correct view renders,
closing the gap between "the tests pass" and "the deployed SPA boots".

### M1-7 — Documentation and ledger

- `10_delivery_backlog/delivery_roadmap.md` — slice-4 row → DONE, plus the Wave-13 register line.
- `docs/project_memory/current_state.md` — the FE stack line, the allowlist line, the NEXT pointer.
- `apps/frontend/README.md` — names `react-router-dom` as **current truth**; corrected (V-5). The
  seven historical records that mention it (FE-1/2/3/3b, TC-1, OPS-1, the roadmap) quote it as
  **history** and stay untouched, per the SR-1 precedent.
- `10_delivery_backlog/wave_12_close_review.md` §5 — the TIPPED item (2) marked PAID.
- The **six-ledger omission sweep** (the standing Wave-13 closeout step), including its new final
  clause: *verify the fix is on `main`*.
- `09_compliance_controls/control_matrix_skeleton.md` — the closeout sweep requires either a CTRL
  row moving or an explicit "no control moved" statement. FE-M1 expects the latter; it is stated,
  not skipped.

## Part 3 — What FE-M1 is NOT

- **Not** a governed number, entity, migration, permission, role, audit code, or RLS change. Zero
  Python. Counts stay 25/40/133.
- **Not** a general dependency refresh. TypeScript 5.9→7.0, eslint 9→10, jsdom 29→30 and the five
  patch bumps (F13) are **out** — see OQ-FE-M1-6. A framework migration whose diff also carries
  unrelated toolchain bumps makes a failure in either indistinguishable in review, which is the
  identical reasoning that split FE-M1 out of OPS-1 in the first place.
- **Not** the tsconfig typecheck-coverage gap (F12). Measured, costed, and recorded to the
  deferral register — it needs a new `@types/node` dependency and is unrelated to React.
- **Not** a UI, routing-structure, or feature change. Route table, views, and styles are untouched.
- **Not** a React-19 opt-in: no `use()`, no Actions, no `useOptimistic`, no compiler. FE-M1 moves
  the floor; adopting what the floor enables is a later slice's merit.

## Part 4 — Open questions for the gate

| OQ | Question | Options | Recommendation |
|---|---|---|---|
| **OQ-FE-M1-1** | Version targets and range style | **A** caret ranges consistent with the rest of the manifest — `react@^19.2.8`, `react-dom@^19.2.8`, `react-router@^8.3.0`, `@types/react@^19.2.17`, `@types/react-dom@^19.2.3`; the lockfile does the pinning · **B** exact pins for the three runtime deps | **A.** Every other dependency in this manifest is a caret range and `npm ci` makes the lockfile the reproducibility boundary; an exact pin here would be a lone inconsistency that buys nothing `npm ci` does not already give. Note `react-router@8.3.0` published **2026-07-22** (six days ago) — it is the *only* version that clears the advisory (F1), so its youth is not a choosable variable |
| **OQ-FE-M1-2** | The `node:20-slim` build image (F9) | **A** bump to `node:24-slim` in this slice · **B** leave it; record as debt | **A.** FE-M1 introduces the `>=22.22.0` engines floor; shipping an image that violates it — on an EOL Node line — while CI never builds that image is exactly the harness-drift class Wave-12 already paid for once. It is a one-line change and it is *caused by* this slice |
| **OQ-FE-M1-3** | The audit gate after the allowlist empties (F10) | **A** `exceptions: []` (keep the file + mechanism) **and** add a committed test over all five gate behaviours, requiring a pure-function extraction · **B** `exceptions: []`, no test · **C** delete the allowlist file and simplify the script | **A.** The standing rule is that a shipped guard carries its EXECUTED negative control; this guard is both the reason the slice exists and — once emptied — enters a state no one has ever exercised. **C** is wrong: the script reads the file unconditionally, and the mechanism is the standing answer to the *next* advisory, which will come |
| **OQ-FE-M1-4** | Regression fences (M1-5) | **A** eslint import ban only · **B** manifest conformance pin only · **C** the ban + the manifest pin · **D** C **plus the single-React pin** · **E** none — rely on the audit gate | **D.** `npm audit`'s own `fixAvailable` field today recommends `react-router-dom@7.11.0`, the refuted downgrade — the reintroduction path is not hypothetical, it is *advised by the tooling*. eslint cannot see `package.json`; a manifest test cannot see import specifiers; **neither sees a duplicate React, which the dry run proved is one forgotten `npm dedupe` away and passes both `tsc` and `vite build` (V-1)**. Each fence covers exactly what the others structurally cannot. **E** fails because a 7.11.x reintroduction goes *green* on the audit gate until the next advisory lands |
| **OQ-FE-M1-5** | Verification standard for a slice with no governed number | **A** the full ladder: `make fe-check` green; `npm audit --omit=dev` measured before **and** after with the output pasted **into this record** (the OQ-W12C-3a rule); the 150-test baseline re-measured and pinned; **the 12-line lockfile delta asserted exactly**; executed negative controls on all three fences and on all five gate behaviours; a `docker compose build frontend` smoke on the new base image; and a deep-link `BrowserRouter` render test (M1-6) · **B** A without the container build and the `BrowserRouter` test | **A.** This slice's entire deliverable *is* a verification claim ("the advisory is gone and nothing broke"), so the verification is the product. The two items **B** drops are precisely the two paths nothing else covers: the container build is the only place the Node floor is exercised (and Docker is confirmed available on this host), and `BrowserRouter` is the only shipped component the suite never mounts. The dry run has already executed most of this ladder once — implementation re-runs it on the real tree, since a scratchpad result is evidence about the plan, not about the commit |
| **OQ-FE-M1-6** | Scope boundary against the rest of `npm outdated` (F13) | **A** react/react-dom/react-router + their `@types` + the Dockerfile base only — **via the `npm dedupe` path (V-2)**; everything else recorded as debt · **B** also take the five safe patch/minor bumps · **C** also take eslint 10 and TypeScript 7 | **A — and note this recommendation survived only because measurement rescued it.** As first drafted, **A was unachievable**: the natural fix for the duplicate React is a lockfile regeneration, which moves **61** packages (V-2). `npm dedupe` was measured as the path that fixes the duplicate while moving exactly **12**, all attributable. On the merits: bundling makes a failure in either half indistinguishable in review — the identical reasoning that split FE-M1 out of OPS-1. **C** would additionally put a **TypeScript major** in the same diff as a **React major**, with no way to attribute a resulting type error to either. The remainder goes to the Wave-13 close as a named FE-toolchain debt item |

### Ratification (2026-07-28)

**All six approved as recommended**, with no amendments:

- **OQ-FE-M1-1 = A** — caret ranges; the lockfile is the reproducibility boundary.
- **OQ-FE-M1-2 = A** — the Dockerfile moves to `node:24-slim` in this slice.
- **OQ-FE-M1-3 = A** — `exceptions: []`, the mechanism kept, and the gate finally gets a test.
- **OQ-FE-M1-4 = D** — all three fences (eslint ban + manifest pin + single-React pin).
- **OQ-FE-M1-5 = A** — the full verification ladder, container build and `BrowserRouter` test included.
- **OQ-FE-M1-6 = A** — scope held to the five declared packages + the Dockerfile base, **via the
  `npm dedupe` path**; the remaining 11 `npm outdated` drifts go to the Wave-13 close as debt.

## Part 5 — Verification plan

Assuming OQ-FE-M1-5 = A:

1. **Before:** `npm audit --omit=dev` recorded (measured today: 2 High, both the single advisory);
   FE suite baseline recorded (28 files / 150 tests green).
2. **The install procedure asserted:** `npm install` → `npm dedupe` → `npm ls react` shows exactly
   one `react@19.2.8`. Then `rm -rf node_modules && npm ci` to prove the lockfile reproducible.
3. **The lockfile delta counted:** exactly the **12** versions enumerated in M1-1. A 13th is a
   finding, not a rounding error.
4. **After the swap:** `make fe-check` — lint, `prettier --check`, `tsc --noEmit`, vitest, `vite
   build`, and `node scripts/check_frontend_audit.mjs` — all green, with the audit gate's stdout
   pasted verbatim into Part 6 of this record.
5. **The advisory is gone, measured:** `npm audit --omit=dev` after → expect **0** moderate+.
   Recorded as output, not as a claim.
6. **Fence negative controls, executed:** reintroduce a `react-router-dom` import → lint **fails**;
   reintroduce the dependency in `package.json` → the manifest pin **fails**; force a duplicate
   React (`npm install` without `npm dedupe`) → the single-React pin **fails** *and names the cause*.
   All three reverted, all three transcripts recorded. **Positive controls too** — `react-router`
   must pass the ban clean, so the fence is not merely a rule that rejects everything.
7. **Gate negative controls, executed:** the five `check_frontend_audit.mjs` behaviours of M1-4,
   each asserted, including the three that must **fail**.
8. **Test-count drift:** the suite is re-counted; the delta is accounted for line by line against
   the tests this slice adds (the migration itself must add **zero** and remove **zero** — proven in
   the dry run, where 150/150 passed with no test file touched).
9. **The container:** `docker compose build frontend` on `node:24-slim` → success; run the image and
   `curl` a deep link (`/ops/breaches`) → **200 + the SPA shell**, proving the history fallback still
   holds under the new build. (Docker confirmed available on this host.)
10. **`make check`** (the Python tier) green — FE-M1 touches no Python, so this is a "nothing else
    was disturbed" control, and a non-zero delta there is itself a finding.
11. **CI to green**, all jobs, watched to completion.

**Standing note on the dry run's status.** Part 1b's results are evidence about **the plan**, not
about **the commit**. Every gate above is re-run on the real tree at implementation; a scratchpad
green is never quoted as a shipped green.

## Part 6 — Implementation outcomes

### What shipped

| Item | Delivered |
|---|---|
| **M1-1** deps | `react` 18.3.1→**19.2.8**, `react-dom` 18.3.1→**19.2.8**, `react-router-dom` 7.18.1 **removed**, `react-router` **8.3.0** added, `@types/react` →19.2.17, `@types/react-dom` →19.2.3. Installed via `npm install` → **`npm dedupe`** → `npm ls react` (one copy) → `npm ci` (reproducible) |
| **M1-2** imports | 18 files, `react-router-dom` → `react-router`. Zero residual references in `src/` |
| **M1-3** container | `infra/docker/frontend.Dockerfile` `node:20-slim` → `node:24-slim` |
| **M1-4** gate | `audit-allowlist.json` → `exceptions: []` (+ a `_history` field recording that the one entry it ever held was retired **by fix**, not by expiry); `scripts/check_frontend_audit.mjs` refactored to export the pure `evaluateAudit(report, allowlist, today)` + `collectAdvisories(report)` behind an `import.meta.url`/`argv[1]` main guard — CLI behaviour unchanged |
| **M1-5** fences | eslint router ban; `router-fence.test.ts` (11); `dependency-fence.test.ts` (8) |
| **M1-6** router | `src/App.browserrouter.test.tsx` (5) |
| **M1-7** docs | README (current truth + two operational warnings), roadmap slice row + register row, `current_state.md` CURRENT TRUTH, `wave_12_close_review.md` §5 TIPPED item (2) marked **PAID** |

### The lockfile delta — declared before implementation, measured after

Part 2 declared **exactly 12**, and said a 13th would be a defect. Measured: **12**, matching
line for line — `react`, `react-dom`, `react-router`, `@types/react`, `@types/react-dom`,
`scheduler` 0.23.2→0.27.0, `cookie-es` added, and `react-router-dom` / `loose-envify` /
`@types/prop-types` / `cookie` / `set-cookie-parser` removed. `vite` stayed at 8.1.3 — the
scope boundary (OQ-FE-M1-6=A) held in fact, not merely in intent.

### The verification ladder (OQ-FE-M1-5=A), executed

| # | Check | Result |
|---|---|---|
| 1 | `npm audit --omit=dev` **before** | 2 High, both `GHSA-qwww-vcr4-c8h2` |
| 2 | install procedure | `npm ls react` → **one** `react@19.2.8`, deduped everywhere; `npm ci` reproducible |
| 3 | lockfile delta | **12**, as declared |
| 4 | `make fe-check` | **green** — eslint, prettier, `tsc --noEmit`, vitest **32 files / 187 tests**, `vite build` 287.95 kB, audit gate |
| 5 | `npm audit --omit=dev` **after** | **`found 0 vulnerabilities`** |
| 6 | fence negative + positive controls | all executed — see below |
| 7 | gate behaviours | 13 cases, incl. the three that must FAIL |
| 8 | test-count drift | 150 → 187 = **+37**, exactly `audit-gate` 13 + `router-fence` 11 + `dependency-fence` 8 + `browserrouter` 5. The migration itself added **0** and removed **0** |
| 9 | container | `docker compose build frontend` on `node:24-slim` **succeeded with ZERO `EBADENGINE` warnings**; the image served `/ops/breaches` → **200 + the SPA shell**, and its `/assets/index-azwg_KpJ.js` → **200, 287,953 bytes** (the migrated bundle, byte-identical to the local build) |
| 10 | `make check` (Python tier) | **2193 passed / 478 skipped**, secret-scan and docs-check green — identical to the OPS-H1 baseline, which is the "nothing else was disturbed" control. Scope confirmed: **zero** Python files, **zero** migrations, frozen `audit/service.py` untouched |
| 11 | CI | **GREEN, all six jobs, on BOTH commits** — run **30388265933** (`8f9711c`, the implementation) and run **30388621527** (`b8767ce`, the review folds), each `conclusion=success` across Frontend (TypeScript), Backend (Python), DB migration (Postgres), API type drift, Documentation check, Secret scan. Written here only after the runs were observed completed, not when they were queued (R-3) |

**The audit gate's own output, pasted verbatim (the OQ-W12C-3a rule):**

```text
$ node scripts/check_frontend_audit.mjs
Frontend runtime-dependency audit passed (no moderate+ advisories).
```

### Executed controls — every guard carries its own refutation

| Guard | Negative control (must FAIL) | Positive control (must PASS) |
|---|---|---|
| eslint router ban | `import { Link } from "react-router-dom"` from six sites incl. `writes.ts` → rejected | `react-router` clean; `@scope/react-router-dom-utils` **not** over-matched |
| the **V-3** hole | Config mutated back to `"no-restricted-imports": "off"` for `writes.ts` → **killed exactly 2 assertions and no others**; config restored, residue grepped clean | write fence still relaxed in `writes.ts` |
| manifest pin | `react-router-dom@^7.11.0` injected into `package.json` + lockfile → 2 assertions failed | restored, `grep` confirms no residue |
| single-React pin | second `react@18.3.1` injected into the lockfile → failed **with a message naming the cause and the `npm dedupe` fix** | restored |
| audit gate | empty allowlist + an advisory → FAIL; expired exception → FAIL (even when the advisory is gone); JSON drift → FAIL-CLOSED | empty allowlist + clean tree → pass; unexpired exception → pass; `review_by == today` → still valid |

### Two things measured that the plan had wrong, and one it had right for the wrong reason

- **V-1/V-2 (folded pre-gate)** are recorded in Part 1b. Both were invisible to reading and to the
  upstream upgrade guide.
- **V-6, restated honestly here because it is a claim about a shipped guard:** the single-React pin
  is a **diagnostic**, not a detector. The suite *does* catch a duplicate React — loudly, at 73
  failures. What it does not do is say *why*. The pin's contribution is the message, plus covering
  the one shape `tsc` and `vite build` both pass.

### The six-ledger omission sweep (standing Wave-13 closeout step)

Run in full, with the SR-1 clause *verify the fix is on `main`* applied to this slice's own commits:

| # | Ledger | Result |
|---|---|---|
| 1 | `canonical_data_model_standard.md` | **No change owed** — FE-M1 mints no entity; "next free = **ENT-066**" remains correct |
| 2 | `audit_event_taxonomy.md` | **No change owed** — FE-M1 mints no audit code; the `PERF.*` reserved set is still exactly three |
| 3 | `control_matrix_skeleton.md` | **NO CONTROL MOVED** — stated explicitly per OQ-W12C-3c. The supply-chain audit gate (TC-1 / OD-TC-1-D) has no CTRL row to move; FE-M1 strengthens its *evidence* (its first test) without changing any control's status |
| 4 | `current_state.md` | **Updated** — CURRENT TRUTH advanced to 2026-07-28c |
| 5 | `02_requirements/` backbone + RTM | **No change owed** — no requirement added or satisfied; the both-halves test stays green under `make check` |
| 6 | Counts | **UNCHANGED at 25/40/133**, and *not* re-derived — FE-M1 adds no demo stage and touches no Python, so the existing post-last-stage pin is the measurement |

## Part 7 — Review and folds

### Method, stated honestly

This session had subagents and workflows unavailable, so the adversarial pass could not be run at
the top of the operating instructions' independence ladder (`/code-review ultra`, then an
independent-context agent). It was run **inside the authoring context**, which is that ladder's
weakest rung and inherits the author's blind spots by construction.

Two things partly compensate, and neither is a substitute:

1. **The pre-ratification pass was empirical, not analytical** (Part 1b). An executed dry run does
   not share the author's blind spots — which is precisely why it caught V-1 and V-2 when reading,
   `grep` and the upstream upgrade guide had all missed them.
2. **Every fence carries an executed mutation control**, so the guards are proven by refutation
   rather than by the author's assessment of them.

`/code-review ultra` on this branch remains available to the user and would be the stronger check.

### R-1 (fold) — the fences had an EXTENSION hole

**Found by probing rather than reading.** Both `no-restricted-imports` fences were scoped to
`.ts`/`.tsx`. A `.jsx` file is linted by **nothing**: eslint reports *"File ignored because no
matching configuration was supplied"* and **exits 0**. So a single JSX component could import
`react-router-dom` — undoing this slice — or reach `client.ts::request` and issue an unaudited
POST, past the OPS-1 M-4 write fence. The app is 100% TypeScript today, but Vite compiles `.jsx`
without complaint, so nothing structural stops it.

This is the **Wave-12 close HIGH's own defect class along a different axis**: there, the write
fence was bypassable by import-path *spellings* the ratifying probe never enumerated; here, by file
*extension*. Its third appearance in the fence family argued for closing it now rather than letting
a close audit find it again.

**Fold:** a fourth eslint block covering `**/*.{js,jsx,mjs,cjs}` with both fences and
`ecmaFeatures.jsx` enabled — a separate block because those files need espree-with-JSX rather than
the TS parser, and because the file set is **disjoint** from the blocks above, so the
re-declaration cannot silently override them (the same flat-config trap V-3 was about).

**Controls executed:** the `.jsx` router import and the `.jsx` `request` import both now fail lint;
a clean `.jsx` importing `react-router` passes. Mutating the block's glob to match nothing **killed
exactly the two negative-control tests**; the positive control correctly survived, because an
unlinted file also yields zero findings — it is a permission check, not a detector. Both cases are
pinned in `router-fence.test.ts` and `write-fence.test.ts` rather than left as a one-time hand
proof.

### R-2 (fold) — an overclaim in the audit-gate refactor's own comment

The refactor header said *"Behaviour is UNCHANGED — the CLI composes exactly the same steps in the
same order."* The **decisions, failure conditions and exit code** are unchanged, but the console
**output order is not**: messages were previously printed as each check ran (interleaved) and are
now collected and emitted as info → warnings → errors. Corrected in place to say exactly that. A
slice whose stated purpose is replacing an untested claim with evidence should not ship a new
untrue claim in the same file.

### R-3 (noted, not folded) — Part 6 asserted a CI result before CI had run

The verification table listed row 11 as "CI — watched to green" while the run was still queued.
Changed to an explicit *pending* marker, filled in only from an observed result. No defect shipped;
recorded because "reporting success without verification" is a named prohibition and this is how it
begins.

### R-4 (fold, found by the cloud review) — the M1-6 `useParams` test proved nothing

`App.browserrouter.test.tsx`'s deep-link-with-a-parameter case booted at `/runs/risk/{uuid}`. But
`risk` is a `permissionFamily` **value** in `FAMILIES`, not a **key** — so `RunDetail`'s allowlist
(`family in FAMILIES`) resolved `validFamily=null`, the effect early-returned **without fetching**,
and the component rendered its *"Unknown run family in the URL"* page rather than the 404 branch
the mock staged. Both assertions (pathname unchanged; walk text absent) are satisfied by that page
too, so the test passed **coincidentally**: a genuine break in `useParams`-over-the-History-API —
the only reason M1-6 exists — would have left it green.

Same defect class as R-1 and the Wave-12 HIGH, one axis further out: a control whose *positive*
result is produced by a path other than the one under test. A by-absence assertion cannot tell
"the param arrived and the view honestly reported not-found" from "the view bailed out early".

**Fold:** `vars` (a real `FAMILIES` key) for `risk`, and the assertions strengthened from
by-absence to by-evidence — the fetch is asserted to have been called **exactly once** with
`/risk/vars/runs/{uuid}` (the runId from the URL reaching the request path is the actual claim), and
the rendered text asserted to be the *not-found* branch, not merely "not the walk overview". The
family-key trap that produced this is now called out in the test's own comment.

### Post-fold gates

`make fe-check` green: **32 files / 190 tests** (187 + the three `.jsx` fence cases; R-4 rewrote an
existing case rather than adding one), `vite build` clean, audit gate clean. `make check` unaffected
(no Python touched). Re-run after R-4: prettier, eslint `--max-warnings=0`, `tsc --noEmit` and the
full 190 all clean; `make docs-check` passed. CI run **30392210205** (`922cf20`, the R-4 fold)
observed **completed / success across all six jobs** — written here after observing the completed
run, per R-3.
