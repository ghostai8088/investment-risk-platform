# Foundational Architecture Decision Records

## Document Control

| Field | Value |
|---|---|
| Document ID | ARCH-ADR-FND-001 |
| Version | 1.0 (Ratified) |
| Status | Accepted — AD-003 … AD-010 ratified 2026-06-17 (Step 1C) |
| Owner | R-02 Chief Architect AI |
| Approver | H-06 Engineering Lead (H-03 CISO for AD-007/AD-009; H-02 for AD-006/AD-009 model aspects; H-04 for AD-005) |
| Created | 2026-06-17 |
| Last Reviewed | 2026-06-17 |
| Related Documents | architecture_baseline.md, architecture_decision_log.md, temporal_reproducibility_standard.md, numerical_quant_standards.md, entitlement_sod_model.md |
| Supported Build Rules | BR-6, BR-9, BR-10, BR-11, BR-12, BR-13, BR-17, BR-18, BR-19 |

> Ratified per Step 1C on 2026-06-17. Decisions below are **Accepted** and binding for implementation; revisit triggers remain.
> The index in [architecture_decision_log.md](../11_decision_log/architecture_decision_log.md) mirrors them.

---

### AD-003 — Technology Stack
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06
- **Context:** A quant-heavy risk platform needs a mature numerical/analytics ecosystem, a maintainable typed service layer, and
  a modern, accessible web UI.
- **Decision (accepted):**
  - **Backend stack:** Python 3.12+, FastAPI for services, Pydantic for typed contracts, SQLAlchemy for persistence; analytics
    on the numpy/pandas/scipy ecosystem; decimal-safe numerics (no binary float for money — QS standards).
  - **Calculation-engine language:** Python (same ecosystem), isolated behind a job/run interface (AD-006); performance-critical
    paths vectorized and, if needed later, offloaded to compiled kernels without changing the interface.
  - **Frontend stack:** TypeScript + React (SPA) with Vite tooling and a component library; WCAG 2.1 AA accessibility target; no
    calculation logic in the UI (ARCH-P-04).
  - **API style:** REST/JSON over HTTPS with typed schemas; entitlement checked at gateway and data layer.
- **Options considered:** (a) Python+TS [accepted]; (b) JVM services; (c) .NET; (d) polyglot with separate quant service.
- **Consequences:** Strong analytics fit; one language across services and engine; clear UI/service split.
- **Risks:** Python batch performance — mitigated by vectorization and isolating hot paths; revisit if NFR-05 unmet.
- **Revisit trigger:** Performance NFR-05 not met, or enterprise buyer stack mandate.

### AD-004 — Datastore Strategy
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06 (H-04 consulted)
- **Context:** Need a transactional system-of-record supporting bitemporal patterns, an efficient store for time-series/market
  data, a document store for GP reports/appraisals, and a segregated immutable audit store.
- **Decision (accepted):**
  - **System-of-record:** PostgreSQL (transactional, supports the bitemporal model; row-level security for tenant isolation).
  - **Time-series/market data:** TimescaleDB (PostgreSQL extension) initially, behind a market-data repository interface so a
    dedicated columnar/time-series store can replace it later without domain changes.
  - **Documents:** S3-compatible object storage for GP reports, appraisals, and large artifacts.
  - **Audit store:** Segregated, append-only PostgreSQL schema/instance, not writable by application administrators (SoD,
    AUD-01), with application-level hash-chaining (AD per audit taxonomy) and a path to WORM (later-hardening).
- **Options considered:** (a) single store; (b) Postgres SoR + Timescale + object + segregated audit [accepted]; (c) doc-first.
- **Consequences:** As-of querying, reproducibility, and audit segregation supported with one DB engine family initially.
- **Risks:** Timescale scale ceiling for very large market-data volumes — mitigated by the repository abstraction.
- **Revisit trigger:** Market-data volume/perf exceeds Timescale; managed-service constraints per AD-010.

### AD-005 — Temporal / Data-Versioning Model
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-04
- **Context:** Reproducibility (BR-6, BR-9) requires distinguishing when a fact is true from when it was known, with immutable
  inputs and results, at proportionate cost.
- **Decision (accepted):** **Selective bitemporality.** Risk-driving inputs use full bitemporal (valid + system time); outputs,
  events, and audit are immutable append-only; reference/config use effective-dated versioning. Entity classification and
  rationale are defined in [temporal_reproducibility_standard.md](../04_data_model/temporal_reproducibility_standard.md) §2A.
- **Options considered:** (a) bitemporal everywhere; (b) **selective bitemporality** [accepted]; (c) valid-time only; (d)
  event-sourcing everywhere.
- **Consequences:** Full as-of reproduction where it matters; lower storage/complexity elsewhere.
- **Risks:** Misclassifying an entity — mitigated by the explicit classification table and review on new entities.
- **Revisit trigger:** A regulatory regime requires stricter immutability/WORM than chosen.

### AD-006 — Calculation-Engine Pattern
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06 (H-02 for model aspects)
- **Context:** Risk results must be deterministic, reproducible, versioned, and separated from UI.
- **Decision (accepted):** Job-based engine producing immutable `CalculationRun` records binding code/model version, input
  dataset snapshot, assumption-set version, parameters, RNG seed (where stochastic), initiator, and timestamps; pluggable
  per-context methodology modules registered in the Model Registry (FW-MDL); no calc logic in the UI; determinism per QS
  standards.
- **Options considered:** (a) run-tracked pluggable engine [accepted]; (b) inline per-request calc; (c) third-party engine.
- **Consequences:** Reproducibility and model governance enabled by construction.
- **Risks:** Upfront engineering before first results — accepted as non-negotiable for an enterprise risk product.
- **Revisit trigger:** Need to integrate a vendor analytics engine.

### AD-007 — Authentication / SSO
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-03 CISO
- **Realized (SSO-1, 2026-07-21):** the API is an **OAuth2 resource server** — it verifies an
  `Authorization: Bearer` JWT against the issuer JWKS (signature, `iss`, `aud`, `exp`, RS256-only
  allow-list) and resolves the `sub` claim to an active `app_user` in the token's tenant
  (`apps/backend/src/irp_backend/auth.py`, `deps.py`). `auth_mode` defaults to `oidc` (fail-closed);
  the legacy `dev_header` shim is permitted only when `app_env == "local"` (startup guard). MFA is
  enforced IdP-side, with an optional `acr`/`amr` assertion check. **OD-048 CLOSED**: the local-dev
  OIDC provider is **Keycloak** (`infra/keycloak/`). The SPA auth-code+PKCE login flow lands with
  FE-3; SAML remains "supported" but unbuilt.
- **Context:** Enterprise buyers require federated identity, MFA, and least privilege.
- **Decision (accepted):** **OIDC as the primary protocol** (SAML supported) federating to the enterprise IdP; **MFA enforced**;
  short-lived signed tokens with rotation; service accounts and AI agents authenticated and scoped through the entitlement
  framework (FW-ENT). Local dev uses a containerized OIDC provider. No local password store for enterprise deployments.
- **Options considered:** (a) OIDC/SAML federation [accepted]; (b) built-in identity; (c) API-keys only.
- **Consequences:** Meets buyer due diligence; centralizes deprovisioning.
- **Risks:** IdP integration variance — mitigated by standards adherence.
- **Revisit trigger:** Buyer mandates a specific IdP or passwordless standard.

### AD-008 — Multi-Tenancy Model
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06 (H-03 consulted)
- **Context:** Multiple asset-manager tenants; data isolation is a primary buyer concern.
- **Decision (accepted):** **Strong logical isolation** — `tenant_id` on every tenant-scoped entity, enforced by PostgreSQL
  **row-level security** plus application entitlement scope (defense in depth, BR-17) — with a **single-tenant deployment
  option** for buyers requiring physical isolation. Tenancy is a first-class scope in FW-ENT.
- **Options considered:** (a) logical isolation + single-tenant option [accepted]; (b) pooled only; (c) physical only.
- **Consequences:** Sales flexibility with strong isolation; tenant scope mandatory on every query.
- **Risks:** Logical isolation defects — mitigated by deny-by-default, RLS, and tenant-scope tests.
- **Revisit trigger:** Regulatory data-residency requirements.

### AD-009 — AI-Usage Boundary
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-05 (H-03, H-02 consulted)
- **Context:** AI agents assist build and operations and may be embedded in the product; authority and data access must be
  bounded.
- **Decision (accepted):** AI may draft, test, review, summarize, and recommend but may not give final approval for the change
  types in BR-15; all material agent actions are logged (BR-16); agents operate under tool-access tiers (registry §2) and never
  hold Tier-5 autonomously; embedded agents must cite governed sources and may not invent numbers; client data is not used for
  model training. For embedded/product AI features, default to current-generation Claude models (e.g., Opus 4.8 / Sonnet 4.6 /
  Haiku 4.5) selected per latency/cost/quality, with provider data-handling terms confirmed.
- **Options considered:** (a) bounded assistive AI with human gates [accepted]; (b) autonomous AI approvals; (c) no AI in product.
- **Consequences:** Preserves accountability and auditability; aligns with model governance independence.
- **Risks:** Prompt injection / data exfiltration for embedded agents — mitigated by entitlement scoping, input/output controls,
  and logging (see threat model THR-13…16).
- **Revisit trigger:** Regulatory guidance on AI in risk/compliance; provider/model changes.

### AD-010 — Deployment Model
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06 (H-10 consulted)
- **Context:** Need a deployment target supporting enterprise security, DR, and the datastore strategy.
- **Decision (accepted):** **Cloud-native, containerized (Docker)** services orchestrated by **Kubernetes** in staging/prod;
  **infrastructure-as-code (Terraform)**; environment parity across dev/test/staging/prod; designed to also support
  single-tenant/on-prem delivery; DR per NFR-03. No manual production changes (IaC + change approval, BR-18 context).
- **Options considered:** (a) cloud-native + on-prem option [accepted]; (b) cloud-only; (c) on-prem-only.
- **Consequences:** Broad enterprise addressability; reproducible environments.
- **Risks:** Multi-target maintenance — mitigated by containerization and IaC.
- **Revisit trigger:** First enterprise buyer's deployment constraints.

### AD-011 — Test / Runtime Database Strategy (added Step 1E)
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06
- **Context:** The foundation needs fast, hermetic unit tests and also real PostgreSQL-specific enforcement (row-level security,
  append-only triggers) that SQLite cannot express.
- **Decision (accepted):** The ORM is engine-agnostic. **Unit tests run on in-memory SQLite**; **runtime and Alembic migrations
  target PostgreSQL**. PostgreSQL-only enforcement is validated by a dedicated CI `migration` job that applies and reverts the
  foundation migration against a real Postgres service.
- **Options considered:** (a) SQLite tests + PG migration job [accepted]; (b) all tests on Postgres (testcontainers); (c)
  SQLite only.
- **Consequences:** Sub-second unit tests with no external dependency, plus genuine validation of RLS/triggers.
- **Risks:** Model/migration drift and SQLite/PG behavioral differences — mitigated by the migration job now and an autogenerate
  drift check later (OD-052).
- **Revisit trigger:** Drift or behavioral gaps cause an escaped defect.

### AD-012 — Audit Hash-Chain Scope (added Step 1E)
- **Status:** Accepted | **Date:** 2026-06-17 | **Approver:** H-06 (H-03 consulted)
- **Context:** The append-only audit trail needs tamper-evidence (BR-18) and tenant isolation.
- **Decision (accepted):** **One hash chain per tenant** (`chain_id = tenant_id`); each event stores
  `previous_event_hash`, `event_payload_hash`, and `event_hash = SHA-256(previous_event_hash + event_payload_hash)`.
  Append-only is enforced in the app (ORM guards) and in the database (PostgreSQL trigger).
- **Options considered:** (a) per-tenant chain [accepted]; (b) single global chain; (c) per-entity chains.
- **Consequences:** Audit trails are tenant-isolated and independently verifiable at bounded cost (verify per tenant).
- **Risks:** Per-chain write concurrency at high volume — to be addressed with advisory-lock/serializable writes (OD-051).
- **Revisit trigger:** Audit write throughput requires chain sharding.

## Resolved Open Decisions

AD-003 … AD-010 are ratified, closing prior OD-004 … OD-011. Residual, non-blocking items now tracked elsewhere:

| ID | Residual (non-blocking) |
|---|---|
| OD-046 | Confirm dedicated columnar/time-series store trigger and target (behind AD-004 market-data interface). |
| OD-047 | Confirm managed vs self-hosted Kubernetes and cloud provider(s) for first deployment (AD-010). |
| OD-048 | ~~Confirm local-dev OIDC provider choice (AD-007).~~ **CLOSED (SSO-1, 2026-07-21): Keycloak** (`infra/keycloak/`). |

## Dependencies

- architecture_baseline.md frameworks bind to these decisions.
- temporal_reproducibility_standard.md (AD-005), numerical_quant_standards.md (AD-006), entitlement_sod_model.md (AD-007/008).
