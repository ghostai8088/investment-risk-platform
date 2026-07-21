# FE-2 Implementation Plan — OpenAPI-generated FE types

Sequence for the ratified scope (OD-FE-2-A…F). One commit per step; `make fe-check` green at each; the CI Frontend job + the new drift-check green before the PR. NO backend change unless OQ-FE-2-3 ratifies the `*In` tighten (then it becomes step 0, with its own `make check`).

**Step 1 — the schema-dump + codegen spike (prove the tool, no FE change yet).**
Add `scripts/dump_openapi.py` (imports `irp_backend.main.app`, writes `app.openapi()` to `apps/frontend/openapi.json` with `json.dumps(..., sort_keys=True, indent=2)` — offline, no server). Add `openapi-typescript` as a frontend devDependency (pin the version; verify Node-24/Vite-8 compat). Add an npm script `gen:api` = dump + generate → `src/api/generated/api-types.d.ts`. Run it; **verify the spike**: a governed `*RowOut` decimal field generates to `string`; the request `*In` decimals generate to `number | string`; a per-family row component (e.g. `SensitivityRowOut`) is a nameable generated type. Commit the pipeline + both generated artifacts. (No view/type change yet — this step only stands the pipeline up and proves OD-A/C.)

**Step 2 — replace the DTO type mirrors with generated types.**
Retype `RiskRunSummary`/`RiskRunList` as aliases of the generated `RiskRunSummaryOut`/`RiskRunListOut`; replace `RunDetailBase`'s lossy `rows: Record<string,string|number|null>[]` envelope with a discriminated union (or per-family generic) over the generated `*RunOut` types. Retype `apiGet<T>` call sites in `RunsList.tsx`/`RunDetail.tsx` against the generated types. Keep the GET-only wrapper (OD-B). `make fe-check` green; the anti-`Number()` `RunDetail.test.tsx` suite unchanged and passing.

**Step 3 — bind the view-config to the generated types (the FL-1 kill, OD-D).**
Type `FAMILY_ROW_COLUMNS` column `key`s as `keyof` the generated per-family row type; key `RUN_TYPE_TO_FAMILY` on the generated `run_type` union; bind `runDetailUrl` to the generated path set where derivable. Prove it: a deliberately-wrong column key (temporarily) must fail `tsc` (a scratch verification, reverted). Labels/ordering/`permissionFamily`/route special-cases stay hand-authored. Replace or subsume `types.test.ts`'s exhaustiveness guard with the stronger compiler binding (keep any assertion the type system can't express).

**Step 4 — the contract guard + the drift-check.**
Add a test asserting a representative governed response field's generated type is `string` (the OQ-FE-1-7 invariant, mechanized). **The CI drift-check needs BOTH Python (to `app.openapi()`-dump) and Node (openapi-typescript) — but the "Frontend (TypeScript)" job is Node-only (verifier finding, MED).** So add a **dedicated small CI job "API type drift"** with `setup-python` + `setup-node` that installs the backend + `openapi-typescript`, regenerates `openapi.json` + `api-types.d.ts`, and `git diff --exit-code`. A `make gen-api-check` target mirrors it locally. Update the code headers (`types.ts:2`/`client.ts:2`) to drop the stale "five endpoints" line.

**Step 5 — retire OD-FE-1-G (dated) + docs.**
Stamp OD-FE-1-G superseded-in-part (OD-F) in `fe_1_decision_record.md` with the FE-2 date + the "surface grew" rationale; PRESERVE the strings-verbatim clause. Update `ui_read_surface_assessment.md` F3 → addressed-by-FE-2 (dated); the roadmap FE-2 row → the closeout stamp lands at closeout. `check_docs` green.

**Step 6 — battery + review + push.**
`make fe-check` + the CI Frontend job + the drift-check all green; if OQ-FE-2-3 ratified, `make check` for the backend `*In` tighten. 4-finder review (adversarial: does the generated union let a `number` reach the DOM anywhere? / drift: can a backend DTO change slip past the drift-check? / doctrine: is the read-only fence intact, no new runtime dep, decimals still `string`-to-DOM? / scope-fence: no new screens/endpoints/permission/identity, generated artifacts committed + deterministic). Fold; push the branch; hand the compare link.

**Deferred / named follow-ups:** the `*In` string-only tighten (if OQ-FE-2-3 defers it) → the FE-write-flow slice; wiring the API-1 read endpoints into actual screens → FE-3 (the IA is the Tier-3 USER decision, OQ-W8C-5).
