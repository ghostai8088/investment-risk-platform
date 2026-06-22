# P1B-0 Decision Record — Security Master & Reference Data

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1B0-DR-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-01 Chief Architect AI (with R-05 Data Architect AI) |
| Approver | H-06 Engineering Lead (H-04 Head of Architecture, H-08 Internal Audit consulted) |
| Created | 2026-06-22 |
| Related Documents | p1a_closeout_p1b_readiness.md, p1b_implementation_plan.md, ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../04_data_model/canonical_data_model_standard.md, ../04_data_model/temporal_reproducibility_standard.md, ../04_data_model/audit_event_taxonomy.md, ../06_security/entitlement_sod_model.md, ../09_compliance_controls/control_matrix_skeleton.md, ../11_decision_log/architecture_decision_log.md |
| Supported Build Rules | BR-3, BR-5, BR-7, BR-11, BR-12, BR-13, BR-17, BR-19 |

**Purpose.** Resolve the ten open decisions (OD-P1B-A … OD-P1B-J) raised by the P1A closeout / P1B
readiness review so that **P1B-1 can be planned and implemented** without re-litigating cross-cutting
design. **Scope: Security Master & Reference Data only.** This is a decision/governance artifact — **no
application code, migrations, or rail changes** are produced. Decisions that touch a ratified baseline
(AD-005, AD-013, the canonical model, the RTM, the audit taxonomy, the entitlement catalog) record the
required ADR / requirement / taxonomy change as a **follow-up action**, executed inside the relevant
P1B build slice, never silently.

**P1B scope entities:** `currency`, `calendar`, `rating_scale`, `legal_entity`, `issuer`,
`counterparty`, `instrument`, `instrument_terms` (FR), `identifier_xref`, `corporate_action`.

**Explicit exclusions (P1C / P2+):** portfolio, positions, valuations, market prices, market-data
ingestion, private-asset ingestion, GP-report parsing, risk calculations, exposure aggregation, limits,
breach workflow, dashboards, reporting, real SSO. None may appear in any P1B deliverable.

---

## OD-P1B-A — Instrument temporal class

1. **Decision.** Split the instrument into two entities: **`instrument` = EV** (identity / master
   attributes — identifier handle, asset_class, issuer reference, status) and **`instrument_terms` = FR**
   (effective-dated economic/legal terms — coupon, maturity, call/put schedules, day-count, denomination
   currency), using `FullReproducibleMixin` (valid-time + system-time).
2. **Rationale.** AD-005 §2A and REQ-SMR-001 (`instrument (FR terms)`, acceptance "Instrument terms
   reconstructable as-of") require bitemporal reproducibility of the terms that drive pricing/risk; EV
   (system-time-only effective dating) cannot reconstruct "as-of valid-time T1 as-known-at T2". Identity
   attributes are not risk-driving and are cheaper as EV. The split confines the expensive FR pattern to
   exactly the risk-driving surface (proportionate cost, AD-005's stated intent).
3. **Alternatives considered.** (a) Blanket EV instrument — rejected: violates REQ-SMR-001 "reconstructable
   as-of" and AD-005 FR-for-risk-inputs; would require an AD-005/REQ amendment. (b) Blanket FR instrument —
   rejected: makes identity attributes needlessly bitemporal. (c) Snapshot-binding (EV instrument + a P2
   snapshot) — rejected for P1B: defers reproducibility off the entity that owns the terms.
4. **Risks.** P1B-3 is the **first real FR/bitemporal domain usage** — temporal-query correctness and
   as-of reconstruction tests are load-bearing; mis-implementation is expensive to retrofit. **Note:**
   `FullReproducibleMixin` exists structurally (`db/mixins.py`) but is **unexercised by any P1A entity or
   test** — P1B-3's "reconstructable as-of" proof is therefore **net-new validation of the FR mixin itself**
   (column behavior, as-of query, valid-time vs system-time axes), not a regression check of tested code.
5. **Impacted requirements.** REQ-SMR-001 (clarified: identity=EV, terms=FR — an annotation, not a scope
   change; "FR terms" already in the backbone).
6. **Impacted controls.** CTRL-004 (data-dictionary field definition — a Preventive/Manual control, BR-4;
   not a runtime gate), CTRL-017 (reproducibility), BX-AUD/BX-LIN.
7. **ADR update required?** No new ADR — this **conforms to** AD-005 §2A. **Canonical-model annotation
   required** (mirroring OD-P1B-D): record that canonical ENT-001 `instrument` is realized as `instrument`
   (EV identity) + `instrument_terms` (FR economic terms) — no entity removed/renamed (executed in P1B-3).
8. **Requirements update required?** Minor: annotate the REQ-SMR-001 row in
   `requirements_traceability_matrix.md` to record the identity-EV / terms-FR split (documentation
   precision; no scope change).

---

## OD-P1B-B — Corporate-action temporal class

1. **Decision.** `corporate_action` = **EV** (effective-dated; applies on its effective/ex-date; amendable
   or cancellable via a superseding effective version before application).
2. **Rationale.** AD-005 §2A lists corporate_action under EV reference/master data; REQ-SMR-004 classifies
   `corporate_action (EV)` with acceptance "Actions apply on effective date". A corporate action is
   effective-dated reference data, not an immutable run/output — IA was a category error in the readiness
   draft (CalculationRun is an IA *run* record, not EV master data).
3. **Alternatives considered.** (a) IA append-only (readiness draft) — rejected: contradicts AD-005 §2A /
   REQ-SMR-004 and forbids the legitimate amend/cancel-before-application lifecycle. (b) A *separate*
   immutable announcement-event log alongside the EV record — deferred: a distinct entity decision, not
   in P1B scope; raise explicitly if ever needed (do not reclass ENT-008).
4. **Risks.** EV supersede semantics must be tested so an amended action does not double-apply. Mitigation:
   effective-dated supersede test in P1B-4; no automatic application logic in P1B (that is P1C). **Note:**
   `corporate_action` (EV) is mutable in place (no IA P0001 trigger), so the **reproducible status-lifecycle
   history depends on the `REFERENCE.*` audit trail + EV effective versions**, not on append-only immutability.
5. **Impacted requirements.** REQ-SMR-004 corporate_action half (already EV — no change). Its other
   acceptance clause, **"calendars drive rolls" (QS-10/11 day-count/roll math), is deferred** (excluded from
   P1B) — so the calendar deliverable in P1B-1 **partially meets** REQ-SMR-004 (mirrors the REQ-SMR-003
   precedence-partial treatment).
6. **Impacted controls.** CTRL-004 (data-dictionary), CTRL-017.
7. **ADR update required?** No — conforms to AD-005 §2A.
8. **Requirements update required?** Annotate REQ-SMR-004 (calendar) as partially met — roll math deferred.

---

## OD-P1B-C — Hybrid global reference-data tenancy

1. **Decision.** Implement AD-013 hybrid tenancy via **SYSTEM_TENANT_ID rows inside the tenant-scoped
   reference tables + an asymmetric RLS policy**, rather than AD-013's literal "separate no-`tenant_id`
   RLS-exempt global tables". For **hybrid** reference tables (currency, calendar, rating_scale only):
   `USING (tenant_id::text = current_setting('app.current_tenant', true) OR tenant_id::text =
   SYSTEM_TENANT_ID)` for reads; `WITH CHECK (tenant_id::text = current_setting('app.current_tenant',
   true))` single-tenant for writes (so SYSTEM_TENANT rows are writable **only** under system context, as
   the shipped P1A-3 test already proves). **Tenant override:** a tenant row shadows a global of the same
   `code`; uniqueness is `UNIQUE(tenant_id, code)` (**never** `UNIQUE(code)`). **The "tenant row wins" is an
   APPLICATION-LAYER read responsibility, NOT an RLS guarantee** — the hybrid `USING` returns BOTH the tenant
   row and the SYSTEM_TENANT row of the same `code` to a tenant reader; the read layer dedups by `code`
   preferring the caller's tenant over SYSTEM_TENANT (e.g. `DISTINCT ON (code) ORDER BY (tenant_id =
   SYSTEM_TENANT_ID)`). **Hard invariant:** proprietary/investment entities (legal_entity, issuer,
   counterparty, instrument, instrument_terms, identifier_xref) are **never** stamped SYSTEM_TENANT and are
   **never** hybrid — they are single-tenant with `WITH CHECK` (no cross-tenant or MNPI leakage). The
   **closed hybrid set is exactly {`currency`, `calendar`, `rating_scale`}**.
2. **Rationale.** Keeping FORCE RLS on every table (vs an RLS-exempt table) preserves a single, proven
   isolation mechanism, reuses the system-context-only write proof, and avoids a second schema/security
   model. AD-013's intent ("global shared read-only; investment tenant-scoped; no proprietary sharing") is
   fully satisfied; only the *mechanism* differs from the "RLS-exempt" consequence AD-013 noted.
3. **Alternatives considered.** (a) Literal AD-013 "separate no-`tenant_id` RLS-exempt global tables" —
   viable but introduces a non-RLS security surface that must be separately proven leak-free, and a second
   table shape per entity. (b) Replicate global rows into every tenant — rejected: storage blow-up + drift.
4. **Risks.** The extended `USING` is intentionally **not fully fail-closed** in the no-context case (a
   context-less read returns the global slice) — acceptable **only** because global rows are
   non-proprietary by construction; a PG test must assert this precisely. **Only the system-context-only
   WRITE is proven by an existing P1A test; the asymmetric global-READ `USING (own OR SYSTEM_TENANT)` is
   net-new in P1B-1 (all P1A tables use symmetric single-tenant `USING`) and is covered by NO P1A test** —
   P1B-1 must add it. Risk of a proprietary entity accidentally made hybrid → enforced by the invariant + a
   scope-fence test (issuer/counterparty/instrument never SYSTEM_TENANT, never hybrid policy).
5. **Impacted requirements.** REQ-SMR-001/002/003/004 (all rely on the tenancy model); CAP-2.
6. **Impacted controls.** CTRL-003 (tenant isolation), CTRL-004, BR-17/AD-008 (MNPI-adjacent isolation).
7. **ADR update required?** **Yes — AD-013-R1 refinement** recording the SYSTEM_TENANT + asymmetric-policy
   mechanism, the proprietary-never-hybrid invariant, and the no-context global-read caveat. Ratifiers:
   R-04 + R-05 + H-04.
8. **Requirements update required?** No (mechanism, not requirement).

---

## OD-P1B-D — Issuer / counterparty / legal-entity model

1. **Decision.** A shared **`legal_entity` core** (identity, LEI, name, domicile, parent/child hierarchy)
   with **separate `issuer` and `counterparty` role/profile tables** that reference the core 1:1 and hold
   role-specific attributes. All EV. A single legal entity may carry both an issuer and a counterparty
   profile.
2. **Rationale.** Canonical ENT-002 (issuer) and ENT-003 (counterparty) are distinct entities; REQ-SMR-002
   names them separately and requires hierarchy rollup; the entitlement catalog already ships separate
   `reference.issuer.*` / `reference.counterparty.*` pairs (SoD-relevant); OD-015 (netting/CSA) is
   counterparty-only and attaches to the counterparty profile later. The shared core removes LEI/hierarchy
   duplication **without** collapsing the canonical entities — "shared core, distinct role tables".
3. **Alternatives considered.** (a) Unified single `legal_entity` + role flags (readiness draft) — rejected:
   contradicts canonical ENT-002/003 and REQ-SMR-002, weakens the SoD permission split, and would force a
   canonical-model amendment. (b) Fully separate issuer/counterparty with no shared core — rejected:
   duplicates LEI/hierarchy and risks divergent hierarchies for the same legal entity.
4. **Risks.** Hierarchy lives on the core; rollup must resolve through the core regardless of role. The 1:1
   core↔profile contract must be enforced (a profile cannot exist without its core). Mitigation: FK +
   hierarchy-rollup test in P1B-2.
5. **Impacted requirements.** REQ-SMR-002 (satisfied; `legal_entity` core is an additive implementation
   structure, not a new requirement).
6. **Impacted controls.** CTRL-004; entitlement SoD (separate issuer/counterparty permissions).
7. **ADR update required?** Optional minor — a canonical-model **annotation** that ENT-002/003 share a
   `legal_entity` core. **`legal_entity` is an implementation-only shared core with NO new ENT id**; canonical
   ENT-002 issuer / ENT-003 counterparty are preserved as the 1:1 role profiles, hierarchy lives on the core.
   No entity removed/renamed; no full ADR. (`instrument`'s issuer FK targets the `issuer` profile, not the
   bare core.)
8. **Requirements update required?** No.

---

## OD-P1B-E — Reference-data CRUD audit codes

1. **Decision.** Mint a new **`REFERENCE`** audit category (taxonomy §3) with explicit codes:
   `REFERENCE.CREATE`, `REFERENCE.UPDATE`, `REFERENCE.CORRECTION`, `REFERENCE.STATUS_CHANGE`, indexed at
   the next free EVT block **EVT-140…143** (categories currently end at AGENT/EVT-130). `entity_type`
   carries the reference entity; effective-dated supersede emits `REFERENCE.UPDATE` (or `.CORRECTION` for a
   restatement of a prior effective version).
2. **Rationale.** The DATA category has **no** generic `.CREATE`/`.UPDATE` action and no REFERENCE category
   exists, so reference CRUD codes are net-new regardless; an explicit category is clearer and auditable
   than overloading DATA, mirroring how MODEL has its own governance category. The user explicitly forbids
   generic undefined `DATA.CREATE`/`DATA.UPDATE`.
   **Reconciliation with the reserved `DATA.CORRECTION` / TR-07 / TR-08 (required, R-07 + R-05):** the
   taxonomy reserves `DATA.CORRECTION` for restatement/override, and TR-07/TR-08 require a correction to be
   an auditable event carrying a **restatement reason + a link to the superseded version** (and, for governed
   values, to flow through `manual_override` with BR-7 fields — a P6/P7 concern, non-enforcing now). Decision:
   `REFERENCE.CORRECTION` is the **reference-domain** restatement code (distinct from `DATA.CORRECTION`, which
   stays reserved for data-lifecycle restatement); an FR `instrument_terms` restatement MUST carry the TR-08
   `restatement_reason` + superseded-version link in its `after_value` (captured in P1B-3). Confirm the
   boundary with R-07 + R-05 at mint time.
3. **Alternatives considered.** (a) New `DATA.*` actions (e.g. `DATA.REFERENCE_CREATE`) — viable but mixes
   reference CRUD into the data-lifecycle category. (b) Reuse `DATA.SOURCE_REGISTER`-style codes — rejected:
   those are provenance-source codes, not entity CRUD.
4. **Risks.** EVT-index collisions if allocated carelessly (the P1A-3 EVT-030 lesson). Mitigation: R-07
   allocates EVT-140 block explicitly; CTRL-012 audit-coverage test asserts the literal codes. **Audit-chain
   note:** audit streams are per-tenant (`chain_id = tenant_id`), so global SYSTEM_TENANT reference seeds
   land on the **SYSTEM_TENANT audit stream**, not any consuming tenant's — verify_chain runs per stream.
5. **Impacted requirements.** REQ-AUD-001 (satisfied cross-cutting). All REQ-SMR (auditable writes).
6. **Impacted controls.** CTRL-005, CTRL-012 (audit coverage), CTRL-032 (fail-closed audit).
7. **ADR update required?** No.
8. **Requirements update required?** **Audit-taxonomy update required** (R-07): add the REFERENCE category +
   EVT-140 block to `audit_event_taxonomy.md`. Executed in the P1B-1 slice, not now.

---

## OD-P1B-F — Entitlement gaps

1. **Decision.** Add the missing reference permissions with **view/edit separation**, standardized as
   `reference.<entity>.<verb>`: **new** `reference.currency.view/edit`, `reference.rating_scale.view/edit`,
   `reference.legal_entity.view/edit`; **add missing `.view`** for `reference.calendar.view`,
   `reference.corporate_action.view` (catalog has only `.edit`); **reuse existing**
   `reference.instrument.view/edit`, `reference.issuer.view/edit`, `reference.counterparty.view/edit`,
   `reference.identifier.resolve`. **Reserve `reference.rating.*`** for the future FR rating-assignment
   domain (not P1B). Grants follow least-privilege (data_steward edit; broader view) with **no role-template
   change beyond additive grants**, governed by R-07.
2. **Rationale.** Deny-by-default requires every endpoint to gate on a real permission; currency/rating_scale
   and the `.view` reads currently have none. View/edit separation supports SoD (a viewer cannot mutate).
3. **Alternatives considered.** (a) Reuse a single coarse `reference.*` permission — rejected: violates
   least-privilege and view/edit SoD. (b) Per-verb-per-field — rejected: over-granular for a skeleton.
4. **Risks.** Over-granting on a role template. Mitigation: additive grants only; bootstrap least-privilege
   test (as in P1A slices) asserts the grant set.
5. **Impacted requirements.** BX-ENT; all REQ-SMR.
6. **Impacted controls.** CTRL-011 (deny-by-default), entitlement SoD.
7. **ADR update required?** No.
8. **Requirements update required?** **Entitlement-catalog update required** (R-07): extend `bootstrap.py`
   PERMISSIONS + grants in the relevant P1B slice (P1B-1 for currency/calendar/rating_scale, P1B-2 for
   legal_entity). Not now.

---

## OD-P1B-G — Identifier resolution

1. **Decision.** `reference.identifier.resolve` is a **deterministic, scoped lookup** returning **exactly
   one** instrument or an **explicit ambiguity error** — never a silent arbitrary match. Resolution scope:
   tenant-scoped (RLS) + effective-date filter on `identifier_xref(valid_from, valid_to)`. Structural
   uniqueness: a **partial unique index** `(tenant_id, scheme, value) WHERE valid_to IS NULL` (active rows
   only — a plain `UNIQUE` cannot express "over the active period" and would collide across superseded EV
   versions) prevents ambiguity at write time where feasible; where multiple active rows still match, the
   resolver returns a typed `AmbiguousIdentifier` error. **Cross-vendor precedence ranking is deferred**
   (OD-012 → P1C).
2. **Rationale.** REQ-SMR-003 acceptance "Any known identifier resolves to one instrument" + a precedence
   test cannot be fully met without OD-012 precedence, so P1B delivers the deterministic-or-explicit-error
   contract (the half that is honest and testable) and records REQ-SMR-003 as **partially met**.
3. **Alternatives considered.** (a) Return first/arbitrary match — rejected: silent wrong resolution, a
   correctness/audit hazard. (b) Build a precedence engine now — rejected: OD-012 is open; over-builds P1B.
4. **Risks.** A consumer assuming full single-resolution where precedence is needed. Mitigation: the
   ambiguity error is explicit and audited; REQ-SMR-003 marked partial; precedence fenced to P1C.
5. **Impacted requirements.** REQ-SMR-003 (partially met; precedence → P1C/OD-012).
6. **Impacted controls.** CTRL-004; CTRL-029 (no silent wrong/empty resolution).
7. **ADR update required?** No.
8. **Requirements update required?** Annotate the REQ-SMR-003 row in `requirements_traceability_matrix.md`:
   P1B delivers deterministic-or-ambiguity resolution; cross-vendor precedence deferred to P1C (OD-012).
   Documentation precision.

---

## OD-P1B-H — Service package / dependency boundaries

1. **Decision.** P1B reference services live in a **new web-framework-free package `irp_shared.reference`**
   (sibling to audit/calc/db/dq/entitlement/ingestion/lineage/model — the eight existing submodules), with FastAPI endpoints in
   `irp_backend/api/reference*`. The model aggregator `irp_shared.models` registers the new models.
   **Dependency direction:** `reference → (lineage, dq, audit, entitlement, db, temporal)` **only** — never
   the reverse, and **no dependency on risk, portfolio, ingestion-mapping, or reporting modules**. The
   optional P1B-5 ingestion-mapping step may depend on `ingestion`; the **reference CRUD core must not**.
2. **Rationale.** Matches the proven per-domain package pattern (zero web-framework imports in
   `irp_shared`); a one-way acyclic dependency keeps reference reusable by web app and workers without
   coupling; an import-direction test enforces it (as P1A-3/P1A-4 do).
3. **Alternatives considered.** (a) Per-entity packages (`irp_shared.currency`, …) — rejected for a skeleton:
   excessive package count; one `reference` package with submodules is cleaner. (b) Put logic in the backend
   — rejected: not reusable by workers; violates the framework-free shared pattern.
4. **Risks.** Accidental import of `irp_backend` / risk / ingestion into the CRUD core. Mitigation:
   import-direction test (forbid `irp_backend`, risk/portfolio/reporting, and `irp_shared.ingestion` in the
   CRUD core).
5. **Impacted requirements.** Architectural (ARCH-P-01/07); no functional REQ change.
6. **Impacted controls.** Maintainability/separation; supports CTRL-013 (lineage) reuse.
7. **ADR update required?** No (follows existing package conventions).
8. **Requirements update required?** No.

---

## OD-P1B-I — Manual `data_source` scope

1. **Decision.** Manually-created reference records bind to a **per-tenant `data_source` of
   `source_type='MANUAL'`** (registered once per tenant via the existing `register_data_source` admin
   utility). Each reference create records ONE origin edge `data_source(MANUAL) → <entity>` via
   `record_lineage` + `assert_has_lineage`, **in the same tenant context as the record being written**.
   API/CRUD tenant records use the **tenant's own MANUAL source** (context = source.tenant = edge.tenant =
   caller tenant → passes both the source `USING` and the `lineage_edge` `WITH CHECK`); **tenant-override
   rows** of a global taxonomy are written under tenant context and likewise use the **tenant's own MANUAL
   source**. **Global (SYSTEM_TENANT) reference rows** are seeded **under SYSTEM_TENANT context** with a
   **SYSTEM_TENANT MANUAL source** (context = source = edge tenant all SYSTEM → passes USING and the
   `lineage_edge` `WITH CHECK`). **`data_source` is therefore NOT made hybrid** — the closed hybrid set stays
   exactly {currency, calendar, rating_scale} (OD-P1B-C). (Rejected earlier idea: "add `data_source` to the
   hybrid read extension" — unsound: `record_lineage` stamps `edge.tenant_id` from the **resolved source's**
   tenant_id, and the `lineage_edge` `WITH CHECK` is single-tenant, so a tenant-context write citing a
   SYSTEM_TENANT source would fail the WITH CHECK regardless of read visibility. Rooting each row's lineage in
   its **own** tenant context avoids this entirely.)
2. **Rationale.** `data_source` is tenant-scoped `UNIQUE(tenant_id, code)`; `source_type` is a controlled-
   vocab string (existing values prove value-level extension needs no schema change). Per-tenant MANUAL keeps
   provenance honest and tenant-isolated; the SYSTEM_TENANT global case is handled by **rooting the lineage in
   SYSTEM_TENANT context** (not by making `data_source` hybrid — the `lineage_edge` `WITH CHECK` is
   single-tenant, so context, source, and edge must share one tenant).
3. **Alternatives considered.** (a) A single global MANUAL source referenced from tenant context — rejected:
   `record_lineage` stamps the edge from the source's tenant and the single-tenant `WITH CHECK` rejects it
   (visibility alone is insufficient). (b) No lineage on manual records — rejected: violates "every governed
   output has provenance" (CTRL-013).
4. **Risks.** Forgetting to seed the tenant MANUAL source → create fails closed. Mitigation: tenant
   onboarding seeds a MANUAL source; P1B-1 test asserts manual create produces an origin edge.
5. **Impacted requirements.** BX-LIN; all REQ-SMR (lineage-rooted writes).
6. **Impacted controls.** CTRL-006, CTRL-013.
7. **ADR update required?** No.
8. **Requirements update required?** No (note in P1B-1 that `source_type='MANUAL'` is added by value).

---

## OD-P1B-J — Currency / rating_scale requirements coverage

1. **Decision.** **Mint a new `REQ-SMR-005` — "Standard reference vocabularies (currency, rating scale)"**
   with explicit acceptance criteria (ISO-4217 currency reference; rating-scale/grade taxonomy; hybrid
   global+override; effective-dated EV) and a new RTM row. **Re-partition CAP-2 sub-capability 2.5**
   ("Calendars/currencies/rating scales"): **calendar stays with REQ-SMR-004**; **currency + rating_scale move
   to REQ-SMR-005**.
2. **Rationale.** currency (ENT-005) and rating_scale (ENT-007) **currently trace to REQ-SMR-004 only
   implicitly via sub-cap 2.5** (REQ-SMR-004 maps to CAP "2.4/2.5" in both the backbone and the RTM) — but
   they are **absent from REQ-SMR-004's entity column** (`corporate_action, calendar (EV)`) **and its
   acceptance criteria**. So they are *under-specified, not untraced*. A dedicated REQ-SMR-005 gives them
   first-class acceptance + RTM traceability and **de-overloads** REQ-SMR-004 (which otherwise spans 2.4
   corporate_action + 2.5 calendar/currency/rating_scale across two slices).
3. **Alternatives considered.** (a) Extend REQ-SMR-004's entity column to add currency/rating_scale — rejected:
   leaves one requirement spanning four entities and two slices, muddying acceptance. (b) Build without a
   dedicated requirement — rejected: leaves currency/rating_scale without acceptance criteria.
4. **Risks.** A new requirement row + the CAP re-partition must be ratified (R-02 + R-05) before P1B-1.
   Mitigation: REQ-SMR-005 + the re-partition drafted in P1B-0; ratified before P1B-1 build.
5. **Impacted requirements.** **New REQ-SMR-005** (currency, rating_scale); **REQ-SMR-004 re-scoped to
   corporate_action + calendar** (CAP column "2.4/2.5" → "2.4 + calendar portion of 2.5").
   **ENT-007 annotation (parallel to OD-P1B-A):** temporal standard §2A classifies ENT-007 wholly **FR** —
   record that ENT-007 splits into an **EV rating_scale/grade taxonomy (P1B)** and an **FR rating-assignment
   entity (deferred to the credit phase)**; annotate §2A / canonical ENT-007 accordingly (a documentation
   refinement, **not** an AD-005 amendment).
6. **Impacted controls.** CTRL-004 (data-dictionary), CTRL-017.
7. **ADR update required?** No.
8. **Requirements update required?** **Yes** — mint REQ-SMR-005 + **edit REQ-SMR-004's CAP mapping
   ("2.4/2.5" → "2.4 + calendar-of-2.5")** in `requirements_backbone.md` + `requirements_traceability_matrix.md`
   (R-02 + R-05); annotate temporal standard §2A / canonical ENT-007 for the EV/FR split. Executed at P1B-1.

---

## Decision summary & required baseline changes

| OD | Decision (one line) | ADR change | Requirements change | Audit/Entitlement change |
|---|---|---|---|---|
| A | instrument split: identity=EV, terms=FR | **canonical annotation** (ENT-001 → instrument + instrument_terms) | annotate REQ-SMR-001 | — |
| B | corporate_action = EV | none | annotate REQ-SMR-004 calendar partial (roll math deferred) | — |
| C | hybrid via SYSTEM_TENANT + asymmetric RLS (set = {currency, calendar, rating_scale}) | **AD-013-R1** | none | — |
| D | legal_entity core (impl-only, no ENT id) + issuer/counterparty role tables | canonical annotation | none | — |
| E | new REFERENCE.* audit codes (EVT-140 block); reconcile vs reserved DATA.CORRECTION/TR-08 | none | none | **taxonomy add (R-07)** |
| F | add currency/rating_scale/legal_entity + `.view` perms | none | none | **catalog add (R-07)** |
| G | deterministic-or-ambiguity identifier resolution | none | annotate REQ-SMR-003 (partial) | — |
| H | `irp_shared.reference`, one-way deps | none | none | — |
| I | per-tenant MANUAL data_source; lineage rooted in each row's own context (SYSTEM for global) | none | none | — |
| J | mint REQ-SMR-005 (currency, rating_scale); re-partition CAP 2.5; annotate ENT-007 EV/FR | none | **new REQ-SMR-005 + REQ-SMR-004 CAP edit + §2A ENT-007 note** | — |

All baseline changes are executed **inside the relevant P1B build slice** (taxonomy/entitlement in P1B-1;
canonical annotations in the slice that builds the entity — instrument/ENT-001 in P1B-3, legal_entity in
P1B-2; the AD-013-R1 ADR + REQ-SMR-005 + CAP re-partition ratified in P1B-0 closure), never as a side effect.

**Remaining deferred decisions (sound; do not gate P1B-1):** OD-012 identifier precedence → P1C (REQ-SMR-003
partial); whether FR `instrument_terms` restatements flow through `manual_override`/BR-7 → decided in OD-E
before P1B-3 builds the CORRECTION path (capture TR-08 reason + superseded link now, enforcement P6/P7);
whether P1B-1 actually seeds global SYSTEM_TENANT taxonomies (if yes, the SYSTEM-context lineage rooting +
hybrid-read test ship in P1B-1); P1B-5 ingestion mapping → defer unless a concrete bulk-load need exists;
`legal_entity` gets no canonical ENT id (implementation-only shared core).
