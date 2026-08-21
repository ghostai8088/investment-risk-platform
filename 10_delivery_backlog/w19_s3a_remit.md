# W19-S3a remit — the INGEST-1 spine: mapping version, interpreter, load path

**Wave 19, slice 0.** Branch `w19-s3a-mapping-spine`. Authority: `wave_19_planning.md` (RATIFIED
2026-08-20, PR #231) + `ingest_1_decision_record.md` (RATIFIED 2026-08-12, OQ-ING-1..4 all = A).
Where this remit and either record disagree, the records win and the disagreement is a FINDING.

**Status: RATIFIED by the owner 2026-08-20** — DS3a-1 through DS3a-4 all as recommended
(AskUserQuestion, four questions, four recommended options selected). DS3a-5 was not put to the owner
and is recorded as a builder's call flagged for reversal (Part 4). **Two of the ratified decisions —
DS3a-2 (the audit-code mint moves into S3a) and DS3a-3 (the self-ratification refusal ships in S3a) —
are scope changes to the wave plan ratified earlier the same day, and they were surfaced as such
rather than taken.** `wave_19_planning.md` Part 2's S3a paragraph and roadmap Part 2.21's S3a row are
amended in this slice's first commit to match, so the plan and the build do not disagree on the record.

Planned against main `d3890a4`, tree clean. Migration head `0073_declare_root_currency`, one head.
Next free canonical id **ENT-077**; next free control id CTRL-040. CI green on all nine checks at
`d3890a4`, verified per conclusion (`gh api …/commits/d3890a4/check-runs`): SBOM, Frontend, API type
drift, Container images, DB migration, Documentation, Stack proof, Secret scan, Backend — all
`success`.

Remits state OUTCOMES and PROOFS (the DEP-1 operating model), not steps.

**G2 (P20 T1) is PAID.** `g2_slice_scope.json` declares `slice: WAVE-19-S3a`,
`slice_scope: ["REQ-INT-001"]`; the row was AMENDED and adjudicated at the wave gate, hash
`eda69d98…`, CURRENT. Re-verified this session: `python3 scripts/check_g2_adjudication.py` → exit 0,
103 rows parsed, 1 in scope, 0 blocking. **Consequence: the acceptance cell must not be touched in
this slice** — even an annotation lapses the hash (the PPM-006/PPM-010 class at the Wave-18 close).

**Verification of this document (P15).** Four refute-by-default lanes — fact-check, acceptance
contract, design/invariants, proof plan — **25 findings, 6 BLOCKING**, all folded below or promoted
to Part 4. *Engine, stated precisely rather than dressed up: Claude Fable's allocation is exhausted
(it failed all four lanes with zero agents completed, the same exhaustion the wave gate hit), so the
lanes ran on **Sonnet 5** — a different model, not a different vendor. That is weaker than the wave
gate's Opus-verifies-Fable pass and stronger than a same-model fresh context, and it is recorded as
what it is.* One lane finding was **REFUTED by execution** and is recorded in Part 5 rather than
folded, because a kill needs a factual refutation (P13) and this one has it.

---

## Part 1 — Scope line, stated so the gap is not read as an omission

REQ-INT-001 has ten acceptance clauses. **This slice delivers eight, plus the batch half of (2) and the refusal half of (6).**

| Clause | Where |
|---|---|
| (1) no-ratified-mapping REFUSES · (3) edited mapping changes rows exactly where the edit says · (4) interpreter is the only write path *from staged rows*, mechanically discovered · (5) each operation's refusal FIRES, unsupported refused BY NAME · (7) proposing model version + prompt identity, or HAND_AUTHORED · (8) demonstrating file exercises ≥3 operation kinds · (9) reproducible from mapping + staged file + code-lookup reference data as of the load · (10) overlapping re-load REFUSES unless flagged a restatement | **S3a** |
| (2) *every ingestion batch* binds the mapping version by hard FK | **S3a** |
| (2) *every loaded position row* binds the mapping version by hard FK | **S3b.** S3a instead roots each loaded row's lineage ORIGIN edge at the ingestion `data_source` (DS3a-4 ratified), so the provenance is TRUE in S3a and becomes a column in S3b. |
| (6) four-eyes ratification | **Split (DS3a-3 ratified).** S3a fires `SelfRatificationError`; S3b ships the governed R-07 permission mint, the P11 holder-set pin, the route census row and the SoD row — the separation, not the equality check, is what makes four-eyes real. |

**REQ-INT-001's Status stays In-Progress at the S3a merge** and goes Delivered at S3b. Both halves
of the register (backbone and RTM) say so — the Wave-18 BLOCKING recurrence class.

---

## Part 2 — Outcomes

### 1. ENT-077 `ingestion_mapping_version` exists, and it is a governed artifact

Tenant-scoped, PROPRIETARY, **symmetric** FORCE RLS (`USING` == `WITH CHECK` == own tenant). **Not**
added to `HYBRID_TABLES` — closed at seven by CLAUDE.md and DB-censused by `test_tenancy_floors_pg.py`.

Temporal class **IA, status-mutable** — the `ingestion_batch` / `calculation_run` precedent: `status`
transitions PROPOSED → RATIFIED → SUPERSEDED, the row is **not** in `APPEND_ONLY_TABLES`, carries no
`irp_prevent_mutation` trigger and no ORM guard, and the authoritative history is the audit chain.
The docstring says which choice was made and why, because the opposite (true IA + trigger) is the
more common one here and a reader must not have to infer it.

**Content columns are never amended in place, and that is ENFORCED, not asserted.** A service-tier
guard rejects any update touching a column other than `status`, `ratified_by_actor_id`,
`ratified_at`, `supersedes_id` — with a mutant proving the guard load-bearing. *(The first draft of
this remit said "never amended in place" and named no enforcement point at all; a verifier lane asked
where it lived and the answer was nowhere.)*

**At most one RATIFIED version per `(tenant_id, data_source_id, source_type)`**, as a partial unique
index. **The predicate is spelled in `postgresql_where` AND an identical `sqlite_where`** — verified
by execution this session that a `postgresql_where`-only index renders on SQLite as a *plain* unique
index with the predicate silently dropped, and the unit tier builds its schema on SQLite. The
precedents that get this right are `uq_position_current` and `uq_identifier_xref_active`, and both
carry the twin predicate. A unit-tier test creates a SUPERSEDED plus a PROPOSED row for the same key
and proves the index is genuinely partial. *(The first draft cited `ModelVersionConflictError` as the
precedent for this. That was wrong: `model_version` carries a plain non-partial unique constraint and
its error is about re-pointing an identity, not about supersession — versions there coexist freely.)*

Columns, each load-bearing:

- `operations` (JSON) + `operations_hash` (sha256 over a canonical serialization) — the
  reproducibility key clause (9) names.
- `authorship` ∈ {`MODEL_PROPOSED`, `HAND_AUTHORED`}, with a **symmetric** CHECK: `MODEL_PROPOSED`
  requires `proposer_model_version_id` and `proposal_prompt_hash` NOT NULL; `HAND_AUTHORED` requires
  both NULL. *(One-directional was the first draft. It let a HAND_AUTHORED row carry stale or forged
  model attribution that a reviewer would read as provenance — the mirror of the false record clause
  (7) exists to prevent.)* This is a conditional NOT NULL, not a vocabulary CHECK — `authorship` and
  `status` stay plain strings extended by value, per the genericity rule.
- `proposer_model_version_id` — hard FK to `model_version`, **re-resolved tenant-filtered before it
  is stamped** (`assert_model_version_in_tenant`), because PostgreSQL FK checks bypass RLS and would
  durably admit a cross-tenant reference. Hard FKs to `model_version` are the norm here (21 sites);
  `calculation_run.model_version_id` is the deliberate FK-less exception, not the precedent.
- `proposal_prompt_hash`, `proposal_prompt_ref`, `proposal_response_ref` (Outcome 5).
- proposer / ratifier actor ids and timestamps; `supersedes_id` (self-FK).

**Migration `0074_ingestion_mapping_version`** (30 chars, under alembic's `varchar(32)`).

**Identifier lengths, computed rather than estimated** — the generated names overflow PostgreSQL's
63-byte limit *silently, by truncation*, and this exact class already bit this repo once
(`classification_assignment.supersedes_id`, 68 chars, found by an executed dry run and fixed with an
explicit name). The two overflows on this table:

| Generated name | Length | Action |
|---|---|---|
| `fk_ingestion_mapping_version_proposer_model_version_id_model_version` | 68 | explicit `fk_ingestion_mapping_version_model_version` |
| `fk_ingestion_mapping_version_supersedes_id_ingestion_mapping_version` | 68 | explicit `fk_ingestion_mapping_version_supersedes` |
| `ck_ingestion_mapping_version_<suffix>` | 29 + suffix | suffix budget is **34 chars**; pass the SUFFIX to `create_check_constraint`, never the full name (the 0057 double-prefix defect) |

Both migrations carry an **`_IDENTIFIERS` assert-at-import list** (`0055_sharpe_ratio_result.py:78-102`
is the pattern), so an overflow fails loudly at import instead of truncating in Postgres. *That
convention was not in the first draft of this remit, and the one identifier length it did show
arithmetic for was wrong — the batch FK is 63, exactly at the limit, not 64. Both errors came from
hand-counting; every length above is from execution.*

### 2. The interpreter is a closed vocabulary, and every arm refuses out loud

Seven operations, exactly as ratified at OQ-ING-2: **rename, cast, scale, parse-date, code-lookup,
constant, concatenate.** Declared as a vocabulary tuple **and** a dispatch table, censused against
each other by **exact set equality in both directions** — the LQ-1 T4 trap, where a vocabulary entry
with no dispatch entry compiles, imports, passes every census, then refuses every capture at runtime.
Each operation additionally has a test proving it EXECUTES.

**An unsupported operation is refused BY NAME** — the message contains the offending string verbatim,
asserted on the message, not the exception type.

**Every refusal names its firing condition here, at planning time, so the slice review checks
reachability against a stated design rather than the implementation's self-report.** This repo has
shipped structurally unfireable refusals twice — CON-1, and again in the Wave-19 ratification commit
— and both times the design document had left the trigger unstated.

| Refusal | Fires when |
|---|---|
| `UnratifiedMappingError` | a load names a `(data_source, source_type)` with no RATIFIED version |
| `UnsupportedOperationError` | `operations[i].op` is outside the seven; message quotes it |
| `MissingSourceColumnError` | a declared source column is absent from the staged payload keys |
| `CastRefusedError` | the value is not castable to the declared target type (`"1,234.00"` → Decimal) |
| `DateParseRefusedError` | the value does not match the declared format (`"31/02/2026"` under `%d/%m/%Y`) |
| `ScaleRefusedError` | the input is non-numeric, **or** the declared factor is zero, negative or non-finite |
| `ConcatenateRefusedError` | any named input column is absent |
| `ConstantTypeRefusedError` | the declared literal is not coercible to the target field's type (a string constant onto `quantity`) |
| `CodeLookupRefusedError` | the identifier resolves to nothing, **or** ambiguously (`AmbiguousIdentifier`) — both fired |
| `UnknownTargetFieldError` | an operation targets a field outside the declared canonical target set (`{portfolio, instrument, quantity, cost_basis, quantity_unit, valid_from}`) |
| `OverlappingLoadError` | a re-load whose `(portfolio, instrument)` already has an open current-head version at the same `valid_from`, not flagged a restatement |
| `SelfRatificationError` | ratifier == proposer — **conditional on DS3a-3** |

Each refusal test ships with a **positive control** (P18 clause 1), and **at least one refusal per
operation fires through the real load entry point** — the service-tier load call, not a bare call to
the operation function. *(The first draft's positive control was "a staged row reached the
interpreter", which a test calling an internal helper with a hand-built dict satisfies while proving
nothing about reachability from the governed path.)*

*P9's mechanical limb does not exist in this repo — verified, not assumed. So each firing test is
hand-written, and the slice review greps the shipped constants against this table.*

### 3. No path from staged rows to `position` except the interpreter

**Clause (4) is scoped to "from staged rows to canonical positions", and the first draft of this
remit widened it to "the only write path to `position`" — which is false and unachievable.**
`POST /positions` calls `create_position` directly under `position.edit`, with no staged file
anywhere near it; it is live, it stays live, and it is **an intentionally unmapped manual-entry path
outside REQ-INT-001's guarantee**, recorded here rather than left to be discovered at review.

The census's subject is therefore the *composition*: by AST across `irp_shared` + `irp_backend` +
`irp_worker`, every module that reads `IngestionStagedRecord` (or its `payload`) **and** reaches a
position write — `Position(...)` construction, `session.add` of a Position, a call to one of the
three binders, ORM bulk paths, or a `text()` literal containing `INSERT INTO position`
(over-capturing on the string arm deliberately, the aggregation census's own trade). The permitted
set is exactly one module: the interpreter.

It ships with **both** guards the precedents carry and the first draft had only one of:

- a **positive control against a known pre-existing production site** — the matcher must still detect
  the three real binder call sites in `position/position.py`, the `test_db_foreign_keys.py` shape, not
  a freshly authored plant the matcher was written for;
- a **P6 coverage floor** — the discovered legitimate-site count is asserted equal to its measured
  value, so a refactor that collapses the population fails loudly rather than reporting an empty
  offender list, which is indistinguishable from total compliance.

### 4. A load is reproducible from three named inputs, and the third is recorded

Clause (9) names the mapping version, the staged file, **and the code-lookup reference data as of the
load**.

**Verified, and it constrains the design: `resolve_identifier(..., as_of=)` over `identifier_xref` is
the only as-of-capable resolver in the repo** — `resolve_node`, `resolve_scheme`, `resolve_ancestors`,
`resolve_currency`, `resolve_calendar` all resolve current state only. Two consequences, both from the
verification:

- **`code-lookup` resolves INSTRUMENTS only.** `resolve_identifier` is hard-fenced to
  `entity_type == 'instrument'` (P1B-3's recorded scope fence); there is no as-of-capable
  portfolio-by-code resolver, and lifting that fence is its own surface. **The demonstrating file is
  therefore a single-account statement and its portfolio arrives through a `constant` operation.** A
  multi-account file needs either a portfolio resolver or the fence lifted, and that is named as an
  S3b/Wave-20 entry condition rather than assumed away.
- **`ingestion_batch` gains `lookup_as_of`** in migration 0075, stamped once at interpretation time
  and used for every code-lookup in that batch — otherwise "as of the load" is an assumption a re-run
  cannot read back. *(The first draft promised the as-of and gave it no column; `grep -n "as_of"`
  over the ingestion package returns nothing, exit 1.)*

**`resolve_identifier` does not honor `is_active`** — it filters `valid_from`/`valid_to` only, while
`is_active` is independently mutable through `update_identifier_xref` without closing `valid_to`. So
a deactivated-but-open xref still resolves. That is existing behavior with other callers, changing it
is its own review, and clause (9) is **explicitly not claiming** `is_active` fidelity. Stated, not
silently inherited.

Proof: re-running the load from `(mapping_version, staged rows, lookup_as_of)` produces canonically
identical rows, and **moving `lookup_as_of` across an `identifier_xref` supersession resolves a
different instrument** — the differential that makes the third input real rather than decorative.

### 5. Clause (3): an edited mapping moves exactly the rows the edit touches

This clause had no outcome of its own in the first draft, and it is the one clause that **collides
with clause (10)**: "re-load the same file" is by definition the overlap `OverlappingLoadError`
refuses. They compose rather than conflict, and the composition is the design:

1. Load the file under RATIFIED mapping V1.
2. Propose V2 — V1's operations with **one** operation edited (a scale factor, say) — and ratify it;
   V1 goes SUPERSEDED. **V2 carries `authorship = HAND_AUTHORED`**, because it is an operator edit of
   a ratified artifact and labelling an operator's edit as model-proposed would be the exact false
   record clause (7) exists to prevent.
3. Re-load the identical staged file **flagged as a restatement**, which is the only way past clause
   (10) and is itself the clause-(10) positive control.
4. Assert the corrected version differs from the prior system-time version **exactly** in the fields
   the edited operation touches, and that every other field and every other position is byte-identical.

### 6. The batch binds its mapping version; an overlapping re-load refuses

**Migration `0075_bind_batch_to_mapping`** adds `ingestion_batch.mapping_version_id` (**nullable** — a
generic non-positions upload legitimately has none, and the table is populated on every live
deployment; nullable-plus-an-honest-docstring is the `0046` precedent) and `lookup_as_of`. Explicit FK
name `fk_ingestion_batch_mapping_version` — the generated name is 63, *exactly* at the limit, and
sitting on a limit is not a margin.

**DP-19-7 mapped onto the shipped FR protocol:** same `valid_from` with an open current head →
`OverlappingLoadError` unless flagged a restatement; a flagged restatement goes through
`correct_position` (as-known, stamping `restatement_reason` — TR-08's existing rail); a later
`valid_from` goes through `supersede_position`.

*The constraint the interpreter must respect: `uq_position_current` is UNIQUE on
`(tenant_id, portfolio_id, instrument_id)` WHERE both close-out columns are NULL, so a file with two
rows for one instrument raises `IntegrityError`, not a duplicate. Reuse the existing `is_unique_violation`
discrimination into a 409 and re-raise everything else loudly — never a blanket `except`.*

### 7. The upload path can actually accept a positions file

**Found by the verification, and it would have stopped the demo dead:** `stage_upload`'s DQ gate is
fail-closed — with **no** active `staging.row` rule the batch is driven to REJECTED — and grep shows
the only places such a rule is ever created are three *test* files. There is no seed, no migration and
no demo fixture that registers one.

So the slice registers at least one active `staging.row` `DataQualityRule` on the demo path, and a
test proves `stage_upload` accepts a well-formed positions file end to end.

### 8. Rule 7: the mapping is visible, and un-ratified does not render as ratified

`ops/mappings` and `ops/mappings/:mappingId`: versions, authorship and proposal provenance (model,
version label, prompt hash), ratification state and actors, the operation list rendered readably, and
the batches loaded under each version.

**Honest-empty is a hard convention here** — an empty version list must not read as an all-clear, and
a PROPOSED mapping must not render as ratified. The detail screen is mounted under a real router in
its test; rendering it bare leaves `useParams` undefined and lets the assertion pass by absence (P5).

`/ingest` is not currently in `API_PREFIXES` though three `/ingest/...` routes exist; if the screen
reads any, the prefix goes into **both** `api-prefixes.ts` and the nginx alternation, whose set
equality is pinned in both directions.

### 9. The drafting model is registered, and the demonstration is genuinely proposed

Per OQ-ING-3 no model call happens inside the deployed product and no API key exists in the deployed
stack. The drafting act runs **operator-side, on SCHEMA ONLY** — column names, inferred types,
obfuscated sample values, never rows.

The demonstrating proposal is produced by actually performing that act at build time, and the
committed artifact carries what it really was: model identity, the verbatim prompt, the obfuscated
schema digest it was given, **and the raw response envelope**, so a reviewer has something
independently checkable rather than the builder's say-so. *(A verifier lane's fair objection: nothing
in the gate battery can distinguish a real call from a hand-typed pair, and the CHECK constrains
presence, not provenance. The envelope narrows that; it does not close it, and the residual is stated
rather than papered over.)*

Registration follows the measured recipe — a methodology doc under `05_analytics_methodologies/`
written **before** the `*_METHODOLOGY_REF` constant is named, `resolve_or_register_model` +
`resolve_or_register_version` with the post-checks intact, and the bare literal `status="REGISTERED"`
(omitting it mints `status=None`, which binds nowhere). **Per-tenant; the SYSTEM path is ruled out.**

*Recorded for the S3b review: an agent actor may REGISTER a model version but may never VALIDATE or
TIER one — `record_validation` and `assign_model_tier` refuse `actor_type != 'user'` before any write
(BR-15/MG-07). Ratification of a mapping is a human act by mechanism, not by convention.*

### 10. The demonstration: a client-shaped file, loaded, read back, run on

DP-19-11 as ratified — a realistic multi-asset CSV in a public broker-statement shape: headers a
custodian would emit, quantities in a scaled unit, a non-ISO date, identifiers by scheme. It exercises
**at least four** of the seven operations against the clause-(8) floor of three, single-account (see
Outcome 4), economically plausible per TD-1, and well under `MAX_UPLOAD_BYTES`.

Demo stage 28 walks it: propose → ratify → load → read back → **run the exposure family over the
loaded book at a NON-ROOT node** — the D2 touch-trigger discharge. **D1 is argued, not asserted:** the
loaded book is a NEW book, not one of the shared flat demo books the D1 residual rests on, so D1 does
not fire; if the slice ends up touching a shared book's goldens, the fresh post-rename re-run lands
in-slice.

---

## Part 3 — Fences, enumerated before drafting (P7's pre-flight companion)

Discovered at recon and verification by execution. Each is a red gate if missed.

1. **`test_scope_fence_generic_only` pins `batch_fks == {"data_source"}` exactly** — the clause-(2)
   bind breaks it on the first commit. It is a SCOPE fence: amended deliberately, in-slice, with the
   ratified reason recorded at the assertion. Same test pins `IngestionStagedRecord`'s six columns —
   **do not add one there.**
2. **Import direction.** `irp_shared/ingestion/` may not import `irp_shared.model`, so the mapping
   code lives in a **new package** that may import ingestion, position, reference and model, and it
   ships **its own import-direction fence test in-slice**, using `rglob` (the ingestion fence globs
   top-level `*.py` only — a subpackage is invisible to it). `irp_shared/position/` may not import it,
   so S3b's `position` FK is spelled as a literal `ForeignKey("ingestion_mapping_version.id")` with no
   Python import — the `HYBRID_TABLES` literal-spelling precedent.
3. **The aggregation AST census** (exact set **and count** equality over three source trees) fires on
   any `+=`, `sum()`, `x = x + y`, or a docstring containing `SUM(`. A row counter trips it. Budget
   `_ALLOWLIST` entries with a taxonomy class, and note
   `irp_shared.ingestion.service::stage_upload::augassign-add` is listed at count 1 — a second `+=` in
   that function drifts the count.
4. **`EXPECTED_ROUTE_COUNT = 308`** is exact; every new route moves it consciously in the same commit.
5. **Ledger obligations in the creating commit.** A `` `ingestion_mapping_version` `` row in
   `canonical_data_model_standard.md`; **the "next free canonical id" pointer exists in THREE live
   copies — lines 97, 130 and 131, all reading ENT-077 — and all three advance to ENT-078.** *(The
   file's own line 97 records that this multi-copy drift already caused two mints to update the
   registry and not the pointer, and nothing mechanical checks it.)* Plus registration in
   `irp_shared.models`, or `alembic check` proposes DROPPING the governed table (the LQ-1 defect).
6. **Ledger 2, the audit taxonomy — see DS3a-2.** A `status` lifecycle with no audit event would be
   the first on this platform; both cited precedents (`ingestion_batch`, `calculation_run`) emit on
   every transition. This is a governance act, not a doc chore.
7. **PG floors:** RLS ENABLED *and* FORCED on the new table; its policy must not mention
   `SYSTEM_TENANT_ID` anywhere; a `has_table_privilege('irp_ops', …) is False` negative control
   matching the two existing ingestion tables; no new grants (0070's ALTER DEFAULT PRIVILEGES covers
   `irp_app`).
8. **`test_migration_head.py:22`** — one line, the final head. **Chain-position assertions for both
   new revisions** in the slice's own test file (0072 and 0073 skipped the convention; do not inherit
   the omission). **No `synthetic` substring** anywhere in a migration file.
9. **CI:** one new `(Postgres, INGEST-1)` step for the new `*_pg.py` suite, placed **before** the demo
   stages unless it seeds a book, or `test_ci_pg_coverage.py` reddens at the unit tier. The
   `Revert migrations to 0071` step runs the new downgrades **over the fully seeded book**.
10. **`make gen-api-check` diffs the worktree; CI diffs HEAD** — `openapi.json` and `api-types.d.ts`
    must both be COMMITTED. **`make fix` before the first gate run.**
11. **`make mutant-anchors` is 130/130**; displaced bytes turn another slice's anchor STALE, and a
    stale anchor reports as a SURVIVOR. Run it early; re-anchor, never delete.
12. **Mutants cannot prove DDL** — the battery runs against an already-migrated database, so every DDL
    claim needs a schema-reading PG test instead. **The mutants this slice owes, named now:** one per
    dispatch-table entry (7), one for the write-path census matcher, one for the content-immutability
    guard, one for the `UnratifiedMappingError` gate, one for the tenant-filtered FK re-resolution,
    one for the restatement flag check — **12**, plus one for `SelfRatificationError` if DS3a-3 is
    ratified. The DDL-side claims (FORCE RLS, the symmetric CHECK, the partial unique index, the
    identifier lengths) are **not** mutation-provable and get schema-reading PG tests instead.
13. **Frontend:** never import `request` outside `src/api/writes.ts`; never `Number()` an API decimal
    (`verbatim()`); a new root-level guard test must be listed in `tsconfig.guards.json`;
    `noUnusedLocals` makes an unused import a build failure; **the `.name`-read census
    (`test_name_census.py:255-274`) pins an exact three-file set** — a screen reading `.name` breaks it.

**Baseline, measured at `d3890a4` and independently re-measured during verification — not derived:**
`pytest --collect-only` 3,539 collected; unit tier **2,908 passed / 631 skipped**, exit 0; frontend 38
files / 266 tests, exit 0; shared-ts 1/1, exit 0; `make mutant-anchors` 130/130, exit 0; G2 register
103 rows / 1 in scope / 0 blocking, exit 0. Any drop after S3a is a regression to explain.

---

## Part 4 — Decisions this slice cannot make for itself

**DS3a-1 — RATIFIED: (b), the service tier.** How the ratification act is guarded, given that the R-07 permission mint is S3b's.
(a) expose propose/ratify over HTTP under the existing `data.upload`, re-pointing at S3b's minted
code; or (b) ship the mapping READS over HTTP (screen included) and keep the ratification act at the
service tier, exercised by tests and the demo stage, with the HTTP verb landing in S3b with its own
code. **Recommend (b).** `data.upload` is an upload permission; gating a governed ratification with it
puts a maker verb and a checker verb behind one code for a slice — the co-granting S3b's mint exists
to prevent — and re-pointing later is a breaking API change.

**DS3a-2 — RATIFIED: (a), the audit-code mint moves into S3a.** A scope change to the ratified plan, surfaced as one. The plan assigns the `MAPPING.*`
audit event codes to **S3b**. But S3a is where the PROPOSED → RATIFIED lifecycle is born, and no
existing code covers it (`DATA.INGEST` is scoped to `ingestion_batch`, `DATA.VALIDATE` to DQ runs). So
S3a as planned ships a governed status lifecycle with **no audit event at all**, which no other
lifecycle on this platform does. Options: (a) **move the `MAPPING.*` audit-code mint into S3a** (an
R-07 act covering audit codes only; the permission codes stay in S3b with the four-eyes lifecycle);
(b) reuse `DATA.INGEST` against `entity_type='ingestion_mapping_version'` and re-point at S3b, which
leaves historical events under a code whose taxonomy row does not describe them; (c) emit nothing in
S3a. **Recommend (a)** — audit codes belong with the entity that emits them, and (c) is not a real
option on this platform.

**DS3a-3 — RATIFIED: ship the refusal in S3a.** Also a scope change to the ratified plan. The plan says "single-actor
ratification in this slice" and puts four-eyes wholly in S3b. Refusing `ratifier == proposer` is cheap
and strictly better, but adding it is a builder widening a ratified scope line, which the standing
rules forbid. **Recommend shipping it**, with clause (6) still counted as S3b's because the permission
separation — not the equality check — is what makes four-eyes real. Reverse by dropping the refusal.

**DS3a-4 — RATIFIED: (b), a source override on the position binders.** How S3a-loaded positions are attributed, now that the first answer is refuted. The first
draft proposed a lineage ORIGIN edge as the stand-in for S3b's per-row FK. **The verification killed
it by reading the code:** `position/service.py::_origin_edge` is hard-coded to root every edge at the
tenant's shared `MANUAL` data source via `ensure_manual_source`, and none of the three binder entry
points accepts a source override — so an interpreter-loaded position would be attributed to *manual
entry*, which is worse than no attribution because it is a false record. Options: (a) accept that
S3a's loaded positions carry attribution only in the audit chain until S3b; (b) extend the three
binders and `_origin_edge` with an explicit source override and root the edge at the ingestion data
source; (c) pull `position.mapping_version_id` into S3a as a third migration. **Recommend (b)** — it
is a small, well-fenced change to a service the slice already touches, it makes the provenance true
rather than merely absent, and it leaves the hard FK exactly where the plan put it.

**DS3a-5 — NOT put to the owner; builder's call, flagged for reversal: NO.** Does S3b's `position.mapping_version_id` enter the snapshot content hash? Decide now, not
at the S3b review. `snapshot/serialize.py::position_content` is a hand-enumerated field list, and
adding the column would make **every** pre-S3b POSITION component drift — 294 of them in the local
validation DB — marking historical snapshots DIVERGED in the CTRL-018 sweep. **Recommend NO**, on
exactly the reasoning that made the S1 pinned-contract finding BLOCKING at the wave gate: a
provenance column is not a value the reproduction is about.

---

## Part 5 — One verification finding REFUTED (P13 requires a factual refutation, and this has one)

A lane reported the frontend `.name`-read census as **fabricated**, citing
`grep -rln "census" apps/frontend --include="*.ts"` returning nothing (exit 1). The census exists:
it is a **Python** test, `packages/shared-python/tests/test_name_census.py:255-274`
(`test_name_census_frontend_has_zero_portfolio_reads`), which `rglob`s `apps/frontend/src` for
`.name` reads and asserts set equality against exactly `{api/writes.ts, views/ops/LimitHealth.tsx,
views/ops/PortfolioStructure.tsx}`. Grepping the frontend tree for the word "census" cannot find a
guard that lives outside it. The fence stands and remains fence item 13.

*Left visible rather than deleted, because a verifier being wrong about one thing is not evidence
about the other 24 findings — and because the wave gate's own lesson was that a re-measurement is not
right merely because it is a re-measurement.*

---

## Part 6 — Proofs (what "done" means, and none of it is a reading)

- `make check` exit 0 with the count quoted; full-PG exit 0 with the count quoted (fresh schema, the
  four-part reset recipe, `IRP_TEST_DATABASE_URL`); `fe-check` 0; `gen-api-check` 0; `g2-check` 0;
  `mutant-anchors` 130/130 plus this slice's 12 (or 13) new mutants all KILLED.
- **Migration proofs, differentiated rather than boilerplated.** `0074` CREATES a table, so there are
  no pre-existing rows and a "P17 harness over a populated DB" would be vacuous — its proof is a
  **schema-reading PG test** (FORCE RLS both flags, the symmetric CHECK firing, the partial unique
  index genuinely partial on both engines, the tenant-filtered FK re-resolution refusing a
  cross-tenant id, `irp_ops` holding no privilege). `0075` ALTERs a table populated on every live
  deployment, so it gets the **real committed harness** on the `0071`/`0073` shape: downgrade, seed
  the pre-migration world with raw SQL, upgrade, assert positives **and** a negative control (a batch
  the migration must not touch), `sys.exit(main())`.
- CI green on all nine checks at the PR head, **verified per conclusion** via
  `gh api …/commits/<sha>/check-runs` and quoted — `gh pr checks --watch` can exit 0 for a head whose
  runs have not registered.
- The adversarial review folded before the push; **P15: at least one pass outside the authoring
  model**, with the engine named for what it is.
- The seven-ledger omission sweep, with the verify-on-main clause run AFTER the merge; the control
  matrix either moved or explicitly recorded as "no control moved"; the status-decay grep across the
  five governance docs; both register halves.
