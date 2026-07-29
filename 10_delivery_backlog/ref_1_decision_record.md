# REF-1 Decision Record — reference dimensions + the vendor-classification capture rail (Wave-14 slice 0)

| Field | Value |
|---|---|
| Status | RATIFIED 2026-07-29 — OQ-REF-1-1…30 ALL approved as recommended ("proceed" on the briefed gate); implementation follows on this branch |
| Slice | Wave-14 slice 0 (`wave_14_planning.md`, roadmap Part 2.18) |
| Entities | ENT-066 `classification_scheme`, ENT-067 `classification_node`, ENT-068 `classification_assignment` |
| Migration | `0056` |
| Sizing | L (split trigger (b) FIRED at this gate — see OQ-REF-1-22) |

> **Method + honesty note.** 6-lane recon fan-out in fresh contexts, each instructed to treat
> `wave_14_planning.md` as an UNVERIFIED claim set authored by the same agent now planning the
> slice (P3): it returned 132 facts, **52 corrections to the wave plan**, 32 costed forks. The
> draft was authored single-threaded, then attacked by a 4-lane refute-by-default verifier pass
> in fresh contexts: **61 findings — 3 BLOCKING, 12 HIGH, 22 MED, 24 LOW — ALL folded into this
> revision.** The three BLOCKINGs and the most consequential HIGHs were hand re-verified by
> execution before folding (Part 0). **One folded finding is a correction of my own
> over-correction:** the draft claimed the wave plan's DQ fact was "materially wrong"; it is not
> (Part 0 fact 3). The full ledger is Part 7.

## Part 0 — Hand-verified facts (executed, not cited)

1. **Migration 0008's `HYBRID_TABLES` is DDL, not a mirror.** The tuple at `:47` drives the policy
   loop at `:150` and the drop loop at `:163`. Adding REF-1's tables to it makes `alembic upgrade
   head` from zero attempt `CREATE POLICY` on tables 0008 never creates. **The ratified wave plan,
   roadmap Part 2.18 and `current_state.md` all call it a "mirror" — Part 6 amends them.**
2. **The closed-set encoding is 38 sites across 36 files** (verifier-counted, corrected from the
   draft's ~34/~33): 31 PG modules with a private `_P1B1_HYBRID`/`_HYBRID` 5-tuple; **three**
   SQLite modules carrying four literals (`test_reference.py:343`, `test_reference_entities.py:457`
   and `:615` — the importlib parity test — and `test_reference_instruments.py:493`); a
   differently-ordered DELETE tuple at `test_reference_pg.py:77`; plus `reference/models.py:60`
   and `0008:47`.
3. **My draft's DQ correction was itself an over-correction — folded.** `run_presence_gate` ships,
   but **executed grep confirms its only production callers are `snapshot/service.py:242`, `:516`
   and `calc/scaffold.py:122`** — snapshot-build and governed-run paths, **none in `ingestion/` or
   any capture binder**. The wave plan's fact 7, read as written (about vendor-file capture), is
   therefore CORRECT: no completeness rule type exists and no capture path invokes a presence gate.
   **The wave plan is NOT amended on this point.** What survives is a narrower true statement,
   recorded at OQ-REF-1-19.
4. **This record's own draft was invisible to the closure-stamp gate.** Executed:
   `check_docs._status_lines(<the draft>)` returned `[]`, because the status sat inside a
   blockquote and neither `_STATUS_ROW` nor `_STATUS_PROSE` anchors after stripping. That is
   **recurrence eight** of the class the Wave-13 close re-folded for the seventh time, and the
   `_MIN_RECORDS_WITH_STATUS = 50` floor over a 62-record population would never have tripped on
   one invisible record. Fixed above (a table row — now matched); **REF-1 ships the missing floor**
   (OQ-REF-1-12).
5. **`update_instrument` mutates `issuer_id` IN PLACE** with only a `record_version` bump and no
   version row (`instrument.py:139-142`) — the prior value is unreconstructable from the table.
   This refutes the draft's grain argument (OQ-REF-1-5) and creates a real CON-1 obligation.
6. **The `auditor_3l` exclusion from proprietary reference reads is pinned in both directions**
   across `legal_entity`, `identifier` and `corporate_action`
   (`test_entitlement_bootstrap.py:138`, `:183`, `:206`). SoD pins are per-code, so a NEW code
   granted to `auditor_3l` is silent — which is exactly what the draft's single-`.view` shape
   would have done (OQ-REF-1-17).
7. **The snapshot vocabulary reserves `REFERENCE` by name** (`snapshot/models.py:148`).

## Part 1 — Data model

- **OQ-REF-1-1 — sector and industry are ONE hierarchy. Recommend A.** Every candidate scheme is
  built that way (ISIC/NACE Section→Division→Group→Class; NAICS sector→…→national-industry; GICS
  and ICB likewise). Two independent dimensions store a derivable parent-child edge twice and
  admit states the source cannot express. *(Reverses the wave plan's "three parallel dimensions" —
  Part 6.)*
  **Consequence the draft missed, now in scope:** vendor files deliver a leaf (industry) code; a
  concentration bucket "per sector" is then an ANCESTOR of that node. **REF-1 therefore ships a
  bounded, cycle-safe ancestor resolver** over `classification_node` (the `portfolio.py` traversal
  precedent — NOT the `legal_entity` one, whose rollup is deferred), because the very next slice
  consumes it. Capture-time policy for a vendor row whose asserted sector contradicts its
  industry's ancestor: **refuse fail-closed**, naming both codes.
- **OQ-REF-1-2 — vocabulary shape. Recommend B: scheme head + hierarchical node table**, with
  three corrections to the draft: the parent self-FK is a **plain FK, not intra-tenant**
  (the `rating_grade`/`calendar_holiday` shape, `UNIQUE(tenant_id, scheme_id, code)`) so a tenant
  can shadow ONE node against a SYSTEM parent rather than duplicating a whole subtree; a
  **cycle guard, same-scheme-parent guard and level-monotonicity guard** are specified and tested;
  and the draft's claim that `rating_scale` "has no parent link and no version column" is
  withdrawn as overstated.
- **OQ-REF-1-3 — assignments are a separate FR bitemporal table. Recommend B.** The decisive
  argument is drift, test-proven in both directions: an EV in-place amend flips `verify_snapshot`
  to `ok=False` (`test_snapshot.py:416-436`); an FR supersede leaves the pin byte-stable
  (`:370-413`), and that flows to the user-visible unfakeable `snapshotVerified` badge. Under an
  EV attribute column, an ordinary reclassification permanently reddens the governance walk on
  every historical concentration run, with **no remedy** — snapshots are IA append-only.
  Independently, AD-005 §2A already classifies rating ASSIGNMENTS as FR (`:47`, `:85-86`,
  OD-P1B-J): REF-1 realizes the taxonomy=EV / assignments=FR split ENT-007 designed.
  **Applying my own criterion consistently to the EV half I kept** (the verifier's catch): the
  vocabulary tables stay EV, so a node correction would drift a CON-1 pin. **Fence:** semantic
  node fields (`code`, `parent_node_id`, `level`) are correctable ONLY by a new scheme revision;
  `name`/`description` are in-place correctable and **excluded from the pinned content hash**. The
  drift criterion is thus satisfied on both halves, not just the one it was convenient for.
- **OQ-REF-1-4 — one generic assignment table with `dimension_kind`. Recommend A**, with the
  draft's sparse-column defect fixed: **`basis` is NOT NULL with a `NOT_APPLICABLE` sentinel** and
  a binder-enforced `dimension_kind` ↔ `basis` invariant with a fail-closed refusal test — the
  `curve_type` ↔ `reference_key` / `REFERENCE_KEY_NONE` precedent (OD-P2-5-K) that the draft cited
  for genericity while contradicting on shape. Every comparability-governing `*_basis` column in
  the codebase is NOT NULL `String(20)`.
- **OQ-REF-1-5 — assignment grain: instrument, via a polymorphic `(entity_type, entity_id)` target
  with REF-1 writing `entity_type='instrument'` only. Recommend B — but the draft's decisive reason
  is STRUCK.** The draft argued issuer grain "forces CON-1 to mint a second, EV-flavored pin". That
  differential is **zero**: REQ-CRD-003's acceptance is literally "per issuer/sector",
  `exposure_aggregate` has no issuer column, so **CON-1 must traverse `instrument.issuer_id` under
  EITHER grain** — and that edge is nullable and mutated in place with no version row (Part 0 fact
  5). The surviving true differential is narrower: instrument grain removes the unpinned hop from
  the **sector and country axes only**.
  **Named CON-1 carry, recorded here so its gate inherits it rather than discovering it:** CON-1
  must either mint an instrument→issuer component kind (an EV-flavored pin, drift-prone) or refuse
  the per-issuer half of REQ-CRD-003. **`instrument` being unpinned is an AD-014 exposure for
  CON-1, not a safety property** — the draft's OQ-REF-1-27 framed it backwards.
  Recorded cost: a reclassification supersedes N instrument rows, not one. Issuer grain stays
  admissible later by value, no migration.
- **OQ-REF-1-6 — country-of-risk is CAPTURED, not derived. Recommend A**, with a NOT NULL `basis`
  in a closed app-side vocabulary (IMMEDIATE_ISSUER_RESIDENCE default — the CRR RTS 1152/2014 /
  BIS-immediate / ECB-SHS convention — vs ULTIMATE_RISK / GUARANTOR_RESIDENCE /
  INDEX_PROVIDER_NATIONALITY). Deriving it is **not computable on today's schema**: every
  authoritative rule needs revenue geography, asset location, listing venue or guarantee
  structures, none of which the platform holds. *(The wave plan omitted this fork entirely —
  Part 6.)*
- **OQ-REF-1-7 — country representation: NOT a fourth table. Recommend: countries are an
  ISO-3166-1 `classification_scheme` whose nodes are countries** (`code` = alpha-2, level 1).
  This resolves the draft's unaccounted fourth table (three verifier lanes independently flagged
  it). **Alpha-3 and M49 numeric are NOT stored in v1** — the `currency` precedent carries
  `numeric_code` because ISO-4217 numeric has payment consumers; we have none. Recorded deferral,
  trigger: *the first consumer requiring alpha-3 (e.g. a regulatory report)*. Licence-clean source
  is the **UNSD M49 list** (ISO's machine-readable collection is a paid subscription).
  **Therefore the closed hybrid set N = 7** (the existing five + `classification_scheme` +
  `classification_node`); the assignment table is symmetric proprietary and does NOT join it.
- **OQ-REF-1-8 — the logical key (NEW — the draft omitted it; the single most load-bearing FR
  decision).** `classification_assignment` current-head partial-unique on
  **`(tenant_id, entity_type, entity_id, scheme_id, dimension_kind) WHERE valid_to IS NULL AND
  system_to IS NULL`**, every promoted column DB-level NOT NULL. `scheme_id` participates
  deliberately: one instrument may legitimately carry an ISIC sector AND a NACE sector at once.
  **Consequence, stated rather than discovered:** a scheme REVISION therefore leaves two open
  assignments in one family, so **mixed-version aggregation is a legal state that reads and CON-1
  must FAIL CLOSED on** (OQ-REF-1-10).

## Part 2 — Taxonomy governance

- **OQ-REF-1-9 — the canonical scheme: ISIC Rev. 5. Recommend A.** Global by construction (NAICS
  is North-America-only, NACE EU-only — neither can honestly describe a multi-tenant book), the
  correspondence hub (NACE is the EU implementation of ISIC), and unambiguously licence-free.
  NACE/NAICS/SIC admitted additionally by value.
  **⚠️ OQ-W14P-3's "ICB/GICS-SHAPED structure" must be STRUCK** — S&P DJI's licence covers the
  structure and forbids derivative works; a deliberately GICS-shaped hierarchy is the
  derivative-work case, not a safe harbour. Part 6.
- **OQ-REF-1-10 — a revision is a NEW scheme row** (`UNIQUE(tenant_id, scheme_family,
  version_label)`), the `model_version` idiom. Revisions reuse code strings with changed meaning
  and changed cardinality (NACE Rev. 2 → 2.1: 21/88 → 22/87/287/651; NAICS 2022 cut 1,057 → 1,012;
  NAICS 2027 publishes CY2026), and inter-version correspondence is many-to-many with partial links.
  **The half the draft omitted, now stated:** a revision requires **per-assignment re-capture**, and
  under instrument grain that is N-per-instrument through per-row binders only. Until re-captured,
  the book is split across two code spaces — **a permitted state, with mixed-version aggregation
  refused fail-closed** rather than silently incoherent. A bulk re-classification path is a
  recorded deferral, trigger: *the first real scheme revision*.
  **Consequence: "a `scheme` discriminator" as ratified is insufficient — it must be
  scheme-family + version.** Part 6.
- **OQ-REF-1-11 — override grain: NODE-grain. Recommend A** (the draft left OQ-9 and OQ-14
  mutually inconsistent and never named the fork). A tenant override is a **tenant node row under
  the SYSTEM `scheme_id`**, so `(scheme_id, code)` dedupe is correct and existing assignments'
  `scheme_id` FK stays stable. Scheme-grain override (a tenant scheme row) would give tenant nodes
  a different `scheme_id`, un-dedupable and orphaning assignment FKs. Pinned with a test that
  creates an override and asserts both the dedupe and the assignment's continued resolution.

## Part 3 — Tenancy (executing the ratified AD-013-R2 direction)

- **OQ-REF-1-12 — extension mechanics. Recommend B; A is incorrect** (Part 0 fact 1): 0008 stays
  **byte-untouched**; REF-1's own migration creates its tables and their asymmetric policy;
  `reference/models.py::HYBRID_TABLES` becomes the single DECLARATION (N = 7); the parity test
  asserts the ORM set equals the union of each migration's own frozen tuple. **The 38 sites**
  (Part 0 fact 2) collapse to imports — including the three SQLite modules and, treated separately
  because it is a DELETE-ordering tuple rather than a census, `test_reference_pg.py:77`. *(Honest
  correction: this is not "behaviour-preserving" as the draft said — it converts 31 independent
  expectations into derived ones. That is the intent, and the two new floors below are what keep
  the guard non-vacuous.)*
  **Three floors ship** (the draft had two, and one of them was itself vacuous):
  (i) for every policy on a `tenant_id`-bearing table, the **EFFECTIVE write check —
  `COALESCE(with_check, qual)` — must not contain the SYSTEM literal.** The draft's "no SYSTEM in
  `with_check`" is blind to a `USING`-only policy, where PostgreSQL reuses `USING` as the write
  check and `with_check` reads NULL — **six USING-only policies already exist on `main`**, so it is
  the natural thing to copy and the exact cross-tenant write breach 0008 warns about. Negative
  control required.
  (ii) a FORCE-RLS floor over every `tenant_id`-bearing table in the metadata.
  (iii) **a closure-stamp floor over `records_without_status`** — Part 0 fact 4's recurrence eight.
- **OQ-REF-1-13 — SYSTEM-row provenance: accept and RECORD the bounded consequence.**
  `data_source`, `lineage_edge` and `data_quality_result` are symmetric, so a SYSTEM-seeded row is
  readable by a tenant while its lineage and DQ results are not; global-reference provenance is
  verifiable on the SYSTEM chain only. Making those rails hybrid is far larger than the wave
  ratified and would put the SYSTEM literal into a rail every governed number depends on.
- **OQ-REF-1-14 — resolution path: BOTH** a generalized `dedupe_tenant_wins` (key function
  defaulting to `lambda r: r.code`, every caller preserved) keyed `(scheme_id, code)`, AND an
  explicit `(own OR SYSTEM)` by-code resolver on the `resolve_currency` shape — **the resolver is
  the only one of the two correct on the SQLite unit tier, where there is no RLS at all.**
- **OQ-REF-1-15 — a new idempotent, context-guarded seeder.** `seed_system_reference` is
  non-idempotent by its own docstring, has no system-context guard (on SQLite it writes SYSTEM rows
  under any context), and is called only from tests.

## Part 4 — Rail, permissions, scope

- **OQ-REF-1-16 — capture template: `marketdata/proxy_mapping.py`.** Corrected description: it
  carries a captured **numeric** attribute (a signed weight), so the analogy is the *protocol*
  (FR bitemporal, cross-tenant FK re-resolution on both targets, MANUAL-style provenance, per-op
  audit grain), not the value type. **The DQ leg cannot come from `reference/`** — that package
  runs no `run_quality_check` at all. **Host package:** a new `classification/` package (the rail
  cannot live in `reference/`, which is allowlist-fenced, nor in `marketdata/`), with its own
  import-direction test.
- **OQ-REF-1-17 — R-07 mint: THREE codes, with holder sets** (the draft named two codes and no
  holders — a BLOCKING SoD defect, Part 0 fact 6):
  - `reference.classification.view` — the hybrid SYSTEM-global vocabulary. Holders follow the
    `reference.currency.view` / `rating_scale.view` / `calendar.view` precedent, **including
    `auditor_3l`**.
  - `reference.classification_assignment.view` — the PROPRIETARY assignment reads. Holders follow
    the `reference.legal_entity.view` / `identifier.view` / `corporate_action.view` precedent,
    **EXCLUDING `auditor_3l`**, with the exclusion pinned in both directions.
  - `reference.classification.edit` — the steward maker verb.
  A single `.view` code over both tenancy classes (the draft's shape) would have handed the 3L
  auditor a proprietary-identity read for the first time, and **no shipped test would have caught
  it** because SoD pins are per-code. Each code ships a `_holders(code) == {...}` pin.
- **OQ-REF-1-18 — audit codes: reuse `REFERENCE.CREATE/.UPDATE/.CORRECTION`** with
  `entity_type='classification_assignment'` — zero mint. **P1 ledger (2) obligations, named:** the
  audit-event taxonomy row is amended with the per-op event grain for the FR assignment lifecycle,
  the DC-2 payload key set, the SYSTEM-chain vs per-tenant-chain choice for the seeded taxonomy,
  and the decision that `classification_node` folds into its parent scheme's event (the
  `calendar_holiday` precedent) rather than emitting its own.
- **OQ-REF-1-19 — DQ completeness rule type: OUT, with the honest statement.** The draft's
  justification is withdrawn (Part 0 fact 3). What is true: no completeness RULE TYPE exists, and
  the shipped presence GATE is invoked on no capture path — so REF-1's rail computes its own
  expected-set diff and calls `run_presence_gate` explicitly, becoming the **first capture-path
  caller**. Minting `RULE_TYPE_COMPLETENESS` (so the persisted rule can say *what* was expected)
  is deferred, trigger: *the first vendor dataset whose acceptance is expressed as an expected key
  set in the rule itself*.
- **OQ-REF-1-20 — vocabulary resolution (NEW — the draft's rail had none).** The capture verb
  resolves `scheme_id` through the own-OR-SYSTEM resolver **fail-closed**, and resolves
  `(scheme_id, node_code)` against `classification_node` **fail-closed before insert**, with a
  named exception and a P5 negative control. Without this a typo becomes its own concentration
  bucket in a governed number one slice later. Recorded: the code-existence check is an **app-side
  refusal, not a DQ rule** (PG referential checks bypass RLS, so an FK alone would let a tenant
  bind a SYSTEM-invisible node).
- **OQ-REF-1-21 — onboarding rail: per-row governed binders only.** The staged→canonical mapping
  is REF-1b if ever: no existing package may host a mapper (both `reference/` and `ingestion/` are
  fenced, test-enforced), and `stage_upload`'s DQ gate is fail-closed on an empty rule set, making
  per-tenant rule provisioning in-scope for that rail.
- **OQ-REF-1-22 — the rf diligence control: FIRE SPLIT TRIGGER (b) — move it out of REF-1.**
  Three findings converge. (a) The draft's discharge home is **forbidden**: editing a shipped
  `SHARPE_ASSUMPTIONS` tuple is the silent un-audited divergence the platform already refused once
  in code (`perf/bootstrap.py:1004-1008`); doing it properly needs a new `version_label` — the same
  registered-assumption machinery **CAL-1 is already building** for RM-1/SR-1. (b) The draft
  narrowed a ratified deliverable (the wave ratified "checklist artifact + control-matrix row";
  the draft delivered prose in three documentary homes) without recording the reversal. (c) A CTRL
  mint is an **R-10 act with H-05 as approver — not R-07**, and no slice has minted one since P0.5.
  **Recommend: the control moves to CAL-1**, where the assumption-versioning machinery and the
  approver routing already exist, delivered as the ratified pair (checklist artifact + CTRL row).
  This is the wave plan's own split trigger (b) firing at the gate, as designed. **Alternative:
  keep it in REF-1 and accept the L+ sizing.**
- **OQ-REF-1-23 — `issuer.sector`: DEPRECATE IN PLACE.** Removal is a breaking response-schema
  change **no gate here can detect** (the drift gate is `git diff --exit-code` over regenerated
  artifacts; there is no API version and no consumer register). Two further facts: the
  `_UPDATABLE` entry has **zero production callers** and there is no PATCH route, so "backfill"
  was never available; and the REFERENCE.CREATE `after_value` key set including `sector` is a
  **pinned audit-payload contract asserted in a test AND written into the ratified P1B-2 plan**.
  **Recorded reversal:** `sector` was deliberately ratified open-vocab under MG-01. *(Honest
  correction to the draft: "no schema change" is right, but freezing writes DOES change `IssuerIn`
  and therefore the OpenAPI artifact — so the regeneration obligation below applies.)*
- **OQ-REF-1-24 — read surface: backend-only.** Rule 7's captured-input clause requires
  entity-filtered list reads from birth and no more; **the FE obligation the draft and the wave
  plan attributed to rule 7 is not in its text**, and the FE has zero reference screens, so any FE
  work would be new surface under the standing no-FE-expansion rule.
  **P5, corrected — the pins fire IN-SLICE, not "later":** the reads ship an `as_of` filter over an
  FR bitemporal table plus GUID `entity_id` filters. **That is precisely the column class that
  ended the eight-wave runtime-clean streak**, and the unit tier is structurally blind to it. **PG-tier
  pins for every assignment-read filter ship from birth, with a negative control that fails if the
  bind is stringified.**
- **OQ-REF-1-25 — snapshot component kind: REF-1 records READINESS; CON-1 mints at its first
  consumer** (the FACTOR_RETURN and BENCHMARK precedents, recorded twice in the vocabulary's own
  comments). Minting here would ship a serializer and verify branch testable only vacuously — the
  P5 failure mode. **Corrected from the draft:** REF-1 does **not** claim the reserved `REFERENCE`
  token, which is broad and would be burned on one family; it names `CLASSIFICATION` and records
  what CON-1 pins — the **assignment rows (FR, drift-free)** plus the **node set content hash
  excluding `name`/`description`** (OQ-REF-1-3's fence).

## Part 5 — Demo, requirements, implementation shape

- **OQ-REF-1-26 — ONE stage** (`ref1_stage18.py`, suite `test_demo_stage9zzzzzzzzz_ref1_pg.py`, one
  `ci.yml` step). Every slice in the platform's history shipped exactly one. *(The wave plan said
  "stages" and folded LQ-1's tiers into the clause — Part 6.)*
- **OQ-REF-1-27 — the count pin: REF-1's suite collates LAST at UNCHANGED 25/40/133**, plus an
  isolated own-contribution assertion. A capture-only stage mints no model code, files no
  validation, creates no run (the CC-1 stage-8 precedent). Leaving the pin at SR-1 **is literally
  the arrangement that produced the SCH-2 109-vs-110 defect**. The relay rule is **not** in the
  operating instructions — REF-1 cites `sr_1_decision_record.md:24` explicitly.
- **OQ-REF-1-28 — backfill `issuer_id` onto existing demo instruments.** All **seven** demo
  `create_instrument` call sites omit it (corrected from the draft's eight; `synthetic/builder.py`
  also omits it but the demo does not import it). Without the backfill CON-1's demo computes
  concentration over an unclassified book — the OPS-1 failure one slice early.
- **OQ-REF-1-29 — demo read access from REF-1's own stage** (the OPS-1 precedent), leaving
  `campaign.py` untouched — **and REF-1 relays the role census**, because the OPS-H1 census
  asserting `auditor_3l` carries exactly two additions collates BEFORE REF-1's stage and would pass
  while becoming false. **Mandatory teardown:** the stage's `role_permission` rows need a narrowed
  teardown or CI's terminal `alembic downgrade base` fails the 0002 downgrade.
- **OQ-REF-1-30 — REQ mints.** A new classification REQ under CAP-2 reusing REQ-SMR-005's five
  acceptance clauses verbatim; **plus the spread-risk REQ**, which the ratified roadmap changelog
  assigns to REF-1 while the plan assigns it nowhere (a three-way discrepancy — the roadmap also
  contradicts itself). Both land in **the backbone AND both RTM halves** (P1 ledger 5).

**Implementation shape.** Migration `0056`: `classification_scheme` (EV, hybrid) →
`classification_node` (EV, hybrid, plain parent self-FK, cycle/level guards) →
`classification_assignment` (FR bitemporal, symmetric proprietary, polymorphic target, NOT NULL
`basis` with sentinel, the OQ-REF-1-8 current-head partial-unique). New `classification/` package
carrying capture/supersede/correct/reconstruct + the fail-closed resolvers + the ancestor resolver.
Reads gated on the two `.view` codes per their tenancy class. Countries as an ISO-3166-1 scheme.

**Gates.** `make check`; fresh-schema full-PG; `alembic check`; **a P4 executed dry run of `0056` up
AND down in a throwaway tree, with the downgrade proven destructive for real** (the SCH-2 lesson: a
smoke deleting zero rows tests nothing) **plus a dedicated CI downgrade-body step**; the new CI PG
step (`test_ci_pg_coverage`'s exempt list is EMPTY); **`make gen-api` regeneration + FE contract
check** (new endpoints AND the `IssuerIn` change — the FE-2 exhaustive guard); **closure stamp
recognized by `check_docs._status_lines`** (verified by execution, Part 0 fact 4); test-data
realism on the fixtures (plausible sector/country mixes; extremes only in labelled boundary tests).

## Part 6 — Amendments the recon + verifier force on the RATIFIED wave plan

Recorded at the gate per the SCH-2 rule; none re-opens the wave's ratified direction. On
ratification, `wave_14_planning.md`, roadmap Part 2.18 and `current_state.md` are amended in place.

1. **"migration-0008/ORM mirror updates" is wrong and would break a fresh database** — 0008's
   tuple is DDL (Part 0 fact 1).
2. **The closed-set surface is 38 sites across 36 files**, not three (Part 0 fact 2).
3. **Sector and industry are not parallel dimensions** — one hierarchy, and an ancestor resolver
   is therefore in REF-1's scope (OQ-REF-1-1).
4. **"ICB/GICS-SHAPED structure" must be struck** — the licence covers the structure (OQ-REF-1-9).
5. **"a `scheme` discriminator" is insufficient** — scheme-family + version (OQ-REF-1-10).
6. **The country-of-risk captured-vs-derived fork was omitted** (OQ-REF-1-6).
7. **The EV-vs-FR discriminator is drift-on-verify, not the §2A promotion test** (OQ-REF-1-3).
8. **Rule 7 contains no FE clause** (OQ-REF-1-24).
9. **A CTRL mint is R-10/H-05, not R-07** (OQ-REF-1-22). *(Narrower than the draft's phrasing: the
   wave plan never names R-07 here — it simply leaves the routing unstated.)*
10. **One demo stage, not "stages"; "tiers" is LQ-1 scope** (OQ-REF-1-26).
11. **The spread-REQ mint discrepancy is three-way** — the roadmap contradicts itself
    (OQ-REF-1-30).
12. **NOT amended:** the DQ fact 7. My draft's "materially wrong" was itself wrong (Part 0 fact 3).

## Part 7 — Cited external research (rule 6a) and the verifier ledger

**Research, sources dated 2026-07-29.** ISIC Rev. 5 (UN Statistical Commission, 54th session
2023; 22/87/258/463; free UNSD publication) chosen over NACE Rev. 2.1 (EU-scoped; 22/87/287/651)
and NAICS 2022 (US-scoped; 1,012 six-digit codes, 2027 revision publishing CY2026); SIC recorded as
legacy. Revision instability and many-to-many partial correspondence are documented in the
Eurostat NACE Rev.2→2.1 correspondence tables and XKOS partial-link definitions — the evidence for
OQ-REF-1-10. Country-of-risk conventions surveyed: CRR RTS 1152/2014 and the BIS
immediate-borrower vs ultimate-risk bases, ECB SHS, against index-provider nationality rules
(MSCI GIMI: incorporation + primary listing; FTSE Russell: incorporation / most-liquid exchange /
HQ cross-referenced with asset and revenue geography) — none computable on today's schema, which
is the evidence for OQ-REF-1-6's captured-with-basis recommendation. ISO 3166-1 alpha-2 as the code
form; UNSD M49 as the licence-clean source (ISO's machine-readable collection is a paid annual
subscription). GICS licensing per the S&P DJI GICS Methodology (April 2026) — the evidence for
striking the wave plan's GICS-shaped option.

**Verifier ledger — 61 findings, all folded.**
- **BLOCKING (3):** the single-`.view` SoD leak handing `auditor_3l` a proprietary read, caught by
  nothing because SoD pins are per-code (→ three codes with holder sets, OQ-REF-1-17); the grain
  argument's decisive reason refuted by the ratified CON-1 scope and self-refuted by my own demo
  OQ (→ struck and re-argued, with the CON-1 carry named, OQ-REF-1-5); this record's own status
  line invisible to the closure-stamp gate, recurrence eight (→ fixed and a floor added,
  OQ-REF-1-12).
- **HIGH (12):** my over-correction of the wave plan's DQ fact; the unaccounted `country` table
  (three lanes); the missing logical key; nullable `basis` contradicting the genericity precedent
  it cited; the ancestor walk homed nowhere while CON-1 needs it; the revision's effect on live
  assignments unstated; the intra-tenant parent FK incompatible with node override; the override
  grain contradiction between two OQs; the rail performing no vocabulary resolution; floor (i)
  itself vacuous against `USING`-only policies; P5 deferring a pin that fires in-slice; the rf
  control's forbidden discharge home.
- **MED (22) / LOW (24):** site counts (38/36, seven call sites, six assertion sites); the
  `proxy_mapping` numeric-attribute misdescription; the `REFERENCE` token; citation ranges; the
  three overstated Part 4b charges softened (count-pin "misreading", the "tiers" location, the
  fact-10 pendency claim); "four-times shipped" → three; "behaviour-preserving" → derived-not-independent;
  the AD-013 "both halves" over-claim narrowed; the missing OpenAPI/FE regeneration, downgrade-body
  step, teardown, and six-ledger completions — all now in Part 5's gates.
