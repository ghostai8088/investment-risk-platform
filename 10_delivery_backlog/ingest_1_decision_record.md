# INGEST-1 — AI-drafted, human-ratified source mappings: decision record

**Status: RATIFIED 2026-08-12** — four decision points, all as recommended, at a design gate the
user opened by asking whether the platform's data-inflow assumptions were best practice and whether
AI changes the answer.

**Slice:** Wave-18 candidate (sequencing implication in §6 — this is NOT yet placed).
**Planned at:** HEAD `1544fa9` on `main`; migration head `0070_app_role` on branch
`deploy-1-app-role`; next free canonical id **ENT-076**.

---

## 1. The question this answers

Mapping a client's data onto a risk system is historically the most expensive part of deploying
one: weeks of consultants per client, per feed. It is why incumbent risk platforms can only
profitably serve large institutions — the onboarding cost has a floor, and that floor sets the
minimum client size.

Language models are genuinely good at proposing a column mapping from a sample. The strategic
claim is therefore: **if onboarding a client's data becomes a supervised 30-minute session rather
than a six-week project, the addressable market changes shape.**

The engineering claim underneath it is narrower and is what this record decides: an AI-drafted
mapping is only usable in a governed platform if it becomes an ordinary governed artifact —
versioned, ratified by a human, executed deterministically, and bound into the provenance of every
row it loads.

## 2. The spine (the sentence the design follows from)

> **The AI proposes a mapping. A human ratifies it. The platform executes the ratified version
> deterministically, forever, and every loaded row records which version loaded it.**

The model is a drafting tool AT THE BOUNDARY. It is never in the path of a number. This is the same
line the platform already draws around risk models — a model produces a number only through
registered, versioned, reproducible code — extended to the meaning of the inputs.

**Corollary, and it is load-bearing: the AI only needs the SCHEMA, not the DATA.** To propose that
`MKT_VAL_BASE` means market value in base currency it needs column names, inferred types, and
obfuscated example values. It does not need real holdings. Deciding this now is what keeps the
data-protection surface small; it is very hard to retrofit once the obvious version is built.

## 3. The rails this reuses rather than invents

Verified at HEAD before the gate, not assumed:

| Rail | State | Use here |
|---|---|---|
| `ModelVersion` (`model/models.py:182`) | Immutable append-only; `version_label`, `methodology_ref`, `code_version`, DRAFT/REGISTERED status; generic, not risk-specific | Registers the AI drafting model, so every proposal is attributable to a model version |
| Four-eyes approval | Proven at three tiers (unit, endpoint, deployed proof) at ONBOARD-1b | Ratifying a mapping version is a maker-checker act |
| `DataSource` + lineage ORIGIN edge | Shipped (P1A-1) | A mapping belongs to a source; the batch already links to one |
| `ingestion_batch` | Shipped; binds `data_source_id` | **GAP:** binds no mapping version — the one hook this design must add |
| Anti-corruption layer | CSV-only, size-capped, formula-neutralised | Unchanged; mapping happens AFTER staging |

The ingestion module's own docstring already states the gap plainly: *"It maps NOTHING into
canonical domain tables (deferred to P1B/P1C)."* This slice is that deferral, collected.

## 4. The ratified decisions

### OQ-ING-1 = A — a mapping is VERSIONED DATA, interpreted

Not generated code. The decisive consequence: onboarding a client requires no software release. A
code-generation design would put the onboarding floor back where the incumbents have it, which
forfeits the entire economic argument in §1.

**The cost, stated rather than discovered:** the platform now executes instructions supplied from
outside itself. That is a genuine surface, and it is why OQ-ING-2 bounds the vocabulary hard. The
two decisions are one decision.

### OQ-ING-2 = A — a CLOSED SET of transformation operations

Rename, cast, scale, parse-date, code-lookup, constant, concatenate — a fixed list, each
independently tested, each with its own refusal proven to FIRE (P9). Not an expression language.

Three reasons, in order of weight: *"what did this mapping do?"* keeps a simple answer that a
non-engineer can audit; reproducing a historical load never means reproducing an interpreter's
exact behaviour; and the platform does not acquire a sandbox to own. A file that cannot be
expressed forces a NEW OPERATION to be added deliberately and reviewed — which is a feature, and
the refusal must name the unsupported operation rather than failing vaguely.

### OQ-ING-3 = A — the AI runs OPERATOR-SIDE, and sees SCHEMA ONLY

No external model call inside the deployed product; no API key in the deployed stack; no client
holdings leaving the tenant boundary. Onboarding is a supervised event, so the experience cost is
small and the diligence answer becomes short and true: *the product makes no third-party model
calls, and the drafting tool sees column names and obfuscated samples, never rows.*

In-product drafting is NOT foreclosed — it is a later decision that this shape keeps available,
because the artifact and its ratification path are identical either way.

### OQ-ING-4 = A — ONE source type, end to end, first

Positions only: the mapping artifact, its ratification, the interpreter, the batch binding, and a
real file loaded, read back, and reproducible. Then prices and benchmarks.

The project's own record is the argument: designs here are usually wrong until executed against
something real (SCH-2 refuted two verifier-endorsed decisions by execution; REPRO-2 found four
registry reasons factually wrong about their own binders). A framework built before its first real
file is a framework fitted to an imagined one.

### Recommended and adopted without a fork — the AI is a REGISTERED MODEL

Every proposal records which model, which version, and which prompt produced it. It costs
something: AI drafting enters model governance with the review burden that implies. The
alternative is an ungoverned model influencing what the data MEANS, inside a platform whose entire
claim is that nothing is ungoverned.

## 5. What this does NOT decide

- **The conversational query surface.** It shares this spine — *propose and parameterise, never
  compute* — but it is a separate slice with its own gate, and nothing here commits to it.
- **The four inflow facts.** Where the data comes from, how it arrives, how often and how large,
  and who wins a restatement. Those are facts about the user's situation, not design choices, and
  the first three narrow this work substantially once known. The FOURTH — who wins a restatement —
  is a genuine judgement call and remains OPEN.
- **The 10 MiB upload cap** (`anticorruption.py:MAX_UPLOAD_BYTES`). Realistic for a few thousand
  line items, not for a large book or any file carrying history. Raising it has knock-on effects on
  how files are processed and is better decided than discovered. **Carry, trigger: the first real
  client file, or the answer to inflow fact 3.**

## 6. Sequencing — an honest conflict, and a recommendation

Wave 18's ratified thesis is **"Show it to someone"** (DEMO-1, DEMO-2, ONBOARD-2, RUN-UI,
PRESENT-1). INGEST-1 was not in it, and it is at least L.

**But it may belong there anyway, and the argument is not a rationalisation.** The recon's largest
demo finding was that the only way to populate a deployed database is to run a 24-file developer
test battery — not something anyone would do in front of an audience. DEMO-1 exists to fix that by
wrapping those stages in a command. INGEST-1 fixes it differently and far more persuasively:

> *"Here is a position file. Watch the platform propose what its columns mean, watch me approve
> that, and watch the book load — governed, reproducible, and attributable to the mapping version
> that loaded it."*

That is a materially stronger forty-five minutes than pre-seeded fixtures, and it demonstrates the
governance architecture rather than describing it.

**Recommendation:** INGEST-1 enters Wave 18 and DEMO-1 narrows to what INGEST-1 does not cover
(reference data, and a seeded starting state so the screens are not empty before the demonstration
begins). The wave lengthens. **NOT self-enacted — this changes a ratified wave scope and is the
user's call at the Wave-18 planning gate.**
