# W19-S3b remit — INGEST-1 governance: four-eyes, attribution, the holdings census

**Wave 19, slice 1.** Branch `w19-s3b-ingest-governance`. Authority: `wave_19_planning.md` §S3b +
`ingest_1_decision_record.md`. Where this remit and either record disagree, the records win and the
disagreement is a FINDING.

**Status: RATIFIED by the owner 2026-08-21** — DS3b-1, DS3b-2, DS3b-5 and DS3b-6 all as recommended
(AskUserQuestion). DS3b-3 and DS3b-4 were flagged rather than asked: each is the only option that is
not a known defect, and both are recorded in Part 4 for reversal.

Verified refute-by-default on a different model before being put up: **10 findings, 4 BLOCKING**,
every one landing on something the draft got wrong — including its own claim that G2 was paid. All
folded, and the two decisions that changed shape under verification say so where they changed.

Planned against main `564a730`, tree clean. Migration head `0075_bind_batch_to_mapping`, one head.
Next free canonical id **ENT-078**; next free control id CTRL-040.

**G2 (P20 T1) is PAID — and the first version of this sentence was FALSE, which is worth more than
the sentence.** The remit asserted the scope file already declared S3b. It did not: the edit had
been written into a shell call the harness BLOCKED, so it never ran. The G2 gate was then read as
confirmation — and its headline, `slice scope: 1 / blocking: 0`, is **identical under both scopes**,
because `["REQ-INT-001"]` and `["REQ-PPM-002"]` each contain exactly one row. A gate whose SUBJECT
you did not verify is not evidence about your subject. Caught by this document's own verification
pass, not by the gate.

Now genuinely true, with the subject named rather than assumed: `g2_slice_scope.json` declares
`slice: WAVE-19-S3b`, `slice_scope: ["REQ-PPM-002"]`, and
`python3 scripts/check_g2_adjudication.py` → exit 0, 1 in scope, **0 blocking**. The row's
adjudication is CURRENT against its post-amendment cell. **Consequence: the acceptance cell must not be touched** — an annotation lapses
the hash (the PPM-006/PPM-010 class), and if an amendment turns out to be needed it is two commits
in the P20 order.

---

## Part 0 — A false claim in W19-S3a's own record, corrected here

The S3a remit (DS3a-5) and slice record both say adding `position.mapping_version_id` to
`position_content` would "mark every pre-S3b POSITION component DIVERGED in the CTRL-018 sweep".
**The conclusion is right and the reason is wrong.** The CTRL-018 reproduction sweep does not read
snapshot content hashes at all — it re-executes binders over pinned bytes and compares result rows;
its only `content_hash` is `report_generation`'s. The real surface is `verify_snapshot` and
`GET /snapshots/{id}/verify`.

The damage is measured rather than argued: **297 of 297 POSITION components currently re-serialize
to their stored hash, and adding the key with a NULL value breaks all 297, across 168 of the 511
snapshots.** So the decision stands, on the correct grounds.

Recorded here rather than quietly fixed, because a governed record that reaches the right answer
through a wrong mechanism is exactly what a later reader will cite.

---

## Part 1 — Scope line

S3b completes REQ-INT-001's two deferred halves and hosts REQ-PPM-002's census clause:

| Outcome | Clause it closes |
|---|---|
| The R-07 ratifier permission mint, never co-granted with the proposer path | REQ-INT-001 (6), the half that makes four-eyes real |
| Four-eyes as an APPEND-ONLY resolution row (ENT-078) | REQ-INT-001 (6) |
| `position.mapping_version_id` hard FK | REQ-INT-001 (2), the position half |
| The holdings-consuming census, discovered mechanically | REQ-PPM-002's census clause |
| **The propose and ratify HTTP verbs**, each behind its own minted code | REQ-INT-001 (6) — and DS3b-2's premise depends on them existing, which the first draft never stated as a build item |
| Rule 7: batch lineage + the loaded book with mapping-version provenance | — |

**REQ-INT-001 goes Delivered at this merge. REQ-PPM-002 does NOT close** — its Status keeps the
portfolio-scope ABAC conjunct deferred to P6+ and says "not closeable until then". The plan is
"In-Progress, census clause delivered", not a close.

---

## Part 2 — Outcomes

### 1. ENT-078 `ingestion_mapping_ratification` — four-eyes that cannot be edited into existence

**A ratification recorded by mutating a row can be edited after the fact, and ENT-077 is
status-mutable by design.** Worse, its content guard is an ORM `before_update` listener, which does
not hold on any non-ORM write path — so ratification evidence stored in ENT-077's own columns is
editable at the database by anything that does not go through the ORM. The approval is the one fact
here that must be unfalsifiable.

So the resolution is a **NEW ROW in a NEW table** referencing the mapping version — the
`entitlement_request` / `breach_action` shape, which the wave plan names explicitly and which
ENT-075's own docstring records as the fix for exactly this defect ("The first implementation …
recorded approval by MUTATING the request row").

- **IA TRUE append-only**: in `APPEND_ONLY_TABLES`, with the `irp_prevent_mutation` trigger AND the
  ORM guard (the 0072 belt-and-braces pattern; ENT-075 shipped without the ORM half and only the
  trigger caught its first mutation).
- **Per-tenant monotonic `seq`**, app-assigned under the tenant advisory lock. A state machine over
  an append-only log needs a DB-monotonic ordering key: a wall clock ties, and two ratifiers acting
  in the same millisecond is precisely what this table adjudicates. **ENT-077 has NO lock on its
  ratify path today** — no `with_for_update`, no advisory lock — so the lock lands WITH the
  lifecycle, not after it.
- **"Ratified by nobody" is unrepresentable**, the CHECK that keeps ENT-075 non-decorative.
- **Person-level SoD**: `ratified_by != proposed_by`, canonicalized. **Three copies of actor
  canonicalization already exist with three different non-UUID fallbacks** (`entitlement` lowers,
  `limit` passes through unchanged, `ingest_mapping` case-folds); this slice picks one deliberately
  and says which, rather than adding a fourth.

**The production gate is RE-POINTED, and the first draft of this outcome forgot to say so — which
would have made ENT-078 evidence nobody consults.** `ratified_mapping_for` queries
`IngestionMappingVersion.status == RATIFIED` directly, and `load_batch` calls it: that is the
interpreter's sole source of truth for *which mapping governs a load*. Minting an append-only
resolution table beside it and leaving the gate reading the mutable column would be the
declaration-without-consumption defect exactly — a governance record placed next to the real
control instead of in front of it. So `ratified_mapping_for` resolves through ENT-078, and a test
proves a mapping whose ENT-077 status says RATIFIED but which has no resolution row **does not
load**.

**And the uniqueness invariant needs an answer, because today it lives on the wrong column.**
"At most one RATIFIED mapping per `(tenant, data_source, source_type)`" is enforced by
`uq_ingestion_mapping_version_active`, a partial unique index keyed on ENT-077's mutable `status` —
the very column ENT-078 exists to stop trusting. Two resolution rows naming different mappings for
one source, written by anything that bypasses `ratify_mapping_version`, would leave the invariant
enforced nowhere. **DS3b-5 decides which surface owns it.**

ENT-077's `status` remains a read-side projection; `ratified_by_actor_id`/`ratified_at` become
**derived from the resolution row** rather than the authority for it.

**Migration `0076`, and this consumes ENT-078 — so S2's report-definition entity moves to ENT-079.**
The Wave-19 gate earmarked ENT-078 for S2 on the assumption S3b minted nothing; S3b comes first in
the real order, and the accounting must not carry a superseded earmark forward.

### 2. The R-07 mint: a ratifier code that cannot sit beside the proposer

Two codes, in `PERMISSIONS` (tenant-local acts, not platform):
`ingest.mapping.propose` and `ingest.mapping.ratify`.

**The precedent to copy is `breach.respond` / `breach.review`, NOT `role.assign` / `role.approve`.**
Those two assertions look alike and enforce opposite things: the entitlement pair is deliberately
CO-GRANTED on `tenant_admin` because its gate is person-level, and copying it would violate this
slice's requirement outright. The breach pair is the cross-line partition.

**The non-co-grant pin must exempt `platform_admin` explicitly, with the reason.** A code in
`PERMISSIONS` enters `ALL_CODES`, and `ROLE_TEMPLATES["platform_admin"] = list(ALL_CODES)`, so that
role holds both by construction and a test already asserts it does. An unexplained exemption reads
as an oversight; an explained one is the design.

P11's three obligations, each with its named home: the holder-set pin by **exact set equality in
both directions** (`test_entitlement_bootstrap.py`), the route census, and the
`entitlement_sod_model.md` row. Plus the P17 delivery obligation: the migration carries a literal
`DELIVERS` tuple, because appending to the constant is a mint for future deployments only — every
from-empty test passes over an undelivered mint, and `0002` still seeds from the live constants.

### 3. The position FK, and the trap that would have silently emptied it

`position.mapping_version_id`, nullable, hard FK, explicitly named (`fk_position_mapping_version`) —
naming the column `ingestion_mapping_version_id` instead would generate a 66-char name and
PostgreSQL truncates at 63 silently.

**The trap, found at recon and worth the whole outcome:** a column outside `POSITION_FIELDS` is
dropped to NULL on every supersede and every correction, because both binders build the new row from
`{**carried, **new_fields}`. `load_batch` issues BOTH verbs. So a naive column is populated on first
capture and **NULL on every subsequent load of the same holding** — a provenance FK that vanishes
exactly when the second file arrives. Prove it with a TWO-FILE load, never a one-file load.

**And the mirror is equally wrong:** adding it to `POSITION_FIELDS` makes it carry forward blindly,
so a hand-typed manual supersede of a file-loaded holding inherits a mapping version that never
produced it — DS3a-4's false-provenance class re-entering by the other door.

**Neither default is right, so it is set PER VERB and both directions are proven:** the interpreter
stamps the version that produced *this* row on create, supersede and correct; a manual binder call
stamps NULL. The Pydantic request models must NOT gain the field — `positions.py` splats
`**body.model_dump()` into the binder and `_check_field_kwargs` only rejects names outside
`POSITION_FIELDS`, so the HTTP route is closed today solely because the models lack it.

**It does NOT enter `position_content`** (Part 0), and a `test_position_pin_key_set_is_frozen` ships
with an exact key-set assertion — `var_result_content` has such a pin and `position_content` has
none, so the next slice to "complete" the serializer reddens 168 snapshots.

Committed P17 harness with both negative controls, mirroring `0075`'s.

### 4. REQ-PPM-002's census — and the reading it needs

**The first draft of this outcome claimed the row might be unsatisfiable as written. That was
wrong, and the correction narrows the slice considerably.**

The claim rested on a shipped fence forbidding the exposure service from naming
`reconstruct_subtree_holdings_as_of` and its siblings. The fence is real — and it AST-scans
`exposure/service.py`'s own source for those NAMES only. It says nothing about `build_snapshot`,
which is what `run_exposure` actually calls, in the same function and the same transaction, on its
**default build-in-request path**; and `build_snapshot` is itself the direct caller of
`reconstruct_subtree_holdings_as_of` and `attach_marks_as_of`. So on the majority path the literal
acceptance text is satisfied almost verbatim: the family's own module invokes the binder that
performs the reconstruction, producing the very snapshot the run then pins.

**The real gap is narrower and is the only thing to decide (DS3b-1):** `run_exposure`'s OTHER input
mode consumes a pre-built `snapshot_id`, built in an earlier, disconnected transaction, possibly by
a different actor — reachable as `POST /snapshots` followed by a separate run. Does a run that
consumes such a snapshot count as "resolving through the as-of reconstruction at the run's pinned
snapshot"?

**And the census needs a rule that does not contradict itself**, which the binder/consumer framing
did: on the build path the consumer *is* the binder-caller, so "a family module may only read pinned
components, never call the binder" would flag exposure's own compliant path. The rule the census
actually encodes: a family is compliant if the holdings reaching it were produced by the as-of
reconstruction — whether the family invoked the binder itself or received pinned components it
produced. What FAILS is a family that reads the `position` table directly for run inputs.

The census follows S3a's shape, not the aggregation census's: **cut the sanctioned route out of the
graph rather than keeping an exemption list** — its own docstring says an exemption list "is how a
census stops meaning anything" — and skip `__pycache__`, which the aggregation census does not.

Three legitimate direct position-table reads will surface and are not families consuming holdings
(`list_positions`' open-head filter, S3a's demo oracle, the binder itself). They are handled by the
graph cut, not by exemptions.

*Also fixed in passing: S3a's census says "These four sites were here before this slice" while its
`KNOWN_POSITION_WRITERS` holds two. A stale prose count inside the slice's own positive control.*

### 5. Rule 7 — and the read surface is not a rendering change

**Batch lineage has no HTTP read to build on.** `GET /lineage/edges/{edge_id}` is the only lineage
endpoint and it takes an id a caller has no way to obtain. S3b mints a by-target lineage read or the
screen is unbuildable. `/lineage` is already in `API_PREFIXES` and the nginx alternation — and has
never been fetched by the SPA, which is exactly the state `/ingest` was in before S3a.

The loaded-book read needs the FK from outcome 3 first: `HoldingRow` carries `position_source` and
no mapping field, and the S3a loader never populates `position_source` anyway. This read is
downstream of the migration, not parallel to it.

**The holdings package's import fence allows only `{db, portfolio, position, valuation, reference,
holdings}`** — adding an `ingest_mapping` import to `holdings/service.py` fails it. Either extend
that set deliberately with a reason, or put the provenance read elsewhere.

---

## Part 3 — Fences enumerated before drafting

1. **`EXPECTED_ROUTE_COUNT = 311`** moves consciously, and the comment block is a running ledger
   whose arithmetic has already been repaired once. Re-derive; do not increment.
2. **A minted code not yet routed** must join `UNROUTED_FORWARD_GATES` with a reason or the census
   fails; and the census scrapes every `str` in a guard closure, so `require_permission(code)` must
   remain the only closure on a route's dependency list.
3. **`DELIVERS` is read from the AST and must be string literals**; the floor is `>= 60` declared
   codes; the two catalogs must stay DISJOINT.
4. **`_DELIBERATELY_EMPTY` is `{}`** and has a stale-entry twin that forces deletion in the same
   commit — relevant only if a role is minted before its routes.
5. **A new audit code** needs a backticked mention in the taxonomy; ONBOARD-1b minted
   `ROLE.GRANT_REQUEST`/`ROLE.GRANT_APPROVE` and REUSED `ACTION_STATUS_CHANGE` rather than minting an
   action verb — "the action vocabulary is a controlled R-07 list".
6. **Partial indexes are spelled TWICE, identically** (`postgresql_where` + `sqlite_where`). Note
   `0051` gets this wrong in the migration while its ORM gets it right.
7. **`alembic check`** requires the FK name to match in migration and ORM exactly.
8. **`gen-api-check` is in `check-all`, NOT in `make check`** — a Python-only run passes over stale
   generated artifacts. `PositionOut` is inside `decimal-contract.ts`'s curated key set, so a new
   `number` field there is an instant tsc failure across the guards program; a string id is fine.
9. **CI's `alembic downgrade 0071`** runs over the fully seeded 28-stage book, so **`0077`'s**
   downgrade must survive real position rows — that is a property of the ALTER, not of `0076`, which
   CREATEs a table and whose downgrade just drops it. Same distinction the repo already draws
   between `0074` and `0075`: **`0076` gets NO populated-DB P17 harness**, because there are no
   pre-existing rows and claiming one would be paperwork rather than evidence. `0077` gets the real
   harness.
10. **Purge `__pycache__` before trusting any gate**, and re-derive the fe baseline: **39 files /
    274 tests** on `564a730` (S3a's commit body says 272; the extra two came from its own fold
    commit).

**Baselines to beat, measured on `564a730`:** `make check` 3,007 passed / 654 skipped · full-PG
3,661, zero skips · fe-check 39 files / 274 tests · anchors 150/150 · route pin 311 · `ALL_CODES` 73.

---

## Part 4 — Decisions

**DS3b-1 — does a run that CONSUMES a pre-built snapshot satisfy REQ-PPM-002?**
*This decision changed shape under verification, and the change is the point.* The draft claimed the
row might be unsatisfiable because a fence blocks the exposure service from naming the as-of
readers. It does not: the fence scans that module's own names, while `run_exposure`'s **default**
path calls `build_snapshot`, which IS the as-of reconstruction. On the majority path the text is
already satisfied literally.

What remains is one narrow question. `run_exposure` also accepts a pre-built `snapshot_id`, produced
in an earlier disconnected transaction, possibly by another actor. (a) That COUNTS — the pinned
components are the reconstruction's output and the run binds them, so the census asserts the
components' provenance rather than the caller's call graph. (b) It does NOT count, and the
consume-existing path must additionally prove its snapshot was built by the as-of reader.
**Recommend (a).** The row's own words are "at the run's pinned snapshot", and a snapshot's
provenance is a property of the snapshot. (b) would make a legitimate two-step workflow —
`POST /snapshots` then run — non-compliant, which nothing in the row asks for.

**DS3b-2 — how a ratifier sees what they are ratifying.**
Every `/ingest` route is gated `data.upload`, the MAKER code, so a ratifier-only holder gets 403 on
the mapping reads. (a) Mint a third code `ingest.mapping.view`, re-gate the three S3a reads, grant
it to both sides. (b) Grant the ratifier `data.upload` — violates "never co-granted" outright.
(c) Leave it. **Recommend (a).** A checker who cannot read the artifact is not a checker, and (c)
stops being true the moment this slice ships the HTTP ratify verb — which it now does, explicitly.

**DS3b-3 — the position FK's carry semantics.** Set PER VERB (the interpreter stamps the version
that produced *this* row; a manual binder call stamps NULL), because both defaults are wrong in
opposite directions: outside `POSITION_FIELDS` the column is dropped to NULL on every supersede and
correction, and inside it the column carries forward onto rows no mapping produced.
*Proof corrected under verification:* a two-file load proves only the interpreter direction — every
row it writes goes through `load_batch`. The NULL direction needs a **separate manual binder call**
against a file-loaded holding. Flagged rather than asked; it is the only choice that is not a known
defect.

**DS3b-4 — ENT-078 is consumed here, and the two migrations land in TWO COMMITS.**
S2's report-definition entity moves to ENT-079. `0076` (the ratification table) and `0077` (the
position FK) are separate commits: the S3a/S3b split exists *because* no commit in this repo's
history has ever added more than one migration — re-verified at this gate, 75 add-commits, only the
genesis scaffold ever adding two — and putting both in one commit would reproduce inside S3b the
exact defect the split was made to prevent. The first draft flagged the count and never said how
they land, which the verification called out.

**DS3b-5 — which surface owns "at most one RATIFIED mapping per source"?**
Today it is a partial unique index on ENT-077's mutable `status` — the column ENT-078 exists to
stop trusting. (a) Denormalize `data_source_id`/`source_type` onto the resolution row and give
ENT-078 its own partial unique index, making the append-only table the enforcement surface.
(b) Keep ENT-077's index as the sole enforcement surface and state plainly that the invariant is
enforced on a mutable column, with the ORM listener as its only guard.
**Recommend (a).** (b) leaves the slice's own headline claim — that approval facts must be
unfalsifiable — resting on the surface it just finished arguing is falsifiable.

**DS3b-6 — the withdraw verb: ship or strike.**
`STATUS_WITHDRAWN` is declared in ENT-077 with no path producing it — the inert-state class the
ENT-075 review struck when it deleted `REJECTED`. (a) Ship `withdraw_mapping_version` beside ratify,
with its own route, permission gating, audit action and route-count delta. (b) Strike the constant
until a verb needs it. **Recommend (a).** A proposal that cannot be withdrawn sits on the queue
forever, and the lifecycle it belongs to is being built in this slice anyway. *The first draft
buried this in Part 5 as an unlisted fifth decision that no build item implemented — so it would
have silently dropped.*

## Part 5 — Findings this slice inherits, each with its disposition

Recon surfaced five defects in code S3b touches but does not own. Each is named so none is silently
absorbed:

| Finding | Disposition |
|---|---|
| **ENT-075's "fails closed on a fourth" is UNTESTED** — one raise site, no test fires it, no off-vocabulary INSERT is attempted. The wave plan's reason for not widening ENT-075 rests on a refusal never fired (the LQ-1 class). | **FIX IN-SLICE.** If S3b cites that rail as its reason, S3b fires it: one negative test at the service, one at the DB. |
| **Grant-id derivation divergence** — `tenant_role_permission_id` is called with a permission UUID by onboarding and `0068`, and with the raw CODE by `0069`. Same (tenant, role, code) yields two different grant ids; a tenant holding both would hit `uq_role_permission_role_id`. Untested across derivations. | **DECLARE AND AVOID.** S3b picks one convention explicitly for any clone backfill it writes and says which. Repairing `0069` is out of scope — named as a Wave-20 candidate. |
| **§5C row 5 cites `tenants_missing_code`, a field `SyncReport` does not have.** The only checklist row about delivering a code to existing tenants' clones has no tell. | **AMEND THE ROW HONESTLY** in this slice, or build the field. Recommend amending: a checklist that names a nonexistent mechanism is worse than one that names none. |
| **`platform_catalog.py` claims `sync_catalog` "gains a platform arm"; it did not.** | Docs-only correction, in-slice. |
| **`STATUS_WITHDRAWN` is inert** in ENT-077 — declared one slice ago with no path producing it, the shape the ENT-075 review struck when it deleted `REJECTED`. | **Promoted to DS3b-6**, because a disposition buried in this table is one no build item implements. |

---

## Part 6 — Proofs

- `make check`, full-PG, `fe-check`, `gen-api-check`, `g2-check` — all exit 0 with counts quoted.
- The committed `0077` P17 harness executed over populated `position` rows, with both negative
  controls.
- **Both directions of the FK carry semantics**: the interpreter direction by a TWO-FILE load, and
  the NULL direction by a separate manual binder call against a file-loaded holding. A two-file load
  alone exercises the interpreter twice and cannot reach the manual path at all.
- **A mapping whose ENT-077 status reads RATIFIED but which has no resolution row does NOT load** —
  the proof that ENT-078 is in front of the gate rather than beside it.
- Mutants for: the SoD comparison, the "ratified by nobody" CHECK, the census's sanctioned-route
  cut, the per-verb stamp, and the non-co-grant pin.
- **The seq lock is proven in a `_pg` suite with REAL CONCURRENT THREADS**, mirroring
  `test_entitlement_admin_pg.py`. It cannot be a unit-tier mutant: `_lock_tenant` is a literal no-op
  on any non-PostgreSQL dialect, and SQLite serializes writes at the file level anyway — so removing
  the lock is invisible there and the mutant would be killed by nothing.
- CI green on all nine checks at the PR head, verified per conclusion.
- **P15: at least one review pass outside the authoring model**, with the engine named for what it is.
- The seven-ledger sweep, verify-on-main AFTER the merge.
