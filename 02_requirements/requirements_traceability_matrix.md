# Requirements Traceability Matrix (RTM)

## Document Control

| Field | Value |
|---|---|
| Document ID | REQ-RTM-001 |
| Version | 0.1 (Draft baseline) |
| Status | Accepted as baseline (synced to requirements_backbone.md) |
| Owner | R-01 Product Manager AI (with R-10 Compliance & Controls AI) |
| Approver | H-07 Product Owner |
| Created | 2026-06-18 |
| Last Reviewed | 2026-06-18 |
| Related Documents | requirements_backbone.md, personas_and_user_journeys.md, definition_of_ready_done.md, ../10_delivery_backlog/build_sequence.md, ../09_compliance_controls/control_matrix_skeleton.md |
| Supported Build Rules | BR-1 … BR-19 |

## 1. Purpose

The traceability spine. Each requirement (defined in [requirements_backbone.md](requirements_backbone.md)) maps here to its
capability, persona, line of defense, cross-cutting governance obligations (audit / entitlement / lineage / model governance),
control, build phase, dependencies, and status. The backbone holds the descriptive attributes; this matrix holds the
traceability attributes. **Status is mirrored from the backbone (canonical there).**

Legend — **Audit/Ent/Lineage** columns reference the inherited baseline cross-cutting requirements (`BX-*`, backbone §5).
**ModelGov** = Y when the requirement defines a model/calculation subject to model governance (BR-3/15). Persona codes are
defined in [personas_and_user_journeys.md](personas_and_user_journeys.md). Phases are defined in
[build_sequence.md](../10_delivery_backlog/build_sequence.md). Dependency tokens are in backbone §6.

## 2. Matrix

| REQ | CAP | Persona | LoD | Phase | Audit | Ent | Lineage | ModelGov | Control(s) | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| REQ-PPM-001 | 1.1 | P-PM,P-ADM | 1L/Plat | P1 | BX-AUD | BX-ENT | — | — | CTRL-001/005/011 | FW-ENT, FW-AUD, FW-TMP | **In-Progress (P1C-0 ratified; P1C-1 planned — single `portfolio` EV table, `node_type` + `parent_portfolio_id`; ABAC scope anchor, enforcement P6+)** |
| REQ-PPM-002 | 1.2 | P-PM,P-RA | 1L | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-006/013/017 | FW-TMP(FR), DEP-SMR, DEP-LIN | In-Progress (P1C-3 `position` FR + as-of; ABAC enforcement → P6+) |
| REQ-PPM-003 | 1.3/1.4 | P-PM,P-DS | 1L/Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-005/017 | FW-AUD, FW-TMP | **In-Progress (P1C-2 transaction conjunct — IA append-only; valuation conjunct → P1C-4)** |
| REQ-PPM-004 | 1.5 | P-RA,P-RM | 1L/2L | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-006/018 | FW-RUN, DEP-LIN, CAP-1 | Draft |
| REQ-SMR-001 | 2.1 | P-DS | Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-004/017 | FW-TMP(FR), DEP-DQF | **In-Progress (P1B-3, migration 0010):** `instrument` (EV) + `instrument_terms` (FR — first persisted bitemporal entity) shipped; "reconstruct-as-of" acceptance delivered on BOTH axes (`reconstruct_terms_as_of`, acceptance-gated tests; REFERENCE.CREATE/UPDATE/CORRECTION audited, MANUAL-source lineage, symmetric RLS). Pricing/cashflow/valuation terms math deferred to P2+ |
| REQ-SMR-002 | 2.2 | P-DS | Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-004 | FW-TMP, DEP-LIN | **In-Progress (P1B-2):** `legal_entity` core + `issuer`/`counterparty` 1:1 profiles shipped (migration 0009, symmetric RLS, REFERENCE.* audited, MANUAL-source lineage, LEI + parent-hierarchy STRUCTURE). The "Hierarchy rollup test / exposure rolls to ultimate parent" acceptance is delivered structurally by the `resolve_ultimate_parent` test; the exposure-rollup **calculation** is deferred (P2+), so REQ-SMR-002 stays In-Progress |
| REQ-SMR-003 | 2.3 | P-DS | Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-004/029 | FW-TMP, DEP-DQF | **In-Progress (P1B-3, migration 0010, partial):** `identifier_xref` (EV) + `resolve_identifier` deterministic single-result-or-`AmbiguousIdentifier` (no silent match — CTRL-029) shipped; active partial-unique `(tenant_id, scheme, value) WHERE valid_to IS NULL`. Cross-vendor precedence / external validation deferred to P1C/OD-012 — REQ-SMR-003 stays partially met |
| REQ-SMR-004 | 2.4/2.5a | P-DS,P-RA | Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-004/017 | FW-TMP, QS-10/11 | **In-Progress (P1B-1 calendar + P1B-4 corporate_action):** `calendar`+`calendar_holiday` EV shipped P1B-1 (mig 0008); `corporate_action` EV **capture-only** shipped P1B-4 (mig 0011, symmetric RLS, REFERENCE.CREATE/UPDATE + STATUS_CHANGE/EVT-143, MANUAL-source lineage, instrument FK). Roll/day-count math (QS-10/11) deferred to P1C |
| REQ-SMR-005 | 2.5b | P-DS | Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-004/017 | FW-TMP, DEP-DQF | **In-Progress (P1B-1):** `currency` + `rating_scale`/`rating_grade` EV taxonomy shipped (migration 0008); hybrid global+override (AD-013-R1) — asymmetric RLS, application-layer tenant-wins, REFERENCE.CREATE/UPDATE, MANUAL-source lineage, representative SYSTEM seed; rating ASSIGNMENTS (FR) deferred. Done pending comprehensive global catalog (OQ-P1B1-001) |
| REQ-PUB-001 | 3.1 | P-DS,P-RA | Plat | P2 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-017/029 | FW-TMP(FR), DEP-DQF, CAP-2 | Draft |
| REQ-PUB-002 | 3.2/3.3 | P-DS,P-RA | Plat | P2 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-017 | FW-TMP, CAP-2 | Draft |
| REQ-PUB-003 | 3.4/3.5 | P-DS,P-RA | Plat | P2 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-029 | FW-TMP, DEP-DQF, CAP-2 | Draft |
| REQ-PRV-001 | 4.1 | P-DS | Plat/1L | P4 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-017 | FW-TMP(FR), DEP-LIN | Draft |
| REQ-PRV-002 | 4.2 | P-DS | Plat | P4 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-005/017 | FW-AUD, FW-TMP | Draft |
| REQ-PRV-003 | 4.3/4.5 | P-DS,P-RA | Plat | P4 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-029 | FW-TMP(FR), DEP-DQF | Draft |
| REQ-PRV-004 | 4.4 | P-DS,P-CO | Plat/2L | P4 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-023 | REQ-ADM-003 (MNPI), DEP-DQF | Draft |
| REQ-MKT-001 | 5.1 | P-RA,P-RM | 1L/2L | P2 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/003/018/020 | FW-RUN, DEP-MREG, DEP-MGW, DEP-LIN, CAP-1/3 | Draft |
| REQ-MKT-002 | 5.2 | P-RA,P-RM | 1L/2L | P2 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/003/018 | FW-RUN, DEP-MREG, CAP-1/3 | Draft |
| REQ-MKT-003 | 5.3 | P-RA,P-RM | 1L/2L | P2 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, DEP-MREG, CAP-3 | Draft |
| REQ-MKT-004 | 5.5 | P-RA,P-RM | 1L/2L | P5 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-9, CAP-1/3 | Draft |
| REQ-CRD-001 | 6.1 | P-RA,P-RM | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/003/018 | FW-RUN, DEP-MREG, DEP-MGW, CAP-2/3 | Draft |
| REQ-CRD-002 | 6.2 | P-RA,P-RM | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-9, CAP-2/3 | Draft |
| REQ-CRD-003 | 6.3/6.4 | P-RA,P-RM | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-2/3 | Draft |
| REQ-CRD-004 | 6.5 | P-RA,P-MV | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/007/022 | FW-RUN, DEP-MGW, CAP-2/4 | Draft |
| REQ-CPT-001 | 7.1/7.3 | P-RA,P-RM | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-2 | Draft |
| REQ-CPT-002 | 7.2 | P-RA,P-RM | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018/020 | FW-RUN, DEP-MREG, CAP-3 | Draft |
| REQ-CPT-003 | 7.4 | P-RA,P-RM | 1L/2L | P3 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-10 | Draft |
| REQ-CPT-004 | 7.5 | P-RA,P-MV | 2L | P3 | BX-AUD | BX-ENT | — | **Y** | CTRL-014 | BX-LIM (placeholder maturity) | Draft |
| REQ-LIQ-001 | 8.1 | P-RA,P-RM | 1L/2L | P4 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-1/2 | Draft |
| REQ-LIQ-002 | 8.2 | P-RA,P-RM | 1L/2L | P4 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-9 | Draft |
| REQ-LIQ-003 | 8.3/8.4 | P-RA,P-RM | 1L/2L | P4 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-9 | Draft |
| REQ-LIQ-004 | 8.5 | P-RA,P-RM | 1L/2L | P4 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-002/018 | FW-RUN, CAP-4 | Draft |
| REQ-SCN-001 | 9.1/9.2 | P-RA,P-RM | 1L/2L | P5 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-008 | FW-TMP(IA), DEP-LIN | Draft |
| REQ-SCN-002 | 9.3 | P-RA,P-RM | 2L | P5 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-008/018 | FW-RUN, CAP-5/6/8 | Draft |
| REQ-SCN-003 | 9.4/9.5 | P-RA,P-RM | 1L/2L | P5 | BX-AUD | BX-ENT | BX-LIN | **Y** | CTRL-008/018 | FW-RUN, CAP-4/5/6/8 | Draft |
| REQ-LIM-001 | 10.1/10.3 | P-RM,P-PM | 2L/1L | P6 | BX-AUD | BX-ENT | — | — | CTRL-015/021/025 | REQ-ADM-002 (SoD), FW-AUD | Draft |
| REQ-LIM-002 | 10.2 | P-RA,P-RM | 1L/2L | P6 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-006/018 | FW-RUN, CAP-5/6/7/8 | Draft |
| REQ-LIM-003 | 10.4 | P-RM | 2L | P6 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-005 | CAP-10.2 | Draft |
| REQ-BRC-001 | 11.1 | P-PM,P-RM | 1L/2L | P6 | BX-AUD | BX-ENT | — | — | CTRL-005/031 | DEP-WFL, CAP-10 | Draft |
| REQ-BRC-002 | 11.2/11.3 | P-PM,P-RM | 1L/2L | P6 | BX-AUD | BX-ENT | — | — | CTRL-021/031 | REQ-ADM-002 (SoD), DEP-WFL | Draft |
| REQ-BRC-003 | 11.4 | P-RM,P-CO | 2L | P6 | BX-AUD | BX-ENT | — | — | CTRL-015/031 | DEP-WFL | Draft |
| REQ-MDG-001 | 12.1/12.2 | P-MV,P-RM | 2L | P1 | BX-AUD | BX-ENT | — | **Y** | CTRL-003/014 | DEP-MREG, FW-AUD | In-Progress (P1A-2 skeleton: inventory + versioning + assumptions/limitations + BR-3 gate; tiering REQ-MDG-002 & validation/approval REQ-MDG-003 → P7. Register writer = model owner/developer `risk_analyst_1l`; P-MV/P-RM are inventory readers) |
| REQ-MDG-002 | 12.3 | P-MV | 2L | P7 | BX-AUD | BX-ENT | — | **Y** | CTRL-003/015 | DEP-MGW | Draft |
| REQ-MDG-003 | 12.4/12.5 | P-MV | 2L | P7 | BX-AUD | BX-ENT | — | **Y** | CTRL-015/022 | DEP-MGW, REQ-ADM-002 (SoD) | Draft |
| REQ-DQR-001 | 13.1 | P-DS | Plat/1L | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-027/029 | DEP-DQF | In-Progress (P1A-3 skeleton: rule define + 2 generic evaluators + result capture + no-silent-failure + `assert_passed_quality_checks` gate; reconciliation REQ-DQR-002 & overrides REQ-DQR-003 → P7. First real on-ingest run at P1A-4) |
| REQ-DQR-002 | 13.2 | P-DS | Plat | P7 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-028 | DEP-DQF, CAP-18 | Draft |
| REQ-DQR-003 | 13.4 | P-DS,P-RM | 1L/2L | P7 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-007/021 | REQ-ADM-002 (SoD), FW-AUD | Draft |
| REQ-LIN-001 | 14.1/14.2 | P-DS,P-IA | Plat | P1 | BX-AUD | BX-ENT | — | — | CTRL-006/013 | DEP-LIN (builds it), FW-AUD | In-Progress (P1A-1 skeleton: capture + retrieve-by-id at entity/run granularity; CAP-14.1 field-level mapping & CAP-14.3 query → REQ-LIN-002/P7) |
| REQ-LIN-002 | 14.3 | P-DS,P-IA | Plat/3L | P7 | BX-AUD | BX-ENT | — | — | CTRL-013 | DEP-LIN | Draft |
| REQ-AUD-001 | 15.1/15.4 | P-IA,P-CO | Plat/3L | P1 | BX-AUD | BX-ENT | — | — | CTRL-005/012 | FW-AUD (extends) | Draft |
| REQ-AUD-002 | 15.2 | P-IA | Plat | P0 | BX-AUD | BX-ENT | — | — | CTRL-026 | FW-AUD, DEP-CIH | Draft |
| REQ-AUD-003 | 15.3 | P-IA,P-CO | 3L/2L | P8 | BX-AUD | BX-ENT | — | — | CTRL-012 | DEP-RPT | Draft |
| REQ-RPT-001 | 16.1 | P-RM,P-RA | 2L/1L | P8 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-009 | DEP-RPT, DEP-LIN | Draft |
| REQ-RPT-002 | 16.3 | P-RM,P-BRD | 2L | P8 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-009/015 | DEP-RPT, BX-SOD | Draft |
| REQ-RPT-003 | 16.4/16.5 | P-CO,P-IA | 2L/3L | P8 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-009 | DEP-RPT, CAP-12/13/15 | Draft |
| REQ-ADM-001 | 17.1 | P-ADM | Plat | P9 | BX-AUD | BX-ENT | — | — | CTRL-010 | DEP-SSO (AD-007) | Draft |
| REQ-ADM-002 | 17.2/17.3 | P-ADM | Plat | P6 | BX-AUD | BX-ENT | — | — | CTRL-015/021/025 | FW-ENT (SoD build) | Draft |
| REQ-ADM-003 | 17.5 | P-CO,P-ADM | 2L/Plat | P4 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-023/024 | CAP-4, DEP-RPT (export part P8) | Draft |
| REQ-ADM-004 | 17.4 | P-ADM | Plat | P9 | BX-AUD | BX-ENT | — | — | CTRL-011 | FW-ENT | Draft |
| REQ-INT-001 | 18.1 | P-DS,P-ADM | Plat | P1 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-027 | anti-corruption, FW-AUD, DEP-DQF | In-Progress (P1A-4 skeleton: generic CSV upload + anti-corruption + raw-row staging + on-ingest DQ + lineage origin + audit; canonical mapping → P1B/P1C; API/SFTP/vendor/GP adapters REQ-INT-002/003 → P9) |
| REQ-INT-002 | 18.2/18.3 | P-DS,P-ADM | Plat | P9 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-027 | DEP-DQF, CAP-2 | Draft |
| REQ-INT-003 | 18.4/18.5 | P-DS,P-ADM | Plat | P9 | BX-AUD | BX-ENT | BX-LIN | — | CTRL-027 | CAP-3/4, DEP-DQF | Draft |
| REQ-BAI-001 | 19.1 | P-DS,P-RA | BAU | P10 | BX-AUD | BX-ENT | — | — | CTRL-016 | FW-AUD, AD-009 (read-only tier) | Draft |
| REQ-BAI-002 | 19.2/19.3 | P-PM,P-RA | BAU | P10 | BX-AUD | BX-ENT | — | — | CTRL-016 | AD-009, CAP-9/11 | Draft |
| REQ-BAI-003 | 19.4/19.5 | P-MV,P-BRD | BAU | P10 | BX-AUD | BX-ENT | — | — | CTRL-015/016 | AD-009, CAP-12/16 | Draft |

## 3. Coverage summary

- **19 capability domains** (CAP-1…19), **~90 sub-capabilities**, **65 baseline requirements** (REQ-…-001…; +REQ-SMR-005 minted P1B-0). Most `Draft`; the P1A rails (LIN/MDG/DQR/INT-001) and the P1B-0 SMR rows are `Ratified`/`In-Progress` per their Status cells.
- Every requirement inherits `BX-AUD` + `BX-ENT`; **44** inherit `BX-LIN`; **21** are model-governed (`ModelGov = Y`).
- Every build rule BR-1…BR-19 is represented via the BX baseline and per-requirement controls.

## 4. Major dependency rollup

| Dependency | Required by (examples) | First needed (phase) |
|---|---|---|
| DEP-LIN (lineage skeleton) | PPM-002/004, SMR-*, PUB-*, PRV-*, MKT-*, RPT-* | P1 |
| DEP-MREG (model registry) | MDG-001, MKT-*, CRD-001, CPT-002 | P1 |
| DEP-DQF (data quality framework) | DQR-*, SMR-*, PUB-*, PRV-*, INT-* | P1 |
| DEP-SMR (security master) | PPM-002 and all risk domains | P1 |
| DEP-WFL (workflow engine) | BRC-001/002/003 | P6 |
| BX-SOD via REQ-ADM-002 (SoD/maker-checker) | LIM-001, BRC-002, MDG-003, DQR-003, RPT-002 | P6 |
| DEP-MGW (model governance workflow) | MDG-002/003, MKT/CRD model sign-off | P7 |
| DEP-RPT (reporting engine) | RPT-*, AUD-003, ADM-003 (export) | P8 |
| DEP-SSO (real SSO) | ADM-001 (replaces dev header shim) | P9 |
| DEP-CIH (CI hardening: drift check, audit concurrency) | AUD-002, all DB-backed work | P0 |
| DEP-FELOCK (frontend lockfile / npm ci) | all frontend work | P0 |

## 5. Open Questions

| ID | Question | Owner |
|---|---|---|
| ~~OQ-001~~ | **CLOSED (2026-06-18):** CAP taxonomy authoritative here; capability_map.md annotated with CAP IDs. | H-07 |
| OQ-002 | Confirm phase ordering vs. commercial priority (e.g., should private markets precede some public-risk depth?). | H-07/H-01 |
| OQ-003 | Confirm which risk methodologies are in initial depth vs. "simple-but-complete" first cut (per design principle). | H-01/H-02 |
| ~~OQ-004~~ | **DECIDED (2026-06-18, DR-P1-3):** defer maker-checker/SoD workflow to P6; P1 preserves audit + adds non-enforcing schema hooks. | H-03/H-01 |
| OQ-005 | Confirm regulatory scope (REG-US-*) that turns specific requirements mandatory vs. optional (links OD-037). | H-05 |
| OQ-006 | Confirm whether CVA (CPT-004) stays placeholder through v1 or is scheduled. | H-02 |
| OQ-007 | Confirm persona consolidation at small team scale without breaking SoD pairs (links OD-001/026). | H-07 |

## 6. Dependencies

This RTM depends on the backbone (requirement definitions), the control matrix (CTRL IDs), the personas doc (persona codes), and
the build sequence (phase IDs). It must be re-synced whenever any requirement's status changes.
