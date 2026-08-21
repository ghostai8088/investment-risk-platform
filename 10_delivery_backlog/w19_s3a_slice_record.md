# W19-S3a slice record — the INGEST-1 mapping spine

| | |
|---|---|
| Status | **COMPLETE and MERGED 2026-08-21.** PR [#234](https://github.com/ghostai8088/investment-risk-platform/pull/234), merged as `7682a1c` — the 42nd autonomous merge. Branch head `57efd4c`. |
| Remit | `w19_s3a_remit.md` — owner-ratified, DS3a-1..4 all as recommended |
| Contract | REQ-INT-001 as amended at the Wave-19 planning gate (ten acceptance clauses) |
| Design authority | `ingest_1_decision_record.md` (2026-08-12, OQ-ING-1..4 all = A) |
| Migrations | `0074_ingestion_mapping_version`, `0075_bind_batch_to_mapping` — one per commit, the repo's precedent |
| Canonical id | **ENT-077** minted; next free **ENT-078**, advanced in all THREE live pointer copies |
| Audit code | **`DATA.MAPPING`** MINTED (R-07) — the taxonomy row is the mint record |

## 1. What the slice delivers, and what it does not

**REQ-INT-001 stays In-Progress**, and the line is drawn deliberately rather than optimistically.
Eight of ten clauses ship, plus the batch half of (2) and the refusal half of (6):

| Delivered here | Deferred to S3b |
|---|---|
| (1) no-ratified-mapping REFUSES · (3) an edited mapping moves exactly the rows the edit touches · (4) the interpreter is the only write path *from staged rows*, mechanically discovered · (5) each operation's refusal FIRES, unsupported refused BY NAME · (7) proposing model version + prompt identity, or HAND_AUTHORED · (8) ≥3 operation kinds · (9) reproducible from mapping + staged file + code-lookup data as of the load · (10) overlapping re-load REFUSES unless flagged a restatement · **(2) the batch's hard FK** · **(6) the `ratifier != proposer` refusal** | **(2) the per-`position` hard FK** — a migration over a table populated since `0014` · **(6) the permission separation** — the R-07 ratifier mint, its P11 holder-set pin, route census and SoD row |

Saying "Delivered" would have been the drift the 2026-08-12 re-baseline exists to stop: an
acceptance criterion satisfiable without delivering its stated purpose. Four-eyes is not four-eyes
until the maker and the checker cannot be granted the same code.

## 2. The two ratified scope changes

Both were surfaced as changes to a plan ratified the previous day, not taken as builder's calls, and
both are written into `wave_19_planning.md` and roadmap Part 2.21 so the plan and the build agree.

- **DS3a-2 — the `MAPPING.*` audit-code mint moved into S3a.** S3a is where the PROPOSED → RATIFIED
  → SUPERSEDED lifecycle is born and no existing code covers it, so S3a as planned would have
  shipped a governed status lifecycle emitting **nothing** — which no other lifecycle here does. One
  code, two actions, the `DATA.INGEST` shape. The permission codes still land at S3b.
- **DS3a-3 — `SelfRatificationError` ships in S3a.** The refusal half only.

Two further ratified calls changed no scope: **DS3a-1** keeps the ratify act at the service tier
(the three new routes are READS behind `data.upload`), and **DS3a-4** gave the position binders an
explicit lineage-source override, so a file-loaded holding is attributed to the INGESTION source
rather than to MANUAL entry.

**DS3a-5 was NOT put to the owner** and is flagged for reversal: S3b's `position.mapping_version_id`
does **not** enter `position_content`'s hash, because adding it would mark every pre-S3b POSITION
component DIVERGED in the CTRL-018 sweep — the platform's loudest alarm, fired by a provenance
column that is not a value the reproduction is about.

## 3. Six defects, none found by reading

**Three by the slice's own proofs:**

1. **`ingestion_batch.status` was `varchar(20)` and its vocabulary declares a 23-character value.**
   A batch that finished WITH WARNINGS could not be persisted on PostgreSQL *at all*. Shipped from
   migration `0007`; survived four waves because SQLite ignores VARCHAR length, so the whole unit
   tier wrote it happily, and no PG test ever drove the warning path. Found by the `0075` P17
   harness. The **class** is closed by `test_controlled_vocab_widths.py`, which discovers its own
   population — 280 pairs, exactly one violation, floor at 200.
2. **The anti-corruption layer made every SHORT position unparseable.** `neutralize_cell` prefixes
   `'` to any cell starting with `= + - @` (THR-06), and a short starts with `-`, while
   `position.quantity` is documented as signed. The repair is confined to the numeric path.
3. **On-ingest DQ rule selection had no tenant predicate.** RLS does not constrain a SUPERUSER —
   not even with FORCE — and every migration, demo seed and psql session runs as one, so on a shared
   database a superuser-path upload ran *another tenant's* rules against this tenant's file.

**Three by the review** — see §4.

## 4. The review

**Five refute-by-default lanes on a different model, then per-finding adversarial verification:
16 raised, 13 confirmed, 2 refuted, 1 partly refuted. All 13 folded.** The reviewers reproduced
rather than argued: planting files, mutating production code, running probes in isolated worktrees.

The three that matter most:

- **A refusal that could never fire, in the slice that shipped a census to prevent exactly that.**
  `assert_only_lifecycle_fields_change` was called by hand at two sites where only lifecycle fields
  had been assigned, and its two tests called it *directly*. A reviewer assigned
  `version.operations` on a RATIFIED row, issued an ordinary query, and autoflush pushed the UPDATE
  with no refusal and no audit event. It is a `before_update` ORM listener now.
- **Four-eyes defeated by an uppercase UUID.** The refusal compared raw strings, and
  `require_uuid_principal_id` accepts any spelling `uuid.UUID()` parses. The ENT-075 rail already
  carries this vector as a named test; this slice did not reuse that rail and so did not inherit
  the lesson.
- **A governed refusal that was a raw `ArithmeticError`.** Nothing restricted which operation may
  fill a decimal target, so a `rename` into `quantity` ratified happily and then died at load with a
  bare `decimal.InvalidOperation` — not a `MappingError`, so a caller failing closed on the family
  caught nothing. Trigger: `1,234.50`.

And a **false claim in the module whose purpose is to prevent them**: `errors.py`'s docstring said a
census asserted every refusal was fired by a test. No such census existed anywhere in the repo. It
does now, discovers its population from `MappingError.__subclasses__()`, and is **P9's mechanical
limb — which this project had never had**.

**The two refutations are recorded, not dropped.** One verifier reset a database, created the
constrained NOSUPERUSER NOBYPASSRLS role and executed the cross-tenant read to show the three new
endpoints are reachable only under it — unlike `stage_upload`, which has a real superuser-path
caller and is why defect 3 was live and this was not. A factual refutation is the only kind that
kills a finding here (P13).

## 5. Lessons, as acts

- **(a) MECHANICAL — `test_controlled_vocab_widths.py`.** Every controlled-vocabulary value fits the
  column that stores it. Discovers its own population; floor; positive control planting the
  historical 23-vs-20 shape; matching-rule boundary cases pinned, including two real near-misses a
  token-overlap rule flagged in the first draft.
- **(a) MECHANICAL — the refusal census.** P9's missing mechanical limb, from `__subclasses__()`.
- **(a) MECHANICAL — the write-path census follows CALLS, to a fixed point.** Two things learned in
  the fixing and recorded in the file: import-following was tried first and was too coarse (it
  flagged the demo stage for importing `campaign` to get two constants, and *a census that needs an
  exemption list stops meaning anything*); and the sanctioned route must be **cut out of the graph**,
  because the question is not "who reaches a position write" but "who reaches one **without** going
  through the ratified mapping".
- **(b) PROCEDURAL — a negative control drives the real function, never a re-implementation of it.**
  The first two-hop control asserted against the algorithm's parts, and a mutant that disabled the
  fixed point *survived it*. Bound to the moment of writing any census control.
- **(b) PROCEDURAL — normalize before any cross-tier datetime comparison.** SQLite returns naive
  datetimes from `DateTime(timezone=True)`; the overlap check was `False` for two identical instants
  and the governed refusal would never have fired.
- **(c) RECURRENCE ACCEPTED — the shared-tree hazard.** A reviewer's planted bypass files were live
  in the tree while a gate of mine ran, and the standing check (`git status` before pushing, purge
  caches, re-run every gate) caught it. Agents that reproduce by planting are *more* valuable, not
  less; the mitigation is the existing rule, applied, not fewer plants.

## 6. Gates at the merge, quoted

`make check` exit 0 — **3,007 passed / 654 skipped** (baseline 2,908) · full-PG exit 0 on a fresh
database — **3,661 passed, ZERO skips** (baseline 3,500) · `fe-check` exit 0 (39 files / 274 tests)
· `gen-api-check` exit 0 · `alembic check` exit 0 · downgrade-over-data to `0071` exit 0 ·
`0074`/`0075` downgrade + re-upgrade exit 0 · P17 harness exit 0 · mutation battery **20/20 KILLED**
· anchors **150/150** · CI green on all nine checks at `57efd4c`, verified per conclusion.

**P16 did not fire:** no control moved to Implemented/Operational on OBSERVED evidence in this
slice. CTRL-027's evidence prose was tightened (the tenant predicate); its status is unchanged.

## 7. NEXT

**Wave-19 slice S3b** — INGEST-1 governance: the R-07 ratifier mint with its P11 holder-set pin,
route census and SoD row; four-eyes as a parallel resolution-row lifecycle on ENT-077 (**not** an
ENT-075 CHECK widening, whose rail is hard-constrained to three entitlement actions and fails closed
on a fourth); the hard-FK attribution on canonical `position` rows; and the REQ-PPM-002
mechanical-discovery census, hosted and enforced in-slice. Its row enters G2 at its own slice gate.
