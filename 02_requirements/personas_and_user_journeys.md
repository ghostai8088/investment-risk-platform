# Personas & User Journeys

## Document Control

| Field | Value |
|---|---|
| Document ID | REQ-PERSONA-001 |
| Version | 0.2 (concrete journey lines J-CRO and J-PM added at the 2026-09-17 product re-baseline) |
| Status | Accepted as baseline |
| Owner | R-01 Product Manager AI |
| Approver | H-07 Product Owner |
| Created | 2026-06-18 |
| Last Reviewed | 2026-09-17 (the first review since 2026-06-18; no wave gate had cited this document in between — see `product_rebaseline_2026-09-17.md` Part 1.3) |
| Related Documents | requirements_backbone.md, requirements_traceability_matrix.md, product_rebaseline_2026-09-17.md, journey_walk_ledger.jsonl, ../01_product_strategy/regulatory_product_scope.md, ../00_ai_operating_model/reconciled_agent_role_registry.md |
| Supported Build Rules | BR-7, BR-11, BR-15, BR-17 |

## 1. Purpose

Define the personas referenced by the RTM and the end-to-end user journeys that the requirements must support. Persona codes
(`P-*`) alias the `PERSONA-0x` IDs in [regulatory_product_scope.md](../01_product_strategy/regulatory_product_scope.md) and the
human accountability roles (`H-*`) in the
[reconciled agent & role registry](../00_ai_operating_model/reconciled_agent_role_registry.md). Personas drive entitlement
design and segregation of duties (1L/2L/3L).

## 2. Personas

| Code | Persona | Alias | LoD | Primary goals | Key capabilities |
|---|---|---|---|---|---|
| P-CRO | Chief Risk Officer / Head of Risk | PERSONA-01 / H-01 | 2L (head) | Risk appetite, board oversight, sign-off limit framework | CAP-10, CAP-16, CAP-9 |
| P-RM | Risk Manager | PERSONA-02 / H-01 | 2L | Oversee risk, review breaches, own limits & 2L review | CAP-5–11, CAP-16 |
| P-RA | Risk Analyst | PERSONA-02 / H-09 | 1L | Run analytics, investigate drivers, prepare packages | CAP-5–9, CAP-1 |
| P-PM | Portfolio Manager | PERSONA-03 / H-09 | 1L | See exposure/risk in scope, respond to breaches | CAP-1, CAP-5–8, CAP-11 |
| P-MV | Model Validator (independent) | PERSONA-04 / H-02 | 2L | Validate models, effective challenge, approve tiers | CAP-12 |
| P-DS | Data Steward | PERSONA-05 / H-04 | Platform | Data quality, reconciliation, overrides, reference data | CAP-2–4, CAP-13, CAP-14, CAP-18 |
| P-CO | Compliance Officer | PERSONA-06 / H-05 | 2L | Controls, MNPI/restricted lists, regulatory themes | CAP-15, CAP-17, CAP-4 |
| P-IA | Internal Auditor | PERSONA-07 / H-08 | 3L | Independent assurance, audit extracts (read-only) | CAP-15, CAP-14 |
| P-ADM | Platform Administrator | PERSONA-08 | Platform | Users, entitlements, configuration | CAP-17, CAP-18 |
| P-BRD | Board / Investment Committee | PERSONA-09 | — | Consume governed summary reporting | CAP-16 |
| P-OPS | Buyer / Operations (COO/CTO) | PERSONA-10 | — | Security, due-diligence, deployment fit | CAP-15, CAP-17 |

**System actor:** BAU AI agents (CAP-19) operate under defined tool tiers (registry §2); they assist these personas but never
hold the approver side of any SoD pair (BR-15) and are always logged (BR-16).

## 3. Segregation-of-Duties anchors (drive entitlement design)

| SoD pair | Maker | Checker | Requirement |
|---|---|---|---|
| Override | P-DS / P-RA | P-RM / P-DS (different person) | REQ-DQR-003 |
| Breach closure | P-PM (1L) | P-RM (2L) | REQ-BRC-002 |
| Model approval | P-RA (developer) | P-MV / H-02 | REQ-MDG-003 |
| Limit change | P-RM | P-CRO / second 2L | REQ-LIM-001 |
| Entitlement change | requester | P-ADM (different) | REQ-ADM-002 |
| Board report publish | P-RM (drafts) | P-CRO | REQ-RPT-002 |

## 4. User Journeys

Each journey lists the steps and the requirements/capabilities exercised. Journeys are the basis for per-phase user stories.

### UJ-1 — 1st Line daily risk review (P-RA, P-PM)
1. Authenticate (SSO; today dev shim) → entitled to specific portfolios (REQ-ADM-001/002, BX-ENT).
2. View positions & exposures as-of (REQ-PPM-002/004).
3. Run/inspect market & credit risk results (REQ-MKT-001/002, REQ-CRD-001) — reproducible, lineage-bound.
4. See limit utilization and any breaches (REQ-LIM-002/003).
5. If breached, initiate 1L response (REQ-BRC-002). *All actions audited (BX-AUD).*

**J-PM — the concrete walk for steps 2 to 4, ratified by the owner 2026-09-17 (DP-RB2-3).** Each
line names what is on the screen and the decision it supports. A line is accepted only when a
roster member walks it on the deployed stack and records, in `journey_walk_ledger.jsonl`, the
decision the persona would take and the value that drove it (gate G5, `scripts/check_journey_walks.py`).
Every threshold and tolerance below is a server-side read, never a browser rule.

| Line | On the screen, and the decision it supports |
|---|---|
| J-PM-1 | Holdings with marks as-of, sortable, with the mark date; a mark is flagged stale when older than the asset class's tolerance (one business day for listed instruments, one hundred for private funds). Decision: which position needs a fresh mark. |
| J-PM-2 | The fund's exposures by factor family and by currency, and its utilisation of each limit that scopes it, as a number (observed over threshold). Decision: how much room is left. Depends on UTIL-1; before it lands this line is NOT WALKABLE by design. |
| J-PM-3 | Any open breach in scope, with the first-line response form on the same page. Decision: respond now or escalate. |
| J-PM-4 | The same headline numbers the CRO sees for this fund, walked by opening both screens. Decision: escalate if the two screens disagree on any value; the driving value is the pair compared. |

### UJ-2 — 2nd Line oversight & breach review (P-RM, P-CRO)
1. Review portfolio/aggregate risk and scenario results (REQ-MKT-004, REQ-SCN-003).
2. Define/approve limits via maker-checker (REQ-LIM-001, SoD).
3. Review 1L breach responses independently; approve/decline closure with evidence (REQ-BRC-002/003).
4. Approve board report for publication (REQ-RPT-002).

**J-CRO — "Monday morning", the concrete walk for step 1, ratified by the owner 2026-09-17
(DP-RB2-3).** P-CRO and P-RM share this screen. The CRO signs in and sees the firm's funds, then
one fund. Same acceptance mechanics as J-PM above.

| Line | On the screen, and the decision it supports |
|---|---|
| J-CRO-1 | Funds ranked by headroom, tightest limit first, with the change since the last close beside each. Decision: which fund to open first. |
| J-CRO-2 | Headline row for the selected fund: total exposure in base currency; VaR and ES at the governed confidence and horizon with the as-of date; tracking error vs the fund's benchmark; each a governed value with provenance one click away. Decision: is today's risk inside appetite. |
| J-CRO-3 | Limit posture: limits in force, breached, and near threshold (utilisation at or above 80 percent), with the open breaches, their owners and response due dates. Decision: which breach to chase. Depends on UTIL-1; before it lands this line shows state words and is NOT WALKABLE by design. |
| J-CRO-4 | Exposure composition: by asset class, by currency, by sector, by factor family; public beside private on the same axis. Decision: where the concentration is. |
| J-CRO-5 | The private sleeve, plainly: for each private fund, reported (appraisal) volatility beside desmoothed volatility with the difference as a number; unfunded commitment and the next projected call. Decision: whether the private book's risk is understated, and by how much. |
| J-CRO-6 | Scenario P&L for the fund under the tenant's scenarios. Decision: which scenario hurts. |
| J-CRO-7 | Trend: the VaR series over the last quarter and rolling drawdown, as charts. Decision: is risk rising. |
| J-CRO-8 | Drill: click total exposure and see the hierarchy nodes and holdings that make it up, with the sum holding. Decision: which sleeve drives it. The VaR drill waits for the decomposition engine (Wave 21) and is not a Wave-20 line. |

### UJ-3 — Independent model validation (P-MV)
1. Open model inventory; select model/version (REQ-MDG-001).
2. Review methodology, assumptions, limitations, benchmark results (BX-DOC).
3. Record validation & effective challenge; cannot have authored the model (REQ-MDG-003, SOD-03).
4. Set approval/restricted-use status; Tier-1 requires H-02 sign-off (BR-15).

### UJ-4 — Data steward data-quality cycle (P-DS)
1. Ingest data via upload/adapter (REQ-INT-001/002) → DQ rules run (REQ-DQR-001).
2. Triage exceptions; reconcile across sources (REQ-DQR-002).
3. Apply a controlled override with justification + approval (REQ-DQR-003, BR-7).
4. Confirm lineage captured for corrected data (REQ-LIN-001).

### UJ-5 — Administration & entitlement management (P-ADM)
1. Create users; assign roles/permissions with tenant scope (REQ-ADM-002).
2. Entitlement changes are maker-checked and audited (BX-SOD).
3. Configure data classification / export controls incl. MNPI barriers (REQ-ADM-003).

### UJ-6 — Board reporting (P-RM → P-CRO → P-BRD)
1. Generate board risk report from approved metrics (REQ-RPT-002) — reproducible (BR-9).
2. P-CRO reviews & approves publication (SoD).
3. P-BRD consumes the governed report; data is entitlement-scoped.

### UJ-7 — Internal audit / due diligence (P-IA, P-OPS)
1. Query the audit trail for a period/entity (REQ-AUD-003) — entitled, read-only.
2. Verify chain integrity (REQ-AUD-002) and pull a signed extract.
3. Trace a specific result to source via lineage (REQ-LIN-002).

### UJ-8 — Private markets onboarding (P-DS, P-CO)
1. Ingest GP NAV / capital calls / commitments (REQ-PRV-001/002/003 via REQ-INT-003).
2. Flag stale valuations; record proxy mappings (REQ-PRV-003).
3. Restrict private company financials behind MNPI barriers (REQ-PRV-004, REQ-ADM-003).

## 5. Open Questions

See [RTM §5](requirements_traceability_matrix.md) (OQ-007 covers persona consolidation at small-team scale).

## 6. Dependencies

Persona-driven entitlement and SoD design depend on REQ-ADM-002 (SoD/maker-checker) and DEP-SSO (real identity); until SSO lands,
journeys use the dev header-shim principal (foundation placeholder).
