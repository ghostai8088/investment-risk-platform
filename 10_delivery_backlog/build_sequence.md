# Build Sequence

## Document Control

| Field | Value |
|---|---|
| Document ID | BACKLOG-BUILDSEQ-001 |
| Version | 0.1 (Draft baseline) |
| Status | Accepted as the construction sequence |
| Owner | R-01 Product Manager AI (with R-02 Chief Architect AI) |
| Approver | H-07 Product Owner (H-06 Engineering Lead) |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | ../02_requirements/requirements_backbone.md, ../02_requirements/requirements_traceability_matrix.md, ../02_requirements/definition_of_ready_done.md, ../11_decision_log/architecture_decision_log.md |
| Supported Build Rules | BR-1 … BR-19 |

## 1. Principle

**Phasing is construction sequencing, not scope reduction (AD-002).** The full-scope architecture and requirements backbone are
fixed; phases order *when* each capability is built. Every phase delivers complete, governed, tested capability — not a thin
prototype. A phase opens only when its dependencies are met and its requirements are `Ready`
([DoR](../02_requirements/definition_of_ready_done.md)); it closes only when its requirements are `Done` and its controls are
`Implemented`.

## 2. Phase map

| Phase | Theme | Primary requirements | Key dependencies delivered | Status |
|---|---|---|---|---|
| **P0** | Foundation slice + hardening | REQ-AUD-002; DEP-CIH, DEP-FELOCK | Audit/entitlement/calc-run/temporal frameworks (done); CI drift check + audit-write concurrency; frontend lockfile/`npm ci` | Partly done (slice committed; hardening pending) |
| **P1** | Reference & portfolio core + governance skeletons | PPM-001..004, SMR-001..004, LIN-001, MDG-001, DQR-001, INT-001, AUD-001 | DEP-SMR, DEP-LIN, DEP-MREG (skeleton), DEP-DQF (skeleton) | Not started |
| **P2** | Public market data + market-risk core | PUB-001..003, MKT-001..003 | Market-data store usage; first FR-class domain + first governed calc runs | Not started |
| **P3** | Credit & counterparty risk | CRD-001..004, CPT-001..004 | Credit/counterparty analytics; seeded MC (PFE/VaR) | Not started |
| **P4** | Private assets + liquidity risk | PRV-001..004, LIQ-001..004, ADM-003 (MNPI barriers) | Private-markets data; MNPI classification; liquidity analytics | Not started |
| **P5** | Scenario & stress testing | SCN-001..003, MKT-004 | Versioned scenarios; combined stress | Not started |
| **P6** | Limits, breach workflow + SoD | LIM-001..003, BRC-001..003, ADM-002 (SoD/maker-checker) | DEP-WFL; SoD/maker-checker across the platform | Not started |
| **P7** | Full model governance + DQ/reconciliation | MDG-002/003, DQR-002/003, LIN-002 | DEP-MGW (validation workflow); reconciliation; lineage query | Not started |
| **P8** | Reporting & dashboards | RPT-001..003, AUD-003 | DEP-RPT; 1L/2L dashboards; reproducible reports | Not started |
| **P9** | Admin, SSO, integration adapters | ADM-001/004, INT-002/003 | DEP-SSO (real OIDC/MFA); API/SFTP/vendor/GP adapters | Not started |
| **P10** | BAU AI agents + production hardening | BAI-001..003 | Embedded/BAU agents under AD-009; final hardening | Not started |

## 3. Phase exit criteria (applies to every phase)

A phase is **Done** only when:
1. All in-scope requirements meet the [Definition of Done](../02_requirements/definition_of_ready_done.md) and their RTM status = `Done`.
2. The phase's controls are `Implemented` in the [control matrix](../09_compliance_controls/control_matrix_skeleton.md).
3. CI is green across all jobs (`backend`, `frontend`, `migration`, `secret-scan`, `docs-check`) plus any new phase gates.
4. The [enterprise review prompt](../00_ai_operating_model/enterprise_review_prompt.md) has been run on the phase output with no open `Critical`/`High` findings.
5. Documentation (methodology, data dictionary, ADRs, limitations register) updated; no code/doc drift.

## 4. Critical-path dependencies

```
P0 (frameworks + hardening)
  └─► P1 (reference/portfolio + lineage/model-registry/DQ skeletons)   ← unblocks everything
        ├─► P2 (market data + market risk)
        │     └─► P3 (credit + counterparty)
        ├─► P4 (private assets + liquidity)
        ├─► P5 (scenarios)  ──► needs P2/P3/P4 outputs for combined stress
        └─► P6 (limits + breach + SoD)  ── needs risk results (P2–P5)
              └─► P7 (model governance + DQ/recon)
                    └─► P8 (reporting/dashboards)
                          └─► P9 (SSO + integration)
                                └─► P10 (BAU AI agents + hardening)
```

P1 is the unblocking phase: **Security Master/Reference Data + the lineage, model-registry, and DQ skeletons** gate every risk
domain. SoD/maker-checker (REQ-ADM-002) must land by **P6** because limits, breach closure, overrides, and model approval all
depend on it (BX-SOD).

## 5. Sequencing rationale

- **Reference data first (P1):** every risk number depends on instruments, entities, and identifiers (DEP-SMR), and on lineage +
  model-registry skeletons so the very first governed calculation is fully traceable and inventoried (BR-3/6/13).
- **Public market risk before private/liquidity (P2 vs P4):** public analytics validate the calc-run/reproducibility path against
  benchmark portfolios before tackling sparse private data.
- **Limits/breach after risk exists (P6):** there is nothing to limit until risk results (P2–P5) are produced.
- **SSO deferred to P9:** the dev header-shim principal is sufficient to build and test entitlement logic; real OIDC is a swap-in
  that should not block domain construction (but must precede any production deployment).
- **BAU AI agents last (P10):** they consume governed, approved outputs that only exist once the domains and reporting are built.

## 6. Open Questions

| ID | Question |
|---|---|
| OQ-002 | Confirm phase order vs. commercial priority (private markets emphasis may pull P4 earlier). |
| OQ-010 | Confirm whether P2 and P4 can run partially in parallel given team capacity, without breaking the P1 gate. |
| OQ-011 | Confirm the minimum P0 hardening (DEP-CIH, DEP-FELOCK) required before opening P1. |

## 7. Dependencies

This sequence depends on the requirements backbone (scope), the RTM (per-requirement dependencies), and the foundational ADRs
(AD-002 phasing principle, AD-004…012). Phase boundaries are revisited after each enterprise review.
