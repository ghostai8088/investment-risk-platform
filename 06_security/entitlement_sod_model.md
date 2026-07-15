# Entitlement & Segregation-of-Duties Model

## Document Control

| Field | Value |
|---|---|
| Document ID | SEC-ENTITLEMENT-001 |
| Version | 0.1 (Draft for Review) |
| Status | Draft |
| Owner | R-07 Security Architect AI |
| Approver | H-03 CISO (H-05 Head of Compliance for MNPI sections) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | reconciled_agent_role_registry.md, audit_event_taxonomy.md, canonical_data_model_standard.md, model_governance_independence_policy.md, foundational_adrs.md (AD-007, AD-008) |
| Supported Build Rules | BR-7, BR-10, BR-11, BR-15, BR-16 |

## 1. Purpose

Define the entitlement (RBAC + ABAC) model, the segregation-of-duties matrix, maker-checker controls, data classification
(including MNPI handling), and export controls. This makes "no module may bypass the entitlement model" (BR-11) and the
human-approval gates (BR-15) enforceable.

## 2. Principles (ENT-P)

| ID | Principle |
|---|---|
| ENT-P-01 | **Deny by default**; access is granted explicitly and is least-privilege. |
| ENT-P-02 | Entitlement checks occur at the API/gateway and again at the data-access layer (defense in depth). |
| ENT-P-03 | Subjects include humans, service accounts, and **AI agents** — all entitled and tiered (registry §2). |
| ENT-P-04 | Every entitlement change is maker-checked and audited (`ENTITLEMENT.*`). |
| ENT-P-05 | Secrets are externalized and never in source (BR-10); access to secrets is Tier-5, human-initiated. |
| ENT-P-06 | Tenancy (`tenant_id`) and portfolio scope are mandatory attributes on every entitled query (AD-008). |

## 3. Model Components

- **Permission (`PERM-*`):** an action on a resource type (e.g., `PERM-OVERRIDE-CREATE` on governed values).
- **Role (`ROLE-*`):** a named bundle of permissions aligned to a business function.
- **Scope (`SCOPE-*`):** ABAC attributes constraining a grant (tenant, portfolio/fund/strategy, asset class, data class).
- **Grant (`entitlement_grant`):** binds subject → role → scope, with validity dates and approver.

## 4. Business Roles (initial)

| Role ID | Role | Line | Indicative permissions |
|---|---|---|---|
| ROLE-PM | Portfolio Manager | 1L | View positions/risk in scope; request scenarios; respond to breaches |
| ROLE-RA | Risk Analyst | 1L | Run calcs, define scenarios (draft), view risk in scope; **register models/versions** (`model.inventory.register`, P1A-2 — 1L developer/owner, the maker side of the future SOD-03; the 2L validator deliberately does not hold register, MG-04) |
| ROLE-RM | Risk Manager | 2L | Review breaches, approve 2L steps, define/approve limits |
| ROLE-MV | Model Validator | 2L (independent) | View models/methodologies, record validation; cannot author methodology |
| ROLE-DS | Data Steward | — | Manage DQ exceptions, approve overrides within remit; **register/manage data sources** (`lineage.source.manage`, P1A-1); **manage data-quality rules** (`dq.rule.manage`, P1A-3 — held by P-DS + platform_admin only, the maker side of the future REQ-DQR-003 override SoD; read roles hold only `dq.result.view`) |
| ROLE-CO | Compliance Officer | 2L | MNPI/restricted-list administration, compliance positions |
| ROLE-ADM | Administrator | — | User/role admin; **cannot** approve own entitlement requests or edit audit |
| ROLE-AUD | Auditor / Internal Audit | 3L | Read-only across controls and audit; no operational actions |
| ROLE-RC | Report Consumer | — | View/export approved reports in scope |
| ROLE-SVC | Service Account | — | Scoped machine access (integration jobs) |
| ROLE-AGENT | AI Agent Principal | — | Tiered (registry §2); cannot hold approval permissions reserved to humans (BR-15) |

## 5. Permission Taxonomy (resource × action)

Resource types map to canonical entities/contexts; actions include: `view`, `create`, `edit`, `approve`, `reject`,
`override`, `run_calc`, `define_limit`, `change_limit`, `close_breach`, `validate_model`, `approve_model`, `manage_entitlement`,
`export`, `deploy`, `admin`. Each (resource, action) is a `PERM-*` and is checked per ENT-P-02.

### 5A. Reference-data permissions (P1B Security Master & Reference Data — ratified P1B-0/OD-P1B-F)

Required `reference.<entity>.<verb>` permissions with **view/edit separation** (a viewer cannot mutate). These are
governance-level definitions; the entitlement bootstrap **code** is updated in the relevant P1B build slice (not here),
deny-by-default, least-privilege (data_steward edit; broader view), with **no role-template change beyond additive grants**.

| Entity | Permissions | Status in catalog (`bootstrap.py`) |
|---|---|---|
| currency | `reference.currency.view`, `reference.currency.edit` | **IMPLEMENTED (P1B-1)** — additive catalog entries + grants |
| calendar | `reference.calendar.view`, `reference.calendar.edit` | **IMPLEMENTED (P1B-1)** — `.view` added (`.edit` pre-existed) |
| rating_scale | `reference.rating_scale.view`, `reference.rating_scale.edit` | **IMPLEMENTED (P1B-1)** — additive catalog entries + grants |
| legal_entity | `reference.legal_entity.view`, `reference.legal_entity.edit` | **IMPLEMENTED (P1B-2)** — additive; `.view` granted to EXACTLY the `issuer`/`counterparty.view` recipient set (data_steward/risk_analyst_1l/risk_manager_2l + platform_admin — **excludes `auditor_3l`**, proprietary-identity SoD; parity test guards drift); `.edit` → data_steward |
| issuer | `reference.issuer.view`, `reference.issuer.edit` | exists |
| counterparty | `reference.counterparty.view`, `reference.counterparty.edit` | exists |
| instrument | `reference.instrument.view`, `reference.instrument.edit` | **IMPLEMENTED (P1B-3)** — `.view` → data_steward/risk_analyst_1l/risk_manager_2l (+ platform_admin), `.edit` → data_steward; **excludes `auditor_3l`** (proprietary security-master SoD); covers `instrument_terms` (terms writes require `.edit`) |
| identifier_xref | `reference.identifier.view`, `reference.identifier.edit`, `reference.identifier.resolve` (read/lookup) | **IMPLEMENTED (P1B-3)** — additive `.view`/`.edit` minted (`.view`/`.resolve` → read tier, `.edit` → data_steward; excludes `auditor_3l`); the pre-existing `.resolve` recipient set is **UNCHANGED** (data_steward/risk_analyst_1l — NOT widened to risk_manager_2l); parity test pins the sets |
| corporate_action | `reference.corporate_action.view`, `reference.corporate_action.edit` | **IMPLEMENTED (P1B-4)** — `.edit` already existed (data_steward); additive `.view` minted → data_steward/risk_analyst_1l/risk_manager_2l (== the `reference.instrument.view` set); **excludes `auditor_3l`** (proprietary security-master SoD); parity test pins the sets |

**Reserved (not minted now):** `reference.rating.*` — held for the future **FR rating-assignment** domain (distinct from the
EV `rating_scale` taxonomy), so the verb namespace does not collide when rating assignments land in a later phase.

**P1B-1 grants (implemented, least-privilege, additive only — no role-template restructure):** the five new permissions
were appended to `irp_shared/entitlement/bootstrap.py` and seeded by `0002_entitlement_seed` on a fresh `alembic upgrade
head` (the established P1A-1/2/3 catalog precedent — no forward migration). `.edit` (`reference.currency.edit`,
`reference.rating_scale.edit`) → `data_steward` (+ `platform_admin` via `ALL_CODES`) only; `.view`
(`reference.currency.view`, `reference.rating_scale.view`, `reference.calendar.view`) → `data_steward`, `risk_analyst_1l`,
`risk_manager_2l`, `auditor_3l` (+ `platform_admin`). A read-tier role cannot mutate; `reference.rating.*` is absent from
the catalog. Asserted by `test_reference_data_permissions_are_additive_and_least_privilege`.

### 5B. Domain permissions — portfolio (P1C Portfolio & Position Management — ratified P1C-0, 2026-06-23)

Portfolio is **domain** data (CAP-1/BC-01), not reference data, so it uses plain **`portfolio.<verb>`** codes (NOT
`reference.portfolio.*`). The catalog codes `portfolio.view` / `portfolio.edit` were seeded as placeholders; **P1C-1
wired them (IMPLEMENTED).**

| Entity | Permissions | Grants (IMPLEMENTED P1C-1) |
|---|---|---|
| portfolio | `portfolio.view`, `portfolio.edit` | `portfolio.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`** (+ `platform_admin` via `ALL_CODES`). `portfolio.edit` is **maker/admin only** — **`data_steward`** + `platform_admin`. P1C-1 additively granted the **`data_steward`** maker **BOTH `portfolio.view` + `portfolio.edit`** (so the maker reads its own writes; it previously held neither). **`auditor_3l` excluded** (scope SoD). Parity test (`test_portfolio_permissions_grants_as_ratified`) pins the sets. |
| transaction | `transaction.view`, `transaction.record` | **IMPLEMENTED (P1C-2).** Newly minted (additive). `.record` is the append-only governed-write verb (a transaction is *recorded*, never *edited* — no `.edit`). `transaction.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`** (+ `platform_admin`). `transaction.record` is **maker/recorder/admin only** — **`data_steward`** + `platform_admin` (the steward is the maker/recorder, OD-P1C2-2). **`auditor_3l` excluded** (operational client data SoD). Parity test (`test_transaction_permissions_grants_as_ratified`) pins the sets. |
| position | `position.view`, `position.edit` | **IMPLEMENTED (P1C-3).** `position.view` **pre-existed** as a seeded catalog placeholder (held by `risk_analyst_1l`, `risk_manager_2l`, `platform_admin`); P1C-3 **wires** it by additively granting the **`data_steward`** maker (the three existing recipients unchanged). `position.edit` is the **one genuinely NEW code** minted here — the FR governed-write verb (a position is captured / superseded / corrected; `.edit` not `.record` because FR is close-out-updated, unlike the IA `transaction`). `position.edit` is **maker/admin only** — **`data_steward`** + `platform_admin` (the steward is the maker, OD-P1C3-2; maker-checker on corrections → P6+). **`auditor_3l` excluded** from both (operational client holdings SoD). Parity test (`test_position_permissions_grants_as_ratified`) pins the sets. |
| dataset_snapshot | `snapshot.view`, `snapshot.create` | **MINTED in P2-1 (`3629baa`; reserved at the P2-0 ratification, 2026-06-26).** Reproducibility-infrastructure permissions for ENT-049/050 (AD-014). `.create` is the **create-once run-artifact** verb (a snapshot is *created*/*initiated*, like `calculation_run` — distinct from the append-only `.record` business-event verb). **Grants (wired + parity-tested in P2-1):** `snapshot.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`** (+ `platform_admin`); `snapshot.create` is **maker/admin only** — **`data_steward`** + `platform_admin` (the steward is the maker). **`auditor_3l` excluded** from both (operational reproducibility-input SoD). Deny-by-default; pinned by `test_snapshot_permissions_grants_as_ratified`. |
| market data (fx_rate, price, curve, benchmark, factor) | `marketdata.view`, `marketdata.ingest` | **MINTED (P2-2 implementation, 2026-06-26).** REUSABLE across all market data (NOT per-entity `fx_rate.*`). `.ingest` is the **governed canonical-write** verb (capture/supersede/correct) — distinct from `data.upload` (raw staging). Grants: `marketdata.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`** (+ `platform_admin`); `marketdata.ingest` is **maker/admin only** — **`data_steward`** + `platform_admin`. **`auditor_3l` excluded** from both (vendor-license isolation is enforced by tenant-scoped RLS, not a role). Deny-by-default; pinned by `test_marketdata_permissions_grants_as_ratified`. **P3-2 REUSES both verbs for the net-new `factor` definition + `factor_return` series (ENT-025) — NO per-entity `factor.*` permission is minted** (`/factors` read = `marketdata.view`, write = `marketdata.ingest`); pinned by `test_factor.py` entitlement-parity + `test_factor_endpoint.py` (403 deny-by-default). Committed `402cb12`, CI #89 green. **PA-0 REUSES both verbs for the FR `proxy_mapping` captured private→public factor proxies (ENT-019) — NO per-entity `proxy.*`/`proxy_mapping.*` permission is minted** (`/proxy-mappings` read = `marketdata.view`, write = `marketdata.ingest`); pinned by `test_proxy_mapping.py` entitlement-parity + `test_proxy_mapping_endpoint.py` (403 deny-by-default). |
| valuation | `valuation.view`, `valuation.edit` | **IMPLEMENTED (P1C-4).** **BOTH codes are newly minted** (neither pre-existed in the catalog, unlike `position.view`) — the `transaction.view`/`transaction.record` mint-both precedent. `valuation.edit` is the FR governed-write verb (a mark is captured / superseded / corrected; `.edit` not `.record` because FR is close-out-updated). `valuation.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`** (+ `platform_admin`). `valuation.edit` is **maker/admin only** — **`data_steward`** + `platform_admin` (the steward is the maker, OD-P1C4-2; maker-checker on corrections → P6+). **`auditor_3l` excluded** from both (operational client valuations SoD). Parity test (`test_valuation_permissions_grants_as_ratified`) pins the sets. |
| exposure_aggregate | `exposure.view`, `exposure.aggregate.run` | **WIRED in P2-3 (`da178fc`; ratified 2026-06-26, OD-P2-3-I).** `exposure.aggregate.run` **pre-exists** as a seeded reserved-unwired catalog code (`bootstrap.py:68`); P2-3 **wires** it and **mints `exposure.view`**. `.aggregate.run` is the **run-the-governed-compute** verb (a derived number is *run*, not *edited*/*recorded* — append-only result). Grants: `exposure.aggregate.run` is **maker/admin only** — **`data_steward`** + **`risk_analyst_1l`** + `platform_admin` (the 1L analyst runs exposure; the steward is the data maker). `exposure.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`**, **`auditor_3l`** (+ `platform_admin`). **`auditor_3l` is INCLUDED in `exposure.view`** — the **first** domain permission to grant the 3L auditor a read: a governed derived **OUTPUT** is exactly what 3L oversight reviews (the `dq.result.view`/`lineage.view` oversight precedent), **distinct** from the operational client-data SoD that excludes the auditor from `portfolio`/`transaction`/`position`/`valuation`/`marketdata` (those are *inputs*, not governed outputs). Deny-by-default (ENT-P-01); pinned by `test_exposure_permissions_grants_as_ratified`. |
| sensitivity_result | `risk.view`, `risk.run` | **MINTED IN P3-1 (2026-06-30; OD-P3-1-I; `entitlement/bootstrap.py`).** BOTH codes NEW. `risk.run` is the **run-the-governed-compute** verb (a risk number is *run*, mirroring `exposure.aggregate.run`); `risk.view` reads results. Grants mirror the exposure family: `risk.run` **maker/admin only** — **`data_steward`** + **`risk_analyst_1l`** + `platform_admin`. `risk.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`**, **`auditor_3l`** (+ `platform_admin`). **`auditor_3l` is INCLUDED in `risk.view`** — a governed risk **OUTPUT** is 3L-oversight scope (the `exposure.view` precedent). Deny-by-default (ENT-P-01); a parity test (`test_risk_permissions_grants_as_ratified`) pins the sets. The sensitivity model registration uses the existing `model.inventory.register` (held by `risk_analyst_1l` + `platform_admin`) — no new code for it. **P3-3 REUSES both `risk.view`/`risk.run` verbatim for `factor_exposure_result`** (a factor exposure is exactly the governed risk OUTPUT class these codes were minted for — OD-P3-3-L): recipient sets UNCHANGED, `bootstrap.py` UNCHANGED, **NO `factor_exposure.*`/`factor.*` permission minted**; asserted by `test_risk_permissions_reused_no_new_codes`. The factor-exposure model registration likewise reuses `model.inventory.register`. **P3-4 REUSES both codes verbatim again for `covariance_result`** (ENT-051 — the same governed risk OUTPUT class; OD-P3-4-M): recipient sets UNCHANGED, `bootstrap.py` UNCHANGED, **NO `covariance.*`/`matrix.*` permission minted** (asserted by the P3-4 `test_risk_permissions_reused_no_new_codes`); the covariance model registration reuses `model.inventory.register`. **P3-5 REUSES both codes verbatim a third time for `var_result`** (ENT-027 — the same governed risk OUTPUT class; OD-P3-5-K): recipient sets UNCHANGED, `bootstrap.py` UNCHANGED, **NO `var.*`/VaR-specific permission minted** (asserted by the P3-5 `test_risk_permissions_reused_no_new_codes`); the VaR model registration reuses `model.inventory.register`. **P3-7 REUSES both codes a fourth time for `active_risk_result`** (ENT-027 third realization; OD-P3-7-A): recipient sets UNCHANGED, NO `active_risk.*` permission minted. **BT-1 REUSES both codes a fifth time for `var_backtest_result`** (ENT-055 — outcomes analysis of a governed risk OUTPUT is itself risk-family scope; OD-BT-1-B): recipient sets UNCHANGED, `bootstrap.py` UNCHANGED, **NO `backtest.*`/`var_backtest.*` permission minted** (asserted by the BT-1 `test_risk_permissions_reused_no_new_codes_bt1`); the var-backtest model registration likewise reuses `model.inventory.register`. |
| portfolio_return_result | `perf.view`, `perf.run` | **MINTED IN PM-1 (2026-07-09; OD-PM-1-A; `entitlement/bootstrap.py`).** BOTH codes NEW — a **PERFORMANCE** number is NOT a risk number, so the perf family gets its OWN verb pair rather than reusing `risk.run`/`risk.view` (the deliberate governed R-07 mint; the perf/risk peer-family boundary carried through to entitlements). `perf.run` is the **run-the-governed-compute** verb (a return is *run*, mirroring `risk.run`/`exposure.aggregate.run`); `perf.view` reads results. Grants mirror the risk family: `perf.run` **maker/admin only** — **`data_steward`** + **`risk_analyst_1l`** + `platform_admin`. `perf.view` → `risk_analyst_1l`, `risk_manager_2l`, **`data_steward`**, **`auditor_3l`** (+ `platform_admin`). **`auditor_3l` is INCLUDED in `perf.view`** — a governed performance **OUTPUT** is 3L-oversight scope (the `risk.view` precedent). Deny-by-default (ENT-P-01); a parity test (`test_perf_permissions_grants_as_ratified`) pins the sets. The portfolio-return model registration reuses the existing `model.inventory.register` (held by `risk_analyst_1l` + `platform_admin`) — no new code for it. **P3-8 REUSES both `perf.run`/`perf.view` verbatim for `benchmark_relative_result`** (ENT-054 — the ex-post benchmark-relative number is exactly the governed performance OUTPUT class these codes were minted for; OD-P3-8-B): recipient sets UNCHANGED, `bootstrap.py` UNCHANGED, **NO `benchmark_relative.*`/`benchmark.*` permission minted** (asserted by the P3-8 `test_perf_permissions_reused_no_new_codes`); the benchmark-relative model registration likewise reuses `model.inventory.register`. |

| model_validation (ENT-037) | `model.validate` | **MINTED IN VW-1 (2026-07-14; OD-VW-1-E; `entitlement/bootstrap.py`).** ONE new code — the first `model.*` mint since P0.5. `model.validate` is the **2L independent-validation write** (record an SR 11-7 validation on a `model_version`). Granted to **`risk_manager_2l` (ROLE-MV)** + `platform_admin` ONLY. **Deliberately WITHHELD from `risk_analyst_1l`** — the SOLE `model.inventory.register` holder (this is SOD-03 author≠validator, enforced at the ROLE level: no non-admin role holds both register and validate) — **and from `data_steward`** (holds no `model.*` code; a maker-tier role must not gain a 2L assurance verb). **Reads REUSE `model.inventory.view`** (a validation record is inventory metadata; the P3-8 no-new-view-code precedent). Deny-by-default (ENT-P-01); a parity test (`test_model_validate_grants_as_ratified`) pins the holder set AND asserts the no-role-holds-both-register-and-validate SoD invariant. |

**ABAC anchor-not-enforce (P1C-1, AD-017):** the portfolio hierarchy is the **portfolio-scope ANCHOR**. A future
`SCOPE-PORTFOLIO` grant (P6+) will reference `portfolio.id` with **subtree** semantics (OQ-014 closed = subtree: a grant on
a node reaches its descendants). P1C-1 provides the bounded **descendant** traversal so subtree membership is **computable**,
but **no scope is enforced** — `portfolio.view` gates by role + tenant only, so within a tenant any holder sees **all**
portfolios until the P6+ `entitlement_grant` scope payload lands. Acceptable in P1C because the data is synthetic (DC-1/DC-2).
**ENT-P-06** is thus **partially satisfied** in P1C-1: the **tenant** attribute is enforced (RLS); the **portfolio-scope**
attribute is **anchored, not enforced** (→ P6+).

## 6. Segregation-of-Duties Matrix (SOD)

Incompatible duties — the same subject must not hold both sides of a pair within the same scope.

| SOD ID | Duty A | Duty B (incompatible) | Rationale |
|---|---|---|---|
| SOD-01 | Create override | Approve that override | Maker-checker (BR-7) |
| SOD-02 | 1L breach response (own breach) | Approve breach closure | 1L/2L independence |
| SOD-03 | Author model methodology (ROLE author) | Validate/approve that model | Effective challenge (model gov) |
| SOD-04 | Request entitlement | Approve entitlement | Access-control integrity |
| SOD-05 | Define/change a limit | Approve that limit change | Limit-framework integrity |
| SOD-06 | Deploy to production | Approve the deployment | Change-management integrity |
| SOD-07 | Administer users/roles | Edit/delete audit records | Audit independence (also AUD-01) |
| SOD-08 | Generate a report | Approve/publish a board report | Reporting integrity |

AI agents are treated as the "maker" side only; the "approver/checker" side of every SOD pair is a human role (BR-15).

## 7. Maker-Checker / Four-Eyes Controls

Four-eyes is mandatory for: overrides (SOD-01), limit changes (SOD-05), model approval (SOD-03), entitlement changes (SOD-04),
report publication (SOD-08), production deployment (SOD-06). Each produces an approval record referenced by `approval_ref` in
the audit event (audit_event_taxonomy.md §5/§6).

## 8. Data Classification (DC)

| DC ID | Level | Examples | Handling |
|---|---|---|---|
| DC-1 | Public | Public market prices, benchmarks | Standard controls |
| DC-2 | Internal | Internal risk results, configs | Entitled access |
| DC-3 | Confidential | Client portfolios, positions | Strict entitlement + scope; masked in logs |
| DC-4 | Restricted / MNPI | Private company financials, GP-confidential data | Information barriers, need-to-know, restricted lists, no plaintext in audit, export-blocked by default |

Every field carries a DC tag (DM-N-07). Logs and audit `before/after` for DC-3/DC-4 use references/hashes, not plaintext.

## 9. MNPI & Information Barriers

| ID | Rule |
|---|---|
| MNPI-01 | Private company financials and GP-confidential data (DC-4) are gated by information barriers; access requires explicit need-to-know grant approved by ROLE-CO/H-05. |
| MNPI-02 | Restricted lists are maintained by Compliance; entitlement enforces barrier scopes. |
| MNPI-03 | Cross-barrier access attempts are denied and audited (`AUTH.DENIED`, `EXPORT.DENIED`). |

## 10. Export Controls

| ID | Rule |
|---|---|
| EXP-01 | Data export is a distinct permission, entitlement- and classification-checked; DC-4 export blocked by default. |
| EXP-02 | Every export emits `EXPORT.DATA` (or `EXPORT.DENIED`) with classification and scope. |
| EXP-03 | Bulk/admin export requires four-eyes approval. |

## 11. Open Decisions

| ID | Open Decision |
|---|---|
| OD-024 | Confirm IdP/SSO integration specifics and MFA policy (AD-007). |
| OD-025 | **CLOSED (P1C-0, 2026-06-23):** portfolio-scope granularity = **portfolio-level** (node + subtree), not position-level; recorded as the P1C-1 scope anchor (§5B), enforcement deferred to P6+ (AD-017). |
| OD-026 | Confirm whether team holds multiple human roles and how SoD pairs are preserved at small scale (links OD-001). |
| OD-027 | Confirm MNPI barrier model and restricted-list source of truth with H-05. |

## 12. Dependencies

- reconciled_agent_role_registry.md (subjects, tiers, human approvers).
- audit_event_taxonomy.md (`ENTITLEMENT.*`, `EXPORT.*`, `approval_ref`).
- canonical_data_model_standard.md (ENT-043/044, DC tags).
- model_governance_independence_policy.md (SOD-03 author/validator).
- AD-007 (auth), AD-008 (tenancy).
