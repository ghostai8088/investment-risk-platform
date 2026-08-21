# Ingest mapping drafting, v1 — the AI as a registered drafting tool at the boundary

**Model family:** `INGEST_MAPPING_DRAFTER` · **Type:** `AI_ML` · **Slice:** W19-S3a ·
**Ratified design:** `10_delivery_backlog/ingest_1_decision_record.md` (2026-08-12, OQ-ING-1..4 all
= A)

This document exists because the drafting model is a **registered `model_version`**, and every
registered model on this platform must have a methodology reference. It is deliberately short: the
model produces no number, and there is no estimator to specify.

## 1. What the model does, and the line it does not cross

> *The AI proposes a mapping. A human ratifies it. The platform executes the ratified version
> deterministically, forever, and every loaded row records which version loaded it.*

The model is a **drafting tool at the boundary**. Given a source file's *schema* it proposes an
ordered list of operations drawn from the closed vocabulary, expressing what each column means in
canonical terms. That proposal is data. It becomes operative only when a human ratifies it, and the
platform then executes the ratified version — never the model's output directly, and never the
model at load time.

**The model is never in the path of a number.** This is the same line the platform already draws
around risk models — a model produces a number only through registered, versioned, reproducible
code — extended to the *meaning of the inputs*. A mapping version is reproducible in exactly the
sense every governed artifact here is: the same ratified operations over the same staged rows and
the same code-lookup reference data produce canonically identical canonical rows, and none of that
re-invokes the model.

## 2. Inputs — SCHEMA ONLY, and this is load-bearing

The drafting act sees:

- column **names**, in file order;
- **inferred types** per column (a coarse label: text, number, date-like);
- **obfuscated sample values** — shape-preserving, value-destroying (digits mapped to digits,
  letters to letters), enough to distinguish `2026-07-31` from `31/07/2026` without disclosing a
  holding.

It does **not** see client holdings, quantities, valuations, portfolio identities, or any row as
recorded. To propose that `MKT_VAL_BASE` means market value in base currency, a model needs the
column name, an inferred type and an obfuscated example. It does not need real positions.

**Deciding this before building was the point** (OQ-ING-3): it keeps the data-protection surface
small, and it is very hard to retrofit once the obvious version is built. The diligence answer is
short and true: *the product makes no third-party model calls, and the drafting tool sees column
names and obfuscated samples, never rows.*

## 3. Where it runs — OPERATOR-SIDE, outside the deployed product

There is **no external model call inside the deployed product and no API key in the deployed
stack.** Onboarding is a supervised event, so the experience cost of running the drafting step
operator-side is small and the security argument is decisive.

In-product drafting is **not foreclosed** — it is a later decision this shape keeps available,
because the artifact and its ratification path are identical either way. Nothing in the schema or
the lifecycle would change.

## 4. Output contract

A proposal is a JSON array of operations. Each names an `op` from the closed set (`rename`, `cast`,
`scale`, `parse-date`, `code-lookup`, `constant`, `concatenate`), a canonical `target`, and the
parameters that operation declares. Anything else is refused — by name, at proposal time, before a
human is asked to ratify it.

The platform validates a proposal on arrival rather than trusting it: undeclared targets, missing
required targets, and constants that cannot be coerced to their target's type are all refused at
`propose`, not merely at load. **Asking a human to ratify something that could never load anything
is worse than refusing it**, because a ratification is a governance record.

## 5. Provenance — what is recorded, and what that does and does not prove

Every `MODEL_PROPOSED` mapping version records:

| Field | What it is |
|---|---|
| `proposer_model_version_id` | hard FK to the registered `model_version`, re-resolved tenant-filtered before it is stamped |
| `proposal_prompt_hash` | sha256 of the committed prompt artifact |
| `proposal_prompt_ref` | the committed prompt |
| `proposal_response_ref` | the committed raw response envelope |

A symmetric database CHECK binds authorship to its evidence in **both** directions: a
`MODEL_PROPOSED` row must carry the model version and the prompt hash, and a `HAND_AUTHORED` row
must carry **neither**. The mirror case matters as much as the obvious one — stale or copied model
attribution sitting on an operator-written row reads to a reviewer as provenance.

**Stated plainly, because the alternative is a false claim:** this is a record of *presence*, not a
cryptographic proof of *origin*. The CHECK guarantees a `MODEL_PROPOSED` row names a real registered
model version and a real committed prompt whose hash matches; it cannot prove the response came from
that model rather than from a person typing. The response envelope narrows the gap — it carries what
a real call returns and a person would have to fabricate — and it does not close it. Closing it
would need signed attestation from the provider, which does not exist today. The residual is
recorded here rather than papered over.

## 6. Governance status and limits

- **Untiered at registration**, like every model head on this platform; an untiered model inherits
  the Tier-1 fail-safe review ceiling.
- **An agent actor may REGISTER a model version but may never VALIDATE or TIER one** —
  `record_validation` and `assign_model_tier` refuse a non-human actor before any write (BR-15 /
  MG-07). Ratifying an AI-drafted mapping is therefore a human act *by mechanism*, not by
  convention.
- **No accuracy claim is made or measured.** A proposal is a draft; its correctness is established
  by the human who ratifies it and by the refusals the interpreter fires, not by a score. There is
  deliberately no "mapping accuracy" metric, because a number like that would invite treating the
  ratification as a formality.

## 7. Limitations, and the trigger each would fire on

- **One source type.** Positions only (OQ-ING-4). Prices and benchmarks follow; the artifact and
  the lifecycle are unchanged, only the target vocabulary grows.
- **`code-lookup` resolves instruments only.** `resolve_identifier` is the platform's only
  as-of-capable resolver and is scope-fenced to `entity_type='instrument'`. A multi-account file
  needs either a portfolio resolver or that fence lifted, deliberately — trigger: the first file
  carrying more than one account.
- **A file the closed vocabulary cannot express is refused, by name.** That is the feature: a new
  operation is added deliberately and reviewed. Trigger: a real client file that needs one.
- **`is_active` on `identifier_xref` is not honoured by resolution** — an operator can deactivate a
  cross-reference without closing its validity period, and a deactivated-but-open row still
  resolves. Existing behaviour with other callers; changing it is its own review.

## 8. What this replaces

Nothing. Before this slice the platform mapped **nothing** into canonical domain tables; the
ingestion module's own docstring said so. The alternative it replaces is the incumbent industry
practice — weeks of consultants per client per feed — which is what sets the minimum client size a
risk platform can profitably serve.
