# Phase P1 Decision Record

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-P1DR-001 |
| Version | 1.0 (Accepted) |
| Status | Accepted |
| Owner | H-07 Product Owner |
| Approver | H-07 Product Owner (with H-06 Engineering Lead; H-04 Data Owner for tenancy; H-03 CISO consulted) |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | p1_scoping_plan.md, ../02_requirements/requirements_traceability_matrix.md, ../02_requirements/definition_of_ready_done.md, build_sequence.md, ../11_decision_log/architecture_decision_log.md, ../04_data_model/canonical_data_model_standard.md, ../04_data_model/temporal_reproducibility_standard.md, ../06_security/entitlement_sod_model.md |
| Supported Build Rules | BR-1, BR-6, BR-7, BR-9, BR-11, BR-15, BR-17, BR-19 |

## 1. Purpose

Record the decisions that unblock Phase P1 (OQ-004, OQ-008, OQ-011, OQ-012, OQ-013). These are accepted and binding for P1
construction. Two of them are architecturally significant and are elevated to the decision log as **AD-013** and **AD-014**;
the remaining three are scoping/process decisions recorded here. No application code is produced or changed.

## 2. Decisions

### DR-P1-1 — OQ-012 Reference-data tenancy → **Accepted (elevated to AD-013)**
**Decision.** Adopt a **hybrid reference-data tenancy model**:
- **Global system reference data** may be used for standard taxonomies and codes: currencies, ISO country codes, standard
  calendars, standard rating scales, and common classifications.
- **Tenant-scoped investment reference data** is the **default** for: instruments, issuer mappings, counterparty mappings,
  identifier precedence, internal classifications, private asset identifiers, override values, and custom hierarchies.
- **Tenant override pattern** is permitted where a tenant needs to modify or extend global reference data.
- **No cross-tenant sharing** of proprietary, client-provided, or private asset reference data.

**Rationale.** Standard taxonomies are non-proprietary and benefit from a single curated source; investment reference data is
client-specific, competitively sensitive, and frequently MNPI-adjacent, so it must default to tenant isolation (BR-17 / AD-008).
The override pattern avoids duplicating global codes while letting tenants extend them.

**Implications for P1B.** `currency`, `calendar` (standard), `rating_scale` (standard), and country/classification codes are
**global** (no `tenant_id`, or a reserved system tenant). `instrument`, `issuer`, `counterparty`, `identifier_xref`,
internal classifications, and custom hierarchies are **tenant-scoped** (carry `tenant_id`, RLS-enforced). A global record may be
**overridden/extended** by a tenant-scoped override row that references the global record. Global reference tables are exempt
from tenant RLS but remain read-only to tenants (write-restricted to platform/admin). Entitlement: read of global reference is
broadly granted; tenant reference is deny-by-default + tenant-scoped.

**Status:** Accepted → see **AD-013**.

### DR-P1-2 — OQ-013 Exposure aggregation / dataset snapshot → **Accepted (principle elevated to AD-014)**
**Decision.** **Defer REQ-PPM-004 exposure aggregation to P2** unless a **minimal `dataset_snapshot` skeleton** is explicitly
delivered as part of P1A or P1C. P1C focuses on **portfolio hierarchy, positions, transactions, valuations, and as-of
reconstruction**. Derived exposure aggregation must **not** be implemented until reproducible input-snapshot mechanics are
available.

**Rationale.** A governed derived output must bind a reproducible input snapshot (BR-6, BR-9, temporal standard §5). FW-RUN's
reproducibility FKs are currently nullable placeholders, so aggregating exposures now would produce non-reproducible results —
a build-rule violation. Better to keep P1C to verifiable as-of stored data and add the snapshot mechanic deliberately.

**Implications.** P1C delivers PPM-001/002/003 (hierarchy, positions, transactions, valuations, as-of). PPM-004 is **moved to
P2** by default. It may re-enter P1C **only if** a minimal `dataset_snapshot` skeleton (pinning position + valuation record
versions at run time) is delivered first in P1A or P1C — that is a separate, explicit decision (remaining open question
**OQ-013a**, below). General rule (AD-014): **no governed derived output without a bound input snapshot.**

**Status:** Accepted → general principle recorded as **AD-014**; PPM-004 scope reflected in p1_scoping_plan.

### DR-P1-3 — OQ-004 SoD / maker-checker → **Accepted (scoping; no new ADR)**
**Decision.** **Defer the full maker-checker workflow and formal SoD approval workflow to P6.** P1 must **preserve
auditability** and include **schema/workflow hooks** that allow maker-checker controls to be added later **without redesign**.

**Rationale.** SoD's first real consumers (limits, breach closure, model approval) arrive in P6; building the full workflow now
would be speculative. But retrofitting approval semantics into schemas later is costly, so P1 entities that will eventually be
maker-checked (overrides, entitlement grants, limit/model changes) must reserve the fields/relationships now.

**Implications.** P1 records that will later be maker-checked include nullable, forward-compatible fields: `approval_status`,
`approval_ref`, `made_by`/`checked_by` (or an equivalent approvals association). No approval *enforcement* in P1 (deny-by-default
entitlement + full audit remain in force). This is consistent with ARCH-P-07 (extensible by configuration) and BX-SOD, so it
does **not** warrant a new ADR. Manual overrides (DQR-003) remain out of P1 (P7).

**Status:** Accepted (scoping/design constraint).

### DR-P1-4 — OQ-008 Test coverage threshold → **Accepted (process; no new ADR)**
**Decision.** **Enforce passing tests now.** Target **≥85% meaningful coverage for foundation modules** and **≥75% for early
domain modules**, but **defer hard global coverage gates until after P1A**. Future risk-calculation modules must have
**benchmark/golden tests**; line coverage alone is not sufficient (BR-1, CTRL-001/018).

**Rationale.** A hard CI coverage gate set before the domain shape is known produces noise; meaningful coverage + golden tests
for calculations is the real quality signal. Locking a global percentage is best done once P1A's patterns settle.

**Implications.** DoR/DoD item D2 stands (tests required + passing). Coverage targets are advisory in P0.5–P1A and become a CI
gate after P1A (revisits OQ-008 then). Calculation modules (P2+) require golden/benchmark tests as a hard DoD criterion.

**Status:** Accepted (process; revisit after P1A).

### DR-P1-5 — OQ-011 Minimum P0.5 hardening scope → **Accepted (scoping)**
**Decision.** **P0.5 includes only:** (1) frontend `package-lock.json` + switch CI from `npm install` to `npm ci`; (2) Alembic
autogenerate drift check; (3) audit-write concurrency control; (4) chain-verification CLI/job; (5) entitlement bootstrap seed.

**Explicitly excluded from P0.5:** real SSO; full SoD workflow; domain tables; Security Master; Reference Data; portfolio or
position entities; risk calculations; dashboards; reporting.

**Rationale.** P0.5 is hygiene only — it gives a byte-stable, reproducible, concurrency-safe CI baseline before any schema-adding
domain work. Anything beyond the five items belongs to P1A+ and would blur the phase boundary.

**Status:** Accepted (matches p1_scoping_plan §2).

## 3. Open questions closed by this record

| OQ | Resolution | Where reflected |
|---|---|---|
| OQ-004 | Defer maker-checker/SoD workflow to P6; P1 keeps audit + adds non-enforcing hooks | RTM §5, this record |
| OQ-008 | Tests enforced now; coverage targets advisory until post-P1A; golden tests for calcs | this record (DoD D2 unchanged) |
| OQ-011 | P0.5 = exactly the five hardening items; explicit exclusions | p1_scoping_plan §2, this record |
| OQ-012 | Hybrid reference-data tenancy (global vs tenant-scoped + override + no cross-tenant proprietary) | AD-013, p1_scoping_plan §4 |
| OQ-013 | Defer PPM-004 to P2 unless a minimal `dataset_snapshot` skeleton is delivered first | AD-014, p1_scoping_plan §5 |

## 4. Remaining open P1 questions

| ID | Question | Blocks | Owner |
|---|---|---|---|
| OQ-013a (new) | Will a minimal `dataset_snapshot` skeleton be delivered in P1A or P1C (which would re-enable PPM-004 in P1C), or stays deferred to P2? | P1C tail / P2 | H-06/H-07 |
| OQ-014 (new) | Portfolio ABAC scope granularity for entitlement — node vs subtree? | P1C | H-03/H-06 |
| OQ-015 (new) | Identifier-precedence rules for `identifier_xref` (vendor priority order) | P1B | H-04 |
| OQ-002 | Overall phase order vs commercial priority (private-markets pull-forward) | P2+ | H-07/H-01 |
| OQ-007 | Persona consolidation at small-team scale without breaking SoD pairs | P6 | H-07 |

None of the remaining questions block **P0.5** (they affect P1B/P1C/P6).

## 5. Dependencies

This record depends on the Step 2 backbone/RTM, the canonical data model (tenancy + temporal), the entitlement model, and the
reproducibility standard. It modifies no code and starts no implementation.
